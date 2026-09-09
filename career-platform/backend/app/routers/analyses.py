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
BATCH_CHUNK_SIZE = 5


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

    return _save_analysis(db, job.id, resume.id, result)


@router.post("/batch", response_model=schemas.BatchAnalysisOut)
async def batch_analyze(
    payload: schemas.AnalysisCreate,
    limit: int = Query(default=BATCH_CHUNK_SIZE, ge=1, le=20),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Analyze up to `limit` jobs that don't yet have an analysis against this resume,
    then report how many are still pending. Call again (same resume) until
    `remaining` is 0 — this is what lets the dashboard process a large batch without
    any single request running long enough to time out."""
    resume = db.query(models.Resume).filter(models.Resume.id == payload.resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    combined = _combined_resumes_text(db, resume)

    already_analyzed_job_ids = {
        a.job_id for a in db.query(models.Analysis.job_id).filter(models.Analysis.resume_id == resume.id).all()
    }
    all_jobs = db.query(models.Job).all()
    pending_jobs = [j for j in all_jobs if j.id not in already_analyzed_job_ids]

    this_chunk = pending_jobs[:limit]
    remaining_after = max(0, len(pending_jobs) - len(this_chunk))

        import asyncio

    async def _analyze_one(job):
        try:
            result = await analyze_fit(resume.raw_text, combined, job.raw_text)
            return job, result, None
        except AnalysisError as e:
            return job, None, e

    # Run all jobs in this chunk concurrently instead of one-at-a-time — this is
    # what actually fixes the timeout: 5 sequential AI calls could take minutes,
    # 5 concurrent calls take roughly as long as the single slowest one.
    outcomes = await asyncio.gather(*[_analyze_one(job) for job in this_chunk])

    created = []
    for job, result, err in outcomes:
        if err is not None:
            # one bad job (e.g. malformed posting text) shouldn't kill the whole batch —
            # it still counts against this chunk's slot so we don't retry it forever
            print(f"Skipping job {job.id}: {err}")
            continue
        created.append(_save_analysis(db, job.id, resume.id, result))

    return {"results": created, "remaining": remaining_after}

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
        cover_letter_full=result.get("cover_letter_full"),
        tailored_resume=result.get("tailored_resume"),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis
