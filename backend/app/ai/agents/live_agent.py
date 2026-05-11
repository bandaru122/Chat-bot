"""Zero-shot ReAct agent over live-data tools.

Why this file exists
--------------------
The chat backend already has reliable, deterministic live-data fetchers in
`app.services.api_service` (weather, crypto, news, etc.). This module gives the
LLM autonomy to *decide* which of those fetchers to call — and call several of
them when the user asks a multi-part question — without any if/else routing.

Design rules followed
---------------------
* Tool count is **deliberately focused** (6 tools — weather, crypto, news,
  sports, stocks, mutual_fund) so the agent has one tool per live-data
  intent the chat backend already supports. More tools => worse selection
  accuracy, so we stop here.
* Tool descriptions are **action-oriented and explicit** about when to use the
  tool, what the input shape is, and what the output looks like. The agent
  picks tools based on these descriptions, so they are the most important
  prompt surface.
* The agent uses LangChain's classic `initialize_agent` with
  `AgentType.ZERO_SHOT_REACT_DESCRIPTION`, exactly as required by the spec.
* All LLM calls go through the LiteLLM proxy (`get_chat_llm()`).
* Intermediate steps (Thought / Action / Observation) are surfaced both in the
  HTTP response body and as Server-Sent-Events for the UI's "AI is thinking…"
  panel.
"""
from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any, AsyncIterator, Callable, Iterator

from langchain.agents import AgentExecutor, AgentType, initialize_agent
from langchain.callbacks.base import BaseCallbackHandler
from langchain_core.tools import tool

from app.ai.llm import get_chat_llm
from app.services import api_service
from app.services import mcp_tools_service


# ──────────────────────────────────────────────────────────────────────────────
# Per-request user-email context — `@tool` callables take only their declared
# arguments, so we stash the authenticated email on a thread-local and read it
# from the MCP-style tools (send_email / create_reminder / send_notification)
# for audit-logging. Set in `build_agent_executor`.
# ──────────────────────────────────────────────────────────────────────────────
_current_user_email = threading.local()


def _get_user_email() -> str | None:
    return getattr(_current_user_email, "value", None)


# ──────────────────────────────────────────────────────────────────────────────
# Tools — keep the set small and the descriptions sharp.
# ──────────────────────────────────────────────────────────────────────────────


@tool("get_weather", return_direct=False)
def get_weather(city: str) -> str:
    """Get the current weather AND short-term forecast for a single named city.

    Use this whenever the user asks about temperature, weather, rain, humidity,
    climate, or forecast (today, tomorrow, or the next couple of days) for a
    specific place. The tool returns current conditions plus a 3-day daily
    forecast including the maximum probability of rain per day, so it CAN
    answer questions like "chance of rain tomorrow in <city>".

    Args:
        city: A city name (e.g. "Visakhapatnam", "Mumbai", "London"). Pass only
            the city name — do not include the word "weather" or any punctuation.

    Returns:
        A short human-readable string with current temperature/wind/humidity
        plus a per-day forecast (today, tomorrow, day-after) with min/max
        temperature and the maximum chance of rain for each day. Source is
        Open-Meteo. Returns an error string if the city cannot be resolved.
    """
    if not city or not city.strip():
        return "ERROR: city name is required."
    result = api_service._weather_for_query(f"weather in {city.strip()}")
    if not result.get("ok"):
        return f"ERROR: weather lookup failed ({result.get('error')}: {result.get('message')})."

    data = result.get("data") or {}
    cw = data.get("current_weather") or {}
    location = data.get("location_name") or city
    parts: list[str] = [f"Current weather in {location}"]
    if cw.get("temperature") is not None:
        parts.append(f"temperature {cw['temperature']}°C")
    if cw.get("windspeed") is not None:
        parts.append(f"wind {cw['windspeed']} km/h")

    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    cw_time = cw.get("time")
    if cw_time and cw_time in times:
        idx = times.index(cw_time)
        humidity_arr = hourly.get("relative_humidity_2m") or []
        precip_arr = hourly.get("precipitation_probability") or []
        if idx < len(humidity_arr) and humidity_arr[idx] is not None:
            parts.append(f"humidity {humidity_arr[idx]}%")
        if idx < len(precip_arr) and precip_arr[idx] is not None:
            parts.append(f"current rain chance {precip_arr[idx]}%")

    current_line = ", ".join(parts) + "."

    # Per-day forecast: today / tomorrow / day after, with max rain probability.
    daily = data.get("daily") or {}
    d_times = daily.get("time") or []
    tmaxs = daily.get("temperature_2m_max") or []
    tmins = daily.get("temperature_2m_min") or []
    pmax = daily.get("precipitation_probability_max") or []
    psum = daily.get("precipitation_sum") or []
    labels = ["Today", "Tomorrow", "Day after"]
    forecast_lines: list[str] = []
    for i, label in enumerate(labels):
        if i >= len(d_times):
            break
        bits: list[str] = []
        if i < len(tmins) and i < len(tmaxs) and tmins[i] is not None and tmaxs[i] is not None:
            bits.append(f"{tmins[i]}°C – {tmaxs[i]}°C")
        if i < len(pmax) and pmax[i] is not None:
            bits.append(f"chance of rain {pmax[i]}%")
        if i < len(psum) and psum[i] is not None:
            bits.append(f"precipitation {psum[i]} mm")
        if bits:
            forecast_lines.append(f"  - {label} ({d_times[i]}): " + ", ".join(bits))

    if forecast_lines:
        current_line += "\nForecast:\n" + "\n".join(forecast_lines)

    return current_line + "\n(source: Open-Meteo)"


@tool("get_crypto", return_direct=False)
def get_crypto(symbol: str) -> str:
    """Get the current USD price for a cryptocurrency.

    Use this for any question about a coin's price, value, or how much it
    costs right now (Bitcoin, Ethereum, etc.).

    Args:
        symbol: Coin name or ticker, e.g. "bitcoin", "btc", "ethereum", "eth".

    Returns:
        A human-readable string with the current USD price, or an error message
        if the price cannot be fetched.

    Note:
        The underlying CoinGecko endpoint currently exposes Bitcoin only; other
        symbols will fall back to Bitcoin until the source is expanded.
    """
    sym = (symbol or "").strip().lower()
    if not sym:
        return "ERROR: symbol is required."
    result = api_service._bitcoin_price()
    if not result.get("ok"):
        return f"ERROR: crypto lookup failed ({result.get('error')}: {result.get('message')})."
    data = result.get("data") or {}
    btc = data.get("bitcoin") or {}
    price = btc.get("usd")
    if price is None:
        return "ERROR: price not present in CoinGecko response."
    label = "Bitcoin" if sym in {"bitcoin", "btc"} else f"Bitcoin (closest available match for '{symbol}')"
    return f"{label} is currently ${price:,} USD (source: CoinGecko)."


@tool("get_news", return_direct=False)
def get_news(topic: str = "") -> str:
    """Get the latest news headlines, optionally filtered by topic.

    Use this whenever the user asks for news, headlines, top stories, breaking
    news, or news about a specific subject (e.g. "iran usa war", "ai regulation").

    Args:
        topic: Optional free-text topic. Pass an empty string to get general
            top headlines for India.

    Returns:
        A newline-separated list of up to 5 headline-source pairs, or an error
        message if no news source could be reached.
    """
    topic_clean = (topic or "").strip()
    sources: dict[str, dict] = {}

    if topic_clean:
        sources["thenewsapi_topic_search"] = api_service._thenews_topic_search(topic_clean)

    sources["rss_the_hindu_news"] = api_service._rss_the_hindu()
    sources["rss_ndtv_india_news"] = api_service._rss_ndtv()
    sources["thenewsapi_top_india"] = api_service._thenews_top_india()

    seen: set[str] = set()
    bullets: list[str] = []

    def add(items: list, label: str) -> None:
        for item in items:
            if len(bullets) >= 5:
                return
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            if not title or title.lower() in seen:
                continue
            seen.add(title.lower())
            bullets.append(f"{len(bullets) + 1}. {title} — {label}")

    if topic_clean:
        topic_data = (sources.get("thenewsapi_topic_search") or {}).get("data") or {}
        add(topic_data.get("data") or [], f"TheNewsAPI ({topic_clean})")
    add(((sources.get("rss_the_hindu_news") or {}).get("data") or {}).get("items") or [], "The Hindu")
    add(((sources.get("rss_ndtv_india_news") or {}).get("data") or {}).get("items") or [], "NDTV")
    add(((sources.get("thenewsapi_top_india") or {}).get("data") or {}).get("data") or [], "TheNewsAPI India")

    if not bullets:
        # Web-search fallback chain:
        # 1) DuckDuckGo (preferred/unmetered)
        # 2) Tavily (metered, only when DDG and all native sources are empty)
        ddg = api_service._duckduckgo_search(topic_clean or "latest news")
        ddg_items = ((ddg.get("data") or {}).get("results") or []) if ddg.get("ok") else []
        add(ddg_items, "DuckDuckGo")

    if not bullets:
        tav = api_service._tavily_search(topic_clean or "latest news")
        tav_items = ((tav.get("data") or {}).get("results") or []) if tav.get("ok") else []
        add(tav_items, "Tavily")

    if not bullets:
        return "ERROR: no news source returned data right now."
    header = f"Top headlines{(' for ' + topic_clean) if topic_clean else ''}:"
    return header + "\n" + "\n".join(bullets)


@tool("get_sports", return_direct=False)
def get_sports(query: str = "") -> str:
    """Get today's cricket matches and currently-live cricket scores.

    Use this whenever the user asks about cricket, IPL, matches, scores,
    fixtures, or "what's happening in sports today". Covers BOTH today's
    scheduled events AND any matches that are currently live.

    Args:
        query: Optional free-text hint (e.g. "ipl today", "live cricket score").
            Currently used only for logging — the underlying APIs return all
            cricket events for today.

    Returns:
        A multi-line string listing today's matches and any currently-live
        cricket scores, with source attribution. Returns an error string if
        no sports data source could be reached.
    """
    _ = query  # accepted for ReAct symmetry
    lines: list[str] = []
    q_low = (query or "").lower()
    prioritize_web = any(token in q_low for token in ["yesterday", "last", "result", "results", "score", "scores", "ipl"])

    def _append_web_updates(search_query: str) -> bool:
        ddg = api_service._duckduckgo_search(search_query)
        ddg_rows = ((ddg.get("data") or {}).get("results") or []) if ddg.get("ok") else []
        if ddg_rows:
            def _row_score(item: dict) -> int:
                text = f"{item.get('title') or ''} {item.get('snippet') or item.get('content') or ''}".lower()
                score = 0
                if any(t in text for t in ["yesterday", "last match", "match result", "results", "who won", "highlights", "scorecard"]):
                    score += 6
                if any(t in text for t in ["today", "live score", "live cricket score"]):
                    score -= 3
                return score

            ranked = [r for r in ddg_rows if isinstance(r, dict)]
            if prioritize_web:
                ranked.sort(key=_row_score, reverse=True)

            lines.append("Live sports updates (DuckDuckGo):")
            for item in ranked[:6]:
                if not isinstance(item, dict):
                    continue
                title = (item.get("title") or "Match update").strip()
                snippet = (item.get("snippet") or item.get("content") or "").strip()
                url = (item.get("url") or "").strip()
                line = f"- {title}"
                if snippet:
                    line += f": {snippet[:160]}"
                if url:
                    line += f" ({url})"
                lines.append(line)
            return True

        tav = api_service._tavily_search(search_query)
        tav_rows = ((tav.get("data") or {}).get("results") or []) if tav.get("ok") else []
        if tav_rows:
            def _row_score(item: dict) -> int:
                text = f"{item.get('title') or ''} {item.get('snippet') or item.get('content') or ''}".lower()
                score = 0
                if any(t in text for t in ["yesterday", "last match", "match result", "results", "who won", "highlights", "scorecard"]):
                    score += 6
                if any(t in text for t in ["today", "live score", "live cricket score"]):
                    score -= 3
                return score

            ranked = [r for r in tav_rows if isinstance(r, dict)]
            if prioritize_web:
                ranked.sort(key=_row_score, reverse=True)

            lines.append("Live sports updates (Tavily):")
            for item in ranked[:6]:
                if not isinstance(item, dict):
                    continue
                title = (item.get("title") or "Match update").strip()
                snippet = (item.get("snippet") or item.get("content") or "").strip()
                url = (item.get("url") or "").strip()
                line = f"- {title}"
                if snippet:
                    line += f": {snippet[:160]}"
                if url:
                    line += f" ({url})"
                lines.append(line)
            return True
        return False

    if prioritize_web:
        if _append_web_updates((query or "yesterday IPL match results").strip()):
            return "\n".join(lines)

    ev = api_service._sports_events_today()
    if ev.get("ok"):
        events = ((ev.get("data") or {}).get("events")) or []
        bullets: list[str] = []
        for item in events[:5]:
            if not isinstance(item, dict):
                continue
            title = item.get("strEvent") or "Match"
            date = item.get("dateEvent") or ""
            t = item.get("strTime") or ""
            status = item.get("strStatus") or ""
            bullet = f"- {title} {date} {t} {status}".strip()
            if bullet:
                bullets.append(bullet)
        if bullets:
            lines.append("Today's cricket matches (TheSportsDB):")
            lines.extend(bullets)

    cm = api_service._cricapi_current_matches()
    if cm.get("ok"):
        items = ((cm.get("data") or {}).get("data")) or []
        bullets = []
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or "Match"
            status = item.get("status") or ""
            bullet = f"- {name} — {status}".strip(" —")
            if bullet:
                bullets.append(bullet)
        if bullets:
            if lines:
                lines.append("")
            lines.append("Currently-live matches (CricAPI):")
            lines.extend(bullets)

    if not lines:
        _append_web_updates((query or "latest IPL cricket score today").strip())

    if not lines:
        return "ERROR: no sports data source returned data right now."
    return "\n".join(lines)


@tool("get_stocks", return_direct=False)
def get_stocks(query: str = "") -> str:
    """Get the latest equity-market snapshot for India.

    Use this whenever the user asks about stocks, share price, Reliance, Nifty,
    Sensex, the stock market, or general market headlines. The tool returns
    the live Reliance (RELIANCE.NS) price plus a few headline market news
    bullets from Economic Times / Moneycontrol.

    Args:
        query: Optional free-text hint (e.g. "reliance share price", "nifty
            today"). Currently informational — the underlying APIs return a
            fixed snapshot.

    Returns:
        A multi-line string with the Reliance price and recent market headlines,
        each with source attribution. Returns an error string if no source
        could be reached.
    """
    _ = query  # accepted for ReAct symmetry
    lines: list[str] = []

    yh = api_service._yahoo_reliance()
    if yh.get("ok"):
        chart = (yh.get("data") or {}).get("chart") or {}
        result = chart.get("result") or []
        if result and isinstance(result[0], dict):
            meta = result[0].get("meta") or {}
            symbol = meta.get("symbol", "RELIANCE.NS")
            currency = meta.get("currency", "INR")
            price = meta.get("regularMarketPrice")
            if price is not None:
                lines.append(f"{symbol}: {price} {currency} (source: Yahoo Finance)")

    for key, fetch, label in (
        ("rss_economic_times_markets", api_service._rss_economic_times, "Economic Times"),
        ("rss_moneycontrol_finance", api_service._rss_moneycontrol, "Moneycontrol"),
    ):
        feed = fetch()
        if not feed.get("ok"):
            continue
        items = ((feed.get("data") or {}).get("items")) or []
        titles = [i.get("title") for i in items[:3] if isinstance(i, dict) and i.get("title")]
        if titles:
            if lines:
                lines.append("")
            lines.append(f"Latest market headlines ({label}):")
            lines.extend(f"- {t}" for t in titles)
            break  # one feed of headlines is enough

    if not lines:
        return "ERROR: no stock-market data source returned data right now."
    return "\n".join(lines)


@tool("get_mutual_fund", return_direct=False)
def get_mutual_fund(query: str = "") -> str:
    """Get mutual-fund information and recent mutual-fund news.

    Use this whenever the user asks about mutual funds, MF NAV, MF schemes,
    or mutual-fund news. Returns the count of indexed schemes from mfapi.in
    plus up to 3 recent mutual-fund headlines.

    Args:
        query: Optional free-text hint (e.g. "best mutual fund 2026"). Currently
            informational.

    Returns:
        A multi-line string with the scheme count and recent MF headlines, each
        with source attribution. Returns an error string if no source could
        be reached.
    """
    _ = query
    lines: list[str] = []

    mf = api_service._mutual_fund_master()
    if mf.get("ok"):
        data = mf.get("data") or []
        if isinstance(data, list) and data:
            lines.append(f"Mutual fund master list: {len(data):,} schemes indexed (source: mfapi.in)")

    nf = api_service._thenews_search_mutual_fund()
    if nf.get("ok"):
        items = ((nf.get("data") or {}).get("data")) or []
        titles = [i.get("title") for i in items[:3] if isinstance(i, dict) and i.get("title")]
        if titles:
            if lines:
                lines.append("")
            lines.append("Recent mutual-fund news (TheNewsAPI):")
            lines.extend(f"- {t}" for t in titles)

    if not lines:
        return "ERROR: no mutual-fund data source returned data right now."
    return "\n".join(lines)


@tool("web_search", return_direct=False)
def web_search(query: str) -> str:
    """Search the web for any topic that domain tools do not cover.

    Use this for commodity prices (gold/silver), geopolitics/war updates, and
    any "latest" topic where dedicated APIs are empty. Provider chain:
      1) DuckDuckGo first (preferred/unmetered)
      2) Tavily fallback only when DuckDuckGo has no results

    Args:
        query: The natural-language search query.

    Returns:
        Up to 6 concise search results with title/snippet/link, or ERROR.
    """
    q = (query or "").strip()
    if not q:
        return "ERROR: query is required."

    ddg = api_service._duckduckgo_search(q)
    rows = ((ddg.get("data") or {}).get("results") or []) if ddg.get("ok") else []
    provider = "DuckDuckGo"

    if not rows:
        tav = api_service._tavily_search(q)
        rows = ((tav.get("data") or {}).get("results") or []) if tav.get("ok") else []
        provider = "Tavily"

    if not rows:
        return "ERROR: no web-search results available right now."

    lines = [f"Top results ({provider}):"]
    for i, item in enumerate(rows[:6], start=1):
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "Untitled").strip()
        snippet = (item.get("snippet") or item.get("content") or "").strip()
        url = (item.get("url") or "").strip()
        lines.append(f"{i}. {title}")
        if snippet:
            lines.append(f"   {snippet[:180]}")
        if url:
            lines.append(f"   {url}")
    return "\n".join(lines)


# Module-level tool list so the executor (and any future tests) share one
# source of truth. Kept intentionally focused — one tool per intent category
# the inline chat already supports.
TOOLS = [
    get_weather,
    get_crypto,
    get_news,
    get_sports,
    get_stocks,
    get_mutual_fund,
    web_search,
]


# ──────────────────────────────────────────────────────────────────────────────
# MCP-style assistant tools — email, reminders, notifications.
# Side-effecting tools live behind `mcp_tools_service` so the agent can be
# unit-tested by mocking that module.
# ──────────────────────────────────────────────────────────────────────────────


@tool("send_email", return_direct=False)
def send_email_tool(to: str, subject: str, body: str) -> str:
    """Send an email via the Resend API. Supports MULTIPLE recipients.

    Use this whenever the user asks you to email, mail, or message someone
    over email — e.g. "email Ravi that the meeting is postponed", or
    "send onboarding email to alice@x.com, bob@y.com".

    If the user gives a NAME instead of an email address, FIRST call the
    `lookup_users` tool to resolve it from the application database, then
    pass the resulting address(es) here. Only ask the human if the lookup
    returns no matches.

    Args:
        to: One or more recipient email addresses. Multiple addresses may be
            comma-, semicolon-, or whitespace-separated
            (e.g. "alice@x.com, bob@y.com").
        subject: Short subject line.
        body: Plain-text body of the email.

    Returns:
        A confirmation string with the Resend message id and the list of
        recipients on success, or an explicit ERROR string on failure.
    """
    result = mcp_tools_service.send_email(
        to=to, subject=subject, body=body, user_email=_get_user_email()
    )
    if result.get("ok"):
        recipients = ", ".join(result["to"])
        provider = result.get("provider", "?")
        return f"Email sent via {provider} to {recipients} (id={result['id']}, subject={result['subject']!r})."
    err = f"ERROR: send_email failed ({result.get('error')}: {result.get('message')})."
    if result.get("hint"):
        err += f" HINT: {result['hint']}"
    return err


@tool("lookup_users", return_direct=False)
def lookup_users_tool(query: str = "") -> str:
    """Find application users by partial name / email match — or list ALL users.

    Use this whenever you need email addresses you don't already have:
    * If the human references a person by NAME ("email Ravi…"), pass the
      name fragment (case-insensitive substring on `full_name` and `email`).
    * If the human asks to email "all users", "every user in the database",
      "the team", or anything similarly broad, call this with an EMPTY
      string (or "all" / "*") — you'll get every active user.
    Then pass the resulting comma-separated addresses straight into
    `send_email` or `send_welcome_email`. Do NOT ask the human for the
    address list — the database is the source of truth.

    Args:
        query: Empty / "*" / "all" → list all active users (capped at 200).
            Otherwise a name fragment or partial email.

    Returns:
        Multi-line string "<name> <email>" per match, or "No matches."
    """
    result = mcp_tools_service.lookup_users(query)
    if not result.get("ok"):
        return f"ERROR: lookup_users failed ({result.get('error')}: {result.get('message')})."
    matches = result.get("matches") or []
    if not matches:
        return "No matches."
    header = (
        f"All active users ({len(matches)}):"
        if result.get("listed_all")
        else f"Found {len(matches)} user(s):"
    )
    lines = [header]
    for m in matches:
        name = m.get("name") or "(no name)"
        lines.append(f"- {name} <{m['email']}>")
    return "\n".join(lines)


@tool("send_welcome_email", return_direct=False)
def send_welcome_email_tool(to: str = "", everyone: bool = False) -> str:
    """Send the styled HTML WELCOME / ONBOARDING email template.

    Use this whenever the human asks for an onboarding, welcome, or
    introduction email — NEVER hand-craft a plain-text onboarding email.
    The template is a multi-section responsive HTML layout with logo,
    hero image, feature grid, benefits list, and a CTA button. Each
    recipient's first name is auto-filled from the users table.

    Args:
        to: Comma/semicolon-separated list of recipient EMAILS or NAMES.
            Names are looked up against the users table automatically.
            Leave empty ("") and set everyone=True to send to all users.
        everyone: When True, send the welcome email to EVERY active user
            in the database. Use this for prompts like "send the welcome
            email to all users".

    Returns:
        Summary of how many sends succeeded / failed, with the failure
        reason on each failed recipient.
    """
    result = mcp_tools_service.send_welcome_email(
        to=to or None,
        everyone=everyone,
        user_email=_get_user_email(),
    )
    if not result.get("ok") and not result.get("sent"):
        return f"ERROR: send_welcome_email failed ({result.get('error')}: {result.get('message')})."
    parts = [
        f"Welcome email sent to {result['sent_count']} recipient(s): {', '.join(result['sent'])}."
    ]
    if result.get("failed"):
        parts.append(f"Failed for {result['failed_count']}:")
        for f in result["failed"]:
            parts.append(
                f"- {f.get('email')}: {f.get('error')} — {f.get('message')}"
            )
    return "\n".join(parts)


@tool("schedule_email", return_direct=False)
def schedule_email_tool(to: str, subject: str, body: str, delay_seconds: int) -> str:
    """Send a PLAIN-TEXT email AFTER a delay (in-process scheduler, max 24h).

    Use this for plain-text follow-ups like "send a follow-up after 2 minutes".
    For scheduled WELCOME / ONBOARDING follow-ups, use
    `schedule_welcome_email` instead so the styled HTML template is preserved
    — NEVER schedule a welcome follow-up through this tool, it will arrive
    as plain text.

    Args:
        to: One or more recipient email addresses (comma/semicolon separated).
        subject: Email subject line.
        body: Plain-text body.
        delay_seconds: How many seconds to wait. >= 1, capped at 86400 (24h).
    """
    result = mcp_tools_service.schedule_email(
        to=to,
        subject=subject,
        body=body,
        delay_seconds=delay_seconds,
        user_email=_get_user_email(),
    )
    if result.get("ok"):
        recipients = ", ".join(result["to"])
        return (
            f"Scheduled plain-text email to {recipients} in {result['delay_seconds']}s "
            f"(job_id={result['job_id']})."
        )
    return f"ERROR: schedule_email failed ({result.get('error')}: {result.get('message')})."


@tool("schedule_welcome_email", return_direct=False)
def schedule_welcome_email_tool(
    to: str = "", everyone: bool = False, delay_seconds: int = 120
) -> str:
    """Schedule the styled HTML FOLLOW-UP onboarding email after a delay.

    This always uses the FOLLOW-UP variant (different subject + copy from the
    welcome email) so a recipient never receives two identical messages. For
    a smarter "only nudge people who didn't open the welcome" workflow, use
    `send_welcome_with_followup` instead — it sends the welcome NOW and
    schedules the follow-up only to non-openers via the Brevo events API.

    Args:
        to: Comma/semicolon-separated emails or names. Empty when
            `everyone=True`.
        everyone: When True, schedules the follow-up to every active user.
        delay_seconds: Wait time in seconds (default 120 = 2 minutes).
    """
    result = mcp_tools_service.schedule_welcome_email(
        to=to or None,
        everyone=everyone,
        delay_seconds=delay_seconds,
        variant="followup",
        user_email=_get_user_email(),
    )
    if not result.get("ok"):
        return f"ERROR: schedule_welcome_email failed ({result.get('error')}: {result.get('message')})."
    target = "everyone" if result.get("everyone") else ", ".join(result.get("to") or [])
    return (
        f"Scheduled HTML follow-up email to {target} in {result['delay_seconds']}s "
        f"(job_id={result['job_id']})."
    )


@tool("send_welcome_with_followup", return_direct=False)
def send_welcome_with_followup_tool(
    to: str = "",
    everyone: bool = False,
    followup_delay_seconds: int = 120,
) -> str:
    """Send the WELCOME email now AND a FOLLOW-UP only to recipients who don't open it.

    Use this whenever the user says things like "send the welcome email now
    and a follow-up after 2 minutes" or "send the welcome and remind users
    who don't open it". One call covers the whole flow:
      1. Render and send the WELCOME template (different subject/body).
      2. After ``followup_delay_seconds`` seconds, query Brevo's transactional
         events API per recipient (https://app.brevo.com/transactional/email/real-time)
         and send the FOLLOW-UP template only to recipients with no "opened"
         event. Recipients that opened the welcome are skipped.

    Requires Brevo as the active provider (BREVO_API_KEY set). With Resend the
    open-tracking step is skipped and the follow-up is sent to everyone.

    Args:
        to: Comma/semicolon-separated emails or names. Empty when
            `everyone=True`.
        everyone: When True, run for every active user in the database.
        followup_delay_seconds: Seconds to wait before checking opens and
            sending the follow-up (default 120 = 2 minutes; max 86400).
    """
    initial = mcp_tools_service.send_welcome_email(
        to=to or None,
        everyone=everyone,
        variant="welcome",
        user_email=_get_user_email(),
    )
    if not initial.get("ok") and not initial.get("sent"):
        return (
            f"ERROR: welcome send failed ({initial.get('error')}: {initial.get('message')}). "
            "Follow-up was NOT scheduled."
        )

    sent_emails = initial.get("sent") or []
    message_ids = initial.get("message_ids") or {}
    parts = [
        f"Welcome (HTML) email sent to {len(sent_emails)} recipient(s): {', '.join(sent_emails)}."
    ]
    if initial.get("failed"):
        parts.append(f"Welcome failed for {initial['failed_count']}:")
        for f in initial["failed"]:
            parts.append(f"- {f.get('email')}: {f.get('error')} — {f.get('message')}")

    if message_ids:
        followup = mcp_tools_service.schedule_followup_if_unopened(
            message_ids=message_ids,
            delay_seconds=followup_delay_seconds,
            user_email=_get_user_email(),
        )
        if followup.get("ok"):
            parts.append(
                f"Follow-up will fire in {followup['delay_seconds']}s; only "
                f"recipients who haven't opened the welcome will receive it "
                f"(job_id={followup['job_id']})."
            )
        else:
            parts.append(
                f"Follow-up could NOT be scheduled: {followup.get('error')} — {followup.get('message')}."
            )
    else:
        parts.append(
            "No provider message ids returned for the welcome send, so an "
            "opens-conditional follow-up could not be scheduled."
        )
    return "\n".join(parts)


@tool("create_reminder", return_direct=False)
def create_reminder_tool(task: str, time: str) -> str:
    """Create a reminder for the current user.

    Use this whenever the user asks to be reminded of something — e.g.
    "remind me to call mom at 7 PM", "set a reminder for tomorrow 9 AM to
    submit the report". The natural-language time is stored verbatim.

    Args:
        task: What to be reminded about (e.g. "call mom").
        time: Natural-language time (e.g. "7 PM today", "tomorrow at 9 AM").

    Returns:
        A short confirmation string on success, or an ERROR string on failure.
    """
    result = mcp_tools_service.create_reminder(
        task=task, time=time, user_email=_get_user_email()
    )
    if result.get("ok"):
        return f"Reminder created: {result['task']!r} at {result['time']!r} (id={result['id']})."
    return f"ERROR: create_reminder failed ({result.get('error')}: {result.get('message')})."


@tool("send_notification", return_direct=False)
def send_notification_tool(message: str) -> str:
    """Push an in-app notification to the current user.

    Use this whenever the user asks to be notified, alerted, or pinged about
    something — e.g. "notify me when the task is completed", "send me a
    notification: build finished".

    Args:
        message: The notification body to deliver.

    Returns:
        A short confirmation string on success, or an ERROR string on failure.
    """
    result = mcp_tools_service.send_notification(
        message=message, user_email=_get_user_email()
    )
    if result.get("ok"):
        return f"Notification queued: {result['message']!r} (id={result['id']})."
    return f"ERROR: send_notification failed ({result.get('error')}: {result.get('message')})."


TOOLS.extend([
    send_email_tool,
    create_reminder_tool,
    send_notification_tool,
    lookup_users_tool,
    schedule_email_tool,
    send_welcome_email_tool,
    schedule_welcome_email_tool,
    send_welcome_with_followup_tool,
])


# ──────────────────────────────────────────────────────────────────────────────
# Streaming-friendly callback handler — translates LangChain agent events into
# small typed events that the FastAPI route can forward to the UI as SSE.
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class StreamingAgentEvent:
    """Single event emitted while the agent is running.

    `type` is one of:
        - "thinking": agent started, no observation yet
        - "tool_start": about to call a tool (with name + input)
        - "tool_end":  tool finished (with truncated output)
        - "final":     final answer ready
        - "error":     unrecoverable failure
    """

    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "data": self.data}


class _QueueCallbackHandler(BaseCallbackHandler):
    """Pushes lightweight progress events onto a thread-safe queue."""

    def __init__(self, queue: "Queue[StreamingAgentEvent | None]") -> None:
        super().__init__()
        self._queue = queue

    # ── chain ────────────────────────────────────────────────────────────────
    def on_chain_start(self, serialized: dict, inputs: dict, **_: Any) -> None:
        self._queue.put(StreamingAgentEvent(
            "thinking",
            {"message": "Agent is thinking…"},
        ))

    # ── tools ────────────────────────────────────────────────────────────────
    def on_tool_start(self, serialized: dict, input_str: str, **_: Any) -> None:
        name = (serialized or {}).get("name") or "tool"
        self._queue.put(StreamingAgentEvent(
            "tool_start",
            {"tool": name, "input": (input_str or "")[:300], "message": f"Calling {name}…"},
        ))

    def on_tool_end(self, output: str, **_: Any) -> None:
        text = output if isinstance(output, str) else str(output)
        max_len = 12000
        self._queue.put(StreamingAgentEvent(
            "tool_end",
            {
                "output": text[:max_len],
                "observation": text[:max_len],
                "truncated": len(text) > max_len,
            },
        ))

    def on_tool_error(self, error: BaseException, **_: Any) -> None:
        self._queue.put(StreamingAgentEvent(
            "tool_end",
            {"output": f"Tool error: {error}", "error": True},
        ))

    # ── agent ────────────────────────────────────────────────────────────────
    def on_agent_action(self, action: Any, **_: Any) -> None:
        # Surface the agent's reasoning text (the "Thought:" portion of ReAct)
        # so the UI can show it.
        log = getattr(action, "log", "") or ""
        thought = log.split("Action:")[0].strip()
        if thought:
            self._queue.put(StreamingAgentEvent(
                "thinking",
                {"message": thought[:400]},
            ))


# ──────────────────────────────────────────────────────────────────────────────
# Executor builder + runners.
# ──────────────────────────────────────────────────────────────────────────────


def build_agent_executor(
    *,
    user_email: str,
    callbacks: list[BaseCallbackHandler] | None = None,
    verbose: bool = True,
) -> AgentExecutor:
    """Construct a zero-shot ReAct agent bound to the LiteLLM-proxied LLM.

    A fresh executor is built per request because the agent embeds the
    callbacks and per-user metadata. The LLM client itself is cached.
    """
    # Make the authenticated email visible to side-effecting tools
    # (send_email / create_reminder / send_notification) for audit logging.
    _current_user_email.value = user_email

    base_llm = get_chat_llm()
    # Bind per-user tracking metadata so LiteLLM cost reports carry the email.
    llm = base_llm.bind(
        user=user_email,
        extra_body={"metadata": {"application": "amzur-ai-chat", "test_type": "agent"}},
    )

    return initialize_agent(
        tools=TOOLS,
        llm=llm,
        # STRUCTURED_CHAT supports multi-argument tools (send_email needs to,
        # subject, body). The plain ZERO_SHOT_REACT_DESCRIPTION agent rejects
        # any tool whose schema has more than one input field with:
        #   "ZeroShotAgent does not support multi-input tool send_email."
        agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
        verbose=verbose,
        handle_parsing_errors=True,
        max_iterations=8,
        early_stopping_method="force",
        return_intermediate_steps=True,
        callbacks=callbacks or [],
    )


def run_agent(query: str, *, user_email: str) -> dict[str, Any]:
    """Run the agent synchronously and return the final answer + steps.

    Used by callers that want one consolidated JSON response (no streaming).
    """
    executor = build_agent_executor(user_email=user_email)
    try:
        result = executor.invoke({"input": query})
    except Exception as exc:
        return {
            "ok": False,
            "answer": f"Agent failed: {exc}",
            "steps": [],
        }
    steps_serialised: list[dict[str, Any]] = []
    for action, observation in result.get("intermediate_steps") or []:
        steps_serialised.append({
            "tool": getattr(action, "tool", "unknown"),
            "tool_input": getattr(action, "tool_input", ""),
            "log": getattr(action, "log", ""),
            "observation": observation if isinstance(observation, str) else str(observation),
        })
    return {
        "ok": True,
        "answer": (result.get("output") or "").strip(),
        "steps": steps_serialised,
    }


async def stream_agent(query: str, *, user_email: str) -> AsyncIterator[StreamingAgentEvent]:
    """Run the agent in a background thread and yield live progress events.

    The agent itself is synchronous (LangChain `initialize_agent`), so we run
    it in a worker thread and bridge the callback queue into an async iterator.
    The route handler can forward the events as Server-Sent Events.
    """
    queue: "Queue[StreamingAgentEvent | None]" = Queue()
    callback = _QueueCallbackHandler(queue)

    final_holder: dict[str, Any] = {}

    def _worker() -> None:
        try:
            executor = build_agent_executor(user_email=user_email, callbacks=[callback])
            result = executor.invoke({"input": query})
            final_holder["answer"] = (result.get("output") or "").strip()
            final_holder["steps"] = []
            for action, observation in result.get("intermediate_steps") or []:
                final_holder["steps"].append({
                    "tool": getattr(action, "tool", "unknown"),
                    "tool_input": getattr(action, "tool_input", ""),
                    "log": getattr(action, "log", ""),
                    "observation": observation if isinstance(observation, str) else str(observation),
                })
        except Exception as exc:  # noqa: BLE001 — we want every failure surfaced
            final_holder["error"] = str(exc)
        finally:
            queue.put(None)  # sentinel: agent finished

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    loop = asyncio.get_running_loop()

    while True:
        # Bridge the blocking queue.get into the running event loop.
        event = await loop.run_in_executor(None, _safe_get, queue)
        if event is None:
            break
        yield event

    if "error" in final_holder:
        yield StreamingAgentEvent("error", {"message": final_holder["error"]})
    else:
        yield StreamingAgentEvent(
            "final",
            {
                "answer": final_holder.get("answer", ""),
                "steps": final_holder.get("steps", []),
            },
        )


def _safe_get(queue: "Queue[StreamingAgentEvent | None]") -> StreamingAgentEvent | None:
    """Block on queue.get with a sane periodic wake-up (cancels stay responsive)."""
    while True:
        try:
            return queue.get(timeout=0.5)
        except Empty:
            continue


def event_to_sse(event: StreamingAgentEvent) -> bytes:
    """Encode a StreamingAgentEvent as an SSE `data:` line."""
    payload = json.dumps(event.to_dict(), ensure_ascii=False)
    return f"data: {payload}\n\n".encode("utf-8")
