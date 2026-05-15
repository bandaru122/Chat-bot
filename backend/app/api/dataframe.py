"""/api/dataframe — DataFrame Q&A via LangChain pandas agent."""
from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.models import User
from app.schemas import DataframeAskRequest, DataframeAskResponse
from app.services import dataframe_service

router = APIRouter(prefix="/api/dataframe", tags=["dataframe"])


@router.post("/ask", response_model=DataframeAskResponse)
async def ask_dataframe(
    req: DataframeAskRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        result = dataframe_service.ask_dataframe(
            question=req.question,
            user_email=current_user.email,
            model=req.model,
            google_sheet_url=req.google_sheet_url,
            worksheet=req.worksheet,
            uploaded_file_url=req.uploaded_file_url,
            max_rows=req.max_rows,
        )
        return DataframeAskResponse(**result)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "dataframe_agent_error", "message": str(exc)},
        ) from exc
