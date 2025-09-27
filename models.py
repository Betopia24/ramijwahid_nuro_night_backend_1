# models.py
from pydantic import BaseModel, Field
from typing import Optional, List

class AudioGenerationResponse(BaseModel):
    message: str
    scenario_id: str
    cloudinary_url: str 
    status: str

class GradingReport(BaseModel):
    TotalScore: float = Field(..., ge=0, le=100)
    Positive: Optional[List[str]] = None
    Negative: Optional[List[str]] = None
    Improvement: Optional[List[str]] = None

class EvaluationResponse(BaseModel):
    message: str
    user_id: str
    submission_id: str