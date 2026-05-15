"""Thread + message persistence and DB-backed chat orchestration."""
import base64
import hashlib
import json
import mimetypes
from pathlib import Path
import re
from urllib.parse import urlparse
import uuid
import zipfile
from xml.etree import ElementTree as ET

import httpx
from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.llm import get_llm_client, tracking_kwargs
from app.ai.rag import query as rag_query
from app.ai.rag import upsert_documents
from app.core.config import settings
from app.models import ChatMessageRow, ChatThread, User
from app.services.rich_content import generate_chart_or_text_response, is_visualization_request
from app.services import sql_service, api_service, llm_service
from app.services.sheets_service import read_sheet, service_account_email

# Live-signal keywords — auto-triggers real API fetch before LLM reply.
# ONLY specific domain keywords are listed. Generic time words (today, now, current, latest)
# are intentionally excluded to avoid false positives on questions like
# "what is today's special day?" that should be answered from LLM training knowledge.
_LIVE_AUTO_KEYWORDS = frozenset([
    # ── crypto / finance ────────────────────────────────────────────────────
    "bitcoin", "crypto", "ethereum", "nifty", "sensex",
    "stock price", "share price", "mutual fund", "nifty 50",
    # ── sports ──────────────────────────────────────────────────────────────
    "cricket", "ipl", "live score", "match score", "score", "scores", "result", "results", "yesterday match",
    # ── news compound phrases (specific) ────────────────────────────────────
    "latest news", "today news", "yesterday news", "breaking news", "headlines today",
    "market today", "today headlines",
    # ── weather (always live context) ───────────────────────────────────────
    "weather", "weather forecast", "current weather", "temperature today",
    # ── geopolitical events ──────────────────────────────────────────────────
    "war", "conflict", "outbreak",
    # ── commodities / broad web-search live asks ───────────────────────────
    "gold", "silver", "commodity", "bullion", "xau", "xag",
    "search", "latest updates", "what is happening",
    "today", "yesterday", "latest", "current",
])

_MEMORY_EXCHANGES = 10
_MEMORY_MAX_MESSAGES = _MEMORY_EXCHANGES * 2


ATTACHMENT_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
GSHEET_URL_RE = re.compile(r"https?://docs\.google\.com/spreadsheets/d/[^\s)]+")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov"}
TABULAR_SUFFIXES = {".xlsx", ".csv", ".tsv", ".json"}

PLAIN_TEXT_SUFFIXES = {
    ".txt", ".md", ".csv", ".tsv", ".json", ".py", ".ts", ".tsx", ".js", ".jsx",
    ".html", ".xml", ".yaml", ".yml", ".sql", ".tex", ".java", ".c", ".cpp", ".cc",
    ".cxx", ".cs", ".go", ".rs", ".php", ".rb", ".sh", ".r", ".kt", ".swift", ".srt", ".vtt",
}


def _uploaded_path_from_url(url: str) -> Path | None:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return None
        if not parsed.path.startswith("/uploads/"):
            return None
        name = Path(parsed.path).name
        if not name:
            return None
        return _uploads_dir() / name
    except Exception:
        return None


def _extract_text_from_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        page_texts: list[str] = []
        for page in reader.pages[:8]:
            page_texts.append((page.extract_text() or "").strip())
        return "\n".join(part for part in page_texts if part)

    if suffix == ".docx":
        with zipfile.ZipFile(path) as archive:
            xml_bytes = archive.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
        texts = [node.text or "" for node in root.iter() if node.tag.endswith("}t")]
        return " ".join(texts)

    if suffix == ".xlsx":
        with zipfile.ZipFile(path) as archive:
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared_strings = [node.text or "" for node in shared_root.iter() if node.tag.endswith("}t")]

            rows: list[str] = []
            for name in archive.namelist():
                if not name.startswith("xl/worksheets/") or not name.endswith(".xml"):
                    continue
                sheet_root = ET.fromstring(archive.read(name))
                for row in [node for node in sheet_root.iter() if node.tag.endswith("}row")]:
                    values: list[str] = []
                    for cell in [node for node in row if node.tag.endswith("}c")]:
                        value_node = next((child for child in cell if child.tag.endswith("}v")), None)
                        if value_node is None or value_node.text is None:
                            continue
                        if cell.attrib.get("t") == "s":
                            try:
                                values.append(shared_strings[int(value_node.text)])
                            except Exception:
                                values.append(value_node.text)
                        else:
                            values.append(value_node.text)
                    if values:
                        rows.append("\t".join(values))
            return "\n".join(rows)

    if suffix == ".ipynb":
        try:
            raw = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            cells = raw.get("cells") if isinstance(raw, dict) else []
            chunks: list[str] = []
            if isinstance(cells, list):
                for cell in cells[:200]:
                    if not isinstance(cell, dict):
                        continue
                    ctype = str(cell.get("cell_type") or "")
                    src = cell.get("source")
                    text = "".join(src) if isinstance(src, list) else str(src or "")
                    text = text.strip()
                    if not text:
                        continue
                    label = "Code" if ctype == "code" else "Markdown"
                    chunks.append(f"{label} cell:\n{text}")
            return "\n\n".join(chunks)
        except Exception:
            return path.read_text(encoding="utf-8", errors="ignore")

    if suffix in PLAIN_TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="ignore")

    return ""


def _media_attachment_note(path: Path) -> str:
    """Return a concise textual note for non-text attachments.

    This enables the assistant to answer attachment-related questions even when
    OCR/transcription is unavailable.
    """
    try:
        size_kb = max(1, round(path.stat().st_size / 1024))
    except Exception:
        size_kb = 0
    suffix = path.suffix.lower()
    mime_type, _ = mimetypes.guess_type(path.name)
    mime = mime_type or "application/octet-stream"

    if suffix in IMAGE_SUFFIXES:
        return f"Image attachment: {path.name} ({mime}, {size_kb}KB)."
    if suffix in VIDEO_SUFFIXES:
        return (
            f"Video attachment: {path.name} ({mime}, {size_kb}KB). "
            "Use this file context for user questions about the uploaded video."
        )
    return f"Attachment: {path.name} ({mime}, {size_kb}KB)."


def _json_rows_for_table(text: str) -> list[dict[str, str]]:
    """Convert JSON array/object payload into table-like rows when possible."""
    try:
        parsed = json.loads(text)
    except Exception:
        return []

    rows: list[dict[str, str]] = []
    if isinstance(parsed, list):
        for item in parsed[:300]:
            if isinstance(item, dict):
                rows.append({str(k): str(v) for k, v in item.items()})
    elif isinstance(parsed, dict):
        # Single object as one-row table
        rows.append({str(k): str(v) for k, v in parsed.items()})
    return rows


def _chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    length = len(cleaned)
    while start < length:
        end = min(length, start + chunk_size)
        chunks.append(cleaned[start:end])
        if end >= length:
            break
        start = max(0, end - overlap)
    return chunks


def _attachment_entries(prompt: str) -> list[tuple[str, str, Path]]:
    entries: list[tuple[str, str, Path]] = []
    for name, url in ATTACHMENT_LINK_RE.findall(prompt):
        path = _uploaded_path_from_url(url)
        if path and path.exists():
            entries.append((name, url, path))
    return entries


def _history_attachment_entries(history: list[dict[str, str]] | None) -> list[tuple[str, str, Path]]:
    if not history:
        return []
    merged: list[tuple[str, str, Path]] = []
    for msg in history:
        if not isinstance(msg, dict):
            continue
        content = str(msg.get("content") or "")
        if not content:
            continue
        merged.extend(_attachment_entries(content))
    return merged


def _image_data_url(path: Path) -> str | None:
    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type or not mime_type.startswith("image/"):
        return None
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _build_user_content(
    user_id: str,
    thread_id: str,
    prompt: str,
    use_rag: bool = True,
    history: list[dict[str, str]] | None = None,
):
    if not use_rag:
        marker = "\n\nAttached files:\n"
        # Frontend appends attachment links in this block. Remove it completely
        # when RAG is OFF so no document hints leak into plain-chat mode.
        if marker in prompt:
            prompt = prompt.split(marker, 1)[0].strip()

    effective_prompt = (
        _prompt_with_rag_context(user_id=user_id, thread_id=thread_id, prompt=prompt)
        if use_rag
        else prompt
    )
    image_urls: list[str] = []

    # Current-turn attachment images.
    for _, _, path in _attachment_entries(prompt):
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        data_url = _image_data_url(path)
        if data_url:
            image_urls.append(data_url)

    # Follow-up turns: if the user asks about previously attached images,
    # include recent image attachments from history so the model can answer.
    if not image_urls:
        for _, _, path in _history_attachment_entries(history):
            if path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            data_url = _image_data_url(path)
            if data_url and data_url not in image_urls:
                image_urls.append(data_url)
            if len(image_urls) >= 3:
                break

    if not image_urls:
        return effective_prompt

    content = [{"type": "text", "text": effective_prompt}]
    content.extend({"type": "image_url", "image_url": {"url": url}} for url in image_urls)
    return content


def _sheet_urls(prompt: str) -> list[str]:
    return list(dict.fromkeys(GSHEET_URL_RE.findall(prompt)))


def _normalize_header(value: str, idx: int) -> str:
    text = (value or "").strip()
    if not text:
        return f"col_{idx + 1}"
    clean = re.sub(r"[^0-9a-zA-Z_ ]+", "", text)
    clean = re.sub(r"\s+", "_", clean).strip("_")
    return clean[:64] or f"col_{idx + 1}"


