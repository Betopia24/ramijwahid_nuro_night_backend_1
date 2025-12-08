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

from langdetect import detect, LangDetectException
import uuid
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

from database import upload_audio_file_to_cloudinary
def generate_audio_from_pdf(pdf_url):
    chunk_files = []
    local_audio_path = None
    
    try:
        text = extract_text_from_pdf_url(pdf_url)

        if not text:
            raise HTTPException(status_code=400, detail="No text found in PDF")
        
        speaker_analysis = identify_speakers_and_assign_voices(text)
        assigned_voices = {}

        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        
        audio_dir = Path("audio_files")
        audio_dir.mkdir(exist_ok=True)
        cloudinary_unique_id = uuid.uuid4()
        local_audio_path = audio_dir / f"{cloudinary_unique_id}.mp3"
        
        # Generate audio chunks
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
                
                chunk_id = uuid.uuid4()
                chunk_path = audio_dir / f"chunk_{chunk_id}_speaker_{speaker_id}_{i}_{j}.mp3"
                
                with open(chunk_path, 'wb') as f:
                    for chunk_bytes in response.iter_bytes():
                        f.write(chunk_bytes)
                
                chunk_files.append(chunk_path)
        
        # Combine all chunks
        all_audio_data = b''
        for chunk_file in chunk_files:
            with open(chunk_file, 'rb') as f:
                all_audio_data += f.read()
        
        with open(local_audio_path, 'wb') as f:
            f.write(all_audio_data)
        
        # Remove individual chunks
        for chunk_file in chunk_files:
            if chunk_file.exists():
                chunk_file.unlink()
        chunk_files = []
        
        # Upload to Cloudinary
        cloudinary_audio_unique_id = uuid.uuid4()
        audio_url = upload_audio_file_to_cloudinary(str(local_audio_path), f"{cloudinary_audio_unique_id}")
        # print("Uploaded to Cloudinary:", audio_url)

        if not audio_url:
            raise HTTPException(status_code=500, detail="Failed to upload audio to Cloudinary")

        if local_audio_path and local_audio_path.exists():
            local_audio_path.unlink()

        return {
            "cloudinary_url": audio_url,
        }
            
    except Exception as e:
        # Cleanup on error
        for chunk_file in chunk_files:
            if chunk_file.exists():
                chunk_file.unlink()
        
        if local_audio_path and local_audio_path.exists():
            local_audio_path.unlink()
            
        print(f"Audio generation from PDF failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# pdf_url = "https://res.cloudinary.com/dap77vbim/raw/upload/v1761799214/uploads/pdfs/pdf_1761799190791_nmz4zme3cj"

# generate_audio_from_pdf(pdf_url)




# from database import get_scenario_by_id, upload_submission_to_db

# scenario_data = get_scenario_by_id("b42ae74f-a474-41b7-af8b-d9fffb43a35e")
        
# if not scenario_data:
#     raise HTTPException(status_code=404, detail="Scenario not found")

# speech_data = scenario_data[0]['speech']
# pdf_url = speech_data['fileUrl']

# result = generate_audio_from_pdf("b42ae74f-a474-41b7-af8b-d9fffb43a35e", pdf_url)





###########################################################################################


def transcribe_audio_from_url(audio_bytes: bytes):
    temp_audio_path = None
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
        text = transcription_dict.get("text", "").strip()

        # ✅ Empty check
        if not text:
            raise HTTPException(status_code=400, detail="Transcription is empty or failed. Please upload a valid audio file.")

        
        # try:
        #     detected_lang = detect(text)
        #     if detected_lang != "en":
        #         raise HTTPException(
        #             status_code=400,
        #             detail=f"Detected non-English language: {detected_lang}. Please submit English audio."
        #         )
        # except LangDetectException:
        #     raise HTTPException(
        #         status_code=400,
        #         detail="Unable to detect language. Please provide clear English audio."
        #     )

        # Only keep desired structure
        structured_output = {
            "Submission": transcription_dict.get("text", ""),
            "Seconds": transcription_dict.get("usage", {}).get("seconds", None)
        }
        
        # print()
        # print(structured_output)

        return structured_output

    except HTTPException:
        # Re-raise HTTPException so validation errors propagate
        raise
    except requests.RequestException as e:
        print(f"Failed to download audio: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download audio: {str(e)}")
    except FileNotFoundError:
        print(f"Audio file not found")
        raise HTTPException(status_code=500, detail="Audio file not found")
    except Exception as e:
        print(f"Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    finally:
        # Clean up temp file
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.unlink(temp_audio_path)
            except Exception as e:
                print(f"Failed to delete temp file: {e}")


# with open("audio.mp3", "rb") as f:
#     audio_bytes = f.read()

# transcribe_audio_from_url(audio_bytes)




def process_pdf_for_instructions(pdf_url):
    # from database import get_pdfUrl_according_to_scenario
    
    # pdf_url = get_pdfUrl_according_to_scenario(scenario_id=scenario_id)
    
    if not pdf_url:  # This check should raise an exception
        raise HTTPException(status_code=404, detail="Scenario not found or PDF URL missing")
    

    try:
        text = extract_text_from_pdf_url(pdf_url)
        #print("Extracted PDF Text:", text)
        # file = open(pdf_url, "rb")

        # # Create reader
        # reader = PyPDF2.PdfReader(file)

        # # Extract text
        # text = ""
        # for page in reader.pages:
        #     page_text = page.extract_text()
        #     if page_text:
        #         text += page_text + "\n"

        # # Print the text
        # print("text:",text)

        # # Close the file
        # file.close()

        # Step 4: Define system prompt
        system_prompt = (
            "You are an expert examiner. Read the instructions text and output a structured JSON. "
            "Each instruction should have: 'id', 'Instruction' and 'MaxMarks'. "
            "For all the point in input text, make proper detailed instructions. "
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

        # print()
        # print("stracture output:", structured_output_json)

        return structured_output_json

    except requests.RequestException as e:
        print(f"Failed to download PDF: {e}")
    except Exception as e:
        print(f"Processing failed: {e}")




# process_pdf_for_instructions("https://plastic-bronze-mkmwalo5bj-drkruz3krx.edgeone.dev/Scenario%201%20Marking%20Pointers%201.pdf")




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
            model="gpt-4.1",  # or gpt-4.1 if available
            messages=[prompt, user_input],
            temperature=0
        )

        # Parse response text into JSON
        raw_content = response.choices[0].message.content

        # print()
        # print(raw_content)

        try:
            # First try direct JSON parsing
            result = json.loads(raw_content)

        except json.JSONDecodeError:
            print("JSON parsing failed, trying to fix...")

            # --- Attempt 1: Remove code fences ---
            cleaned = raw_content.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```", 1)[-1].strip()
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0].strip()

            # --- Attempt 2: Attempt common JSON fixes ---
            cleaned = cleaned.replace("\n", "")
            cleaned = cleaned.replace("\t", "")
            
            # Add missing braces (common model mistakes)
            if not cleaned.startswith("{"):
                cleaned = "{" + cleaned
            if not cleaned.endswith("}"):
                cleaned = cleaned + "}"

            try:
                result = json.loads(cleaned)
            except:
                print("Unable to auto-fix JSON. Falling back to text mode.")

                # --- Worst-case fallback ---
                result = {
                    "TotalScore": 0,
                    "Positive": [],
                    "Negative": ["Model returned invalid JSON for this chunk"],
                    "Improvement": []
                }

        # Always append a result — NEVER skip a chunk
        results.append(result)


    # Merge results into one final JSON
    final_result = merge_results(results)
    # print()
    # print("Final grading report:", final_result)
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


# transcription_data = {
#     "Submission": "Loading... Here's the Loading... Loading... Pressing Time. Loading... Pressing Time. I have now made the order as requested by the applicant for the extension of time for the filing of the defence. Your Honour, although the starting point is that the costs follow the event under CPR 44.2, the judge retains discretion. The application costs claimed by the applicant in the sum of £4,991 are set out in the Statement of Costs Unreasonable and Disproportionate. The use of the Grade A fee earner was not appropriate. The application was straightforward and could have been prepared in the hearing attended by a more junior fee earner. Grade C or Grade D would have been more appropriate. The time spent by the defendant, the applicant, was 10 hours for a straightforward application. This is excessive given the simplicity of the application, especially considering this is a Grade A fee earner. We would suggest a maximum of 5 hours in preparation of the application for a Grade C fee earner. Also the travel costs, the defendant's representative travelled 180 miles for the hearing. This was excessive. A local barrister could have been used instead. If the hearing is going to, if the court is going to allow travelling costs, the rate should be reduced perhaps to half of £141 per hour. An application cost in the region of between £1,500 to £2,000 would be much more reasonable. This is broken down as a Grade C fee earner at a rate of £177 per hour for 5 hours for the application when it comes to £885 plus a local barrister's fee in the sum of £400. So the total including VAT would be in the region of £1,500. You can see brother it says the negatives exceeded, submission exceeded the 5 minute time limit for our submissions. Makes no sense as I have just basically read out the whole of the contents of the marking so it should be 100%.",
#     "Seconds": 214.0
# }

# instructions_data = [
#     {
#         "id": 1,
#         "Instruction": "The student should refer to the Judge as 'your honour'. The student should speak clearly, at a measured pace and for no longer than 6 minutes.",
#         "MaxMarks": 10
#     },
#     {
#         "id": 2,
#         "Instruction": "Although the starting point is that the costs follow the event CPR 44.2, the Judge retains discretion.",
#         "MaxMarks": 10
#     },
#     {
#         "id": 3,
#         "Instruction": "The application costs claimed by the Applicant in the sum of £4991 as set out in their statement of costs are unreasonable and disproportionate.",
#         "MaxMarks": 15
#     },
#     {
#         "id": 4,
#         "Instruction": "The use of a Grade A fee earner was not appropriate. The application was straightforward and could have been prepared and the hearing attended by a more junior fee-earner. Grade C or Grade D fee earner more appropriate.",
#         "MaxMarks": 15
#     },
#     {
#         "id": 5,
#         "Instruction": "Time Spent – The Defendant claims 10 hours of work for a straightforward application. This is excessive given the simplicity of the application especially considering this is a Grade A fee earner. Maximum of 5 hours for a Grade C fee earner.",
#         "MaxMarks": 15
#     },
#     {
#         "id": 6,
#         "Instruction": "Travel Costs – The Defendant’s representative travelled 180 miles for the hearing. This was excessive. A local Barrister could have been instructed instead. If the Court is going to allow the travelling costs, the rate should perhaps be reduced to half at £141 per hour.",
#         "MaxMarks": 15
#     },
#     {
#         "id": 7,
#         "Instruction": "Application costs in the region of between £1500 to £2000 would be much more reasonable. This is broken down as a Grade C fee-earner at a rate of £177 per hour for 5 hours for the application which comes to £885 plus a local Barrister’s fee in the sum of £400. Total including VAT is in the region of £1500.",
#         "MaxMarks": 20
#     }
# ]


# report(transcription_data["Submission"], instructions_data)