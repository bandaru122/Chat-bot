"""/api/threads — CRUD + send message."""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db import get_db
from app.models import User
from app.schemas import (
    MessageOut,
    SendMessageRequest,
    ThreadCreate,
    ThreadDetail,
    ThreadOut,
    ThreadUpdate,
)
from app.services import thread_service

router = APIRouter(prefix="/api/threads", tags=["threads"])


@router.get("", response_model=list[ThreadOut])
async def list_threads(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return await thread_service.list_threads(db, current)


@router.post("", response_model=ThreadOut, status_code=status.HTTP_201_CREATED)
async def create_thread(
    req: ThreadCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return await thread_service.create_thread(db, current, req.title)


@router.get("/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return await thread_service.get_thread(db, current, thread_id)


@router.patch("/{thread_id}", response_model=ThreadOut)
async def update_thread(
    thread_id: uuid.UUID,
    req: ThreadUpdate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return await thread_service.rename_thread(db, current, thread_id, req.title)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    await thread_service.delete_thread(db, current, thread_id)


@router.post("/{thread_id}/messages", response_model=ThreadDetail)
async def send_message(
    thread_id: uuid.UUID,
    req: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    await thread_service.send_message(db, current, thread_id, req.content, req.model)
    # Return the full updated thread (with messages) for simple frontend handling.
    return await thread_service.get_thread(db, current, thread_id)


@router.patch("/{thread_id}/messages/{message_id}", response_model=ThreadDetail)
async def edit_message(
    thread_id: uuid.UUID,
    message_id: uuid.UUID,
    req: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return await thread_service.edit_message(
        db, current, thread_id, message_id, req.content, req.model
    )
