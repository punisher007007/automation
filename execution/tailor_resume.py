"""
tailor_resume.py — Layer 3: Execution

Calls the Grok API to tailor the base resume for a specific job description.
Loads the prompt template and base resume from data/, assembles the full
message, and returns the tailored resume text.

Input:  Job description (string)
Output: Tailored resume (string)
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

GROK_API_KEY = os.environ["GROK_API_KEY"]
GROK_MODEL = "grok-3"

# Paths relative to project root (where the pipeline is run from)
PROMPT_PATH = "data/grok_prompt.txt"
RESUME_PATH = "data/base_resume.txt"


def _load(path: str) -> str:
    with open(path) as f:
        return f.read().strip()


def tailor(job_description: str) -> str:
    """
    Sends the full prompt (template + JD + base resume) to Grok.
    Returns the tailored resume as plain text.
    """
    prompt_template = _load(PROMPT_PATH)
    base_resume = _load(RESUME_PATH)

    # The prompt template already contains the user's raw experience.
    # We also append the formatted resume so Grok has both for max context.
    full_prompt = (
        f"{prompt_template}\n\n"
        f"---\n\n"
        f"**The Job Description to Tailor For:**\n\n"
        f"{job_description}\n\n"
        f"---\n\n"
        f"**My Current Formatted Resume (for reference on structure and phrasing):**\n\n"
        f"{base_resume}"
    )

    resp = requests.post(
        "https://api.x.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROK_MODEL,
            "messages": [{"role": "user", "content": full_prompt}],
            "max_tokens": 4000,
        },
        timeout=120,
    )
    resp.raise_for_status()

    return resp.json()["choices"][0]["message"]["content"]


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            jd = f.read()
        print(tailor(jd))
    else:
        print("Usage: python tailor_resume.py <job_description_file>")
