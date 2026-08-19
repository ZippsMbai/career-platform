# Career Intelligence Platform — V1

See `PRODUCT.md` and `ARCHITECTURE.md` for scope and design decisions, and `DEPLOY.md`
for deploying it for free (Vercel + Render + Neon) instead of running it locally.

## What's here

A working backend (FastAPI + PostgreSQL, four tables, the `/analyses` endpoint reusing the
exact prompt validated in the browser prototype) and a working frontend (Next.js dashboard:
add resumes and jobs, run an analysis, track the result as an application). Both build clean —
verified with `next build` and a live import/schema check on the API, not just written and
hoped for.

## Setup

1. **Environment**
   ```bash
   cd backend
   cp .env.example .env
   ```
   Fill in `ANTHROPIC_API_KEY` and `JWT_SECRET` (any long random string).

2. **Generate your password hash** (one-time, single-user auth):
   ```bash
   python -c "from app.auth import hash_password; print(hash_password('your-chosen-password'))"
   ```
   Paste the output into `AUTH_PASSWORD_HASH` in `.env`, and set `AUTH_EMAIL` to whatever email you want to log in with.

3. **Run everything**
   ```bash
   docker compose up --build
   ```
   This starts Postgres and the API on `http://localhost:8000`.

4. **Run the migration** (first time, and after any schema change):
   ```bash
   docker compose exec backend alembic upgrade head
   ```

5. **Try it**
   Open `http://localhost:8000/docs`. Log in via `POST /auth/login`, use the returned token
   as a Bearer token for the rest, then:
   - `POST /resumes` with your resume text
   - `POST /jobs` with a posting
   - `POST /analyses` with both IDs — this calls Claude and returns the fit analysis
   - `POST /applications` to start tracking it

## Local dev without Docker

Backend:
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# make sure Postgres is running locally and DATABASE_URL in .env points to it
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:
```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```
Open `http://localhost:3000`, log in with the email/password you set on the backend, and use
the dashboard: add a resume, add a job, run an analysis, track it.

## Running the tests

```bash
cd backend
pip install -r requirements-dev.txt
# needs a real Postgres reachable at DATABASE_URL — a throwaway local or CI database, not your real one
DATABASE_URL="postgresql+psycopg2://user:pass@localhost:5432/career_platform_test" pytest tests/ -v
```
Runs automatically on every push via `.github/workflows/backend-tests.yml` once this is on GitHub —
no setup needed beyond pushing.

## What's next

- **Daily automated sync**: `.github/workflows/daily-job-sync.yml` runs `job_watch.py` →
  `sync_jobs.py` automatically every day at 00:00 EAT (21:00 UTC — GitHub Actions cron is
  always UTC, adjusted here for Nairobi). To enable it once this is on GitHub:
  1. Repo Settings → Secrets and variables → Actions → New repository secret:
     `AUTH_EMAIL` and `AUTH_PASSWORD` (your backend login).
  2. Same page, "Variables" tab → New variable: `API_BASE` = your deployed backend URL
     (from `DEPLOY.md`), and optionally `JOB_KEYWORDS` to override the default search terms.
  3. That's it — it runs nightly with no further input. Trigger it manually anytime from
     the repo's Actions tab ("Run workflow") to test it without waiting for midnight.

  Dedup is against the live database (not a local file), verified to work correctly across
  separate runs — necessary since GitHub Actions gives you a fresh disk every run.
- See `ARCHITECTURE.md` for the phased roadmap beyond V1.
