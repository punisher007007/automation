"""
auth_google.py — Completes Google OAuth in headless environments.

Usage:
  1. Run the pipeline — if no browser is available, it prints an auth URL
     (or generate one yourself: python execution/auth_google.py --url)
  2. Open that URL in your browser and authorize the app
  3. You'll land on a localhost error page — the URL bar will contain a code
     parameter (looks like: 4/0AeaYSHC...)
  4. Copy that code and run:
         python execution/auth_google.py <CODE>

After that, token.json is cached and the pipeline works without re-auth.
"""

import sys
import json

import requests

CREDS_PATH = "credentials.json"
TOKEN_PATH = "token.json"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = (
    "https://www.googleapis.com/auth/drive "
    "https://www.googleapis.com/auth/spreadsheets"
)


def _load_client():
    """Reads client_id and client_secret from credentials.json."""
    with open(CREDS_PATH) as f:
        cfg = json.load(f)["installed"]
    return cfg["client_id"], cfg["client_secret"]


def print_auth_url():
    """Prints the Google authorization URL."""
    client_id, _ = _load_client()
    url = (
        "https://accounts.google.com/o/oauth2/auth"
        f"?client_id={client_id}"
        "&redirect_uri=http://localhost"
        "&response_type=code"
        f"&scope={SCOPES.replace(' ', '+')}"
        "&access_type=offline"
        "&prompt=consent"
    )
    print(f"\nOpen this URL in your browser:\n\n  {url}\n")
    print("After authorizing, copy the code from the browser URL bar")
    print("(it looks like: 4/0AeaYSHC…)\n")
    print("Then run:  python execution/auth_google.py <CODE>\n")


def exchange_code(code: str):
    """
    Exchanges an authorization code for access + refresh tokens.
    Saves token.json in the format google.oauth2.credentials expects.
    """
    client_id, client_secret = _load_client()

    resp = requests.post(TOKEN_URL, data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": "http://localhost",
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    token_data = resp.json()

    # Format expected by google.oauth2.credentials.Credentials.from_authorized_user_info
    creds = {
        "token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", ""),
        "token_uri": TOKEN_URL,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": SCOPES.split(),
    }

    with open(TOKEN_PATH, "w") as f:
        json.dump(creds, f, indent=2)

    print("\n✓ token.json saved.")
    print("  Run the pipeline again: python execution/run_pipeline.py\n")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "--url":
        print_auth_url()
    else:
        exchange_code(sys.argv[1])
