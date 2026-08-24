import json
import httpx

from app.config import settings

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-6"

# Update this if Google returns a different available model
GEMINI_MODEL = "gemini-2.5-flash"

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

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
Do not invent experience not present in the resume.

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