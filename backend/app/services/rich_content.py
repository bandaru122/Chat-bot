"""Helpers for rich-content responses such as chart/table/text JSON payloads."""

from typing import Any

from app.ai.llm import tracking_kwargs

STRUCTURED_RESPONSE_PROMPT = """You are a smart assistant for a web app.

Classify user intent using these rules:
- If the user asks for comparisons, statistics, or top items: return a chart JSON object.
- If the user asks for rankings, standings, or points table: return a table JSON object.
- Otherwise: return a text JSON object.

Output formats:

For chart:
{
    "type": "chart",
    "chartType": "bar",
    "title": "string",
    "labels": [],
    "data": [],
    "xAxisLabel": "",
    "yAxisLabel": ""
}

For table:
{
    "type": "table",
    "title": "string",
    "columns": [],
    "rows": []
}

For text:
{
    "type": "text",
    "content": "string"
}

Guidelines:
- Use realistic sample data if real data is not available.
- If attachment context (files/images) is present in the user input, use it directly.
- Do not say you are unable to view/interpret images when image context is provided.
- Keep output simple and valid JSON.
- Do not output markdown, backticks, or explanation text outside JSON.
- If unsure, return type=text.
"""


def is_visualization_request(user_query: str) -> bool:
    lowered = user_query.lower()
    chart_keywords = (
        "comparison",
        "compare",
        "statistics",
        "stats",
        "top",
    )
    table_keywords = (
        "ranking",
        "rankings",
        "standings",
        "points table",
    )
    return any(keyword in lowered for keyword in chart_keywords + table_keywords)


def generate_chart_or_text_response(
    client,
    llm_model: str,
    user_email: str,
    user_query: Any,
    history: list[dict[str, Any]] | None = None,
) -> str:
    messages: list[dict[str, Any]] = [{"role": "system", "content": STRUCTURED_RESPONSE_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_query})

    response = client.chat.completions.create(
        model=llm_model,
        messages=messages,
        max_tokens=800,
        temperature=0.2,
        user=user_email,
        **{k: v for k, v in tracking_kwargs("structured").items() if k != "user"},
    )
    return response.choices[0].message.content or ""
