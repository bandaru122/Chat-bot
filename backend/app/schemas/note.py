"""Pydantic schemas for Note resources."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NoteBase(BaseModel):
    title: str
    content: str = ""


class NoteCreate(NoteBase):
    owner_email: Optional[str] = None


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None


class NoteOut(NoteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    summary: Optional[str] = None
    owner_email: Optional[str] = None
    created_at: datetime
    updated_at: datetime
