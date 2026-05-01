"""Pydantic schemas for chat / summarize."""
from typing import Optional

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: Optional[str] = None


class ChatResponse(BaseModel):
    model: str
    content: str
    prompt_tokens: int
    completion_tokens: int


class SummarizeRequest(BaseModel):
    note_id: int


class SummarizeResponse(BaseModel):
    note_id: int
    summary: str
