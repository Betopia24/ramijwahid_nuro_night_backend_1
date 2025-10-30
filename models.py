# models.py
from pydantic import BaseModel, Field
from typing import Optional, List

class AudioGenerationRequest(BaseModel):
    pdf_url: str

class AudioGenerationResponse(BaseModel):
    message: str
    cloudinary_url: str 
    status: str

class GradingReport(BaseModel):
    TotalScore: float = Field(..., ge=0, le=100)
    Positive: Optional[List[str]] = None
    Negative: Optional[List[str]] = None
    Improvement: Optional[List[str]] = None

class EvaluationResponse(BaseModel):
    message: str
    total_score: float
    positive: Optional[List[str]] = None
    negative: Optional[List[str]] = None
    improvement: Optional[List[str]] = None