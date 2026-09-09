"""
Best-effort extraction of a pay figure/range from raw job posting text. This is
regex heuristics, not parsing — postings phrase compensation wildly inconsistently,
so this catches common patterns and returns None rather than guessing when nothing
matches. Shown in the UI as "Pay not listed" when it returns None, never fabricated.
"""
import re

# Ordered roughly by how commonly postings phrase things. Each captures a currency
# symbol/code plus a number or range, optionally followed by a period (year/month/hour).
_PATTERNS = [
    # $80,000 - $120,000, $80k-$120k, $80,000 to $120,000
    r"(?:USD|US\$|\$|£|GBP|€|EUR|KES|Ksh\.?|KSh)\s?\d[\d,\.]*\s?[kK]?\s?(?:-|to|–|—)\s?(?:USD|US\$|\$|£|GBP|€|EUR|KES|Ksh\.?|KSh)?\s?\d[\d,\.]*\s?[kK]?(?:\s?/\s?(?:year|yr|annum|month|mo|hour|hr))?",
    # single figure: $120,000, $120k, KES 250,000
    r"(?:USD|US\$|\$|£|GBP|€|EUR|KES|Ksh\.?|KSh)\s?\d[\d,\.]*\s?[kK]?(?:\s?/\s?(?:year|yr|annum|month|mo|hour|hr))?",
    # "120,000 - 150,000 per year" with no leading symbol but a trailing period unit
    r"\d[\d,\.]*\s?[kK]?\s?(?:-|to|–|—)\s?\d[\d,\.]*\s?[kK]?\s?(?:USD|EUR|GBP|KES)?\s?(?:per\s?(?:year|annum|month|hour)|/\s?(?:year|yr|month|hour))",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]


def extract_pay(text: str) -> str | None:
    """Returns the first plausible pay mention found, trimmed, or None if nothing
    matched. Deliberately conservative — a missed real figure is better than a
    fabricated-looking false positive (e.g. matching a phone number or a year)."""
    if not text:
        return None
    for pattern in _COMPILED:
        match = pattern.search(text)
        if match:
            found = match.group(0).strip()
            # Guard against obviously-wrong matches: bare 4-digit numbers that are
            # almost certainly years (2020-2030), not pay
            if re.fullmatch(r"\d{4}", found) and 1990 <= int(found) <= 2035:
                continue
            return found
    return None
