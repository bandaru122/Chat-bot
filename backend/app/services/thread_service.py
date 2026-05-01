"""Thread + message persistence and DB-backed chat orchestration."""
import uuid

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.llm import get_llm_client, tracking_kwargs
from app.core.config import settings
from app.models import ChatMessageRow, ChatThread, User


async def list_threads(db: AsyncSession, user: User) -> list[ChatThread]:
    res = await db.execute(
        select(ChatThread)
        .where(ChatThread.user_id == user.id)
        .order_by(ChatThread.updated_at.desc())
    )
    return list(res.scalars().all())


async def get_thread(db: AsyncSession, user: User, thread_id: uuid.UUID) -> ChatThread:
    res = await db.execute(
        select(ChatThread)
        .where(ChatThread.id == thread_id, ChatThread.user_id == user.id)
        .options(selectinload(ChatThread.messages))
    )
    thread = res.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


async def create_thread(
    db: AsyncSession, user: User, title: str | None = None
) -> ChatThread:
    thread = ChatThread(user_id=user.id, title=title or "New chat")
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return thread


async def rename_thread(
    db: AsyncSession, user: User, thread_id: uuid.UUID, title: str
) -> ChatThread:
    thread = await get_thread(db, user, thread_id)
    thread.title = title.strip()[:200] or thread.title
    await db.commit()
    await db.refresh(thread)
    return thread


async def delete_thread(db: AsyncSession, user: User, thread_id: uuid.UUID) -> None:
    thread = await get_thread(db, user, thread_id)
    await db.delete(thread)
    await db.commit()


async def _save_message(
    db: AsyncSession, thread: ChatThread, role: str, content: str
) -> ChatMessageRow:
    msg = ChatMessageRow(thread_id=thread.id, role=role, content=content)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


def _generate_title(user_message: str, model: str | None = None) -> str:
    """Ask the LLM for a short, descriptive thread title."""
    client = get_llm_client()
    llm_model = model or settings.LLM_MODEL
    try:
        resp = client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Generate a very short title (max 6 words, no quotes, "
                        "no trailing punctuation) summarising the user's first message."
                    ),
                },
                {"role": "user", "content": user_message[:1000]},
            ],
            max_tokens=24,
            temperature=0.3,
            **tracking_kwargs("thread_title"),
        )
        title = (resp.choices[0].message.content or "").strip().strip("\"'.") or "New chat"
        return title[:80]
    except Exception:
        # Fallback to a deterministic title slice if the LLM call fails.
        return user_message.strip().split("\n", 1)[0][:60] or "New chat"


async def send_message(
    db: AsyncSession,
    user: User,
    thread_id: uuid.UUID,
    content: str,
    model: str | None = None,
) -> tuple[ChatThread, ChatMessageRow, ChatMessageRow]:
    """Persist user message, call LLM with full history, persist assistant reply."""
    thread = await get_thread(db, user, thread_id)
    is_first = len(thread.messages) == 0

    user_msg = await _save_message(db, thread, "user", content)

    history = [{"role": m.role, "content": m.content} for m in thread.messages]
    history.append({"role": "user", "content": content})

    client = get_llm_client()
    llm_model = model or settings.LLM_MODEL
    resp = client.chat.completions.create(
        model=llm_model,
        messages=history,
        max_tokens=1200,
        temperature=0.7,
        user=user.email,
        **{
            k: v
            for k, v in tracking_kwargs("chat").items()
            if k != "user"
        },
    )
    reply = resp.choices[0].message.content or ""
    assistant_msg = await _save_message(db, thread, "assistant", reply)

    if is_first:
        thread.title = _generate_title(content, model)
        await db.commit()
        await db.refresh(thread)

    return thread, user_msg, assistant_msg


async def edit_message(
    db: AsyncSession,
    user: User,
    thread_id: uuid.UUID,
    message_id: uuid.UUID,
    new_content: str,
    model: str | None = None,
) -> ChatThread:
    """Edit a user message, delete all messages after it, and regenerate assistant responses."""
    thread = await get_thread(db, user, thread_id)

    # Find the message to edit
    msg_res = await db.execute(
        select(ChatMessageRow).where(ChatMessageRow.id == message_id)
    )
    message = msg_res.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # Verify it's a user message (only allow editing user messages)
    if message.role != "user":
        raise HTTPException(
            status_code=400, detail="Can only edit user messages, not assistant responses"
        )

    # Verify message belongs to this thread
    if message.thread_id != thread.id:
        raise HTTPException(status_code=404, detail="Message not found in this thread")

    # Find the index of the message in the thread
    msg_index = next(
        (i for i, m in enumerate(thread.messages) if m.id == message_id), None
    )
    if msg_index is None:
        raise HTTPException(status_code=404, detail="Message not found in thread")

    # Delete all messages after this one
    messages_to_delete = thread.messages[msg_index + 1 :]
    for m in messages_to_delete:
        await db.delete(m)

    # Update the message content
    message.content = new_content.strip()
    await db.commit()

    # Rebuild history up to and including the edited message
    history = [
        {"role": m.role, "content": m.content}
        for m in thread.messages[: msg_index + 1]
    ]

    # Generate new assistant response
    client = get_llm_client()
    llm_model = model or settings.LLM_MODEL
    resp = client.chat.completions.create(
        model=llm_model,
        messages=history,
        max_tokens=1200,
        temperature=0.7,
        user=user.email,
        **{
            k: v
            for k, v in tracking_kwargs("chat").items()
            if k != "user"
        },
    )
    reply = resp.choices[0].message.content or ""
    await _save_message(db, thread, "assistant", reply)

    # Refresh and return
    await db.refresh(thread, ["messages"])
    return thread
