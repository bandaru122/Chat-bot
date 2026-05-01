"""Business logic for chat + summarize — invoked by app/api routers."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import get_llm_client, tracking_kwargs
from app.core.config import settings
from app.models import Note
from app.schemas import ChatMessage, ChatResponse


def chat(messages: list[ChatMessage], model: str | None = None) -> ChatResponse:
    client = get_llm_client()
    chosen = model or settings.LLM_MODEL
    resp = client.chat.completions.create(
        model=chosen,
        messages=[m.model_dump() for m in messages],
        max_tokens=600,
        temperature=0.7,
        **tracking_kwargs("chat"),
    )
    return ChatResponse(
        model=resp.model,
        content=resp.choices[0].message.content or "",
        prompt_tokens=resp.usage.prompt_tokens,
        completion_tokens=resp.usage.completion_tokens,
    )


async def summarize_note(db: AsyncSession, note: Note) -> str:
    client = get_llm_client()
    resp = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": "Summarize the user's note in 2-3 concise sentences."},
            {"role": "user", "content": f"Title: {note.title}\n\n{note.content}"},
        ],
        max_tokens=200,
        temperature=0.3,
        **tracking_kwargs("summarize"),
    )
    summary = resp.choices[0].message.content or ""
    note.summary = summary
    await db.commit()
    return summary
