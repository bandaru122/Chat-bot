"""/api/chat and /api/summarize — HTTP only."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import ChatRequest, ChatResponse, SummarizeRequest, SummarizeResponse
from app.services import chat_service, notes_service

router = APIRouter(prefix="/api", tags=["llm"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        return chat_service.chat(req.messages, req.model)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}") from e


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize(req: SummarizeRequest, db: AsyncSession = Depends(get_db)):
    note = await notes_service.get_note(db, req.note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    try:
        summary = await chat_service.summarize_note(db, note)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}") from e
    return SummarizeResponse(note_id=note.id, summary=summary)
