"""Business logic for Notes — invoked by routers in app/api."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Note
from app.schemas import NoteCreate, NoteUpdate


async def list_notes(db: AsyncSession) -> list[Note]:
    result = await db.execute(select(Note).order_by(Note.created_at.desc()))
    return list(result.scalars().all())


async def get_note(db: AsyncSession, note_id: int) -> Note | None:
    return await db.get(Note, note_id)


async def create_note(db: AsyncSession, payload: NoteCreate) -> Note:
    note = Note(**payload.model_dump())
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def update_note(db: AsyncSession, note: Note, payload: NoteUpdate) -> Note:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(note, field, value)
    await db.commit()
    await db.refresh(note)
    return note


async def delete_note(db: AsyncSession, note: Note) -> None:
    await db.delete(note)
    await db.commit()
