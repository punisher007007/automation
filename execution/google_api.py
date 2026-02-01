"""
google_api.py — Layer 3: Execution

All Google Drive + Sheets operations in one place:
  - OAuth2 credential management (browser auth on first run, cached after)
  - ATS-friendly .docx creation from plain-text resume output
  - File upload to Google Drive
  - Master "Job Applications" sheet: create, populate headers, append rows
"""

import os
import json

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

DRIVE_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]
SHEET_TITLE = "Job Applications"
TOKEN_PATH = "token.json"
CREDS_PATH = "credentials.json"


# ── Auth ──────────────────────────────────────────────────────────────────


def get_credentials():
    """
    Standard OAuth2 installed-app flow.
    First run: opens browser for user consent.
    Subsequent runs: reads cached token.json.
    """
    creds = None

    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH) as f:
            creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return creds


# ── DOCX Builder ──────────────────────────────────────────────────────────


def _add_section_border(paragraph):
    """Thin bottom border under a section header — standard ATS resume style."""
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "000000")
    pBdr.append(bottom)
    pPr.append(pBdr)


def create_resume_docx(resume_text: str, filepath: str) -> str:
    """
    Parses Grok's plain-text resume and builds a clean, ATS-friendly .docx.

    Detection logic (applied line-by-line):
      1. First non-empty line  → Name (bold, 16pt, centered)
      2. Line with @ or ( and | → Contact line (9pt, centered)
      3. ALL-CAPS short line    → Section header (bold, 11pt, bottom border)
      4. Line with | but no @   → Company/role line (bold, 10pt)
      5. Line starting with •   → Bullet point (hanging indent)
      6. Anything else          → Body text (10pt)

    All text is Calibri. Margins are 0.7–0.75 in to fit one page.
    """
    doc = Document()

    # Tight margins — maximise usable space
    for section in doc.sections:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)

    # Strip markdown artifacts Grok sometimes leaves behind
    cleaned = (
        resume_text
        .replace("```", "")
        .replace("**", "")
        .replace("##", "")
        .replace("###", "")
    )

    lines = [line.strip() for line in cleaned.split("\n")]
    is_name = True  # first meaningful line is the name

    for line in lines:
        if not line:
            continue

        # ── Name ──────────────────────────────────────────────
        if is_name:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(line)
            run.bold = True
            run.font.size = Pt(16)
            run.font.name = "Calibri"
            p.paragraph_format.space_after = Pt(2)
            is_name = False
            continue

        # ── Contact info ──────────────────────────────────────
        if ("@" in line or "(" in line) and "|" in line:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(line)
            run.font.size = Pt(9)
            run.font.name = "Calibri"
            p.paragraph_format.space_after = Pt(4)
            continue

        # ── Section header (ALL CAPS, short, no digits) ───────
        clean = line.replace(":", "").strip()
        if clean.isupper() and 3 < len(clean) < 40 and not any(c.isdigit() for c in clean):
            p = doc.add_paragraph()
            run = p.add_run(line)
            run.bold = True
            run.font.size = Pt(11)
            run.font.name = "Calibri"
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(2)
            _add_section_border(p)
            continue

        # ── Company / role line (has |, no @) ─────────────────
        if "|" in line and "@" not in line:
            p = doc.add_paragraph()
            run = p.add_run(line)
            run.bold = True
            run.font.size = Pt(10)
            run.font.name = "Calibri"
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(1)
            continue

        # ── Bullet point ──────────────────────────────────────
        if line.startswith(("•", "-", "*", "–", "·")):
            text = line.lstrip("•-*–· ").strip()
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.4)
            p.paragraph_format.first_line_indent = Inches(-0.2)
            run = p.add_run("• " + text)
            run.font.size = Pt(10)
            run.font.name = "Calibri"
            p.paragraph_format.space_after = Pt(1)
            continue

        # ── Body text (summary, education details, etc.) ─────
        p = doc.add_paragraph()
        run = p.add_run(line)
        run.font.size = Pt(10)
        run.font.name = "Calibri"
        p.paragraph_format.space_after = Pt(1)

    doc.save(filepath)
    return filepath


# ── Drive ─────────────────────────────────────────────────────────────────


def upload_to_drive(file_path: str, file_name: str) -> str:
    """Uploads a file to the configured Drive folder. Returns the web link."""
    creds = get_credentials()
    drive = build("drive", "v3", credentials=creds)

    mime_map = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
    }
    ext = os.path.splitext(file_path)[1]

    file_metadata = {"name": file_name, "parents": [DRIVE_FOLDER_ID]}
    media = MediaFileUpload(
        file_path,
        mimetype=mime_map.get(ext, "application/octet-stream"),
    )

    file = (
        drive.files()
        .create(body=file_metadata, media_body=media, fields="id,webLink")
        .execute()
    )
    return file["webLink"]


# ── Sheets ────────────────────────────────────────────────────────────────


def get_or_create_sheet() -> tuple:
    """
    Returns (sheet_id, sheet_web_link).
    Creates the master "Job Applications" sheet if it doesn't already exist
    in the configured Drive folder.
    """
    creds = get_credentials()
    drive = build("drive", "v3", credentials=creds)
    sheets = build("sheets", "v4", credentials=creds)

    # Check if master sheet already exists in the folder
    results = drive.files().list(
        q=(
            f"name='{SHEET_TITLE}' "
            f"and '{DRIVE_FOLDER_ID}' in parents "
            f"and mimeType='application/vnd.google-apps.spreadsheet'"
        ),
        fields="files(id, name, webLink)",
    ).execute()

    files = results.get("files", [])
    if files:
        return files[0]["id"], files[0]["webLink"]

    # ── Create new sheet ────────────────────────────────────────────
    file_meta = {
        "name": SHEET_TITLE,
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "parents": [DRIVE_FOLDER_ID],
    }
    file = drive.files().create(body=file_meta, fields="id,webLink").execute()
    sheet_id = file["id"]

    # Write column headers
    headers = [[
        "Job Title",
        "Company",
        "Location",
        "Date Posted",
        "Job Link",
        "Tailored Resume",
    ]]
    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="Sheet1!A1",
        valueInputOption="USER_ENTERED",
        body={"values": headers},
    ).execute()

    # Bold headers and auto-resize columns
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={
            "requests": [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": 0,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {"bold": True}
                            }
                        },
                        "fields": "userEnteredFormat.textFormat.bold",
                    }
                },
                {
                    "autoResizeDimensionRange": {
                        "dimension": {
                            "sheetId": 0,
                            "dimension": "COLUMNS",
                            "startIndex": 0,
                            "endIndex": 6,
                        }
                    }
                },
            ]
        },
    ).execute()

    return sheet_id, file["webLink"]


def append_to_sheet(sheet_id: str, row: list):
    """Appends one row to the master sheet."""
    creds = get_credentials()
    sheets = build("sheets", "v4", credentials=creds)

    sheets.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="Sheet1!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [row]},
    ).execute()
