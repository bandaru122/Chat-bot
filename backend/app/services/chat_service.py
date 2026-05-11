"""Business logic for chat + summarize — invoked by app/api routers."""
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import get_llm_client, tracking_kwargs
from app.core.config import settings
from app.models import Note
from app.schemas import ChatMessage, ChatResponse
from app.services import api_service, llm_service
from app.services.rich_content import generate_chart_or_text_response


LIVE_HINTS = ("live", "today", "current", "latest")


def _is_live_query(query: str) -> bool:
    q = query.lower()
    return any(token in q for token in LIVE_HINTS)


def run_live_query(
    query: str,
    user_email: str,
    model: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    live_data = api_service.get_live_data(query)
    if live_data.get("has_data"):
        answer = llm_service.ask_llm(
            query,
            live_data,
            user_email=user_email,
            model=model,
            history=history,
        )
        return {
            "mode": "live",
            "query": query,
            "model": model or settings.LLM_MODEL,
            "live_data": live_data,
            "answer": answer,
            "fallback_used": False,
        }

    answer = llm_service.ask_llm_fallback(
        query,
        user_email=user_email,
        model=model,
        history=history,
    )
    return {
        "mode": "fallback",
        "query": query,
        "model": model or settings.LLM_MODEL,
        "live_data": live_data,
        "answer": answer,
        "fallback_used": True,
    }


def chat(messages: list[ChatMessage], model: str | None = None) -> ChatResponse:
    chosen = model or settings.LLM_MODEL
    last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")

    if _is_live_query(last_user):
        history = [{"role": m.role, "content": m.content} for m in messages[:-1]]
        live = run_live_query(last_user, user_email="anonymous", model=chosen, history=history)
        content = live.get("answer", "")
    else:
        client = get_llm_client()
        content = generate_chart_or_text_response(client, chosen, "anonymous", last_user)

    return ChatResponse(
        model=chosen,
        content=content,
        prompt_tokens=0,
        completion_tokens=0,
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
