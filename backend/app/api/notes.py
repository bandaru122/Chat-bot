"""/api/notes — HTTP only."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import NoteCreate, NoteOut, NoteUpdate
from app.services import notes_service

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.get("", response_model=list[NoteOut])
async def list_notes(db: AsyncSession = Depends(get_db)):
    return await notes_service.list_notes(db)


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(payload: NoteCreate, db: AsyncSession = Depends(get_db)):
    return await notes_service.create_note(db, payload)


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(note_id: int, db: AsyncSession = Depends(get_db)):
    note = await notes_service.get_note(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.patch("/{note_id}", response_model=NoteOut)
async def update_note(note_id: int, payload: NoteUpdate, db: AsyncSession = Depends(get_db)):
    note = await notes_service.get_note(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return await notes_service.update_note(db, note, payload)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: int, db: AsyncSession = Depends(get_db)):
    note = await notes_service.get_note(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    await notes_service.delete_note(db, note)
