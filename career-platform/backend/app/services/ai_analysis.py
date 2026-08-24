import json
import httpx

from app.config import settings

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-6"

GEMINI_MODEL = "gemini-3.6-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

PROMPT_TEMPLATE = """You are a career-intelligence analyst. Compare the RESUME against the JOB POSTING below.

Respond with ONLY raw JSON (no markdown fences, no preamble), matching exactly this schema:
{{
  "fit_score": <integer 0-100>,
  "summary": "<2-3 sentence plain-language verdict on fit>",
  "matched_signals": ["<short phrase>", ...],
  "gaps": ["<short phrase, specific and honest>", ...],
  "tailored_bullets": ["<rewritten resume bullet tailored to this posting, based on real content in the resume, not invented>", ...],
  "cover_letter_opening": "<2-3 sentence cover letter opening paragraph, specific to this posting>"
}}

Keep matched_signals and gaps to 3-5 items each. Keep tailored_bullets to 3-4 items. Do not invent experience not present in the resume.

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
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise AnalysisError(f"Could not parse model output as JSON: {e}\nRaw: {cleaned[:500]}")


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


async def _call_gemini(prompt: str) -> dict:
    if not settings.gemini_api_key:
        raise AnalysisError("GEMINI_API_KEY is not set in the environment.")

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{GEMINI_URL}?key={settings.gemini_api_key}",
            headers={"content-type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1500},
            },
        )

    if response.status_code != 200:
        raise AnalysisError(f"Gemini API error {response.status_code}: {response.text}")

    data = response.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise AnalysisError(f"Unexpected Gemini response shape: {json.dumps(data)[:500]}")
    return _clean_json(text)


async def analyze_fit(resume_text: str, job_text: str) -> dict:
    prompt = PROMPT_TEMPLATE.format(resume=resume_text, job=job_text)

    if settings.ai_provider == "gemini":
        return await _call_gemini(prompt)
    elif settings.ai_provider == "anthropic":
        return await _call_anthropic(prompt)
    else:
        raise AnalysisError(f"Unknown AI_PROVIDER '{settings.ai_provider}' — use 'anthropic' or 'gemini'.")