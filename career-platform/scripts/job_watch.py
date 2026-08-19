"""
job_watch.py — polls public, open job-board APIs and writes matching postings
to a local JSON file, ready for scripts/sync_jobs.py to import into the platform.

Sources used (all public, unauthenticated feeds/APIs — no scraping, no bot-bypass):
  - RemoteOK        https://remoteok.com/api
  - Arbeitnow       https://www.arbeitnow.com/api/job-board-api
  - We Work Remotely https://weworkremotely.com/remote-jobs.rss (official public RSS)
  - Remotive        https://remotive.com/api/remote-jobs (official public API)
  - Jobicy          https://jobicy.com/api/v2/remote-jobs (official public API)
  - ReliefWeb       https://api.reliefweb.int/v2/jobs (official UN/OCHA public API — humanitarian/NGO/UN roles)
  - Working Nomads  https://www.workingnomads.com/api/exposed_jobs/ (official public API, linked from their own site)
  - Greenhouse      https://boards-api.greenhouse.io/v1/boards/{company}/jobs
  - Lever           https://api.lever.co/v0/postings/{company}?mode=json
  - Ashby            https://api.ashbyhq.com/posting-api/job-board/{board}

Checked and NOT included:
  - Nomad List: primarily a cost-of-living/best-cities-for-remote-work tool, not really a
    job-listings aggregator at its core — no confirmed public jobs API found.
  - Hiring Cafe: aggregates the same underlying ATS listings but sits behind Cloudflare bot
    protection — every scraper for it needs an anti-detect browser + residential proxies.
  - Devex: only exposes an API for POSTING jobs (employer-side, needs a Devex-issued key),
    not for reading/searching listings — no read access available.
  - Impactpool: no official public API at all; every source found for it is a third-party
    scraper. Same reasoning as Hiring Cafe.
  If you find another board worth checking, send the URL — same standard applies: genuine
  open feed = added, needs bypassing protection or reverse-engineering an undocumented
  private endpoint = not added.

RemoteOK and Arbeitnow list postings across many companies with no setup needed.
Greenhouse/Lever/Ashby only expose one company's board at a time, so you need to
tell this script which companies to watch — add their board slugs to
COMPANY_BOARDS below (find a company's slug from its careers page URL, e.g.
boards.greenhouse.io/<slug> or jobs.lever.co/<slug>).

USAGE
    python job_watch.py --keywords security,cloud,SOC --out job_watch_output.json

Then feed the output into the platform:
    python sync_jobs.py --source job_watch_output.json --email you@example.com --password ...
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

# Add company board slugs here as you find roles worth tracking regularly.
# Example: {"greenhouse": ["some-company"], "lever": ["another-co"], "ashby": ["a-startup"]}
COMPANY_BOARDS = {
    "greenhouse": [],
    "lever": [],
    "ashby": [],
}

EMEA_AFRICA_HINTS = [
    "remote", "emea", "africa", "europe", "worldwide", "anywhere",
    "kenya", "nairobi", "uk", "germany", "netherlands", "south africa",
]

HEADERS = {"User-Agent": "job-watch-script/0.1 (personal job search tool)"}


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def matches_keywords(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    lower = text.lower()
    return any(k.lower() in lower for k in keywords)


def looks_emea_africa(text: str) -> bool:
    lower = text.lower()
    return any(hint in lower for hint in EMEA_AFRICA_HINTS)


def fetch_remoteok(keywords: list[str]) -> list[dict]:
    try:
        resp = httpx.get("https://remoteok.com/api", headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[remoteok] fetch failed: {e}", file=sys.stderr)
        return []

    results = []
    for item in data:
        if not isinstance(item, dict) or "position" not in item:
            continue  # first element is usually a metadata blob, skip it
        title = item.get("position", "")
        company = item.get("company", "")
        description = strip_html(item.get("description", ""))
        blob = f"{title} {description}"
        if not matches_keywords(blob, keywords):
            continue
        results.append({
            "title": title,
            "company": company,
            "url": item.get("url"),
            "description": description,
        })
    return results


def fetch_arbeitnow(keywords: list[str]) -> list[dict]:
    try:
        resp = httpx.get("https://www.arbeitnow.com/api/job-board-api", headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as e:
        print(f"[arbeitnow] fetch failed: {e}", file=sys.stderr)
        return []

    results = []
    for item in data:
        title = item.get("title", "")
        description = strip_html(item.get("description", ""))
        blob = f"{title} {description} {' '.join(item.get('tags', []))}"
        if not matches_keywords(blob, keywords):
            continue
        if not (item.get("remote") or looks_emea_africa(blob)):
            continue
        results.append({
            "title": title,
            "company": item.get("company_name"),
            "url": item.get("url"),
            "description": description,
        })
    return results


def fetch_weworkremotely(keywords: list[str]) -> list[dict]:
    try:
        resp = httpx.get("https://weworkremotely.com/remote-jobs.rss", headers=HEADERS, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except Exception as e:
        print(f"[weworkremotely] fetch failed: {e}", file=sys.stderr)
        return []

    results = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        description = strip_html(item.findtext("description") or "")
        link = (item.findtext("link") or "").strip()
        blob = f"{title} {description}"
        if not matches_keywords(blob, keywords):
            continue
        # every WWR listing is remote by definition, no EMEA/Africa filter needed
        company = title.split(":")[0].strip() if ":" in title else None
        results.append({"title": title, "company": company, "url": link, "description": description})
    return results


def fetch_remotive(keywords: list[str]) -> list[dict]:
    try:
        search = keywords[0] if keywords else ""
        resp = httpx.get("https://remotive.com/api/remote-jobs", params={"search": search}, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("jobs", [])
    except Exception as e:
        print(f"[remotive] fetch failed: {e}", file=sys.stderr)
        return []

    results = []
    for item in data:
        title = item.get("title", "")
        description = strip_html(item.get("description", ""))
        blob = f"{title} {description}"
        if not matches_keywords(blob, keywords):
            continue
        results.append({
            "title": title,
            "company": item.get("company_name"),
            "url": item.get("url"),
            "description": description,
        })
    return results


def fetch_jobicy(keywords: list[str]) -> list[dict]:
    try:
        tag = keywords[0] if keywords else ""
        resp = httpx.get("https://jobicy.com/api/v2/remote-jobs", params={"count": 50, "tag": tag}, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("jobs", [])
    except Exception as e:
        print(f"[jobicy] fetch failed: {e}", file=sys.stderr)
        return []

    results = []
    for item in data:
        title = item.get("jobTitle", "")
        description = strip_html(item.get("jobDescription", ""))
        blob = f"{title} {description}"
        if not matches_keywords(blob, keywords):
            continue
        results.append({
            "title": title,
            "company": item.get("companyName"),
            "url": item.get("url"),
            "description": description,
        })
    return results


def fetch_reliefweb(keywords: list[str]) -> list[dict]:
    """ReliefWeb (UN OCHA) public Jobs API — no auth, appname param is just for their usage stats."""
    try:
        query = " OR ".join(keywords) if keywords else ""
        params = {
            "appname": "career-intelligence-platform",
            "profile": "full",
            "sort[]": "date:desc",
        }
        if query:
            params["query[value]"] = query
        resp = httpx.get("https://api.reliefweb.int/v2/jobs", params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as e:
        print(f"[reliefweb] fetch failed: {e}", file=sys.stderr)
        return []

    results = []
    for item in data:
        fields = item.get("fields", {})
        title = fields.get("title", "")
        description = strip_html(fields.get("body", ""))
        sources = fields.get("source", [])
        company = sources[0].get("name") if sources else None
        url_alias = fields.get("url_alias") or fields.get("url")
        blob = f"{title} {description}"
        if not matches_keywords(blob, keywords):
            continue
        results.append({"title": title, "company": company, "url": url_alias, "description": description})
    return results


def fetch_workingnomads(keywords: list[str]) -> list[dict]:
    """Working Nomads exposes this endpoint openly from their own site footer as "API" — public, no auth."""
    try:
        resp = httpx.get("https://www.workingnomads.com/api/exposed_jobs/", headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[workingnomads] fetch failed: {e}", file=sys.stderr)
        return []

    results = []
    for item in data:
        title = item.get("title", "")
        description = strip_html(item.get("description", ""))
        tags = item.get("tags", "")
        blob = f"{title} {description} {tags}"
        if not matches_keywords(blob, keywords):
            continue
        results.append({
            "title": title,
            "company": item.get("company_name"),
            "url": item.get("url"),
            "description": description,
        })
    return results


def fetch_greenhouse(company: str, keywords: list[str]) -> list[dict]:
    try:
        resp = httpx.get(f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true", headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("jobs", [])
    except Exception as e:
        print(f"[greenhouse:{company}] fetch failed: {e}", file=sys.stderr)
        return []

    results = []
    for item in data:
        title = item.get("title", "")
        description = strip_html(item.get("content", ""))
        location = item.get("location", {}).get("name", "")
        blob = f"{title} {description} {location}"
        if not matches_keywords(blob, keywords):
            continue
        if not looks_emea_africa(blob):
            continue
        results.append({
            "title": title,
            "company": company,
            "url": item.get("absolute_url"),
            "description": description,
        })
    return results


def fetch_lever(company: str, keywords: list[str]) -> list[dict]:
    try:
        resp = httpx.get(f"https://api.lever.co/v0/postings/{company}?mode=json", headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[lever:{company}] fetch failed: {e}", file=sys.stderr)
        return []

    results = []
    for item in data:
        title = item.get("text", "")
        description = strip_html(item.get("descriptionPlain") or item.get("description") or "")
        location = (item.get("categories", {}) or {}).get("location", "")
        blob = f"{title} {description} {location}"
        if not matches_keywords(blob, keywords):
            continue
        if not looks_emea_africa(blob):
            continue
        results.append({
            "title": title,
            "company": company,
            "url": item.get("hostedUrl"),
            "description": description,
        })
    return results


def fetch_ashby(board: str, keywords: list[str]) -> list[dict]:
    try:
        resp = httpx.get(f"https://api.ashbyhq.com/posting-api/job-board/{board}", headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("jobs", [])
    except Exception as e:
        print(f"[ashby:{board}] fetch failed: {e}", file=sys.stderr)
        return []

    results = []
    for item in data:
        title = item.get("title", "")
        description = strip_html(item.get("descriptionPlain") or "")
        location = item.get("location", "")
        blob = f"{title} {description} {location}"
        if not matches_keywords(blob, keywords):
            continue
        if not looks_emea_africa(blob):
            continue
        results.append({
            "title": title,
            "company": board,
            "url": item.get("jobUrl") or item.get("applyUrl"),
            "description": description,
        })
    return results


def main():
    parser = argparse.ArgumentParser(description="Poll public job-board APIs for matching postings")
    parser.add_argument("--keywords", default="security,cloud,SOC,SIEM,governance,compliance",
                         help="Comma-separated keywords to match against title/description")
    parser.add_argument("--out", default="job_watch_output.json")
    args = parser.parse_args()

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    all_results = []
    all_results += fetch_remoteok(keywords)
    all_results += fetch_arbeitnow(keywords)
    all_results += fetch_weworkremotely(keywords)
    all_results += fetch_remotive(keywords)
    all_results += fetch_jobicy(keywords)
    all_results += fetch_reliefweb(keywords)
    all_results += fetch_workingnomads(keywords)
    for company in COMPANY_BOARDS["greenhouse"]:
        all_results += fetch_greenhouse(company, keywords)
    for company in COMPANY_BOARDS["lever"]:
        all_results += fetch_lever(company, keywords)
    for board in COMPANY_BOARDS["ashby"]:
        all_results += fetch_ashby(board, keywords)

    # dedupe by url within this run
    seen = set()
    deduped = []
    for job in all_results:
        u = job.get("url")
        if u and u in seen:
            continue
        if u:
            seen.add(u)
        deduped.append(job)

    with open(args.out, "w") as f:
        json.dump(deduped, f, indent=2)

    print(f"Fetched {len(deduped)} matching postings ({datetime.now(timezone.utc).isoformat()}) -> {args.out}")
    if not any(COMPANY_BOARDS.values()):
        print("Note: COMPANY_BOARDS is empty — only RemoteOK/Arbeitnow were polled. "
              "Add company slugs to COMPANY_BOARDS in this file to also watch specific Greenhouse/Lever/Ashby boards.")


if __name__ == "__main__":
    main()
