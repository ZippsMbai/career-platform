# What's actually been tested

Being precise about this rather than just saying "it works" — here's exactly what was
verified, how, and what's still on you to confirm.

## Verified live, against a real PostgreSQL 16 database (not SQLite, not mocks)

- Alembic migration runs clean and creates all four tables with correct foreign keys
  (checked with `\dt` and `\d applications` directly in psql)
- `POST /auth/login` — rejects wrong password (401), accepts correct one (200, real JWT)
- `GET /jobs` and other endpoints reject requests with no token (401)
- `POST /resumes`, `POST /jobs` — create rows, return them correctly shaped
- `GET /resumes`, `GET /jobs` — list what was created
- `POST /applications`, `GET /applications` — create and list tracking records
- `PATCH /applications/{id}` — updates status, correctly auto-sets `applied_at` only
  when status becomes "applied"
- `POST /analyses` and `POST /analyses/batch` — full DB read/write path, foreign keys
  to job+resume, and the batch endpoint's core logic (skip jobs already analyzed for
  this resume) confirmed correct: given one already-analyzed job and one new one,
  batch correctly analyzed only the new one.
- Frontend: `next build` compiles clean, both routes prerender, TypeScript checks pass.

For the `/analyses` tests, the actual outbound call to Claude was stubbed with a fixed
response — everything downstream of that (saving to DB, response shape, batch skip-logic)
is real; the call to `api.anthropic.com` itself is not, because this sandbox has no API
key to make that call with.

## Still needs you, because this sandbox genuinely can't reach it

1. **The live AI analysis quality** — whether the fit scores and gaps are actually good,
   once real Claude calls are happening with your real `ANTHROPIC_API_KEY`.
2. **`job_watch.py`'s live HTTP calls** — RemoteOK, Arbeitnow, We Work Remotely, Remotive,
   Jobicy, ReliefWeb. Parsing logic was checked against realistic sample data, but the
   actual API responses from those six domains have never been fetched from here.
3. **The frontend in an actual browser** — the build compiles, but no one has clicked
   through the login → dashboard → triage flow with real eyes on it.
4. **Docker Compose specifically** — the pieces were tested with a locally-installed
   Postgres and a bare `uvicorn` process, not through `docker-compose up`. Worth a run
   to catch anything Docker-networking-specific (service name resolution, etc.).

## Suggested order for your own test pass

```bash
docker compose up --build
docker compose exec backend alembic upgrade head
# then in another terminal:
python scripts/job_watch.py --keywords security,cloud,SOC,governance --out out.json
python scripts/sync_jobs.py --source out.json --email you@example.com --password ...
# then open http://localhost:3000, log in, hit "Analyze All New Jobs"
```

If `docker compose up` fails on something, that's genuinely useful signal I couldn't
get any other way from here — send me the error and I'll fix it.
