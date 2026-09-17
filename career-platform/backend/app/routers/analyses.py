import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app import models, schemas
from app.services.ai_analysis import analyze_fit, analyze_fit_batch, AnalysisError

router = APIRouter(prefix="/analyses", tags=["analyses"])

# How many jobs to pull from the DB per HTTP request from the frontend.
BATCH_CHUNK_SIZE = 10
# How many jobs go into ONE AI prompt/call within that chunk. 10 jobs / 5 per
# call = 2 AI requests per HTTP call instead of 10 — this is the actual fix
# for both rate-limit exhaustion and per-request timeouts.
AI_BATCH_SIZE = 5


def _combined_resumes_text(db: Session, primary_resume: models.Resume) -> str:
    all_resumes = db.query(models.Resume).all()
    if len(all_resumes) <= 1:
        return primary_resume.raw_text
    parts = []
    for r in all_resumes:
        label = r.label or "resume"
        marker = " (primary, selected for this analysis)" if r.id == primary_resume.id else ""
        parts.append(f"--- {label}{marker} ---\n{r.raw_text}")
    return "\n\n".join(parts)


def _chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


@router.post("", response_model=schemas.AnalysisOut)
async def create_analysis(payload: schemas.AnalysisCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    job = db.query(models.Job).filter(models.Job.id == payload.job_id).first()
    resume = db.query(models.Resume).filter(models.Resume.id == payload.resume_id).first()
    if not job or not resume:
        raise HTTPException(status_code=404, detail="Job or resume not found")

    combined = _combined_resumes_text(db, resume)

    try:
        result = await analyze_fit(resume.raw_text, combined, job.raw_text)
    except AnalysisError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return _upsert_analysis(db, job.id, resume.id, result)


@router.post("/batch", response_model=schemas.BatchAnalysisOut)
async def batch_analyze(
    payload: schemas.AnalysisCreate,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=BATCH_CHUNK_SIZE, ge=1, le=50),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Re-analyzes jobs against this resume, grouping several jobs into each AI
    call (AI_BATCH_SIZE) to cut total API requests. Always re-scores — no
    'already analyzed, skip it' tracking. Frontend pages through using `offset`
    until `remaining` is 0."""
    resume = db.query(models.Resume).filter(models.Resume.id == payload.resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    combined = _combined_resumes_text(db, resume)

    all_jobs = db.query(models.Job).order_by(models.Job.created_at.desc()).all()
    this_chunk = all_jobs[offset : offset + limit]
    remaining_after = max(0, len(all_jobs) - (offset + len(this_chunk)))

        async def _run_ai_batch(job_group):
        job_dicts = [{"id": j.id, "text": j.raw_text} for j in job_group]
        try:
            results_by_id = await analyze_fit_batch(resume.raw_text, combined, job_dicts)
            return job_group, results_by_id, None
        except Exception as e:
            # Catches AnalysisError AND anything unexpected (a provider SDK quirk,
            # a malformed response, etc.) — one bad group of 5 jobs should never be
            # able to take down the entire /analyses/batch endpoint for everyone.
            return job_group, None, e

    ai_batches = list(_chunked(this_chunk, AI_BATCH_SIZE))
    outcomes = await asyncio.gather(*[_run_ai_batch(group) for group in ai_batches])

    created = []
    for job_group, results_by_id, err in outcomes:
        if err is not None:
            print(f"Skipping AI batch of {len(job_group)} jobs: {err}")
            continue
        for job in job_group:
            result = results_by_id.get(job.id)
            if not result:
                print(f"No result returned for job {job.id} in this batch")
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