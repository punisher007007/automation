"""
run_pipeline.py — Main entry point

Orchestrates the full job-automation flow:
  1. Search Google Jobs via SerpAPI
  2. Scrape each listing for full description + posted date
  3. Drop anything posted > 1 week ago or with an unusable description
  4. Tailor the base resume via OpenRouter for each surviving job
  5. Package each as an ATS-friendly .docx, save to .tmp/
  6. Write a summary CSV to .tmp/jobs.csv

Run from the project root:
    python execution/run_pipeline.py
"""

import os
import sys
import re
import json
import csv

# Allow importing sibling modules regardless of where the script is invoked
sys.path.insert(0, os.path.dirname(__file__))

from search_jobs import search                                          # noqa: E402
from scrape_job import scrape, is_within_one_week                       # noqa: E402
from tailor_resume import tailor                                        # noqa: E402
from google_api import create_resume_docx                               # noqa: E402


def sanitize(name: str) -> str:
    """Collapse non-alphanumeric chars into underscores for safe file names."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name).strip("_")[:40]


def main():
    print("=" * 60)
    print("  JOB AUTOMATION PIPELINE")
    print("=" * 60)

    # ── 1. Search ───────────────────────────────────────────────────
    print("\n[1/3] Searching Google for jobs…")
    raw_jobs = search()
    print(f"       → {len(raw_jobs)} results returned")

    if not raw_jobs:
        print("       No results. Verify your SerpAPI key or query.")
        return

    # ── 2. Scrape + filter ──────────────────────────────────────────
    print("\n[2/3] Scraping job pages and filtering…")
    jobs = []

    for i, job in enumerate(raw_jobs):
        short_title = job["title"][:55]
        print(f"       [{i+1}/{len(raw_jobs)}] {short_title}…")

        try:
            scraped = scrape(job["link"])
        except Exception as e:
            print(f"              ✗ scrape failed: {e}")
            continue

        if len(scraped.get("description", "")) < 100:
            print("              ✗ skipped — description too short")
            continue

        if not is_within_one_week(scraped.get("posted_date", "")):
            print(f"              ✗ skipped — posted {scraped.get('posted_date', 'unknown')}")
            continue

        # Fill any blanks from the original search result
        if not scraped["title"]:
            scraped["title"] = job.get("title", "Unknown Role")
        if not scraped["company"]:
            scraped["company"] = job.get("displayed_link", "").split(".")[0].title()

        jobs.append(scraped)
        print(f"              ✓ included (posted: {scraped.get('posted_date', 'N/A')})")

    print(f"\n       → {len(jobs)} jobs passed all filters")

    if not jobs:
        print("       Nothing to process. Exiting.")
        return

    os.makedirs(".tmp", exist_ok=True)
    with open(".tmp/jobs_filtered.json", "w") as f:
        json.dump(jobs, f, indent=2)

    # ── 3. Tailor + save locally ────────────────────────────────────
    print("\n[3/3] Tailoring resumes…")

    csv_rows = []  # accumulate rows for the summary CSV

    for i, job in enumerate(jobs):
        title = job["title"][:45]
        company = job["company"][:25]
        print(f"\n       [{i+1}/{len(jobs)}] {title} @ {company}")

        try:
            # a) Tailor the resume
            print("              → tailoring…")
            tailored = tailor(job["description"])

            # b) Build the ATS-friendly .docx
            safe_name = f"Resume_{sanitize(company)}_{sanitize(title)}.docx"
            docx_path = os.path.join(".tmp", safe_name)
            print("              → creating DOCX…")
            create_resume_docx(tailored, docx_path)
            print(f"              ✓ saved .tmp/{safe_name}")

            csv_rows.append([
                job.get("title", ""),
                job.get("company", ""),
                job.get("location", ""),
                job.get("posted_date", "N/A"),
                job.get("url", ""),
                safe_name,
            ])

        except Exception as e:
            print(f"              ✗ error: {e}")
            continue

    # ── Write summary CSV ───────────────────────────────────────────
    csv_path = ".tmp/jobs.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Job Title", "Company", "Location", "Date Posted", "Job Link", "Resume File"])
        writer.writerows(csv_rows)

    # ── Done ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  DONE")
    print(f"  {len(csv_rows)} resumes saved to .tmp/")
    print(f"  Summary CSV  → .tmp/jobs.csv")
    print("=" * 60)


if __name__ == "__main__":
    main()
