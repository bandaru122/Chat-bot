"""/api/sheets — HTTP only."""
from fastapi import APIRouter, HTTPException, Query

from app.services.sheets_service import read_sheet, service_account_email

router = APIRouter(prefix="/api/sheets", tags=["sheets"])


@router.get("/service-account")
async def whoami() -> dict:
    try:
        return {"client_email": service_account_email()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{spreadsheet_id}")
async def read(spreadsheet_id: str, worksheet: str = Query("0")):
    ws: str | int = int(worksheet) if worksheet.isdigit() else worksheet
    try:
        rows = read_sheet(spreadsheet_id, ws)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Sheets error: {e}") from e
    return {"rows": rows, "row_count": len(rows)}
