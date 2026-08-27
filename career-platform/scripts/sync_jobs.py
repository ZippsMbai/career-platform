"""
sync_jobs.py — bridges job_watch.py's local JSON output into the Career
Intelligence Platform via its API.

USAGE
    python sync_jobs.py --source /path/to/job_watch_output.json \
        --api-base http://localhost:8000 --email you@example.com --password ...

DEDUP
    Dedupes against the live database (fetches existing jobs' source_urls via
    GET /jobs before importing), not a local file. This matters if you're running
    this on a schedule (cron, GitHub Actions, etc.) where there's no persistent
    local disk between runs — the database is the single source of truth, so
    dedup works identically whether you run this locally or in CI.

WHAT IT ASSUMES
    job_watch.py already outputs the right shape (raw_text, source_url, title,
    company). If you're feeding this a different tool's output, edit the four
    lines in map_job() below — everything else stays the same.
"""
import argparse
import json
import sys
from pathlib import Path

import httpx


def map_job(raw: dict) -> dict | None:
    """Translate one job_watch.py record into the platform's /jobs payload.
    Edit this function if your source JSON uses different field names."""
    url = raw.get("url") or raw.get("source_url") or raw.get("link")
    text = raw.get("description") or raw.get("text") or raw.get("raw_text")
    if not text:
        return None  # nothing to analyze without posting text — skip
    return {
        "raw_text": text,
        "source_url": url,
        "title": raw.get("title"),
        "company": raw.get("company"),
    }


def main():
    parser = argparse.ArgumentParser(description="Sync job_watch.py output into the Career Platform API")
    parser.add_argument("--source", required=True, help="Path to job_watch.py's JSON output file")
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--email", required=True, help="Login email (matches AUTH_EMAIL on the backend)")
    parser.add_argument("--password", required=True, help="Login password")
    args = parser.parse_args()

    # Validate BEFORE making any network call. An empty string passed explicitly
    # (e.g. --api-base "$API_BASE" where API_BASE is unset) silently overrides
    # argparse's default and previously produced a cryptic httpx.UnsupportedProtocol
    # traceback instead of a clear message — this catches that case directly.
    missing = []
    if not args.api_base or not args.api_base.strip():
        missing.append("--api-base (or the API_BASE env var feeding it) is empty")
    elif not (args.api_base.startswith("http://") or args.api_base.startswith("https://")):
        missing.append(f"--api-base value '{args.api_base}' doesn't start with http:// or https://")
    if not args.email or not args.email.strip():
        missing.append("--email (or the AUTH_EMAIL env var feeding it) is empty")
    if not args.password or not args.password.strip():
        missing.append("--password (or the AUTH_PASSWORD env var feeding it) is empty")

    if missing:
        print("Cannot proceed — configuration problem detected before any network call:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        print(
            "If running via GitHub Actions, check Settings > Secrets and variables > Actions "
            "and confirm AUTH_EMAIL / AUTH_PASSWORD (Secrets tab) and API_BASE (Variables tab) "
            "are all actually saved there — not just referenced in the workflow file.",
            file=sys.stderr,
        )
        sys.exit(1)

    source_path = Path(args.source)
    if not source_path.exists():
        print(f"Source file not found: {source_path}", file=sys.stderr)
        sys.exit(1)

    raw_jobs = json.loads(source_path.read_text())
    if isinstance(raw_jobs, dict):
        for key in ("jobs", "results", "postings"):
            if key in raw_jobs:
                raw_jobs = raw_jobs[key]
                break

    with httpx.Client(base_url=args.api_base, timeout=30) as client:
        try:
            login_resp = client.post("/auth/login", json={"email": args.email, "password": args.password})
            login_resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            print(f"Login failed: {e.response.status_code} {e.response.text}", file=sys.stderr)
            sys.exit(1)

        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # dedup against the live DB, not a local file — correct whether run locally or on a schedule
        existing = client.get("/jobs", headers=headers)
        existing.raise_for_status()
        existing_urls = {j["source_url"] for j in existing.json() if j.get("source_url")}

        imported, skipped, unmappable = 0, 0, 0
        for raw in raw_jobs:
            job = map_job(raw)
            if job is None:
                unmappable += 1
                continue
            if job["source_url"] and job["source_url"] in existing_urls:
                skipped += 1
                continue

            resp = client.post("/jobs", json=job, headers=headers)
            if resp.status_code == 200:
                imported += 1
                if job["source_url"]:
                    existing_urls.add(job["source_url"])
            else:
                print(f"Failed to import '{job.get('title')}': {resp.status_code} {resp.text}", file=sys.stderr)

    print(f"Imported {imported}, skipped {skipped} already-synced, {unmappable} unmappable (missing posting text).")


if __name__ == "__main__":
    main()
