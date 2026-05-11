"""MCP-style assistant tools: send_email, create_reminder, send_notification.

These are exposed to the live ReAct agent (see `app.ai.agents.live_agent`) so
the LLM can autonomously decide when to send an email, schedule a reminder, or
push an in-app notification.

Design choices
--------------
* Email delivery goes through the Resend HTTP API
  (https://resend.com/docs/api-reference/emails/send-email). The API key is
  read from `settings.RESEND_API_KEY` — never hardcoded.
* Reminders and notifications are persisted as append-only JSON-lines files
  under `settings.MCP_DATA_DIR`. This keeps the implementation framework-free
  and lets the live-agent UI (or any future endpoint) tail them later without
  introducing a new DB table.
* Every function returns a plain dict the agent tool wrappers can stringify.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import httpx
from sqlalchemy import create_engine, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RESEND_ENDPOINT = "https://api.resend.com/emails"
_BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
_BREVO_EVENTS_ENDPOINT = "https://api.brevo.com/v3/smtp/statistics/events"


# ──────────────────────────────────────────────────────────────────────────────
# Storage helpers — JSON-lines files under MCP_DATA_DIR.
# ──────────────────────────────────────────────────────────────────────────────


def _data_dir() -> Path:
    path = Path(settings.MCP_DATA_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _append_jsonl(filename: str, record: dict[str, Any]) -> None:
    path = _data_dir() / filename
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────────────────
# Recipient parsing — accepts a string (single, comma- or semicolon- or
# whitespace-separated) or an iterable of strings.
# ──────────────────────────────────────────────────────────────────────────────


def _parse_addresses(value: str | Iterable[str] | None) -> list[str]:
    """Split a free-form recipient field into validated email addresses."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[\s,;]+", value.strip())
    else:
        parts: list[str] = []
        for v in value:
            parts.extend(re.split(r"[\s,;]+", str(v).strip()))
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        p = p.strip().strip("<>")
        if not p or p.lower() in seen:
            continue
        seen.add(p.lower())
        out.append(p)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Sync DB engine — reuses the same psycopg2 URL helper as the SQL agent so
# the live ReAct agent (which runs in a worker thread) can do blocking lookups.
# ──────────────────────────────────────────────────────────────────────────────


def _sync_db_url() -> str:
    if settings.DATABASE_URL_SYNC:
        return settings.DATABASE_URL_SYNC
    return settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")


@lru_cache
def _sync_engine() -> Engine:
    return create_engine(_sync_db_url(), future=True)


def lookup_users(query: str = "", *, limit: int = 50) -> dict[str, Any]:
    """Find users by partial name or email match (case-insensitive).

    If ``query`` is empty/None/"*"/"all", returns ALL active users (capped at
    ``limit``). Otherwise returns active users whose name OR email contains
    the substring (case-insensitive). The ReAct agent calls this whenever it
    needs an address it doesn't already have.
    """
    q = (query or "").strip()
    list_all = q == "" or q in {"*", "all", "everyone"}
    try:
        with Session(_sync_engine()) as session:
            stmt = select(User.full_name, User.email).where(User.is_active.is_(True))
            if not list_all:
                pattern = f"%{q}%"
                stmt = stmt.where(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))
            stmt = stmt.order_by(User.email).limit(max(1, min(limit, 200)))
            rows = session.execute(stmt).all()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "db_error", "message": str(exc)}
    matches = [{"name": r[0] or "", "email": r[1]} for r in rows]
    return {"ok": True, "count": len(matches), "matches": matches, "listed_all": list_all}


# ──────────────────────────────────────────────────────────────────────────────
# Welcome-email template — rendered per recipient with a Jinja-free
# {{Placeholder}} substitution so the agent can call it from a tool without
# pulling in a templating engine.
# ──────────────────────────────────────────────────────────────────────────────


_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _read_template(name: str) -> str:
    path = _TEMPLATE_DIR / name
    return path.read_text(encoding="utf-8")