def _rows_to_table(rows: list[list[str]], max_rows: int = 300) -> tuple[list[str], list[dict[str, str]]]:
    if not rows:
        return [], []

    header_row = rows[0]
    column_count = max(len(r) for r in rows)
    if column_count == 0:
        return [], []

    normalized: list[str] = []
    seen: dict[str, int] = {}
    for idx in range(column_count):
        raw = header_row[idx] if idx < len(header_row) else ""
        candidate = _normalize_header(raw, idx)
        count = seen.get(candidate, 0)
        seen[candidate] = count + 1
        normalized.append(candidate if count == 0 else f"{candidate}_{count + 1}")

    data_rows = rows[1:] if len(rows) > 1 else []
    table_rows: list[dict[str, str]] = []
    for raw_row in data_rows[:max_rows]:
        mapped: dict[str, str] = {}
        for idx, col in enumerate(normalized):
            mapped[col] = raw_row[idx] if idx < len(raw_row) else ""
        table_rows.append(mapped)
    return normalized, table_rows


def _text_to_rows(text: str) -> list[list[str]]:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    delimiter = "\t" if any("\t" in line for line in lines[:10]) else ","
    rows: list[list[str]] = []
    for line in lines:
        rows.append([cell.strip() for cell in line.split(delimiter)])
    return rows


def _tabular_sources_from_attachments(prompt: str) -> list[dict]:
    sources: list[dict] = []
    for name, url, path in _attachment_entries(prompt):
        if path.suffix.lower() not in TABULAR_SUFFIXES:
            continue
        try:
            text = _extract_text_from_file(path)
        except Exception:
            continue
        if not text.strip():
            continue
        if path.suffix.lower() == ".json":
            json_rows = _json_rows_for_table(text)
            if not json_rows:
                continue
            columns = list(json_rows[0].keys())
            rows = json_rows
        else:
            columns, rows = _rows_to_table(_text_to_rows(text))
        if not columns or not rows:
            continue
        sources.append(
            {
                "source": name,
                "source_url": url,
                "columns": columns,
                "rows": rows,
            }
        )
    return sources


def _tabular_sources_from_gsheets(prompt: str) -> list[dict]:
    sources: list[dict] = []
    for url in _sheet_urls(prompt):
        try:
            raw_rows = read_sheet(url)
        except Exception:
            continue
        columns, rows = _rows_to_table(raw_rows)
        if not columns or not rows:
            continue
        sources.append(
            {
                "source": "Google Sheet",
                "source_url": url,
                "columns": columns,
                "rows": rows,
            }
        )
    return sources


def _collect_tabular_sources(prompt: str) -> list[dict]:
    return _tabular_sources_from_attachments(prompt) + _tabular_sources_from_gsheets(prompt)


def _tabular_preview(sources: list[dict], max_rows_per_source: int = 40) -> str:
    chunks: list[str] = []
    for idx, src in enumerate(sources, start=1):
        columns = src.get("columns", [])
        rows = src.get("rows", [])
        preview_rows = rows[:max_rows_per_source]
        chunks.append(
            json.dumps(
                {
                    "index": idx,
                    "source": src.get("source"),
                    "source_url": src.get("source_url"),
                    "columns": columns,
                    "rows": preview_rows,
                },
                ensure_ascii=True,
            )
        )
    return "\n".join(chunks)


def _ask_tabular_sources(
    *,
    client,
    llm_model: str,
    user_email: str,
    question: str,
    sources: list[dict],
) -> tuple[str, list[str], list[dict]]:
    source_by_name = {str(s.get("source")): s for s in sources}
    preview = _tabular_preview(sources)

    system_prompt = (
        "You answer questions using provided tabular data only. "
        "Return strict JSON object with keys: answer, source, columns, rows. "
        "rows must be an array of objects with keys from columns. "
        "Do not fabricate values. If data is insufficient, return empty columns and rows."
    )
    user_prompt = (
        f"Question:\n{question}\n\n"
        "Tabular sources (JSON lines):\n"
        f"{preview}\n\n"
        "Constraints:\n"
        "- Choose one best source for the answer and set it in 'source'.\n"
        "- Return at most 20 rows.\n"
        "- Keep answer concise."
    )

    resp = client.chat.completions.create(
        model=llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=1200,
        user=user_email,
        **_tracking_without_user("tabular_qa"),
    )
    raw = (resp.choices[0].message.content or "").strip()
    parsed: dict = {}
    try:
        parsed = json.loads(raw)
    except Exception:
        # Some providers wrap JSON in markdown fences.
        fenced = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            parsed = json.loads(fenced)
        except Exception:
            parsed = {}

    answer = str(parsed.get("answer") or "I could not compute a confident result from the spreadsheet data.")
    source_name = str(parsed.get("source") or "")
    columns = parsed.get("columns") if isinstance(parsed.get("columns"), list) else []
    rows = parsed.get("rows") if isinstance(parsed.get("rows"), list) else []

    if source_name in source_by_name and not columns:
        columns = source_by_name[source_name].get("columns", [])

    safe_rows: list[dict] = []
    for item in rows[:20]:
        if not isinstance(item, dict):
            continue
        if columns:
            safe_rows.append({col: item.get(col) for col in columns})
        else:
            safe_rows.append(item)

    if source_name:
        answer = f"{answer}\n\nSource: {source_name}"
    return answer, columns, safe_rows


