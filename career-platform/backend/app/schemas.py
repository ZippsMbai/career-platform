from datetime import datetime
from typing import Optional, List, Any

from pydantic import BaseModel, ConfigDict


class ResumeCreate(BaseModel):
    label: str = "default"
    raw_text: str


class ResumeOut(BaseModel):
    id: str
    label: str
    raw_text: str
    parsed_json: Optional[Any] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobCreate(BaseModel):
    raw_text: str
    source_url: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None


class JobOut(BaseModel):
    id: str
    raw_text: str
    source_url: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    pay_text: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnalysisCreate(BaseModel):
    job_id: str
    resume_id: str


class AnalysisOut(BaseModel):
    id: str
    job_id: str
    resume_id: str
    fit_score: int
    summary: Optional[str] = None
    matched_signals: Optional[List[str]] = None
    gaps: Optional[List[str]] = None
    tailored_bullets: Optional[List[str]] = None
    cover_letter_opening: Optional[str] = None
    cover_letter_full: Optional[str] = None
    tailored_resume: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BatchAnalysisOut(BaseModel):
    """Batch triage processes a small slice per call rather than every pending job
    at once, so no single HTTP request runs long enough to hit a platform timeout.
    `remaining` tells the frontend whether to call /analyses/batch again."""
    results: List[AnalysisOut]
    remaining: int


class ApplicationCreate(BaseModel):
    job_id: str
    analysis_id: Optional[str] = None
    status: str = "saved"
    notes: Optional[str] = None


class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


class ApplicationOut(BaseModel):
    id: str
    job_id: str
    analysis_id: Optional[str] = None
    status: str
    notes: Optional[str] = None
    applied_at: Optional[datetime] = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: str
    password: str