def _safe_first_name(full_name: str | None, email: str) -> str:
    if full_name and full_name.strip():
        return full_name.strip().split()[0]
    return email.split("@", 1)[0].replace(".", " ").title()


def render_welcome_email(
    *,
    full_name: str | None,
    email: str,
    variant: str = "welcome",
    app_name: str = "Amzur AI Chat",
    company_name: str = "Amzur Technologies",
    app_link: str = "https://chat.amzurbot.com",
    logo_url: str = "https://www.amzur.com/wp-content/uploads/2021/03/amzur-logo.svg",
    hero_url: str = "https://images.unsplash.com/photo-1677442136019-21780ecad995?w=1200&q=60",
    intro_text: str | None = None,
) -> tuple[str, str]:
    """Return ``(subject, html)`` for a personalised onboarding email.

    Two variants share the same renderer:
      * ``"welcome"``  → first-touch welcome (welcome_email.html). Subject:
            "Welcome to {AppName}, {UserName} 🎉"
      * ``"followup"`` → nudge-style follow-up (followup_email.html). Subject:
            "Hi {UserName}, did you get a chance to try {AppName}?"

    Subject and intro copy intentionally differ between variants — the
    follow-up acknowledges the unopened welcome and uses a tighter, more
    direct layout.
    """
    user_name = _safe_first_name(full_name, email)

    if variant == "followup":
        template_name = "followup_email.html"
        subject = f"Hi {user_name}, did you get a chance to try {app_name}?"
        default_intro = (
            f"A few days ago we sent you a welcome to {app_name}. "
            "We noticed you haven’t opened it yet, so here’s the short version."
        )
    else:
        template_name = "welcome_email.html"
        subject = f"Welcome to {app_name}, {user_name} 🎉"
        default_intro = (
            f"We’re excited to have you onboard at {app_name}! Your AI-powered "
            "assistant is ready to help you automate tasks, query data, and boost "
            "productivity from a single chat window."
        )

    template = _read_template(template_name)
    intro = intro_text or default_intro
    replacements = {
        "{{UserName}}": user_name,
        "{{AppName}}": app_name,
        "{{CompanyName}}": company_name,
        "{{AppLink}}": app_link,
        "{{LogoUrl}}": logo_url,
        "{{HeroUrl}}": hero_url,
        "{{IntroText}}": intro,
        "{{Subject}}": subject,
    }
    html = template
    for key, value in replacements.items():
        html = html.replace(key, value)
    return subject, html


