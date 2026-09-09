from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app import models, schemas

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("", response_model=schemas.ApplicationOut)
def create_application(payload: schemas.ApplicationCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    # Idempotent by job: if this job already has an application row (from an earlier
    # click, a double-click, or re-running analysis on the same job), update that
    # existing row instead of creating a duplicate. This is the actual fix for
    # "pressing Save/Applied multiple times creates multiple entries" — the bug was
    # here, not in the frontend button.
    existing = db.query(models.Application).filter(models.Application.job_id == payload.job_id).first()
    if existing:
        existing.status = payload.status
        if payload.analysis_id is not None:
            existing.analysis_id = payload.analysis_id
        if payload.notes is not None:
            existing.notes = payload.notes
        if payload.status == "applied" and existing.applied_at is None:
            existing.applied_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    app_row = models.Application(
        job_id=payload.job_id,
        analysis_id=payload.analysis_id,
        status=payload.status,
        notes=payload.notes,
        applied_at=datetime.now(timezone.utc) if payload.status == "applied" else None,
    )
    db.add(app_row)
    db.commit()
    db.refresh(app_row)
    return app_row


@router.get("", response_model=list[schemas.ApplicationOut])
def list_applications(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(models.Application).order_by(models.Application.updated_at.desc()).all()


@router.patch("/{application_id}", response_model=schemas.ApplicationOut)
def update_application(application_id: str, payload: schemas.ApplicationUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    app_row = db.query(models.Application).filter(models.Application.id == application_id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    if payload.status is not None:
        app_row.status = payload.status
        if payload.status == "applied" and app_row.applied_at is None:
            app_row.applied_at = datetime.now(timezone.utc)
    if payload.notes is not None:
        app_row.notes = payload.notes
    db.commit()
    db.refresh(app_row)
    return app_row


@router.delete("/{application_id}", status_code=204)
def delete_application(application_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    app_row = db.query(models.Application).filter(models.Application.id == application_id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    db.delete(app_row)
    db.commit()
    return None
