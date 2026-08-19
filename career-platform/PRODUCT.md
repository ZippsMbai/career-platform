# Career Intelligence Platform — Product Requirements (V1)

## What this is

A personal tool that does one thing well: takes a resume and a job posting, tells you honestly how well they fit, and produces the tailored materials to apply — resume bullets and a cover letter opening. Everything else (job discovery, application tracking, interview prep) exists to feed that core loop or act on its output.

This is not the venture-scale platform from the original plan. It's the smallest version that is genuinely useful for your own job search and defensible as a portfolio piece — built to be extended once it's proven, not built to impress on day one.

## Who it's for

- Primary: you, actively job-hunting for UN/remote security-governance and AI/dev roles.
- Secondary (portfolio value): anyone evaluating your engineering judgment — the thing they'll notice is a small system that actually works end to end, not a folder of half-built services.

## Core loop (validated by the prototype)

1. A job posting comes in (pasted, or later pulled from your existing job-watch feed).
2. The system scores fit against your resume, honestly — flagging real gaps, not padding matches.
3. It produces tailored resume bullets and a cover letter opening, grounded only in what's actually in your resume.
4. You review, edit, and mark the application as applied / skipped.
5. Applied jobs are tracked so you're not managing this in a spreadsheet.

## V1 scope (in)

- **Resume storage**: one resume per user, stored as structured text (not just a file blob) so it can be reasoned about.
- **Job intake**: paste a posting by URL or text. (Pulling automatically from your existing Greenhouse/Lever/Ashby job-watch script is a natural V1.5, not required for V1.)
- **Fit analysis**: the scoring/gaps/tailoring engine from the prototype, now persisted instead of ephemeral.
- **Application tracking**: status per job (saved / applied / interviewing / rejected / offer), with the tailored materials attached to each record.
- **Single-user auth**: enough to protect the deployment, not a multi-tenant system.
- **Basic dashboard**: list of tracked applications, fit scores, current status.

## V1 scope (explicitly out — revisit later, not now)

- Multi-provider AI switching (OpenAI/Gemini/Ollama) — one provider (Claude) is enough until there's a real reason to swap.
- Browser automation (Playwright) for auto-submitting applications — high risk, low trust, do this manually until the rest is solid.
- Full MCP server exposing tools/resources/prompts — worth building once there's a stable core to expose, not before.
- Celery/Redis background workers — V1 traffic is one user; synchronous requests are fine.
- Multi-tenant design, plugin architecture, ADRs-as-ceremony — these are startup-scale concerns, not portfolio-project concerns yet.

## Success criteria for V1

- You can paste a real posting and get output you'd actually send, in under 30 seconds, more often than not.
- Fit scores and flagged gaps hold up against your own judgment — if the tool is consistently wrong, the loop isn't ready to build on.
- You track at least a handful of real applications through it instead of falling back to a spreadsheet.

## Open questions to settle before/while building

- Does job intake start manual (paste) or should the job-watch script feed it directly from day one?
- Where does this run — local only, or deployed somewhere you can reach from a phone?
- Single resume, or do you want variant resumes per role type (security vs. dev) tracked separately?