def _index_attachments_for_rag(user_id: str, thread_id: str, prompt: str) -> None:
    entries = _attachment_entries(prompt)
    if not entries:
        return

    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []

    for name, url, path in entries:
        try:
            text = _extract_text_from_file(path).strip()
        except Exception:
            text = ""
        if not text:
            continue

        chunks = _chunk_text(text)
        for idx, chunk in enumerate(chunks):
            digest = hashlib.sha1(f"{thread_id}:{path.name}:{idx}:{chunk[:64]}".encode("utf-8")).hexdigest()
            ids.append(f"thr-{thread_id}-{digest}")
            docs.append(chunk)
            metas.append(
                {
                    "thread_id": thread_id,
                    "file_name": name,
                    "file_url": url,
                    "chunk_index": idx,
                }
            )

    if ids:
        upsert_documents(user_id=user_id, ids=ids, texts=docs, metadatas=metas)


def _retrieve_rag_context(user_id: str, thread_id: str, question: str, n_results: int = 5) -> str:
    try:
        res = rag_query(user_id=user_id, q=question, n=n_results, where={"thread_id": thread_id})
    except Exception:
        return ""

    docs = (res or {}).get("documents") or []
    metas = (res or {}).get("metadatas") or []
    if not docs or not docs[0]:
        return ""

    chunks = docs[0]
    chunk_metas = metas[0] if metas else [{} for _ in chunks]
    lines: list[str] = []
    for idx, chunk in enumerate(chunks):
        meta = chunk_metas[idx] if idx < len(chunk_metas) else {}
        name = meta.get("file_name", "attached-file") if isinstance(meta, dict) else "attached-file"
        lines.append(f"Source: {name}\n{chunk}")
    return "\n\n".join(lines)


def _build_attachment_context(prompt: str) -> str:
    matches = ATTACHMENT_LINK_RE.findall(prompt)
    if not matches:
        return ""

    snippets: list[str] = []
    for name, url in matches:
        file_path = _uploaded_path_from_url(url)
        if not file_path or not file_path.exists():
            continue
        try:
            text = _extract_text_from_file(file_path).strip()
        except Exception:
            text = ""
        if text:
            trimmed = text[:12000]
            snippets.append(
                f"File: {name}\n"
                f"Source: {url}\n"
                f"Extracted content:\n{trimmed}"
            )
        else:
            snippets.append(
                f"File: {name}\n"
                f"Source: {url}\n"
                f"Attachment context: {_media_attachment_note(file_path)}"
            )

    if not snippets:
        return ""
    return "\n\n".join(snippets)


def _prompt_with_attachment_context(prompt: str) -> str:
    attachment_context = _build_attachment_context(prompt)
    if not attachment_context:
        return prompt
    return (
        f"{prompt}\n\n"
        "Use the extracted attachment content below as primary context for your answer.\n\n"
        f"{attachment_context}"
    )


def _prompt_with_rag_context(user_id: str, thread_id: str, prompt: str) -> str:
    _index_attachments_for_rag(user_id=user_id, thread_id=thread_id, prompt=prompt)
    rag_context = _retrieve_rag_context(user_id=user_id, thread_id=thread_id, question=prompt)
    if not rag_context:
        return _prompt_with_attachment_context(prompt)
    return (
        f"{prompt}\n\n"
        "Use the following retrieved context from attached files to answer accurately. "
        "If context is insufficient, say what is missing.\n\n"
        f"{rag_context}"
    )


def _model_type(model_id: str) -> str:
    """Classify model usage so non-chat models use the correct API route."""
    lowered = model_id.lower()
    if "embedding" in lowered:
        return "embedding"
    if "imagen" in lowered or "/image" in lowered or "image-" in lowered:
        return "image"
    return "chat"


def _tracking_without_user(test_type: str) -> dict:
    """Use explicit end-user email while preserving LiteLLM metadata headers/body."""
    return {k: v for k, v in tracking_kwargs(test_type).items() if k != "user"}


