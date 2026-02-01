"""
run_pipeline.py — Main entry point

Orchestrates the full job-automation flow:
  1. Search Google Jobs via SerpAPI
  2. Scrape each listing for full description + posted date
  3. Drop anything posted > 1 week ago or with an unusable description
  4. Tailor the base resume via Grok for each surviving job
  5. Package each as an ATS-friendly .docx and upload to Google Drive
  6. Log every job + resume link into the master Google Sheet

Run from the project root:
    python execution/run_pipeline.py
"""

import os
import sys
import re
import json

# Allow importing sibling modules regardless of where the script is invoked
sys.path.insert(0, os.path.dirname(__file__))

from search_jobs import search                                          # noqa: E402
from scrape_job import scrape, is_within_one_week                       # noqa: E402
from tailor_resume import tailor                                        # noqa: E402
from google_api import (                                                # noqa: E402
    create_resume_docx,
    upload_to_drive,
    get_or_create_sheet,
    append_to_sheet,
)


def sanitize(name: str) -> str:
    """Collapse non-alphanumeric chars into underscores for safe file names."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name).strip("_")[:40]


def main():
    print("=" * 60)
    print("  JOB AUTOMATION PIPELINE")
    print("=" * 60)

    # ── 1. Search ───────────────────────────────────────────────────
    print("\n[1/4] Searching Google for jobs…")
    raw_jobs = search()
    print(f"       → {len(raw_jobs)} results returned")

    if not raw_jobs:
        print("       No results. Verify your SerpAPI key or query.")
        return

    # ── 2. Scrape + filter ──────────────────────────────────────────
    print("\n[2/4] Scraping job pages and filtering…")
    jobs = []

    for i, job in enumerate(raw_jobs):
        short_title = job["title"][:55]
        print(f"       [{i+1}/{len(raw_jobs)}] {short_title}…")

        # Scrape the page
        try:
            scraped = scrape(job["link"])
        except Exception as e:
            print(f"              ✗ scrape failed: {e}")
            continue

        # Need a real description to tailor against
        if len(scraped.get("description", "")) < 100:
            print("              ✗ skipped — description too short")
            continue

        # Date filter: only jobs posted < 1 week ago
        if not is_within_one_week(scraped.get("posted_date", "")):
            print(f"              ✗ skipped — posted {scraped.get('posted_date', 'unknown')}")
            continue

        # Fill any blanks from the original search result
        if not scraped["title"]:
            scraped["title"] = job.get("title", "Unknown Role")
        if not scraped["company"]:
            # Best-effort: first segment of the displayed URL
            scraped["company"] = job.get("displayed_link", "").split(".")[0].title()

        jobs.append(scraped)
        print(f"              ✓ included (posted: {scraped.get('posted_date', 'N/A')})")

    print(f"\n       → {len(jobs)} jobs passed all filters")

    if not jobs:
        print("       Nothing to process. Exiting.")
        return

    # Persist filtered jobs for debugging / inspection
    os.makedirs(".tmp", exist_ok=True)
    with open(".tmp/jobs_filtered.json", "w") as f:
        json.dump(jobs, f, indent=2)

    # ── 3. Google Sheet setup ───────────────────────────────────────
    print("\n[3/4] Connecting to Google Sheets…")
    sheet_id, sheet_link = get_or_create_sheet()
    print(f"       → {sheet_link}")

    # ── 4. Tailor + upload + log ────────────────────────────────────
    print("\n[4/4] Tailoring resumes and uploading…")

    for i, job in enumerate(jobs):
        title = job["title"][:45]
        company = job["company"][:25]
        print(f"\n       [{i+1}/{len(jobs)}] {title} @ {company}")

        try:
            # a) Tailor the resume with Grok
            print("              → tailoring with Grok…")
            tailored = tailor(job["description"])

            # b) Build the ATS-friendly .docx
            safe_name = f"Resume_{sanitize(company)}_{sanitize(title)}.docx"
            docx_path = os.path.join(".tmp", safe_name)
            print("              → creating DOCX…")
            create_resume_docx(tailored, docx_path)

            # c) Upload to Google Drive
            print("              → uploading to Drive…")
            resume_link = upload_to_drive(docx_path, safe_name)
            print(f"              → {resume_link}")

            # d) Append a row to the master sheet with clickable links
            row = [
                job.get("title", ""),
                job.get("company", ""),
                job.get("location", ""),
                job.get("posted_date", "N/A"),
                f'=HYPERLINK("{job["url"]}", "View Job")',
                f'=HYPERLINK("{resume_link}", "View Resume")',
            ]
            append_to_sheet(sheet_id, row)
            print("              ✓ sheet updated")

        except Exception as e:
            print(f"              ✗ error: {e}")
            continue

    # ── Done ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  DONE")
    print(f"  Master Sheet → {sheet_link}")
    print("=" * 60)


if __name__ == "__main__":
    main()
