from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone

from app.database import get_db
from app.auth import get_current_user
from app import models, schemas
from app.services.pay_extraction import extract_pay

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _utcnow():
    return datetime.now(timezone.utc)


@router.post("", response_model=schemas.JobOut)
def create_job(payload: schemas.JobCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    # Dedup before creating. When a match is found, this also "touches"
    # last_seen_at — this is what lets a daily sync mark a posting as still
    # live just by re-submitting it, without needing a separate endpoint.
    if payload.source_url:
        existing = db.query(models.Job).filter(models.Job.source_url == payload.source_url).first()
        if existing:
            existing.last_seen_at = _utcnow()
            db.commit()
            db.refresh(existing)
            return existing

    if payload.title and payload.company:
        existing = db.query(models.Job).filter(
            func.lower(models.Job.title) == payload.title.strip().lower(),
            func.lower(models.Job.company) == payload.company.strip().lower(),
        ).first()
        if existing:
            existing.last_seen_at = _utcnow()
            db.commit()
            db.refresh(existing)
            return existing

    job = models.Job(
        raw_text=payload.raw_text,
        source_url=payload.source_url,
        title=payload.title,
        company=payload.company,
        pay_text=extract_pay(payload.raw_text),
        last_seen_at=_utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("", response_model=list[schemas.JobOut])
def list_jobs(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(models.Job).order_by(models.Job.created_at.desc()).all()


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    db.query(models.Application).filter(models.Application.job_id == job_id).delete()
    db.query(models.Analysis).filter(models.Analysis.job_id == job_id).delete()
    db.delete(job)
    db.commit()
    return None