"""Google Sheets service (formerly app/sheets.py).

`GOOGLE_SERVICE_ACCOUNT_JSON` may be a filesystem path OR an inline JSON string.
"""
import json
import os
import csv
from functools import lru_cache
from pathlib import Path
from io import StringIO
from urllib.parse import parse_qs, urlparse

import gspread
import httpx
from google.oauth2.service_account import Credentials

from app.core.config import settings

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _load_credentials_info() -> dict:
    raw = settings.GOOGLE_SERVICE_ACCOUNT_JSON
    if not raw:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON is empty. Set it in .env (file path or inline JSON)."
        )
    if os.path.exists(raw):
        return json.loads(Path(raw).read_text(encoding="utf-8"))
    raw = raw.strip().strip("'").strip('"')
    return json.loads(raw)


@lru_cache
def get_gspread_client() -> gspread.Client:
    info = _load_credentials_info()
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def service_account_email() -> str:
    return _load_credentials_info()["client_email"]


def read_sheet(spreadsheet_id_or_url: str, worksheet: str | int = 0) -> list[list[str]]:
    try:
        client = get_gspread_client()
        sheet = (
            client.open_by_url(spreadsheet_id_or_url)
            if spreadsheet_id_or_url.startswith("http")
            else client.open_by_key(spreadsheet_id_or_url)
        )
        ws = sheet.get_worksheet(worksheet) if isinstance(worksheet, int) else sheet.worksheet(worksheet)
        return ws.get_all_values()
    except Exception as primary_error:
        # If service-account access fails, try public CSV export for link-shared sheets.
        if isinstance(worksheet, str) and not worksheet.isdigit():
            raise RuntimeError(
                f"Google Sheets access failed via service account and worksheet '{worksheet}' "
                "cannot be resolved via public fallback. "
                f"Share with {service_account_email()} or pass worksheet index. "
                f"Original error: {primary_error}"
            ) from primary_error

        try:
            rows = _read_public_sheet_csv(spreadsheet_id_or_url, worksheet)
            if rows:
                return rows
        except Exception:
            pass

        raise RuntimeError(
            "Google Sheets access failed. Share the sheet with the service account "
            f"{service_account_email()} (Viewer) or make the sheet publicly readable. "
            f"Original error: {primary_error}"
        ) from primary_error


def _read_public_sheet_csv(spreadsheet_id_or_url: str, worksheet: str | int) -> list[list[str]]:
    spreadsheet_id, gid = _parse_sheet_id_and_gid(spreadsheet_id_or_url, worksheet)
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()

    text = resp.text.strip()
    if not text or "<html" in text.lower():
        return []

    reader = csv.reader(StringIO(resp.text))
    return [list(row) for row in reader]


def _parse_sheet_id_and_gid(spreadsheet_id_or_url: str, worksheet: str | int) -> tuple[str, int]:
    if spreadsheet_id_or_url.startswith("http"):
        parsed = urlparse(spreadsheet_id_or_url)
        parts = [p for p in parsed.path.split("/") if p]
        if "d" in parts:
            d_idx = parts.index("d")
            if d_idx + 1 < len(parts):
                spreadsheet_id = parts[d_idx + 1]
            else:
                raise ValueError("Missing spreadsheet id in Google Sheets URL")
        else:
            raise ValueError("Invalid Google Sheets URL")

        query = parse_qs(parsed.query)
        gid_str = query.get("gid", ["0"])[0]
    else:
        spreadsheet_id = spreadsheet_id_or_url
        gid_str = "0"

    if isinstance(worksheet, int):
        gid = worksheet
    else:
        gid = int(gid_str) if gid_str.isdigit() else 0

    return spreadsheet_id, gid
