from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import resumes, jobs, analyses, applications, auth_router

app = FastAPI(title="Career Intelligence Platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(resumes.router)
app.include_router(jobs.router)
app.include_router(analyses.router)
app.include_router(applications.router)


@app.get("/health")
def health():
    return {"status": "ok"}
