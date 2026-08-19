from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app import models, schemas
from app.services.ai_analysis import analyze_fit, AnalysisError

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.post("", response_model=schemas.AnalysisOut)
async def create_analysis(payload: schemas.AnalysisCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    job = db.query(models.Job).filter(models.Job.id == payload.job_id).first()
    resume = db.query(models.Resume).filter(models.Resume.id == payload.resume_id).first()
    if not job or not resume:
        raise HTTPException(status_code=404, detail="Job or resume not found")

    try:
        result = await analyze_fit(resume.raw_text, job.raw_text)
    except AnalysisError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return _save_analysis(db, job.id, resume.id, result)


@router.post("/batch", response_model=list[schemas.AnalysisOut])
async def batch_analyze(payload: schemas.AnalysisCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Analyze every job that doesn't yet have an analysis against this resume.
    Run once after job_watch + sync_jobs bring in new postings, then sort by
    fit_score in the dashboard instead of opening each job by hand."""
    resume = db.query(models.Resume).filter(models.Resume.id == payload.resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    already_analyzed_job_ids = {
        a.job_id for a in db.query(models.Analysis.job_id).filter(models.Analysis.resume_id == resume.id).all()
    }
    all_jobs = db.query(models.Job).all()
    pending_jobs = [j for j in all_jobs if j.id not in already_analyzed_job_ids]

    created = []
    for job in pending_jobs:
        try:
            result = await analyze_fit(resume.raw_text, job.raw_text)
        except AnalysisError as e:
            # one bad job (e.g. malformed posting text) shouldn't kill the whole batch
            print(f"Skipping job {job.id}: {e}")
            continue
        created.append(_save_analysis(db, job.id, resume.id, result))

    return created


@router.get("/{analysis_id}", response_model=schemas.AnalysisOut)
def get_analysis(analysis_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    analysis = db.query(models.Analysis).filter(models.Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


def _save_analysis(db: Session, job_id: str, resume_id: str, result: dict) -> models.Analysis:
    analysis = models.Analysis(
        job_id=job_id,
        resume_id=resume_id,
        fit_score=result.get("fit_score", 0),
        summary=result.get("summary"),
        matched_signals=result.get("matched_signals"),
        gaps=result.get("gaps"),
        tailored_bullets=result.get("tailored_bullets"),
        cover_letter_opening=result.get("cover_letter_opening"),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis
