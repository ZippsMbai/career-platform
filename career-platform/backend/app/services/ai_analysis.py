import asyncio
import json
import httpx

from app.config import settings

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-6"

# Tried in order — if one is overloaded (503) or rate-limited (429), the next is used.
# Google renames/deprecates these periodically; if all of them start 404ing, that means
# the API error message itself will name the current replacement — swap it in here.
GEMINI_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT_TEMPLATE = """You are a career-intelligence analyst. Compare the RESUME against the JOB POSTING below.

Respond with ONLY raw JSON (no markdown fences, no preamble), matching exactly this schema:
{{
  "fit_score": 0,
  "summary": "2-3 sentence plain-language verdict on fit",
  "matched_signals": ["short phrase"],
  "gaps": ["short phrase"],
  "tailored_bullets": ["rewritten resume bullet"],
  "cover_letter_opening": "2-3 sentence cover letter opening paragraph"
}}

Keep matched_signals and gaps to 3-5 items each.
Keep tailored_bullets to 3-4 items.
Do not invent experience not present in the resume but you can give experience a more relevant framing if I seem to be capable of having it.



For tailored_bullets and cover_letter_opening specifically, write like a real person editing
their own resume, not like an AI generating marketing copy. Concretely:
- Avoid stock corporate-speak: "leverage," "delve," "spearheaded," "utilize," "robust,"
  "seamless," "furthermore," "in today's fast-paced environment."
- Avoid the rule-of-three list pattern ("X, Y, and Z") repeated across every sentence.
- Avoid uniform sentence lengths and parallel grammatical structures in every bullet — real
  writing varies.
- Prefer plain verbs a person would actually say out loud over inflated ones.
- The cover letter opening should sound like the start of an actual letter, not an ad.

RESUME:
\"\"\"{resume}\"\"\"

JOB POSTING:
\"\"\"{job}\"\"\"
"""


class AnalysisError(Exception):
    pass


def _clean_json(text: str) -> dict:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "", 1)
        cleaned = cleaned.replace("```", "")
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise AnalysisError(
            f"Could not parse model output as JSON: {e}\nRaw: {cleaned[:500]}"
        )


async def _call_anthropic(prompt: str) -> dict:
    if not settings.anthropic_api_key:
        raise AnalysisError("ANTHROPIC_API_KEY is not set in the environment.")

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}],
            },
        )

    if response.status_code != 200:
        raise AnalysisError(f"Anthropic API error {response.status_code}: {response.text}")

    data = response.json()
    text_block = next((b for b in data.get("content", []) if b.get("type") == "text"), None)
    if not text_block:
        raise AnalysisError("No text content returned from the model.")
    return _clean_json(text_block["text"])


async def _try_one_gemini_model(client: httpx.AsyncClient, model: str, prompt: str) -> dict:
    url = GEMINI_URL_TEMPLATE.format(model=model)
    response = await client.post(
        f"{url}?key={settings.gemini_api_key}",
        headers={"content-type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 3000},
        },
    )

    if response.status_code != 200:
        raise AnalysisError(f"Gemini API error {response.status_code} ({model}): {response.text}")

    data = response.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise AnalysisError(f"Unexpected Gemini response shape ({model}): {json.dumps(data)[:500]}")
    return _clean_json(text)


async def _call_gemini(prompt: str) -> dict:
    if not settings.gemini_api_key:
        raise AnalysisError("GEMINI_API_KEY is not set in the environment.")

    errors = []
    async with httpx.AsyncClient(timeout=60) as client:
        for i, model in enumerate(GEMINI_MODELS):
            try:
                return await _try_one_gemini_model(client, model, prompt)
            except AnalysisError as e:
                errors.append(str(e))
                if i < len(GEMINI_MODELS) - 1:
                    await asyncio.sleep(1)  # brief pause before trying the next model
                continue

    raise AnalysisError(
        "All Gemini models failed:\n" + "\n".join(errors)
    )


async def analyze_fit(resume_text: str, job_text: str) -> dict:
    prompt = PROMPT_TEMPLATE.format(resume=resume_text, job=job_text)

    if settings.ai_provider == "gemini":
        return await _call_gemini(prompt)
    elif settings.ai_provider == "anthropic":
        return await _call_anthropic(prompt)
    else:
        raise AnalysisError(
            f"Unknown AI_PROVIDER '{settings.ai_provider}' — use 'anthropic' or 'gemini'."
        )