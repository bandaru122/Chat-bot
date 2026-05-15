"""Business logic for DataFrame question-answering via LangChain pandas agent."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.services.sheets_service import read_sheet


def ask_dataframe(
    *,
    question: str,
    user_email: str,
    model: str | None,
    google_sheet_url: str | None,
    worksheet: str,
    uploaded_file_url: str | None,
    max_rows: int,
) -> dict:
    dataframe, source = _load_dataframe(
        google_sheet_url=google_sheet_url,
        worksheet=worksheet,
        uploaded_file_url=uploaded_file_url,
        max_rows=max_rows,
    )

    llm = ChatOpenAI(
        model=model or settings.LLM_MODEL,
        base_url=settings.LITELLM_PROXY_URL,
        api_key=settings.LITELLM_API_KEY,
        timeout=60,
        max_retries=2,
        temperature=0,
    )
    agent = create_pandas_dataframe_agent(
        llm,
        dataframe,
        verbose=False,
        return_intermediate_steps=True,
        allow_dangerous_code=True,
    )

    result = agent.invoke(
        {"input": question},
        config={"metadata": {"user_email": user_email}},
    )

    answer = str(result.get("output") or "No answer generated.")
    steps = _format_intermediate_steps(result.get("intermediate_steps"))

    return {
        "answer": answer,
        "row_count": int(len(dataframe.index)),
        "columns": [str(c) for c in dataframe.columns.tolist()],
        "source": source,
        "intermediate_steps": steps,
    }


def _load_dataframe(
    *,
    google_sheet_url: str | None,
    worksheet: str,
    uploaded_file_url: str | None,
    max_rows: int,
) -> tuple[pd.DataFrame, str]:
    if uploaded_file_url:
        path = _uploaded_path_from_url(uploaded_file_url)
        suffix = path.suffix.lower()
        if suffix == ".csv":
            df = pd.read_csv(path)
        elif suffix in {".xlsx", ".xls"}:
            df = pd.read_excel(path)
        else:
            raise ValueError("Only .csv, .xlsx and .xls files are supported")
        return _cap_rows(df, max_rows), path.name

    if not google_sheet_url:
        raise ValueError("google_sheet_url or uploaded_file_url is required")

    ws: str | int = int(worksheet) if worksheet.isdigit() else worksheet
    rows = read_sheet(google_sheet_url, ws)
    if not rows:
        raise ValueError("Google Sheet has no rows")

    headers = _normalize_headers(rows[0])
    body = rows[1:] if len(rows) > 1 else []
    frame = pd.DataFrame(body, columns=headers)
    return _cap_rows(frame, max_rows), "google-sheet"


def _uploaded_path_from_url(file_url: str) -> Path:
    parsed = urlparse(file_url)
    name = Path(parsed.path).name
    if not name:
        raise ValueError("Invalid uploaded_file_url")

    upload_path = Path(settings.UPLOAD_DIR) / name
    if not upload_path.exists():
        raise ValueError("Uploaded file not found on server")
    return upload_path


def _normalize_headers(raw_headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for idx, value in enumerate(raw_headers):
        candidate = re.sub(r"\s+", "_", (value or "").strip())
        candidate = re.sub(r"[^0-9a-zA-Z_]", "", candidate) or f"col_{idx + 1}"
        count = seen.get(candidate, 0)
        seen[candidate] = count + 1
        out.append(candidate if count == 0 else f"{candidate}_{count + 1}")
    return out


def _cap_rows(df: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    safe_limit = max(1, min(max_rows, 5000))
    return df.head(safe_limit).copy()


def _format_intermediate_steps(raw_steps: object) -> list[str]:
    if not isinstance(raw_steps, list):
        return []

    formatted: list[str] = []
    for item in raw_steps:
        try:
            action, observation = item
            tool = getattr(action, "tool", "tool")
            tool_input = getattr(action, "tool_input", "")
            formatted.append(
                f"tool={tool}; input={tool_input}; observation={str(observation)[:500]}"
            )
        except Exception:
            formatted.append(str(item)[:500])
    return formatted
