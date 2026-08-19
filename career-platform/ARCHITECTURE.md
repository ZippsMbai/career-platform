# Career Intelligence Platform — Architecture (V1)

Companion to PRODUCT.md. Every decision here is justified by that scope — nothing is included because it "should" be part of a real system.

## Stack

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI (Python 3.12+) | Matches your existing Python/security tooling background; async-friendly if job intake grows. |
| Data | PostgreSQL | Structured application/resume records need real relations, not a document store. |
| ORM/migrations | SQLAlchemy 2.0 + Alembic | Standard, well-documented, keeps schema changes reviewable. |
| Auth | Single-user, session or JWT via FastAPI | No multi-tenant complexity needed for V1. |
| Frontend | Next.js (App Router) + Tailwind | One dashboard, a form, a list — doesn't need much, but Next gives room to grow. |
| AI | Anthropic API only (Claude Sonnet) | The prototype already validated this; multi-provider is speculative until there's a concrete reason. |
| Deployment | Docker Compose, single host (Fly.io / Railway / a VPS) | No Kubernetes, no multi-region — one user, one database. |

Explicitly deferred: Redis/Celery, Playwright, MCP server, multi-provider AI abstraction. Each gets added when a V1 limitation actually forces it — see Roadmap below.

## Data model (sketch)

```
users
  id, email, password_hash, created_at

resumes
  id, user_id, label ("security" / "dev" / default), raw_text,
  parsed_json (skills, experience, education — structured on save), updated_at

jobs
  id, user_id, source_url, raw_text, title, company, created_at

analyses
  id, job_id, resume_id, fit_score, summary,
  matched_signals (json), gaps (json),
  tailored_bullets (json), cover_letter_opening, created_at

applications
  id, job_id, analysis_id, status (saved/applied/interviewing/rejected/offer),
  applied_at, notes, updated_at
```

`analyses` is intentionally immutable history — re-running analysis on the same job/resume pair creates a new row, so you can see how tailoring changed if you edit your resume later.

## API surface (V1)

```
POST   /resumes                 upload/update a resume, get parsed_json back
GET    /resumes

POST   /jobs                    add a posting (url or raw text)
GET    /jobs

POST   /analyses                { job_id, resume_id } -> fit_score, gaps, tailored_bullets, cover_letter_opening
GET    /analyses/{id}

POST   /applications            { job_id, analysis_id, status }
PATCH  /applications/{id}       update status/notes
GET    /applications            dashboard list, filterable by status
```

The `/analyses` endpoint is the prototype's logic, moved server-side and made persistent — same prompt/schema, now backed by a database instead of a browser session.

## Phased roadmap

**V1 (this doc's scope)**: manual job paste → analyze → track. Single Claude provider. Local or single-host deploy.

**V1.5**: wire your existing job-watch script in as an automatic job source instead of manual paste — this is the highest-leverage next step since the infrastructure already exists.

**V2, only if V1 earns it**:
- Multi-resume support becomes a real workflow (not just a schema field) if you're regularly tailoring across role types.
- MCP server exposing `analyze_job`, `list_applications`, `update_status` as tools — makes sense once the core is stable enough to be worth exposing to other agents/tools.
- Background jobs (Celery/ARQ) only if job intake volume or analysis latency actually becomes a problem.

**V3, speculative**: Playwright-based application automation, multi-provider AI, multi-tenant if this ever needs to serve more than you. None of this is scoped or estimated — revisit only if V1/V1.5 prove the core loop is worth scaling.

## What's next

Once you confirm this scope, the next step is scaffolding the actual V1 repo: FastAPI app skeleton, the four tables above via Alembic, the `/analyses` endpoint reusing the prototype's prompt, and a minimal Next.js dashboard. I can start that here in chat, or set it up properly in Claude Code if you want git history and a real dev loop from the start.
