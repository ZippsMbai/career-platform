from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app import models, schemas

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
