# Job Automation Pipeline

## Goal

Automatically search for entry/mid-level Data Analyst jobs on greenhouse.io and lever.co, scrape their descriptions, tailor the resume using Grok (Harvard OCS methodology), package each as an ATS-friendly .docx, upload to Google Drive, and log everything into a master Google Sheet.

---

## Inputs

| Input | Where |
|-------|-------|
| SerpAPI key | `.env` → `SERPAPI_KEY` |
| Grok API key | `.env` → `GROK_API_KEY` |
| Google Drive folder ID | `.env` → `DRIVE_FOLDER_ID` |
| Google OAuth credentials | `credentials.json` (gitignored) |
| Base resume | `data/base_resume.txt` |
| Grok prompt template | `data/grok_prompt.txt` |

---

## Flow

```
search_jobs.py  →  scrape_job.py  →  [filter < 1 week]  →  tailor_resume.py  →  google_api.py
   SerpAPI           requests/BS4         date check            Grok API          Drive + Sheets
```

1. **`execution/search_jobs.py`** — Hits SerpAPI with the configured Google query. Targets greenhouse.io and lever.co for entry/junior/associate/mid Data Analyst roles in the US. Writes raw results to `.tmp/jobs_raw.json`.

2. **`execution/scrape_job.py`** — Scrapes each job URL for the full description and posted date. Has specific selectors for greenhouse.io and lever.co, plus a generic fallback (longest text block). Returns structured data.

3. **Filter** (inside `run_pipeline.py`) — Drops jobs where:
   - Description is < 100 characters (scrape failed or page is JS-rendered)
   - Posted date is > 7 days ago

4. **`execution/tailor_resume.py`** — Loads the prompt template and base resume from `data/`, appends the job description, and calls Grok (`grok-3`). Returns the tailored resume as plain text.

5. **`execution/google_api.py`** — Three jobs:
   - Parses Grok's text output into an ATS-friendly `.docx` (Calibri, single-column, section borders, hanging-indent bullets)
   - Uploads the `.docx` to the configured Drive folder
   - Creates or reuses a "Job Applications" Google Sheet and appends a row with clickable links

---

## Run

```bash
# From the project root:
pip install -r requirements.txt
python execution/run_pipeline.py
```

**First run:** Google OAuth will open a browser tab for you to authorize. After that, `token.json` is cached and no further prompts appear.

---

## Outputs

| Output | Location |
|--------|----------|
| Raw search results | `.tmp/jobs_raw.json` |
| Filtered jobs | `.tmp/jobs_filtered.json` |
| Tailored resumes (local) | `.tmp/Resume_*.docx` |
| Tailored resumes (cloud) | Google Drive → configured folder |
| Master tracking sheet | Google Sheets → "Job Applications" |

The master sheet columns: **Job Title · Company · Location · Date Posted · Job Link · Tailored Resume** — last two are clickable hyperlinks.

---

## Edge Cases & Learnings

- SerpAPI returns organic results, not structured job data. Posting dates must come from scraping each page.
- Greenhouse.io and lever.co have different HTML structures. The scraper tries site-specific selectors first, then falls back to the longest text block on the page.
- Some job pages require JavaScript to render. If scraping consistently returns < 100 chars for a site, consider switching to a headless browser (playwright/selenium) — flag this and update this directive.
- Google OAuth requires `Drive API` and `Sheets API` to be enabled in Google Cloud Console for the project.
- Grok model is `grok-3`. If rate-limited, add a delay between calls in `run_pipeline.py` and update this directive.
- The master sheet is reused across runs — rows accumulate. It is not recreated each time.

---

## How to Update

- **Change search query:** Edit `SEARCH_PARAMS` in `execution/search_jobs.py`
- **Change resume or prompt:** Edit files in `data/`
- **Change Drive folder:** Update `DRIVE_FOLDER_ID` in `.env`
