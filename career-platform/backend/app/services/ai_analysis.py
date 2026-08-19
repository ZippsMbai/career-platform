import json
import httpx

from app.config import settings

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"

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


async def analyze_fit(resume_text: str, job_text: str) -> dict:
    if not settings.anthropic_api_key:
        raise AnalysisError("ANTHROPIC_API_KEY is not set in the environment.")

    prompt = PROMPT_TEMPLATE.format(resume=resume_text, job=job_text)

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
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

    cleaned = text_block["text"].strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise AnalysisError(f"Could not parse model output as JSON: {e}\nRaw: {cleaned[:500]}")
