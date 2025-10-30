# main.py
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
import config
# from database import upload_submission_to_db
from services import (
    generate_audio_from_pdf, 
    transcribe_audio_from_url, 
    process_pdf_for_instructions, 
    report
)
from models import AudioGenerationRequest, AudioGenerationResponse, GradingReport, EvaluationResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],   # Allow all HTTP methods
    allow_headers=["*"],   # Allow all headers
)


@app.get("/")
async def root():
    return {"message": "Server is running fine!"}



@app.post("/speech/generate-from-scenario", response_model=AudioGenerationResponse)
async def generate_audio_from_scenario_endpoint(request: AudioGenerationRequest):
    try:
        pdf_url = request.pdf_url


        # if not pdf_url or not pdf_url.endswith(".pdf"):
        #     raise HTTPException(status_code=400, detail="Invalid or missing PDF URL")

        # Pass PDF URL directly to your audio generation logic
        result = generate_audio_from_pdf(pdf_url)

        return AudioGenerationResponse(
            message="Audio generated successfully",
            cloudinary_url=result["cloudinary_url"],
            status="completed"
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        error_msg = str(e) if str(e) else "An unexpected error occurred"
        raise HTTPException(status_code=500, detail=error_msg)


    

@app.post("/grade/evaluate-submission", response_model=EvaluationResponse)
async def evaluate_submission_endpoint(
    pdf_url: str,
    audio_file: UploadFile = File(...)
):
    """Evaluate uploaded audio submission against PDF instructions"""
    try:
        # Read uploaded file content
        contents = await audio_file.read()

        # Validate file existence and non-empty content
        if not contents:
            raise HTTPException(status_code=400, detail="No audio file provided or file is empty")

        transcription = transcribe_audio_from_url(contents)
        isinstance = process_pdf_for_instructions(pdf_url)



        if not isinstance:
            raise HTTPException(status_code=404, detail="No instructions found for scenario")

        rep = report(transcription, isinstance)

        # Validate report structure using Pydantic
        grading_report = GradingReport(**rep)

        # Extract the 4 features with safe handling
        total_score = grading_report.TotalScore
        positives = grading_report.Positive or []
        negatives = grading_report.Negative or []
        improvements = grading_report.Improvement or []

        # Convert lists to strings (comma-separated or newline-separated)
        positives_str = "\n".join(positives)
        negatives_str = "\n".join(negatives)
        improvements_str = "\n".join(improvements)

    

        return {
            "message": "Evaluation completed successfully",
            "total_score": total_score,
            "positive": positives,
            "negative": negatives,
            "improvement": improvements
        }
            
    except ValueError as ve:
    # Handle database constraint violations and validation errors
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        # Handle empty error messages
        error_msg = str(e) if str(e).strip() else "An unexpected error occurred during submission evaluation"
        print(f"Unexpected error in evaluate_submission_endpoint: {e}")  # For debugging
        print(f"Error type: {type(e)}")  # Additional debugging
        raise HTTPException(status_code=500, detail=error_msg)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT)


