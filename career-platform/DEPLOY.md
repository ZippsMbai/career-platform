# Deploying for free — Vercel + Render + Neon

Checked current (2026) free-tier terms before recommending this combination — Railway and
Fly.io no longer offer real free tiers for new signups, and Render's own free Postgres
auto-deletes after 30 days with no warning. This combination avoids both problems.

| Piece | Service | Free tier reality |
|---|---|---|
| Frontend | Vercel | Free, no card required, built for Next.js |
| Backend | Render (Web Service) | Free, sleeps after 15 min idle, ~30-60s cold start on next request — fine for single-user use |
| Database | Neon | Free, persistent (no 30-day expiry, unlike Render's own Postgres) |

## 1. Push the repo to GitHub

Both Vercel and Render deploy from a Git repo.

```bash
cd career-platform
git init
git add .
git commit -m "Initial commit"
```
Create a new repo on GitHub, then:
```bash
git remote add origin https://github.com/<you>/career-platform.git
git push -u origin main
```

## 2. Database — Neon

1. Sign up at neon.tech (free, no card).
2. Create a project. Copy the connection string it gives you — looks like
   `postgresql://user:password@ep-xxx.neon.tech/neondb?sslmode=require`.
3. SQLAlchemy needs the `psycopg2` driver prefix, so change it to:
   `postgresql+psycopg2://user:password@ep-xxx.neon.tech/neondb?sslmode=require`
4. Run the migration against it from your machine (VS Code terminal):
   ```bash
   cd backend
   pip install -r requirements.txt
   DATABASE_URL="postgresql+psycopg2://...neon-connection-string..." alembic upgrade head
   ```

## 3. Backend — Render

1. Sign up at render.com (free, no card for the Hobby tier).
2. New → Web Service → connect your GitHub repo.
3. Root directory: `backend`
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Environment variables (Render's dashboard, not a committed file):
   - `DATABASE_URL` = your Neon connection string
   - `ANTHROPIC_API_KEY` = your real key
   - `JWT_SECRET` = a long random string
   - `AUTH_EMAIL` = the email you want to log in with
   - `AUTH_PASSWORD_HASH` = output of `python -c "from app.auth import hash_password; print(hash_password('your-password'))"`
   - `CORS_ORIGINS` = leave as `http://localhost:3000` for now — update after step 4 once you have your Vercel URL
7. Deploy. Render gives you a URL like `https://career-platform-api.onrender.com`.

## 4. Frontend — Vercel

1. Sign up at vercel.com (free, no card).
2. New Project → import the same GitHub repo.
3. Root directory: `frontend`
4. Environment variable: `NEXT_PUBLIC_API_BASE` = your Render backend URL from step 3.
5. Deploy. Vercel gives you a URL like `https://career-platform.vercel.app`.

## 5. Close the loop — update CORS

Go back to Render's environment variables and update:
```
CORS_ORIGINS=http://localhost:3000,https://career-platform.vercel.app
```
(comma-separated, no spaces). Render redeploys automatically when you save an env var change.
This is the step that's easy to forget and shows up as a confusing "CORS error" in the browser
console if skipped.

## 6. Test it

Open the Vercel URL, log in with the email/password you set in step 3, and run through the
dashboard flow. First request after any idle period will be slow (Render waking up) — that's
expected on the free tier, not a bug.

## Running job_watch.py / sync_jobs.py against the deployed backend

Same commands as local dev, just point `--api-base` at your Render URL instead of
`http://localhost:8000`:
```bash
python scripts/sync_jobs.py --source job_watch_output.json \
  --api-base https://career-platform-api.onrender.com \
  --email you@example.com --password your-password
```
