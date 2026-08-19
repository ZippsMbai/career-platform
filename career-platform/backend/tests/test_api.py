"""
Codifies the manual verification done during the build into repeatable tests.
Requires a real Postgres database (DATABASE_URL env var) — see .github/workflows
for the CI setup that spins one up automatically. The outbound Claude API call in
analyze_fit is mocked throughout; everything else (routing, auth, DB writes,
relationships, the batch skip-logic) is exercised for real.
"""
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("JWT_SECRET", "test-secret-for-ci")
os.environ.setdefault("AUTH_EMAIL", "test@example.com")
# bcrypt hash of "testpass123" — fine to hardcode, this only ever runs against a throwaway CI database
os.environ.setdefault("AUTH_PASSWORD_HASH", "$2b$12$Ov3gWW6Os9PVQWHcBKTsyuaaOInIAYXflJEJXHe4rbn37pHo/hKIC")

from app.main import app  # noqa: E402
from app.database import Base, engine  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def setup_schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    resp = client.post("/auth/login", json={"email": "test@example.com", "password": "testpass123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_login_rejects_wrong_password(client):
    resp = client.post("/auth/login", json={"email": "test@example.com", "password": "wrong"})
    assert resp.status_code == 401


def test_login_accepts_correct_password(client):
    resp = client.post("/auth/login", json={"email": "test@example.com", "password": "testpass123"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_rate_limited_after_repeated_failures(client):
    from app.routers.auth_router import _failed_attempts
    _failed_attempts.clear()  # isolate from other tests sharing TestClient's fake IP

    for _ in range(5):
        client.post("/auth/login", json={"email": "test@example.com", "password": "wrong"})
    resp = client.post("/auth/login", json={"email": "test@example.com", "password": "wrong"})
    assert resp.status_code == 429

    # correct password should also be blocked while rate-limited
    resp = client.post("/auth/login", json={"email": "test@example.com", "password": "testpass123"})
    assert resp.status_code == 429

    _failed_attempts.clear()  # don't leak into subsequent tests either


def test_endpoints_reject_missing_token(client):
    resp = client.get("/jobs")
    assert resp.status_code == 401


def test_resume_create_and_list(client, auth_headers):
    resp = client.post("/resumes", json={"label": "security", "raw_text": "Security engineer, Azure, Splunk."}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["label"] == "security"

    resp = client.get("/resumes", headers=auth_headers)
    assert resp.status_code == 200
    assert any(r["label"] == "security" for r in resp.json())


def test_job_create_and_list(client, auth_headers):
    resp = client.post("/jobs", json={"title": "Cloud Security Engineer", "company": "Acme", "raw_text": "Azure security role."}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Cloud Security Engineer"

    resp = client.get("/jobs", headers=auth_headers)
    assert resp.status_code == 200
    assert any(j["title"] == "Cloud Security Engineer" for j in resp.json())


def test_application_create_list_and_patch(client, auth_headers):
    job = client.post("/jobs", json={"title": "SOC Analyst", "raw_text": "SOC role."}, headers=auth_headers).json()

    resp = client.post("/applications", json={"job_id": job["id"], "status": "saved"}, headers=auth_headers)
    assert resp.status_code == 200
    app_row = resp.json()
    assert app_row["status"] == "saved"
    assert app_row["applied_at"] is None

    resp = client.get("/applications", headers=auth_headers)
    assert any(a["id"] == app_row["id"] for a in resp.json())

    resp = client.patch(f"/applications/{app_row['id']}", json={"status": "applied"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "applied"
    assert resp.json()["applied_at"] is not None  # auto-set on transition to "applied"


FAKE_ANALYSIS = {
    "fit_score": 82,
    "summary": "Strong match on cloud security fundamentals.",
    "matched_signals": ["Azure experience"],
    "gaps": ["No Splunk mentioned in posting"],
    "tailored_bullets": ["Administered Azure/Entra ID security controls at scale"],
    "cover_letter_opening": "I'm excited to apply my Azure security background to this role.",
}


def test_analysis_create(client, auth_headers):
    resume = client.post("/resumes", json={"label": "default", "raw_text": "Security engineer."}, headers=auth_headers).json()
    job = client.post("/jobs", json={"title": "Security Role", "raw_text": "Security posting."}, headers=auth_headers).json()

    with patch("app.routers.analyses.analyze_fit", new=AsyncMock(return_value=FAKE_ANALYSIS)):
        resp = client.post("/analyses", json={"job_id": job["id"], "resume_id": resume["id"]}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["fit_score"] == 82
    assert resp.json()["job_id"] == job["id"]


def test_batch_analysis_skips_already_analyzed(client, auth_headers):
    resume = client.post("/resumes", json={"label": "default", "raw_text": "Security engineer."}, headers=auth_headers).json()
    job_a = client.post("/jobs", json={"title": "Already Analyzed", "raw_text": "posting a"}, headers=auth_headers).json()
    job_b = client.post("/jobs", json={"title": "Brand New", "raw_text": "posting b"}, headers=auth_headers).json()

    with patch("app.routers.analyses.analyze_fit", new=AsyncMock(return_value=FAKE_ANALYSIS)):
        # analyze job_a individually first
        client.post("/analyses", json={"job_id": job_a["id"], "resume_id": resume["id"]}, headers=auth_headers)

        # batch should only pick up job_b (and any other unanalyzed jobs from prior tests
        # in this module, since the schema is shared for the whole module's run)
        resp = client.post("/analyses/batch", json={"job_id": "", "resume_id": resume["id"]}, headers=auth_headers)

    assert resp.status_code == 200
    analyzed_job_ids = {a["job_id"] for a in resp.json()}
    assert job_b["id"] in analyzed_job_ids
    assert job_a["id"] not in analyzed_job_ids  # already had an analysis, batch must skip it
