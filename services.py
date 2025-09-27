import openai
import requests
import tempfile
import os
import PyPDF2
from pathlib import Path
import json
from fastapi import HTTPException
import config

import mimetypes
from typing import Optional


import os
from dotenv import load_dotenv
import openai

load_dotenv()  # Loads variables from .env

openai.api_key = os.getenv("OPENAI_API_KEY")

def extract_text_from_pdf_url(pdf_url: str, max_size_mb: int = 5) -> str:
    if not pdf_url or not pdf_url.strip():
        raise ValueError("PDF URL cannot be empty")
    
    if not pdf_url.startswith(('http://', 'https://')):
        raise ValueError("Invalid PDF URL format")
    
    try:
        response = requests.get(pdf_url)
        response.raise_for_status()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(response.content)
            temp_file_path = temp_file.name
        
        text = ""
        with open(temp_file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text()
        
        os.unlink(temp_file_path)
        return text.strip()
        
    except Exception as e:
        print(f"PDF text extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF extraction failed: {str(e)}")

def chunk_text(text, max_chars=4000):
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        if end < len(text):
            newline_pos = text.rfind("\n", start, end)
            if newline_pos != -1:
                end = newline_pos
        chunks.append(text[start:end].strip())
        start = end
    return chunks

def identify_speakers_and_assign_voices(text):
    try:
        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        
        system_prompt = (
            "Analyze the text and identify different speakers. Return a JSON object with:"
            "1. 'speakers': list of identified speakers with their characteristics"
            "2. 'dialogue': array of objects with 'speaker_id', 'text', 'voice_type' (male/female)"
            "Use 'speaker1', 'speaker2', etc. as IDs. Default to 'male' voice unless explicitly mentioned as female."
            "If no dialogue/multiple speakers found, return single speaker with all text."
        )
        
        response = client.chat.completions.create(
            model=config.OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0
        )
        
        result = response.choices[0].message.content
        
        if result.startswith("```json"):
            result = result[7:-3].strip()
        
        return json.loads(result)
        
    except Exception as e:
        print(f"Speaker identification failed: {e}")
        return {
            "speakers": [{"id": "speaker1", "type": "male"}],
            "dialogue": [{"speaker_id": "speaker1", "text": text, "voice_type": "male"}]
        }

def assign_voice_to_speaker(speaker_id, voice_type, assigned_voices):
    if speaker_id in assigned_voices:
        voice = assigned_voices[speaker_id]
        # print(f"Assigned voice '{voice}' to speaker '{speaker_id}' (type: {voice_type})")
        return voice
    
    if voice_type.lower() == "female":
        voice = config.OPENAI_VOICES["female"]
    else:
        if speaker_id in config.OPENAI_VOICES:
            voice = config.OPENAI_VOICES[speaker_id]
        else:
            available_male_voices = ["echo", "onyx", "fable", "alloy"]
            used_male_voices = [v for v in assigned_voices.values() if v in available_male_voices]
            
            for voice in available_male_voices:
                if voice not in used_male_voices:
                    break
            else:
                voice = config.OPENAI_VOICES["default"]
    
    assigned_voices[speaker_id] = voice
    # print(f"Assigned voice '{voice}' to speaker '{speaker_id}' (type: {voice_type})")
    return voice

def generate_audio_from_pdf(scenario_id, pdf_url):
    try:
        text = extract_text_from_pdf_url(pdf_url)
        
        if not text:
            raise HTTPException(status_code=400, detail="No text found in PDF")
        
        speaker_analysis = identify_speakers_and_assign_voices(text)
        assigned_voices = {}

        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        
        audio_dir = Path("audio_files")
        audio_dir.mkdir(exist_ok=True)
        
        local_audio_path = audio_dir / f"{scenario_id}.mp3"
        
        chunk_files = []
        try:
            for i, dialogue_item in enumerate(speaker_analysis["dialogue"]):
                speaker_id = dialogue_item["speaker_id"]
                text_content = dialogue_item["text"]
                voice_type = dialogue_item["voice_type"]
                
                voice = assign_voice_to_speaker(speaker_id, voice_type, assigned_voices)
                
                text_chunks = chunk_text(text_content, max_chars=4000)
                
                for j, chunk in enumerate(text_chunks):
                    response = client.audio.speech.create(
                        model=config.OPENAI_TTS_MODEL,
                        voice=voice,
                        input=chunk
                    )
        
                    chunk_path = audio_dir / f"scenario_{scenario_id}_speaker_{speaker_id}_chunk_{i}_{j}.mp3"
                    with open(chunk_path, 'wb') as f:
                        for chunk in response.iter_bytes():
                            f.write(chunk)
                    chunk_files.append(chunk_path)
            
            all_audio_data = b''
            for chunk_file in chunk_files:
                with open(chunk_file, 'rb') as f:
                    all_audio_data += f.read()
            
            with open(local_audio_path, 'wb') as f:
                f.write(all_audio_data)
            
            for chunk_file in chunk_files:
                chunk_file.unlink()
            
            # print(f"Audio file saved locally at: {local_audio_path}")

            from database import upload_audio_file_to_cloudinary, upload_audio_url_to_db
            
            audio_url = upload_audio_file_to_cloudinary(str(local_audio_path), f"{scenario_id}")

            if not audio_url:
                raise HTTPException(status_code=500, detail="Failed to upload audio to Cloudinary")

            audio_format = local_audio_path.suffix.lstrip('.')
            audio_size = local_audio_path.stat().st_size

            
            success = upload_audio_url_to_db(scenario_id, audio_url, audio_format, audio_size)
            
            if success:
                local_audio_path.unlink()
                return {
                    "scenario_id": scenario_id,
                    "cloudinary_url": audio_url,
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to store audio URL in database")
                
        except Exception as e:
            for chunk_file in chunk_files:
                if chunk_file.exists():
                    chunk_file.unlink()
            raise e
            
    except Exception as e:
        print(f"Audio generation from PDF failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    


# from database import get_scenario_by_id, upload_submission_to_db

# scenario_data = get_scenario_by_id("b42ae74f-a474-41b7-af8b-d9fffb43a35e")
        
# if not scenario_data:
#     raise HTTPException(status_code=404, detail="Scenario not found")

# speech_data = scenario_data[0]['speech']
# pdf_url = speech_data['fileUrl']

# result = generate_audio_from_pdf("b42ae74f-a474-41b7-af8b-d9fffb43a35e", pdf_url)





###########################################################################################


def transcribe_audio_from_url(audio_bytes: bytes):
    try:
        # Initialize OpenAI client
        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)

        # Save the binary audio to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
            tmp_file.write(audio_bytes)
            temp_audio_path = tmp_file.name

        # Transcribe audio
        with open(temp_audio_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model=config.OPENAI_TRANSCRIBE_MODEL,
                file=audio_file,
                response_format="json"
            )

        # Convert transcription object to dict
        transcription_dict = transcription.model_dump()

        # Only keep desired structure
        structured_output = {
            "Submission": transcription_dict.get("text", ""),
            "Seconds": transcription_dict.get("usage", {}).get("seconds", None)
        }

        return structured_output

    except requests.RequestException as e:
        print(f"Failed to download audio: {e}")
    except FileNotFoundError:
        print(f"Audio file not found: {temp_audio_path}")
    except Exception as e:
        print(f"Transcription failed: {e}")

def process_pdf_for_instructions(scenario_id):
    from database import get_pdfUrl_according_to_scenario
    
    pdf_url = get_pdfUrl_according_to_scenario(scenario_id=scenario_id)
    
    if not pdf_url:  # This check should raise an exception
        raise HTTPException(status_code=404, detail="Scenario not found or PDF URL missing")
    

    try:
        text = extract_text_from_pdf_url(pdf_url)

        # Step 4: Define system prompt
        system_prompt = (
            "You are an expert examiner. Read the instructions text and output a structured JSON. "
            "Each instruction should have: 'id', 'Instruction' and 'MaxMarks'. "
            "If the mark is vague or in words like 'Maximum 15%', calculate and adjust marks so total is 100. "
            "Format the output as a JSON list."
        )

        # Step 5: Send to OpenAI
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model=config.OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0
        )

        # Get raw string output
        structured_output = response.choices[0].message.content

        # --- Clean Markdown fences if present ---
        cleaned_output = structured_output.strip()
        if cleaned_output.startswith("```json"):
            cleaned_output = cleaned_output[len("```json"):].strip()
        if cleaned_output.endswith("```"):
            cleaned_output = cleaned_output[:-3].strip()

        # --- Convert string to Python object ---
        try:
            structured_output_json = json.loads(cleaned_output)
        except json.JSONDecodeError:
            print("Could not parse JSON. Saving raw text instead.")
            structured_output_json = cleaned_output

        return structured_output_json

    except requests.RequestException as e:
        print(f"Failed to download PDF: {e}")
    except Exception as e:
        print(f"Processing failed: {e}")

def report(transcription, instructions):
    client = openai.OpenAI(api_key=config.OPENAI_API_KEY)

    results = []
    chunk_size = 3  # send instructions in chunks (tweak as needed)

    # Break the instructions into chunks
    for i in range(0, len(instructions), chunk_size):
        chunk = instructions[i:i+chunk_size]

        prompt = {
            "role": "system",
            "content": (
                "You are a grading assistant specialized in Legal Advocacy in the UK. "
                "Evaluate a student's oral or written submission against the provided instructions in a fair, professional manner. "
                "Return a JSON object with the following keys: "
                "'TotalScore' (numeric, reflecting the overall performance), "
                "'Positive' (optional list of points where the student followed instructions correctly), "
                "'Negative' (optional list of points where the student failed to meet instructions), "
                "and 'Improvement' (optional list of short, actionable suggestions to improve the submission). "
                "If there are no relevant points for a list, you may omit it or leave it empty. "
                "All text should be in clear UK English. "
                "Do not include any explanations outside the JSON. "
                "Keep feedback practical, concise, and directly tied to the instructions."
            )
        }

        user_input = {
            "role": "user",
            "content": json.dumps({
                "Submission": transcription,
                "Instructions": chunk
            }, indent=2, ensure_ascii=False)
        }

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # or gpt-4.1 if available
            messages=[prompt, user_input],
            temperature=0.3
        )

        # Parse response text into JSON
        try:
            result = json.loads(response.choices[0].message.content)
            results.append(result)
        except Exception as e:
            print("Error parsing response:", e)
            continue

    # Merge results into one final JSON
    final_result = merge_results(results)
    return final_result

def merge_results(results):
    def ensure_list(x):
        if isinstance(x, list):
            return x
        elif isinstance(x, str):
            return [x]
        else:
            return []

    total_score = sum(r.get("TotalScore", 0) for r in results) 
    
    positives = []
    negatives = []
    improvements = []

    for r in results:
        positives.extend(ensure_list(r.get("Positive")))
        negatives.extend(ensure_list(r.get("Negative")))
        improvements.extend(ensure_list(r.get("Improvement")))

    return {
        "TotalScore": total_score,
        "Positive": positives or None,
        "Negative": negatives or None,
        "Improvement": improvements or None
    }