def _uploads_dir() -> Path:
    path = Path(settings.UPLOAD_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _extension_from_content_type(content_type: str | None) -> str:
    if not content_type:
        return "png"
    ctype = content_type.lower()
    if "jpeg" in ctype or "jpg" in ctype:
        return "jpg"
    if "webp" in ctype:
        return "webp"
    if "gif" in ctype:
        return "gif"
    return "png"


def _save_generated_image(image_bytes: bytes, ext: str = "png") -> str:
    filename = f"gen_{uuid.uuid4().hex}.{ext}"
    path = _uploads_dir() / filename
    path.write_bytes(image_bytes)
    return f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}/uploads/{filename}"


def _decode_b64_image(b64_value: str) -> bytes | None:
    if not b64_value:
        return None
    payload = b64_value.split(",", 1)[1] if "," in b64_value else b64_value
    try:
        return base64.b64decode(payload)
    except Exception:
        return None


def _value_from_item(item, key: str):
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _bounded_history(history: list[dict[str, str]] | None, max_messages: int = _MEMORY_MAX_MESSAGES) -> list[dict[str, str]]:
    if not history:
        return []
    filtered = [
        {"role": str(m.get("role") or ""), "content": str(m.get("content") or "")}
        for m in history
        if isinstance(m, dict) and m.get("role") in {"user", "assistant"} and str(m.get("content") or "").strip()
    ]
    return filtered[-max_messages:]


def _history_without_attachment_context(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """Drop turns that include uploaded-file references when RAG is disabled."""
    if not history:
        return []
    cleaned: list[dict[str, str]] = []
    for msg in history:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "")
        if not role or not content.strip():
            continue
        low = content.lower()
        if "attached files:" in low:
            continue
        if ATTACHMENT_LINK_RE.search(content):
            continue
        if "/uploads/" in low:
            continue
        cleaned.append({"role": role, "content": content})
    return cleaned


def _is_memory_recall_query(question: str) -> bool:
    q = (question or "").lower()
    memory_patterns = (
        "what is my name",
        "what's my name",
        "who am i",
        "what is my company",
        "where do i work",
        "what did i say",
        "do you remember",
        "remember my",
        "my name",
        "my company",
    )
    return any(p in q for p in memory_patterns)


def _generate_assistant_reply(
    *,
    client,
    llm_model: str,
    user_email: str,
    history: list[dict[str, str]],
    prompt: str,
    raw_prompt: str | None = None,
    mode: str | None = None,
    use_rag: bool = True,
) -> str:
    """Generate assistant output for chat, image, or embedding models."""
    mtype = _model_type(llm_model)

    if mtype == "chat":
        mode_lower = (mode or "").lower()
        question = raw_prompt if isinstance(raw_prompt, str) else (prompt if isinstance(prompt, str) else str(prompt))
        bounded_history = _bounded_history(history)
        if not use_rag:
            bounded_history = _history_without_attachment_context(bounded_history)
        has_attachments = bool(_attachment_entries(question)) or bool(_history_attachment_entries(bounded_history))

        # ── Live data mode ─────────────────────────────────────────────────────
        # Triggered when mode="live" OR the query contains a recognised live keyword.
        lowered_question = question.lower()
        auto_live = any(kw in lowered_question for kw in _LIVE_AUTO_KEYWORDS)
        # Keep inline chat aligned with Live Agent behavior: if the query looks
        # like a web-search/live-information ask, route through live-data APIs
        # (DuckDuckGo primary, Tavily fallback) instead of plain model chat.
        try:
            auto_live = auto_live or api_service._is_search_related_query(question)
        except Exception:
            pass
        # Attachment-related questions should use attachment/RAG context first,
        # not live web-search routing.
        if has_attachments:
            auto_live = False
        # Personal recall/follow-up queries should use conversation memory,
        # not live web-search routing.
        if _is_memory_recall_query(question):
            auto_live = False
        if mode_lower != "sql" and (mode_lower == "live" or auto_live):
            answer: str | None = None

            # Multi-intent path: detect 2+ categories → targeted per-category fetch
            # → strict sectioned formatter (one section per intent, in order).
            try:
                intents = api_service.detect_multiple_intents(question)
            except Exception:
                intents = []

            try:
                if len(intents) >= 2:
                    multi_data = api_service.get_multi_intent_data(question)
                    if multi_data.get("success_count", 0) > 0:
                        answer = llm_service.ask_llm_multi_intent(
                            question, multi_data, user_email=user_email, model=llm_model
                        )
                elif len(intents) == 1:
                    # Single intent: fetch only its sources, then let the LLM
                    # reason over the data (and fall back to training knowledge
                    # when the data doesn't directly answer).
                    multi_data = api_service.get_multi_intent_data(question)
                    if multi_data.get("success_count", 0) > 0:
                        answer = llm_service.ask_llm(
                            question,
                            multi_data,
                            user_email=user_email,
                            model=llm_model,
                            history=bounded_history,
                        )
            except Exception:
                answer = None

            # Generic live fetch fallback (covers queries that didn't match any
            # intent but still contained a live keyword).
            if not answer:
                try:
                    live_data = api_service.get_live_data(question)
                    if live_data.get("has_data"):
                        answer = llm_service.ask_llm(
                            question,
                            live_data,
                            user_email=user_email,
                            model=llm_model,
                            history=bounded_history,
                        )
                except Exception:
                    answer = None

            # Sanity check: reject empty / "no data" / "I don't have" replies and
            # rescue them with a training-knowledge fallback so the user always
            # gets something useful.
            def _is_unhelpful(text: str | None) -> bool:
                if not text or not text.strip():
                    return True
                low = text.lower()
                bad_phrases = (
                    "i don't have real-time", "i do not have real-time",
                    "i don't have access to real-time", "no data found",
                    "i'm unable to provide real-time", "i am unable to provide real-time",
                    "i cannot access real-time", "data not available right now.\n\n[",
                    "i cannot provide the real-time", "i cannot provide real-time",
                    "my knowledge cutoff", "as of my knowledge cutoff",
                    "as of my last update", "i don't have the ability to access",
                    "please check a live", "please visit",
                )
                return any(p in low for p in bad_phrases)

            if _is_unhelpful(answer):
                try:
                    answer = llm_service.ask_llm_fallback(
                        question,
                        user_email=user_email,
                        model=llm_model,
                        history=bounded_history,
                    )
                except Exception as exc:
                    answer = (
                        "I couldn't reach the live data sources right now and the "
                        f"fallback model also failed ({exc}). Please try again."
                    )

            if answer:
                return answer
            # If we somehow still have no answer, fall through to normal chat below.

        # ── SQL / spreadsheet mode ─────────────────────────────────────────────
        if mode_lower == "sql":
            sql_model = llm_model if _model_type(llm_model) == "chat" else settings.LLM_MODEL
            question = raw_prompt if isinstance(raw_prompt, str) else (prompt if isinstance(prompt, str) else str(prompt))
            sheet_urls = _sheet_urls(question)

            tabular_sources = _collect_tabular_sources(question)
            if tabular_sources:
                answer, columns, rows = _ask_tabular_sources(
                    client=client,
                    llm_model=sql_model,
                    user_email=user_email,
                    question=question,
                    sources=tabular_sources,
                )
                if columns and rows:
                    table_rows = [[row.get(col) for col in columns] for row in rows]
                    return json.dumps(
                        {
                            "type": "table",
                            "title": "Spreadsheet Results",
                            "columns": columns,
                            "rows": table_rows,
                            "summary": answer,
                        }
                    )
                return json.dumps({"type": "text", "content": answer})

            if sheet_urls:
                try:
                    sa_email = service_account_email()
                except Exception:
                    sa_email = "<service-account-email-unavailable>"
                return json.dumps(
                    {
                        "type": "text",
                        "content": (
                            "I found a Google Sheet URL but could not read it. "
                            "Please either share the sheet with this service account (Viewer): "
                            f"{sa_email} "
                            "or set the sheet to public read access."
                        ),
                    }
                )

            sql, columns, rows = sql_service.ask_database(
                question=question,
                user_email=user_email,
                model=sql_model,
                limit=100,
            )
            if not rows:
                return json.dumps(
                    {
                        "type": "text",
                        "content": f"No rows returned. Generated SQL: {sql}",
                    }
                )

            table_rows = []
            for row in rows:
                table_rows.append([row.get(col) for col in columns])

            return json.dumps(
                {
                    "type": "table",
                    "title": "Database Results",
                    "columns": columns,
                    "rows": table_rows,
                }
            )

        return generate_chart_or_text_response(client, llm_model, user_email, prompt, history=bounded_history)

    if mtype == "image":
        # Some LiteLLM proxies register Imagen under a different alias than the
        # canonical Vertex name. Try a couple of common variants before giving
        # up so the user sees a useful image instead of a confusing 404.
        candidate_models: list[str] = []
        seen: set[str] = set()
        for cand in (
            llm_model,
            llm_model.split("/", 1)[1] if "/" in llm_model else llm_model,
            f"vertex_ai/{llm_model.split('/', 1)[1]}" if "/" in llm_model else llm_model,
            settings.IMAGE_GEN_MODEL,
        ):
            if cand and cand not in seen:
                seen.add(cand)
                candidate_models.append(cand)

        last_error: Exception | None = None
        img_resp = None
        used_model = llm_model
        for cand in candidate_models:
            try:
                img_resp = client.images.generate(
                    model=cand,
                    prompt=prompt,
                    user=user_email,
                    **_tracking_without_user("image"),
                )
                used_model = cand
                break
            except Exception as exc:  # noqa: BLE001 — surface any provider error
                last_error = exc
                continue

        if img_resp is None:
            # All candidates failed — return the proxy's own message verbatim so
            # the user can see exactly why (404 model_not_found / 401 / etc.).
            tried = ", ".join(candidate_models)
            return (
                f"Image generation failed for `{llm_model}` "
                f"(also tried: {tried}).\n\nError: {last_error}"
            )

        first = img_resp.data[0] if img_resp.data else None
        if not first:
            return f"Image generation failed: no data returned by {used_model}"

        # Some providers return base64 image content.
        b64_image = _value_from_item(first, "b64_json")
        image_bytes = _decode_b64_image(b64_image) if b64_image else None
        if image_bytes:
            local_url = _save_generated_image(image_bytes, "png")
            return (
                f"Generated image using {used_model}.\n\n"
                f"![Generated image]({local_url})\n\n"
                f"[Open image]({local_url})"
            )

        # Some providers return a URL; fetch and store locally for reliable rendering.
        image_url = _value_from_item(first, "url")
        if image_url:
            try:
                with httpx.Client(timeout=30.0, follow_redirects=True) as http_client:
                    fetched = http_client.get(image_url)
                    fetched.raise_for_status()
                ext = _extension_from_content_type(fetched.headers.get("content-type"))
                local_url = _save_generated_image(fetched.content, ext)
                return (
                    f"Generated image using {used_model}.\n\n"
                    f"![Generated image]({local_url})\n\n"
                    f"[Open image]({local_url})"
                )
            except Exception:
                # Fallback to direct provider URL if proxy-download fails.
                return (
                    f"Generated image using {used_model}.\n\n"
                    f"![Generated image]({image_url})\n\n"
                    f"[Open image]({image_url})"
                )

        return (
            f"Image generation completed using {used_model}, but no displayable image payload was returned."
        )

    emb_resp = client.embeddings.create(
        model=llm_model,
        input=prompt,
        user=user_email,
        **_tracking_without_user("embedding"),
    )
    vector = emb_resp.data[0].embedding if emb_resp.data else []
    dims = len(vector)
    preview = ", ".join(f"{v:.4f}" for v in vector[:8])
    ellipsis = ", ..." if dims > 8 else ""
    return (
        f"Generated embedding using {llm_model}.\n\n"
        f"Vector dimensions: {dims}\n"
        f"Preview: [{preview}{ellipsis}]"
    )


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
    mode: str | None = None,
    use_rag: bool = True,
) -> tuple[ChatThread, ChatMessageRow, ChatMessageRow]:
    """Persist user message, call LLM with full history, persist assistant reply."""
    thread = await get_thread(db, user, thread_id)
    is_first = len(thread.messages) == 0

    user_msg = await _save_message(db, thread, "user", content)

    history = [{"role": m.role, "content": m.content} for m in thread.messages]
    history.append({"role": "user", "content": content})
    # RAG OFF must behave like plain LLM chat with no document-memory bleed.
    # Use a clean context for generation to avoid reusing earlier PDF-derived replies.
    generation_history = history[:-1] if use_rag else []

    client = get_llm_client()
    llm_model = model or settings.LLM_MODEL
    effective_prompt = _build_user_content(
        user_id=str(user.id),
        thread_id=str(thread.id),
        prompt=content,
        use_rag=use_rag,
        history=generation_history,
    )
    try:
        reply = _generate_assistant_reply(
            client=client,
            llm_model=llm_model,
            user_email=user.email,
            history=generation_history,
            prompt=effective_prompt,
            raw_prompt=content,
            mode=mode,
            use_rag=use_rag,
        )
    except Exception as exc:
        reply = (
            f"Model '{llm_model}' could not complete this request. "
            f"Details: {exc}"
        )

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
    mode: str | None = None,
    use_rag: bool = True,
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
    generation_history = history[:-1] if use_rag else []

    # Generate new assistant response
    client = get_llm_client()
    llm_model = model or settings.LLM_MODEL
    effective_prompt = _build_user_content(
        user_id=str(user.id),
        thread_id=str(thread.id),
        prompt=new_content,
        use_rag=use_rag,
        history=generation_history,
    )
    try:
        reply = _generate_assistant_reply(
            client=client,
            llm_model=llm_model,
            user_email=user.email,
            history=generation_history,
            prompt=effective_prompt,
            raw_prompt=new_content,
            mode=mode,
            use_rag=use_rag,
        )
    except Exception as exc:
        reply = (
            f"Model '{llm_model}' could not complete this request. "
            f"Details: {exc}"
        )

    await _save_message(db, thread, "assistant", reply)

    # Refresh and return
    await db.refresh(thread, ["messages"])
    return thread


