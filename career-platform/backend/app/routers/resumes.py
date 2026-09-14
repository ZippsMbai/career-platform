from fastapi import APIRouter, Depends, File, UploadFile, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app import models, schemas
from app.services.resume_extract import extract_text_from_upload

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("", response_model=schemas.ResumeOut)
def create_resume(payload: schemas.ResumeCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    resume = models.Resume(label=payload.label, raw_text=payload.raw_text)
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


@router.get("", response_model=list[schemas.ResumeOut])
def list_resumes(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(models.Resume).order_by(models.Resume.created_at.desc()).all()


@router.post("/upload", response_model=schemas.ResumeOut)
async def upload_resume(
    label: str = Form("default"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    content = await file.read()
    raw_text = extract_text_from_upload(file.filename, content)
    resume = models.Resume(label=label, raw_text=raw_text)
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume