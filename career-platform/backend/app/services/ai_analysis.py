import asyncio
import json
import httpx

TRANSPORT_ERRORS = (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)

from app.config import settings

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-6"

GEMINI_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

MAX_OUTPUT_TOKENS = 4500
# Batched calls return N results at once, so they need proportionally more room.
MAX_OUTPUT_TOKENS_BATCH = 4500 * 5

TIMEOUT_SECONDS = 45

PROMPT_TEMPLATE = """You are a career-intelligence analyst. Compare the PRIMARY RESUME against the JOB POSTING below, using the CANDIDATE'S FULL BACKGROUND (all their saved resumes combined) as additional context for what they've actually done.

Respond with ONLY raw JSON (no markdown fences, no preamble), matching exactly this schema:
{{
  "fit_score": 0,
  "summary": "2-3 sentence plain-language verdict on fit",
  "matched_signals": ["short phrase"],
  "gaps": ["short phrase"],
  "tailored_bullets": ["rewritten resume bullet"],
  "cover_letter_opening": "2-3 sentence cover letter opening paragraph",
  "cover_letter_full": "complete cover letter, 3-4 paragraphs, ready to send",
  "tailored_resume": "a complete tailored resume draft in plain text, reordered/reworded to foreground what matters for this posting"
}}

Keep matched_signals and gaps to 3-5 items each.
Keep tailored_bullets to 3-4 items.
Do not invent experience not present in the candidate's full background (primary resume plus
the other resumes provided) — but you may reasonably infer TRANSFERABLE or ADJACENT fit where
skills are close but not an exact match (e.g. someone with SIEM/detection-engineering experience
has real, honest potential for a "threat hunting" role even without that literal job title
before). When you do this, say so plainly in matched_signals or the resume text itself
("adjacent experience in X suggests strong potential for Y") rather than presenting inferred
fit as identical to direct experience — the gaps list should still name what's genuinely not
there.

For tailored_resume specifically: build it from the CANDIDATE'S FULL BACKGROUND (not only the
primary resume) — pull in relevant experience from any of their other resumes if it's a better
fit for this posting than what's in the primary one. Structure it as a normal resume (contact
line placeholder, summary, experience, skills, education) using plain text with line breaks,
not JSON or markdown formatting within the string itself.

For tailored_bullets, cover_letter_opening, and cover_letter_full specifically, write like a
real person editing their own resume, not like an AI generating marketing copy. Concretely:
- Avoid stock corporate-speak: "leverage," "delve," "spearheaded," "utilize," "robust,"
  "seamless," "furthermore," "in today's fast-paced environment."
- Avoid the rule-of-three list pattern ("X, Y, and Z") repeated across every sentence.
- Avoid uniform sentence lengths and parallel grammatical structures in every bullet — real
  writing varies.
- Prefer plain verbs a person would actually say out loud over inflated ones.
- The cover letter should sound like an actual letter a person wrote, not an ad.

PRIMARY RESUME (the one selected for this analysis):
\"\"\"{primary_resume}\"\"\"

CANDIDATE'S FULL BACKGROUND (all saved resumes, for pulling in relevant experience the primary one might not cover):
\"\"\"{combined_resumes}\"\"\"

JOB POSTING:
\"\"\"{job}\"\"\"
"""

BATCH_PROMPT_TEMPLATE = """You are a career-intelligence analyst. You will be given the CANDIDATE'S PRIMARY RESUME, their FULL BACKGROUND (all saved resumes combined), and SEVERAL job postings, each tagged with a job_id.

For EACH job posting, independently compare it against the resume material and produce one result object. Respond with ONLY a raw JSON array (no markdown fences, no preamble) — one object per job, in the same order given, each matching exactly this schema:
{{
  "job_id": "the exact job_id given for this posting",
  "fit_score": 0,
  "summary": "2-3 sentence plain-language verdict on fit",
  "matched_signals": ["short phrase"],
  "gaps": ["short phrase"],
  "tailored_bullets": ["rewritten resume bullet"],
  "cover_letter_opening": "2-3 sentence cover letter opening paragraph",
  "cover_letter_full": "complete cover letter, 3-4 paragraphs, ready to send",
  "tailored_resume": "a complete tailored resume draft in plain text, reordered/reworded to foreground what matters for this posting"
}}

Keep matched_signals and gaps to 3-5 items each. Keep tailored_bullets to 3-4 items.
Do not invent experience not present in the candidate's full background — but you may reasonably
infer TRANSFERABLE or ADJACENT fit where skills are close but not an exact match, saying so
plainly rather than presenting inferred fit as identical to direct experience.
For tailored_resume: build it from the FULL BACKGROUND, not only the primary resume, structured
as a normal resume in plain text with line breaks.
For tailored_bullets, cover_letter_opening, and cover_letter_full: write like a real person
editing their own resume — avoid corporate-speak ("leverage," "spearheaded," "utilize," "robust,"
"seamless"), avoid rule-of-three list patterns, avoid uniform sentence lengths, prefer plain verbs.

PRIMARY RESUME:
\"\"\"{primary_resume}\"\"\"

CANDIDATE'S FULL BACKGROUND:
\"\"\"{combined_resumes}\"\"\"

JOB POSTINGS:
{jobs_block}
"""


class AnalysisError(Exception):
    pass


def _extract_json(text: str):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "", 1)
        cleaned = cleaned.replace("```", "")
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise AnalysisError(f"Could not parse model output as JSON: {e}\nRaw: {cleaned[:500]}")


async def _call_anthropic(prompt: str, max_tokens: int) -> str:
    if not settings.anthropic_api_key:
        raise AnalysisError("ANTHROPIC_API_KEY is not set in the environment.")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={"model": ANTHROPIC_MODEL, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]},
            )
    except TRANSPORT_ERRORS as e:
        raise AnalysisError(f"Anthropic request timed out or failed at the network level: {e}")
    if response.status_code != 200:
        raise AnalysisError(f"Anthropic API error {response.status_code}: {response.text}")
    data = response.json()
    text_block = next((b for b in data.get("content", []) if b.get("type") == "text"), None)
    if not text_block:
        raise AnalysisError("No text content returned from the model.")
    return text_block["text"]


async def _try_one_gemini_model(client: httpx.AsyncClient, model: str, prompt: str, max_tokens: int) -> str:
    url = GEMINI_URL_TEMPLATE.format(model=model)
    try:
        response = await client.post(
            f"{url}?key={settings.gemini_api_key}",
            headers={"content-type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.4, "maxOutputTokens": max_tokens}},
        )
    except TRANSPORT_ERRORS as e:
        raise AnalysisError(f"Gemini request timed out or failed at the network level ({model}): {e}")
    if response.status_code != 200:
        raise AnalysisError(f"Gemini API error {response.status_code} ({model}): {response.text}")
    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise AnalysisError(f"Unexpected Gemini response shape ({model}): {json.dumps(data)[:500]}")


async def _call_groq(prompt: str, max_tokens: int) -> str:
    if not settings.groq_api_key:
        raise AnalysisError("GROQ_API_KEY is not set — no fallback provider available.")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {settings.groq_api_key}", "content-type": "application/json"},
                json={"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.4, "max_tokens": max_tokens},
            )
    except TRANSPORT_ERRORS as e:
        raise AnalysisError(f"Groq request timed out or failed at the network level: {e}")
    if response.status_code != 200:
        raise AnalysisError(f"Groq API error {response.status_code}: {response.text}")
    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise AnalysisError(f"Unexpected Groq response shape: {json.dumps(data)[:500]}")

async def _call_gemini(prompt: str, max_tokens: int) -> str:
    if not settings.gemini_api_key:
        raise AnalysisError("GEMINI_API_KEY is not set in the environment.")
    errors = []
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        for i, model in enumerate(GEMINI_MODELS):
            try:
                return await _try_one_gemini_model(client, model, prompt, max_tokens)
            except AnalysisError as e:
                errors.append(str(e))
                if i < len(GEMINI_MODELS) - 1:
                    await asyncio.sleep(1)
                continue

    if settings.groq_api_key:
        try:
            return await _call_groq(prompt, max_tokens)
        except AnalysisError as e:
            errors.append(f"Groq fallback also failed: {e}")

    raise AnalysisError("All providers failed:\n" + "\n".join(errors))


async def _get_completion(prompt: str, max_tokens: int) -> str:
    if settings.ai_provider == "gemini":
        return await _call_gemini(prompt, max_tokens)
    elif settings.ai_provider == "anthropic":
        return await _call_anthropic(prompt, max_tokens)
    elif settings.ai_provider == "groq":
        return await _call_groq(prompt, max_tokens)
    else:
        raise AnalysisError(f"Unknown AI_PROVIDER '{settings.ai_provider}' — use 'anthropic', 'gemini', or 'groq'.")


async def analyze_fit(primary_resume_text: str, combined_resumes_text: str, job_text: str) -> dict:
    """Single-job analysis — used by the one-off 'Run Analysis' feature."""
    prompt = PROMPT_TEMPLATE.format(primary_resume=primary_resume_text, combined_resumes=combined_resumes_text, job=job_text)
    text = await _get_completion(prompt, MAX_OUTPUT_TOKENS)
    return _extract_json(text)


async def analyze_fit_batch(primary_resume_text: str, combined_resumes_text: str, jobs: list[dict]) -> dict:
    """Analyzes multiple jobs in ONE prompt/API call instead of one call per job.
    `jobs` is a list of {"id": str, "text": str}. Returns {job_id: result_dict}.
    Cuts total API requests roughly N-fold vs one-call-per-job, which is what
    actually matters against daily rate limits and per-request timeouts."""
    jobs_block = "\n\n".join(
        f'--- job_id: {j["id"]} ---\n"""{j["text"]}"""' for j in jobs
    )
    prompt = BATCH_PROMPT_TEMPLATE.format(
        primary_resume=primary_resume_text, combined_resumes=combined_resumes_text, jobs_block=jobs_block
    )
    max_tokens = min(MAX_OUTPUT_TOKENS_BATCH, MAX_OUTPUT_TOKENS * max(len(jobs), 1))
    text = await _get_completion(prompt, max_tokens)
    parsed = _extract_json(text)

    if not isinstance(parsed, list):
        raise AnalysisError(f"Expected a JSON array from batch call, got: {type(parsed).__name__}")

    results_by_job_id = {}
    for item in parsed:
        job_id = item.get("job_id")
        if job_id:
            results_by_job_id[job_id] = item
    return results_by_job_id