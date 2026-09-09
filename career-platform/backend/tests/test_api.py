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


def test_job_dedup_by_title_and_company_across_different_urls(client, auth_headers):
    """The actual bug reported: the same posting synced from multiple sources with
    different (or missing) URLs created duplicate job cards. This confirms dedup by
    title+company catches it even when source_url doesn't match."""
    r1 = client.post("/jobs", json={
        "title": "AI Content Analyst", "company": "Peroptyx", "raw_text": "posting", "source_url": None,
    }, headers=auth_headers)
    r2 = client.post("/jobs", json={
        "title": "AI Content Analyst", "company": "Peroptyx", "raw_text": "posting", "source_url": None,
    }, headers=auth_headers)
    r3 = client.post("/jobs", json={
        "title": "ai content analyst", "company": "PEROPTYX", "raw_text": "posting", "source_url": "https://siteA.com/1",
    }, headers=auth_headers)
    r4 = client.post("/jobs", json={
        "title": "AI Content Analyst", "company": "Peroptyx", "raw_text": "posting", "source_url": "https://siteB.com/2",
    }, headers=auth_headers)

    ids = {r1.json()["id"], r2.json()["id"], r3.json()["id"], r4.json()["id"]}
    assert len(ids) == 1, f"expected all 4 to resolve to the same job, got {len(ids)} distinct rows"

    all_jobs = client.get("/jobs", headers=auth_headers).json()
    matching = [j for j in all_jobs if j["title"].lower() == "ai content analyst" and j["company"].lower() == "peroptyx"]
    assert len(matching) == 1


def test_job_delete_cascades_to_analyses_and_applications(client, auth_headers):
    job = client.post("/jobs", json={"title": "Delete Cascade Job", "raw_text": "posting"}, headers=auth_headers).json()
    resume = client.post("/resumes", json={"label": "t", "raw_text": "r"}, headers=auth_headers).json()

    with patch("app.routers.analyses.analyze_fit", new=AsyncMock(return_value=FAKE_ANALYSIS)):
        client.post("/analyses", json={"job_id": job["id"], "resume_id": resume["id"]}, headers=auth_headers)
    client.post("/applications", json={"job_id": job["id"], "status": "saved"}, headers=auth_headers)

    resp = client.delete(f"/jobs/{job['id']}", headers=auth_headers)
    assert resp.status_code == 204, "delete failed despite manual cascade cleanup — likely a foreign-key error"

    remaining_jobs = client.get("/jobs", headers=auth_headers).json()
    assert not any(j["id"] == job["id"] for j in remaining_jobs)

    remaining_apps = client.get("/applications", headers=auth_headers).json()
    assert not any(a["job_id"] == job["id"] for a in remaining_apps), "application row survived job deletion"

    resp2 = client.delete(f"/jobs/{job['id']}", headers=auth_headers)
    assert resp2.status_code == 404


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


def test_repeated_application_clicks_do_not_duplicate(client, auth_headers):
    """The actual bug reported: clicking Save/Applied multiple times on the same job
    in the Run Analysis panel created multiple Application rows. This confirms
    POST /applications is idempotent per job — repeated calls update the one row."""
    job = client.post("/jobs", json={"title": "Dedup Test Job", "raw_text": "posting"}, headers=auth_headers).json()

    first_id = None
    for _ in range(4):
        resp = client.post("/applications", json={"job_id": job["id"], "status": "saved"}, headers=auth_headers)
        assert resp.status_code == 200
        if first_id is None:
            first_id = resp.json()["id"]
        else:
            assert resp.json()["id"] == first_id, "a new row was created instead of updating the existing one"

    all_apps = client.get("/applications", headers=auth_headers).json()
    matching = [a for a in all_apps if a["job_id"] == job["id"]]
    assert len(matching) == 1, f"expected exactly 1 application row, found {len(matching)}"

    # transitioning status (saved -> applied) must update the same row, not add another
    resp = client.post("/applications", json={"job_id": job["id"], "status": "applied"}, headers=auth_headers)
    assert resp.json()["id"] == first_id
    assert resp.json()["status"] == "applied"
    assert resp.json()["applied_at"] is not None

    all_apps_after = client.get("/applications", headers=auth_headers).json()
    matching_after = [a for a in all_apps_after if a["job_id"] == job["id"]]
    assert len(matching_after) == 1


def test_application_delete(client, auth_headers):
    job = client.post("/jobs", json={"title": "Delete Test Job", "raw_text": "posting"}, headers=auth_headers).json()
    app_row = client.post("/applications", json={"job_id": job["id"], "status": "saved"}, headers=auth_headers).json()

    resp = client.delete(f"/applications/{app_row['id']}", headers=auth_headers)
    assert resp.status_code == 204

    remaining = client.get("/applications", headers=auth_headers).json()
    assert not any(a["id"] == app_row["id"] for a in remaining)

    # deleting again should 404, not crash
    resp2 = client.delete(f"/applications/{app_row['id']}", headers=auth_headers)
    assert resp2.status_code == 404


FAKE_ANALYSIS = {
    "fit_score": 82,
    "summary": "Strong match on cloud security fundamentals.",
    "matched_signals": ["Azure experience"],
    "gaps": ["No Splunk mentioned in posting"],
    "tailored_bullets": ["Administered Azure/Entra ID security controls at scale"],
    "cover_letter_opening": "I'm excited to apply my Azure security background to this role.",
    "cover_letter_full": "Dear Hiring Manager,\n\nI'm excited to apply...\n\nSincerely,\nCandidate",
    "tailored_resume": "JANE CANDIDATE\nSecurity Engineer\n\nSUMMARY\n...\n\nEXPERIENCE\n...",
}