async def suggest_follow_ups(
    db: AsyncSession,
    user: User,
    thread_id: uuid.UUID,
    model: str | None = None,
) -> list[str]:
    """Generate 4 context-aware follow-up suggestions based on the recent chat history.

    Uses the LLM with the last few exchanges as context. If the call fails or returns
    nothing usable, returns a small set of generic prompts as a graceful fallback.
    """
    thread = await get_thread(db, user, thread_id)
    if not thread.messages:
        return []

    # Take the last 6 messages (3 exchanges) — enough context, low token cost.
    recent = thread.messages[-6:]
    transcript_lines: list[str] = []
    for m in recent:
        role = "User" if m.role == "user" else "Assistant"
        text = (m.content or "").strip()
        # Truncate any one message at 800 chars so a giant code dump doesn't dominate.
        if len(text) > 800:
            text = text[:800] + "…"
        transcript_lines.append(f"{role}: {text}")
    transcript = "\n\n".join(transcript_lines)

    system_prompt = (
        "You generate short, helpful next-question suggestions for a chat user, "
        "in the same style as Codex/Claude/Gemini.\n"
        "STRICT OUTPUT RULES:\n"
        "- Output EXACTLY 4 lines, each containing one suggestion.\n"
        "- No preamble, no numbering, no bullets, no dashes, no quotes, no "
        "  markdown, no code fences. Just the 4 plain question lines.\n"
        "- Each line must be a direct, natural question or instruction the user "
        "  might plausibly ask next, given the conversation topic.\n"
        "- Each line must be <= 90 characters.\n"
        "- Suggestions must be RELEVANT to the recent conversation. If the topic "
        "  is weather, suggest weather follow-ups. If it's cricket, suggest "
        "  cricket follow-ups. If it's code, suggest code follow-ups. NEVER mix.\n"
        "- Do not repeat questions already asked verbatim in the conversation."
    )

    client = get_llm_client()
    chosen = model or settings.LLM_MODEL
    try:
        resp = client.chat.completions.create(
            model=chosen,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": (
                    f"Recent conversation:\n\n{transcript}\n\n"
                    "Generate 4 follow-up suggestions now (4 lines, plain text, no markup):"
                )},
            ],
            temperature=0.6,
            max_tokens=400,
            **tracking_kwargs("follow_up_suggestions"),
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception:
        return _generic_follow_ups(thread.messages[-1].content if thread.messages else "")

    suggestions: list[str] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip common decoration the model may add: bullets, numbering, quotes.
        line = re.sub(r"^\s*(?:[\-\*\u2022\u00b7]|\d+\s*[\.\)])\s*", "", line)
        line = line.strip().strip("\"'`*_")
        if not line or len(line) < 5:
            continue
        # Skip lines that look like preamble/explanation rather than a question.
        low = line.lower()
        if low.startswith(("here are", "here's", "sure", "of course", "based on")):
            continue
        if line in seen:
            continue
        seen.add(line)
        if len(line) > 140:
            line = line[:140].rstrip() + "…"
        suggestions.append(line)
        if len(suggestions) >= 4:
            break

    if not suggestions:
        return _generic_follow_ups(thread.messages[-1].content if thread.messages else "")

    # If the model produced fewer than 4 valid lines, top up with topic-aware
    # generic suggestions so the UI always has a useful set.
    if len(suggestions) < 4:
        last = thread.messages[-1].content if thread.messages else ""
        for extra in _generic_follow_ups(last):
            if extra not in suggestions:
                suggestions.append(extra)
            if len(suggestions) >= 4:
                break

    return suggestions[:4]


def _generic_follow_ups(last_message: str) -> list[str]:
    """Tiny topic-aware default set used when the LLM call fails."""
    text = (last_message or "").lower()
    if "```" in text or " code" in text or "python" in text or "function" in text:
        return [
            "Can you optimize this and explain the time complexity?",
            "Add edge-case handling and tests.",
            "Convert this to TypeScript.",
            "Walk me through the code line by line.",
        ]
    if "weather" in text or "temperature" in text or "°c" in text:
        return [
            "What about tomorrow's forecast?",
            "Will it rain today?",
            "Show the weekly forecast.",
            "Compare this with another city.",
        ]
    if "bitcoin" in text or "crypto" in text or "usd" in text:
        return [
            "How has the price moved this week?",
            "Compare Bitcoin and Ethereum.",
            "What are the current gas fees?",
            "Show top 10 cryptocurrencies by market cap.",
        ]
    if "match" in text or "cricket" in text or "score" in text:
        return [
            "Show the full scorecard.",
            "Who are the top run scorers this season?",
            "When is the next match?",
            "Show the points table.",
        ]
    return [
        "Can you explain that in simpler terms?",
        "Summarise this in 5 bullet points.",
        "What should I do next, step by step?",
        "Show this as a table.",
    ]
