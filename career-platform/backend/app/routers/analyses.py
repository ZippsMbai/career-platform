import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app import models, schemas
from app.services.ai_analysis import analyze_fit, AnalysisError

router = APIRouter(prefix="/analyses", tags=["analyses"])

# Analyzing every un-scored job in one HTTP request used to run long enough to hit
# Render's/the browser's connection timeout once real sync volume showed up — this
# caps each call to a small slice so no single request runs that long. The frontend
# calls /analyses/batch repeatedly (using `remaining`) until nothing's left.
BATCH_CHUNK_SIZE = 2


def _combined_resumes_text(db: Session, primary_resume: models.Resume) -> str:
    """All saved resumes concatenated, so the model can pull in relevant experience
    from any of them (not just the one selected for this analysis) when building the
    tailored resume and cover letter — the actual "use my resumes combined" request."""
    all_resumes = db.query(models.Resume).all()
    if len(all_resumes) <= 1:
        return primary_resume.raw_text
    parts = []
    for r in all_resumes:
        label = r.label or "resume"
        marker = " (primary, selected for this analysis)" if r.id == primary_resume.id else ""
        parts.append(f"--- {label}{marker} ---\n{r.raw_text}")
    return "\n\n".join(parts)


@router.post("/batch", response_model=schemas.BatchAnalysisOut)
async def batch_analyze(
    payload: schemas.AnalysisCreate,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=BATCH_CHUNK_SIZE, ge=1, le=20),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Re-analyzes every saved job against this resume every time it's called —
    no 'already analyzed, skip it' tracking. Existing analyses for the same
    job+resume pair are updated in place rather than duplicated. The frontend
    pages through jobs using `offset`, chunk by chunk, until `remaining` is 0."""
    resume = db.query(models.Resume).filter(models.Resume.id == payload.resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    combined = _combined_resumes_text(db, resume)

    all_jobs = db.query(models.Job).order_by(models.Job.created_at.desc()).all()
    this_chunk = all_jobs[offset : offset + limit]
    remaining_after = max(0, len(all_jobs) - (offset + len(this_chunk)))

    async def _analyze_one(job):
        try:
            result = await analyze_fit(resume.raw_text, combined, job.raw_text)
            return job, result, None
        except AnalysisError as e:
            return job, None, e

    outcomes = await asyncio.gather(*[_analyze_one(job) for job in this_chunk])

    created = []
    for job, result, err in outcomes:
        if err is not None:
            print(f"Skipping job {job.id}: {err}")
            continue
        created.append(_upsert_analysis(db, job.id, resume.id, result))

    return {"results": created, "remaining": remaining_after}


@router.get("/{analysis_id}", response_model=schemas.AnalysisOut)
def get_analysis(analysis_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    analysis = db.query(models.Analysis).filter(models.Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


def _upsert_analysis(db: Session, job_id: str, resume_id: str, result: dict) -> models.Analysis:
    existing = db.query(models.Analysis).filter(
        models.Analysis.job_id == job_id, models.Analysis.resume_id == resume_id
    ).first()
    analysis = existing or models.Analysis(job_id=job_id, resume_id=resume_id)
    analysis.fit_score = result.get("fit_score", 0)
    analysis.summary = result.get("summary")
    analysis.matched_signals = result.get("matched_signals")
    analysis.gaps = result.get("gaps")
    analysis.tailored_bullets = result.get("tailored_bullets")
    analysis.cover_letter_opening = result.get("cover_letter_opening")
    analysis.cover_letter_full = result.get("cover_letter_full")
    analysis.tailored_resume = result.get("tailored_resume")
    if not existing:
        db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis