"""Google Sheets service (formerly app/sheets.py).

`GOOGLE_SERVICE_ACCOUNT_JSON` may be a filesystem path OR an inline JSON string.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

import gspread
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
    client = get_gspread_client()
    sheet = (
        client.open_by_url(spreadsheet_id_or_url)
        if spreadsheet_id_or_url.startswith("http")
        else client.open_by_key(spreadsheet_id_or_url)
    )
    ws = sheet.get_worksheet(worksheet) if isinstance(worksheet, int) else sheet.worksheet(worksheet)
    return ws.get_all_values()