def test_analysis_saves_full_cover_letter_and_tailored_resume(client, auth_headers):
    """The new features: a full cover letter and a tailored resume draft should be
    generated and persisted alongside the existing fit-score fields, not just the
    short cover_letter_opening from before."""
    resume = client.post("/resumes", json={"label": "default", "raw_text": "Security engineer."}, headers=auth_headers).json()
    job = client.post("/jobs", json={"title": "Full Doc Test Role", "raw_text": "posting text"}, headers=auth_headers).json()

    with patch("app.routers.analyses.analyze_fit", new=AsyncMock(return_value=FAKE_ANALYSIS)):
        resp = client.post("/analyses", json={"job_id": job["id"], "resume_id": resume["id"]}, headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["cover_letter_full"] == FAKE_ANALYSIS["cover_letter_full"]
    assert body["tailored_resume"] == FAKE_ANALYSIS["tailored_resume"]

    # confirm it round-trips through GET too, not just the immediate POST response
    fetched = client.get(f"/analyses/{body['id']}", headers=auth_headers).json()
    assert fetched["cover_letter_full"] == FAKE_ANALYSIS["cover_letter_full"]
    assert fetched["tailored_resume"] == FAKE_ANALYSIS["tailored_resume"]


def test_analysis_combines_multiple_resumes_into_the_prompt(client, auth_headers):
    """The actual 'use my resumes combined' request: when more than one resume
    exists, analyze_fit should be called with a combined-text argument that contains
    content from every saved resume, not just the one selected as primary."""
    resume_a = client.post("/resumes", json={"label": "security", "raw_text": "UNIQUE_MARKER_SECURITY_TEXT"}, headers=auth_headers).json()
    resume_b = client.post("/resumes", json={"label": "dev", "raw_text": "UNIQUE_MARKER_DEV_TEXT"}, headers=auth_headers).json()
    job = client.post("/jobs", json={"title": "Combined Resume Test Role", "raw_text": "posting"}, headers=auth_headers).json()

    captured_args = {}

    async def capturing_analyze_fit(primary_resume_text, combined_resumes_text, job_text):
        captured_args["primary"] = primary_resume_text
        captured_args["combined"] = combined_resumes_text
        return FAKE_ANALYSIS

    with patch("app.routers.analyses.analyze_fit", new=capturing_analyze_fit):
        client.post("/analyses", json={"job_id": job["id"], "resume_id": resume_a["id"]}, headers=auth_headers)

    assert captured_args["primary"] == "UNIQUE_MARKER_SECURITY_TEXT"
    assert "UNIQUE_MARKER_SECURITY_TEXT" in captured_args["combined"]
    assert "UNIQUE_MARKER_DEV_TEXT" in captured_args["combined"], "second resume's content missing from combined text"


def test_job_pay_extraction_on_create(client, auth_headers):
    resp = client.post("/jobs", json={
        "title": "Paid Role", "company": "PayCo", "raw_text": "Great role. Salary: $100,000 - $130,000 per year.",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["pay_text"] is not None
    assert "100,000" in resp.json()["pay_text"]

    resp2 = client.post("/jobs", json={
        "title": "Unpaid-Mention Role", "company": "NoPayCo", "raw_text": "Great culture, no pay mentioned.",
    }, headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["pay_text"] is None


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

        # limit=20 (max allowed) so this dedup check isn't affected by other pending
        # jobs left over from earlier tests sharing this schema — chunk-size behavior
        # itself is covered separately in test_batch_analysis_chunks_large_pending_sets
        resp = client.post("/analyses/batch?limit=20", json={"job_id": "", "resume_id": resume["id"]}, headers=auth_headers)

    assert resp.status_code == 200
    # (not asserting remaining == 0 here — other tests sharing this schema may have
    # created additional pending jobs; the chunking test elsewhere covers that behavior)
    analyzed_job_ids = {a["job_id"] for a in resp.json()["results"]}
    assert job_b["id"] in analyzed_job_ids
    assert job_a["id"] not in analyzed_job_ids  # already had an analysis, batch must skip it


def test_batch_analysis_chunks_large_pending_sets(client, auth_headers):
    """The actual bug this fixes: analyzing every pending job in one request could run
    long enough to hit a platform timeout once real sync volume showed up. This confirms
    the endpoint processes a bounded slice per call and correctly reports how many remain,
    with no job analyzed twice across chunks."""
    resume = client.post("/resumes", json={"label": "chunk-test", "raw_text": "resume"}, headers=auth_headers).json()
    job_ids = []
    for i in range(12):
        job = client.post("/jobs", json={"title": f"Chunk job {i}", "raw_text": f"posting {i}"}, headers=auth_headers).json()
        job_ids.append(job["id"])

    with patch("app.routers.analyses.analyze_fit", new=AsyncMock(return_value=FAKE_ANALYSIS)):
        seen = set()
        chunk_sizes = []
        for _ in range(10):  # safety cap, well above what 12 jobs / chunk size 5 should need
            resp = client.post("/analyses/batch", json={"job_id": "", "resume_id": resume["id"]}, headers=auth_headers)
            assert resp.status_code == 200
            body = resp.json()
            chunk_sizes.append(len(body["results"]))
            for a in body["results"]:
                assert a["job_id"] not in seen, "same job analyzed twice across chunks"
                seen.add(a["job_id"])
            if body["remaining"] == 0:
                break

    # Other tests in this module may have created jobs too (shared schema for the run) —
    # this resume has analyzed none of them, so they're legitimately "pending" as well.
    # The real assertion is that our 12 specific jobs all got covered, not that nothing else did.
    assert set(job_ids).issubset(seen), "not every one of our 12 pending jobs was analyzed"
    assert len(chunk_sizes) > 1, "expected more than one chunk given the number of pending jobs"
    assert max(chunk_sizes) <= 5, "a chunk exceeded the intended cap"
