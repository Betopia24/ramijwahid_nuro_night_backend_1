# main.py
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
import config
from database import get_scenario_by_id, upload_submission_to_db
from services import (
    generate_audio_from_pdf, 
    transcribe_audio_from_url, 
    process_pdf_for_instructions, 
    report
)
from models import AudioGenerationResponse, GradingReport, EvaluationResponse

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Server is running fine!"}


@app.post("/speech/generate-from-scenario", response_model=AudioGenerationResponse)
async def generate_audio_from_scenario_endpoint(scenario_id: str):
    try:
        scenario_data = get_scenario_by_id(scenario_id)
        
        if not scenario_data or len(scenario_data) == 0:
            raise HTTPException(status_code=404, detail="Scenario not found")

        try:
            speech_data = scenario_data[0]['speech']
            pdf_url = speech_data['fileUrl']
        except (KeyError, IndexError) as e:
            raise HTTPException(status_code=400, detail="Invalid scenario data structure")

        
        result = generate_audio_from_pdf(scenario_id, pdf_url)
        
        return AudioGenerationResponse(
            message="Audio generated from scenario successfully",
            scenario_id=result["scenario_id"],
            cloudinary_url=result["cloudinary_url"],
            status="Database updated"
        )
        
    except HTTPException:
    # Re-raise HTTP exceptions (like 404) without modification
        raise
    except Exception as e:
        # Log the actual error for debugging
        print(f"Unexpected error: {e}")
        error_msg = str(e) if str(e) else "An unexpected error occurred"
        raise HTTPException(status_code=500, detail=error_msg)
    

@app.post("/grade/evaluate-submission", response_model=EvaluationResponse)
async def evaluate_submission_endpoint(
    scenario_id: str,
    user_id: str,
    audio_file: UploadFile = File(...)
):
    """Evaluate uploaded audio submission against PDF instructions"""
    try:
        # Read uploaded file content
        contents = await audio_file.read()

        transcription = transcribe_audio_from_url(contents)
        isinstance = process_pdf_for_instructions(scenario_id)

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

        id = upload_submission_to_db(user_id, scenario_id, total_score, positives_str, negatives_str, improvements_str)


        if not id:  
            raise HTTPException(status_code=500, detail="Failed to save submission to database")

        return EvaluationResponse(
            message="database updated",
            user_id=user_id,
            submission_id=id
        )
    
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


