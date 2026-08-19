import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


def utcnow():
    return datetime.now(timezone.utc)


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    label = Column(String, default="default")  # e.g. "security", "dev"
    raw_text = Column(Text, nullable=False)
    parsed_json = Column(JSON, nullable=True)  # structured skills/experience/education
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    analyses = relationship("Analysis", back_populates="resume")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    source_url = Column(String, nullable=True)
    raw_text = Column(Text, nullable=False)
    title = Column(String, nullable=True)
    company = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    analyses = relationship("Analysis", back_populates="job")
    applications = relationship("Application", back_populates="job")


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    job_id = Column(UUID(as_uuid=False), ForeignKey("jobs.id"), nullable=False)
    resume_id = Column(UUID(as_uuid=False), ForeignKey("resumes.id"), nullable=False)
    fit_score = Column(Integer, nullable=False)
    summary = Column(Text, nullable=True)
    matched_signals = Column(JSON, nullable=True)
    gaps = Column(JSON, nullable=True)
    tailored_bullets = Column(JSON, nullable=True)
    cover_letter_opening = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    job = relationship("Job", back_populates="analyses")
    resume = relationship("Resume", back_populates="analyses")
    applications = relationship("Application", back_populates="analysis")


class Application(Base):
    __tablename__ = "applications"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    job_id = Column(UUID(as_uuid=False), ForeignKey("jobs.id"), nullable=False)
    analysis_id = Column(UUID(as_uuid=False), ForeignKey("analyses.id"), nullable=True)
    status = Column(String, default="saved")  # saved / applied / interviewing / rejected / offer
    notes = Column(Text, nullable=True)
    applied_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    job = relationship("Job", back_populates="applications")
    analysis = relationship("Analysis", back_populates="applications")
