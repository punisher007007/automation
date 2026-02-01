"""
scrape_job.py — Layer 3: Execution

Scrapes a single job posting (greenhouse.io or lever.co) for the full
job description and posted date.

Input:  Job URL (CLI arg or called programmatically)
Output: dict { title, company, description, posted_date, url }
"""

import re
import sys
import json

import requests
from bs4 import BeautifulSoup

# Rotate user-agents to reduce chance of trivial blocks
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Safari/605.1.15",
]


def _headers(idx=0):
    return {"User-Agent": USER_AGENTS[idx % len(USER_AGENTS)]}


def scrape(url: str) -> dict:
    """
    Fetches the job page and extracts title, company, description, posted date.
    Uses site-specific selectors for greenhouse.io / lever.co, then a generic
    fallback (longest text block) if those miss.
    """
    resp = requests.get(url, headers=_headers(), timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    title, company, description, posted_date = "", "", "", ""

    # ── Greenhouse.io ─────────────────────────────────────────
    if "greenhouse.io" in url:
        # Title
        t = soup.select_one("h1.page-title, h1")
        title = t.get_text(strip=True) if t else ""

        # Company — subtitle, dedicated element, or meta fallback
        c = soup.select_one(".company-name, .subtitle, [class*='company']")
        if c:
            company = c.get_text(strip=True)
        else:
            meta = soup.select_one('meta[name="description"]')
            if meta:
                company = meta.get("content", "").split("–")[0].strip()

        # Description — try known containers in order
        for sel in [
            "#desc_container",
            ".public-job-description",
            ".description--text",
            "[class*='job-description']",
            "[class*='description']",
        ]:
            d = soup.select_one(sel)
            if d and len(d.get_text(strip=True)) > 100:
                description = d.get_text(separator="\n", strip=True)
                break

        # Posted date
        dt = soup.select_one(".posted-date, [class*='date'], [class*='posted']")
        posted_date = dt.get_text(strip=True) if dt else ""

    # ── Lever.co ──────────────────────────────────────────────
    elif "lever.co" in url:
        t = soup.select_one("h1, .title")
        title = t.get_text(strip=True) if t else ""

        c = soup.select_one(".company-name, [class*='company']")
        company = c.get_text(strip=True) if c else ""

        for sel in [
            ".description--text",
            "[data-test-id='job-description']",
            "[class*='description']",
        ]:
            d = soup.select_one(sel)
            if d and len(d.get_text(strip=True)) > 100:
                description = d.get_text(separator="\n", strip=True)
                break

        dt = soup.select_one("[class*='date'], [class*='posted'], .time")
        posted_date = dt.get_text(strip=True) if dt else ""

    # ── Generic fallback — longest text block on the page ─────
    if len(description) < 100:
        blocks = [
            el.get_text(separator="\n", strip=True)
            for el in soup.find_all(["div", "section", "article"])
            if 200 < len(el.get_text(strip=True)) < 50000
        ]
        if blocks:
            description = max(blocks, key=len)

    return {
        "title": title,
        "company": company,
        "description": description,
        "posted_date": posted_date,
        "url": url,
    }


def is_within_one_week(posted_date_str: str) -> bool:
    """
    Parses relative date strings like '3 days ago', '1 week ago'.
    Returns True if the job was posted less than 7 days ago.

    If the string can't be parsed or is empty, returns True —
    better to over-include than silently drop jobs.
    """
    if not posted_date_str:
        return True  # can't determine → include

    text = posted_date_str.lower().strip()
    nums = re.findall(r"\d+", text)
    num = int(nums[0]) if nums else 1

    if any(w in text for w in ("hour", "minute", "second", "just now", "today")):
        return True
    if "day" in text:
        return num < 7
    if "week" in text:
        return num < 2  # "1 week ago" is borderline — include it
    if "month" in text or "year" in text:
        return False

    return True  # unknown format → include


if __name__ == "__main__":
    if len(sys.argv) > 1:
        result = scrape(sys.argv[1])
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python scrape_job.py <url>")