def send_welcome_email(
    *,
    to: str | Iterable[str] | None = None,
    everyone: bool = False,
    variant: str = "welcome",
    app_name: str = "Amzur AI Chat",
    company_name: str = "Amzur Technologies",
    app_link: str = "https://chat.amzurbot.com",
    user_email: str | None = None,
) -> dict[str, Any]:
    """Render and send the HTML welcome / follow-up template.

    Resolution order:
      * If ``everyone`` is True, send to every active user in the DB.
      * Else if ``to`` is provided, accept a string or iterable of:
            - email addresses, OR
            - bare names (looked up against the users table).
      * Personalises ``{{UserName}}`` per recipient using their DB name.

    Args:
        variant: "welcome" (default) or "followup". Controls subject + body.

    Returns:
        Dict including ``sent`` (list of emails) and ``message_ids`` (mapping
        of email → provider message id) so callers can later check open
        status via ``brevo_email_was_opened``.
    """
    targets: list[tuple[str | None, str]] = []  # (full_name, email)

    if everyone:
        users = lookup_users("", limit=200)
        if not users.get("ok"):
            return users
        for m in users.get("matches", []):
            targets.append((m.get("name") or None, m["email"]))
    else:
        tokens = _parse_addresses(to) if to else []
        if isinstance(to, str) and not tokens:
            tokens = [to]
        names_to_resolve = [t for t in tokens if "@" not in t]
        emails_direct = [t for t in tokens if "@" in t]

        resolved_by_email: dict[str, str | None] = {}
        for name in names_to_resolve:
            r = lookup_users(name, limit=5)
            if r.get("ok"):
                for m in r.get("matches", []):
                    resolved_by_email.setdefault(m["email"], m.get("name") or None)
        if emails_direct:
            try:
                with Session(_sync_engine()) as session:
                    stmt = (
                        select(User.full_name, User.email)
                        .where(User.email.in_(emails_direct))
                        .where(User.is_active.is_(True))
                    )
                    for row in session.execute(stmt).all():
                        resolved_by_email.setdefault(row[1], row[0])
            except Exception:  # noqa: BLE001
                pass
            for em in emails_direct:
                resolved_by_email.setdefault(em, None)

        for em, nm in resolved_by_email.items():
            targets.append((nm, em))

    if not targets:
        return {"ok": False, "error": "no_targets", "message": "No recipients resolved."}

    sent: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    message_ids: dict[str, str] = {}
    for full_name, email in targets:
        subject, html = render_welcome_email(
            full_name=full_name,
            email=email,
            variant=variant,
            app_name=app_name,
            company_name=company_name,
            app_link=app_link,
        )
        result = send_email(
            to=email,
            subject=subject,
            body=(
                f"Welcome to {app_name}! Open this email in an HTML-capable client to view the full message."
                if variant == "welcome"
                else f"Did you get a chance to try {app_name}? Open this email in an HTML-capable client to view the full message."
            ),
            html=html,
            user_email=user_email,
        )
        if result.get("ok"):
            sent.append({"email": email, **result})
            if result.get("id"):
                message_ids[email] = result["id"]
        else:
            failed.append({"email": email, **result})

    return {
        "ok": not failed or bool(sent),
        "variant": variant,
        "sent_count": len(sent),
        "failed_count": len(failed),
        "sent": [s["email"] for s in sent],
        "failed": failed,
        "message_ids": message_ids,
    }


# ──────────────────────────────────────────────────────────────────────────────
# send_email — Resend HTTP API.
# ──────────────────────────────────────────────────────────────────────────────


def send_email(
    *,
    to: str | Iterable[str],
    subject: str,
    body: str,
    cc: str | Iterable[str] | None = None,
    bcc: str | Iterable[str] | None = None,
    html: str | None = None,
    reply_to: str | None = None,
    user_email: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """Send an email via Brevo or Resend (auto-pick by availability).

    Provider selection (highest priority first):
      1. Explicit ``provider`` argument ("brevo" or "resend").
      2. ``settings.EMAIL_PROVIDER`` if set to "brevo" or "resend".
      3. Auto: prefer Brevo when ``BREVO_API_KEY`` is set, else Resend.

    Both providers accept the same call shape (multi-recipient, optional cc/
    bcc/html/reply_to). The provider that actually delivered is reported back
    in the result dict as ``provider``.
    """
    to_list = _parse_addresses(to)
    cc_list = _parse_addresses(cc)
    bcc_list = _parse_addresses(bcc)
    subject_clean = (subject or "").strip()
    body_clean = (body or "").strip()

    if not to_list:
        return {"ok": False, "error": "missing_recipient", "message": "At least one recipient email is required."}
    bad = [a for a in (to_list + cc_list + bcc_list) if not _EMAIL_RE.match(a)]
    if bad:
        return {"ok": False, "error": "invalid_recipient", "message": f"Invalid email address(es): {bad}"}
    if not subject_clean:
        return {"ok": False, "error": "missing_subject", "message": "Subject is required."}
    if not body_clean and not html:
        return {"ok": False, "error": "missing_body", "message": "Email body (text or html) is required."}

    chosen = (provider or settings.EMAIL_PROVIDER or "auto").lower()
    if chosen == "auto":
        chosen = "brevo" if settings.BREVO_API_KEY else "resend"

    if chosen == "brevo":
        return _send_via_brevo(
            to_list, cc_list, bcc_list, subject_clean, body_clean, html,
            reply_to, user_email,
        )
    return _send_via_resend(
        to_list, cc_list, bcc_list, subject_clean, body_clean, html,
        reply_to, user_email,
    )


def _send_via_resend(
    to_list: list[str],
    cc_list: list[str],
    bcc_list: list[str],
    subject: str,
    body: str,
    html: str | None,
    reply_to: str | None,
    user_email: str | None,
) -> dict[str, Any]:
    """POST to https://api.resend.com/emails (Bearer auth)."""
    if not settings.RESEND_API_KEY:
        return {
            "ok": False,
            "error": "resend_not_configured",
            "message": (
                "RESEND_API_KEY is empty in backend/.env. Get a key from "
                "https://resend.com/api-keys , paste it as RESEND_API_KEY=re_xxx, "
                "and restart the backend."
            ),
        }

    payload: dict[str, Any] = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": to_list,
        "subject": subject,
    }
    if body:
        payload["text"] = body
    if html:
        payload["html"] = html
    if cc_list:
        payload["cc"] = cc_list
    if bcc_list:
        payload["bcc"] = bcc_list
    if reply_to:
        payload["reply_to"] = reply_to

    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(_RESEND_ENDPOINT, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        return {"ok": False, "error": "network_error", "message": str(exc), "provider": "resend"}

    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text}

    if resp.status_code >= 400:
        msg = None
        if isinstance(data, dict):
            msg = data.get("message") or data.get("error") or data.get("name")
        return {
            "ok": False,
            "provider": "resend",
            "error": "resend_error",
            "status": resp.status_code,
            "message": msg or resp.text[:300],
            "hint": (
                "If Resend says 'You can only send testing emails to your own address', "
                "verify a domain at https://resend.com/domains and set RESEND_FROM_EMAIL "
                "to an address on that domain — OR set BREVO_API_KEY in .env to switch to Brevo."
            ),
        }

    record = {
        "id": (data.get("id") if isinstance(data, dict) else None) or str(uuid.uuid4()),
        "provider": "resend",
        "to": to_list,
        "cc": cc_list,
        "bcc": bcc_list,
        "subject": subject,
        "body": body,
        "html": bool(html),
        "from": settings.RESEND_FROM_EMAIL,
        "requested_by": user_email,
        "sent_at": _now_iso(),
    }
    _append_jsonl("email_log.jsonl", record)
    return {"ok": True, "provider": "resend", "id": record["id"], "to": to_list, "subject": subject}


def _send_via_brevo(
    to_list: list[str],
    cc_list: list[str],
    bcc_list: list[str],
    subject: str,
    body: str,
    html: str | None,
    reply_to: str | None,
    user_email: str | None,
) -> dict[str, Any]:
    """POST to https://api.brevo.com/v3/smtp/email (api-key header).

    Brevo SMTP API spec: https://developers.brevo.com/reference/sendtransacemail
    """
    if not settings.BREVO_API_KEY:
        return {
            "ok": False,
            "error": "brevo_not_configured",
            "message": (
                "BREVO_API_KEY is empty in backend/.env. Get a key from "
                "https://app.brevo.com/settings/keys/api , add a verified "
                "sender at https://app.brevo.com/senders/list , set BREVO_FROM_EMAIL, "
                "and restart the backend."
            ),
        }

    sender_email = settings.BREVO_FROM_EMAIL or settings.RESEND_FROM_EMAIL
    if not sender_email:
        return {
            "ok": False,
            "error": "brevo_missing_sender",
            "message": (
                "BREVO_FROM_EMAIL is not set. Add a verified sender at "
                "https://app.brevo.com/senders/list and set BREVO_FROM_EMAIL=<that address>."
            ),
        }

    payload: dict[str, Any] = {
        "sender": {"email": sender_email, "name": settings.BREVO_FROM_NAME},
        "to": [{"email": e} for e in to_list],
        "subject": subject,
    }
    if html:
        payload["htmlContent"] = html
    if body:
        payload["textContent"] = body
    if cc_list:
        payload["cc"] = [{"email": e} for e in cc_list]
    if bcc_list:
        payload["bcc"] = [{"email": e} for e in bcc_list]
    if reply_to:
        payload["replyTo"] = {"email": reply_to}

    headers = {
        "api-key": settings.BREVO_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(_BREVO_ENDPOINT, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        return {"ok": False, "error": "network_error", "message": str(exc), "provider": "brevo"}

    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text}

    if resp.status_code >= 400:
        msg = None
        if isinstance(data, dict):
            msg = data.get("message") or data.get("code") or data.get("error")
        return {
            "ok": False,
            "provider": "brevo",
            "error": "brevo_error",
            "status": resp.status_code,
            "message": msg or resp.text[:300],
            "hint": (
                "If Brevo says the sender is unauthorized, verify the address at "
                "https://app.brevo.com/senders/list and update BREVO_FROM_EMAIL."
            ),
        }

    record = {
        "id": (data.get("messageId") if isinstance(data, dict) else None) or str(uuid.uuid4()),
        "provider": "brevo",
        "to": to_list,
        "cc": cc_list,
        "bcc": bcc_list,
        "subject": subject,
        "body": body,
        "html": bool(html),
        "from": sender_email,
        "requested_by": user_email,
        "sent_at": _now_iso(),
    }
    _append_jsonl("email_log.jsonl", record)
    return {"ok": True, "provider": "brevo", "id": record["id"], "to": to_list, "subject": subject}


# ──────────────────────────────────────────────────────────────────────────────
# schedule_email — fire-and-forget background timer that calls send_email
# after `delay_seconds`. Survives only as long as the uvicorn process; for
# durable scheduling, swap to APScheduler / Celery later.
# ──────────────────────────────────────────────────────────────────────────────


def schedule_email(
    *,
    to: str | Iterable[str],
    subject: str,
    body: str,
    delay_seconds: int,
    html: str | None = None,
    user_email: str | None = None,
) -> dict[str, Any]:
    """Send an email after ``delay_seconds`` seconds.

    Args:
        delay_seconds: How long to wait before sending. Capped at 24h.
        html: Optional HTML body — forwarded verbatim to ``send_email`` so
            scheduled follow-ups can use the same template as the immediate
            send (e.g. a follow-up that mirrors the welcome email).
    """
    if delay_seconds is None or delay_seconds < 1:
        return {"ok": False, "error": "invalid_delay", "message": "delay_seconds must be >= 1."}
    delay = min(int(delay_seconds), 24 * 60 * 60)

    job_id = str(uuid.uuid4())

    def _fire() -> None:
        result = send_email(
            to=to, subject=subject, body=body, html=html, user_email=user_email
        )
        _append_jsonl(
            "scheduled_email_log.jsonl",
            {
                "job_id": job_id,
                "fired_at": _now_iso(),
                "result": result,
            },
        )

    timer = threading.Timer(delay, _fire)
    timer.daemon = True
    timer.start()

    record = {
        "job_id": job_id,
        "to": _parse_addresses(to),
        "subject": (subject or "").strip(),
        "delay_seconds": delay,
        "requested_by": user_email,
        "scheduled_at": _now_iso(),
    }
    _append_jsonl("scheduled_emails.jsonl", record)
    return {"ok": True, "job_id": job_id, "delay_seconds": delay, "to": record["to"]}


def schedule_welcome_email(
    *,
    to: str | Iterable[str] | None = None,
    everyone: bool = False,
    delay_seconds: int,
    variant: str = "followup",
    user_email: str | None = None,
) -> dict[str, Any]:
    """Send the styled HTML welcome / follow-up template after a delay.

    Same recipient resolution as ``send_welcome_email``. ``variant`` defaults
    to ``"followup"`` because the typical use is "send the welcome now and a
    follow-up later" — and the follow-up MUST use the follow-up template, not
    re-send the welcome copy.
    """
    if delay_seconds is None or delay_seconds < 1:
        return {"ok": False, "error": "invalid_delay", "message": "delay_seconds must be >= 1."}
    delay = min(int(delay_seconds), 24 * 60 * 60)

    job_id = str(uuid.uuid4())

    def _fire() -> None:
        result = send_welcome_email(
            to=to, everyone=everyone, variant=variant, user_email=user_email
        )
        _append_jsonl(
            "scheduled_email_log.jsonl",
            {"job_id": job_id, "fired_at": _now_iso(), "kind": variant, "result": result},
        )

    timer = threading.Timer(delay, _fire)
    timer.daemon = True
    timer.start()

    record = {
        "job_id": job_id,
        "kind": variant,
        "to": list(_parse_addresses(to)) if to else [],
        "everyone": everyone,
        "delay_seconds": delay,
        "requested_by": user_email,
        "scheduled_at": _now_iso(),
    }
    _append_jsonl("scheduled_emails.jsonl", record)
    return {
        "ok": True,
        "job_id": job_id,
        "delay_seconds": delay,
        "everyone": everyone,
        "variant": variant,
        "to": record["to"],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Brevo open-tracking — query the transactional events API per messageId.
# Docs: https://developers.brevo.com/reference/getemaileventreport
#       https://app.brevo.com/transactional/email/real-time
# ──────────────────────────────────────────────────────────────────────────────


def brevo_email_was_opened(message_id: str, *, recipient: str | None = None) -> dict[str, Any]:
    """Return whether a Brevo-sent email has been opened.

    Queries ``GET /smtp/statistics/events?messageId=<id>&event=opened`` and
    returns ``{"ok": True, "opened": bool, "events": [...]}``. If the API key
    isn't set, returns ``{"ok": False, ...}`` so callers can decide whether
    to default-open or default-not-open.
    """
    if not settings.BREVO_API_KEY:
        return {"ok": False, "error": "brevo_not_configured", "opened": False}
    if not message_id:
        return {"ok": False, "error": "missing_message_id", "opened": False}

    headers = {"api-key": settings.BREVO_API_KEY, "Accept": "application/json"}
    params: dict[str, Any] = {
        "messageId": message_id,
        "event": "opened",
        "limit": 50,
    }
    if recipient:
        params["email"] = recipient
    try:
        with httpx.Client(timeout=12) as client:
            resp = client.get(_BREVO_EVENTS_ENDPOINT, headers=headers, params=params)
    except httpx.HTTPError as exc:
        return {"ok": False, "error": "network_error", "message": str(exc), "opened": False}

    if resp.status_code == 404:
        # 404 means "no matching events yet" — not an error.
        return {"ok": True, "opened": False, "events": []}
    if resp.status_code >= 400:
        return {
            "ok": False,
            "error": "brevo_error",
            "status": resp.status_code,
            "message": resp.text[:200],
            "opened": False,
        }

    try:
        data = resp.json()
    except ValueError:
        return {"ok": False, "error": "bad_response", "opened": False}

    events = (data or {}).get("events") or []
    return {"ok": True, "opened": bool(events), "events": events}


def schedule_followup_if_unopened(
    *,
    message_ids: dict[str, str],
    delay_seconds: int | None = None,
    user_email: str | None = None,
) -> dict[str, Any]:
    """After ``delay_seconds``, send the follow-up template ONLY to non-openers.

    Args:
        message_ids: Mapping ``{recipient_email: brevo_message_id}`` returned
            by ``send_welcome_email`` (only recipients the welcome actually
            reached).
        delay_seconds: Seconds to wait before checking opens. Defaults to
            ``settings.BREVO_FOLLOWUP_DELAY_SECONDS`` (default 120).

    The job:
      1. Sleeps ``delay_seconds``.
      2. For each (email, messageId), queries Brevo events.
      3. Sends the FOLLOW-UP variant of the template to recipients that have
         no ``opened`` event. Recipients that opened are skipped.
      4. Logs the outcome to ``data/scheduled_email_log.jsonl``.
    """
    if not message_ids:
        return {"ok": False, "error": "no_message_ids", "message": "No initial sends to follow up on."}
    delay = max(1, min(int(delay_seconds or settings.BREVO_FOLLOWUP_DELAY_SECONDS), 24 * 60 * 60))
    job_id = str(uuid.uuid4())

    def _fire() -> None:
        unopened: list[str] = []
        skipped_opened: list[str] = []
        check_failed: list[dict[str, Any]] = []
        for email, mid in message_ids.items():
            status = brevo_email_was_opened(mid, recipient=email)
            if not status.get("ok"):
                # If we can't read events (Brevo key missing, network blip),
                # fail-open: send the follow-up rather than silently dropping.
                check_failed.append({"email": email, "reason": status.get("error")})
                unopened.append(email)
                continue
            if status.get("opened"):
                skipped_opened.append(email)
            else:
                unopened.append(email)

        send_result: dict[str, Any] = {"sent": [], "failed": [], "sent_count": 0}
        if unopened:
            send_result = send_welcome_email(
                to=",".join(unopened),
                variant="followup",
                user_email=user_email,
            )
        _append_jsonl(
            "scheduled_email_log.jsonl",
            {
                "job_id": job_id,
                "fired_at": _now_iso(),
                "kind": "followup_if_unopened",
                "checked": len(message_ids),
                "skipped_opened": skipped_opened,
                "unopened": unopened,
                "check_failed": check_failed,
                "send_result": send_result,
            },
        )

    timer = threading.Timer(delay, _fire)
    timer.daemon = True
    timer.start()

    record = {
        "job_id": job_id,
        "kind": "followup_if_unopened",
        "recipients": list(message_ids.keys()),
        "delay_seconds": delay,
        "requested_by": user_email,
        "scheduled_at": _now_iso(),
    }
    _append_jsonl("scheduled_emails.jsonl", record)
    return {
        "ok": True,
        "job_id": job_id,
        "delay_seconds": delay,
        "recipient_count": len(message_ids),
    }


# ──────────────────────────────────────────────────────────────────────────────
# create_reminder — persisted to data/reminders.jsonl.
# ──────────────────────────────────────────────────────────────────────────────


def create_reminder(
    *,
    task: str,
    time: str,
    user_email: str | None = None,
) -> dict[str, Any]:
    """Create a reminder entry.

    The natural-language `time` string is stored verbatim — interpreting it
    into an exact timestamp is intentionally left to a future scheduler.

    Args:
        task: What to be reminded about.
        time: Free-text time, e.g. "tomorrow at 9 AM" or "2026-05-08T09:00".
        user_email: Authenticated user's email. Stored on the record.
    """
    task_clean = (task or "").strip()
    time_clean = (time or "").strip()
    if not task_clean:
        return {"ok": False, "error": "missing_task", "message": "Task description is required."}
    if not time_clean:
        return {"ok": False, "error": "missing_time", "message": "Reminder time is required."}

    record = {
        "id": str(uuid.uuid4()),
        "task": task_clean,
        "time": time_clean,
        "owner": user_email,
        "created_at": _now_iso(),
    }
    _append_jsonl("reminders.jsonl", record)
    return {"ok": True, "id": record["id"], "task": task_clean, "time": time_clean}


# ──────────────────────────────────────────────────────────────────────────────
# send_notification — persisted to data/notifications.jsonl.
# ──────────────────────────────────────────────────────────────────────────────


def send_notification(
    *,
    message: str,
    user_email: str | None = None,
) -> dict[str, Any]:
    """Push an in-app notification.

    For now this is just an audit-log append; the same file can be tailed by a
    future websocket/SSE notifier without changing the agent contract.
    """
    message_clean = (message or "").strip()
    if not message_clean:
        return {"ok": False, "error": "missing_message", "message": "Notification message is required."}

    record = {
        "id": str(uuid.uuid4()),
        "message": message_clean,
        "owner": user_email,
        "created_at": _now_iso(),
    }
    _append_jsonl("notifications.jsonl", record)
    return {"ok": True, "id": record["id"], "message": message_clean}
