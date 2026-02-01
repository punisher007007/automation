"""
search_jobs.py — Layer 3: Execution

Searches Google for job listings via SerpAPI using a query that targets
greenhouse.io and lever.co for entry/mid-level Data Analyst roles in the US.

Output: .tmp/jobs_raw.json
"""

import os
import json

import requests
from dotenv import load_dotenv

load_dotenv()

SERPAPI_KEY = os.environ["SERPAPI_KEY"]

# Search parameters — mirrors the user-configured query
SEARCH_PARAMS = {
    "q": (
        '(site:greenhouse.io OR site:lever.co) '
        '"Data Analyst" "United States" '
        '("entry" OR "junior" OR "associate" OR "mid") '
        '-senior -lead -manager -director'
    ),
    "location": "United States",
    "hl": "en",
    "gl": "us",
    "google_domain": "google.com",
    "api_key": SERPAPI_KEY,
}


def search() -> list[dict]:
    """
    Hits SerpAPI, extracts organic results, persists to .tmp/jobs_raw.json.
    Returns the list of raw job dicts.
    """
    resp = requests.get(
        "https://serpapi.com/search.json",
        params=SEARCH_PARAMS,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    results = []
    for r in data.get("organic_results", []):
        results.append({
            "title": r.get("title", ""),
            "link": r.get("link", ""),
            "snippet": r.get("snippet", ""),
            "displayed_link": r.get("displayed_link", ""),
        })

    os.makedirs(".tmp", exist_ok=True)
    with open(".tmp/jobs_raw.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"[search_jobs] {len(results)} results written to .tmp/jobs_raw.json")
    return results


if __name__ == "__main__":
    search()
