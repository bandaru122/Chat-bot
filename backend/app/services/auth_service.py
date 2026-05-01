"""Auth service: email/password + Google OAuth."""
import secrets
import urllib.parse

import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models import User
from app.services import user_service

ALLOWED_DOMAIN = "amzur.com"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


def _check_domain(email: str) -> None:
    if not email.lower().endswith(f"@{ALLOWED_DOMAIN}"):
        raise HTTPException(
            status_code=403,
            detail=f"Only @{ALLOWED_DOMAIN} accounts may sign in",
        )


async def register_employee(
    db: AsyncSession, email: str, password: str, full_name: str | None
) -> User:
    _check_domain(email)
    existing = await user_service.get_user_by_email(db, email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    return await user_service.create_user(
        db,
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
    )


async def login_employee(db: AsyncSession, email: str, password: str) -> User:
    _check_domain(email)
    user = await user_service.get_user_by_email(db, email)
    if not user or not user.hashed_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user


def google_authorize_url(state: str) -> str:
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


def make_state() -> str:
    return secrets.token_urlsafe(24)


async def google_exchange_and_login(db: AsyncSession, code: str) -> User:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Google token exchange failed: {token_resp.text}")
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="No access_token from Google")

        info = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if info.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch Google userinfo")
        profile = info.json()

    email = (profile.get("email") or "").lower()
    google_id = profile.get("id")
    full_name = profile.get("name")
    picture = profile.get("picture")
    if not email or not google_id:
        raise HTTPException(status_code=400, detail="Google profile missing email/id")
    _check_domain(email)

    by_google = await user_service.get_user_by_google_id(db, google_id)
    if by_google:
        return by_google
    by_email = await user_service.get_user_by_email(db, email)
    if by_email:
        return await user_service.link_google(db, by_email, google_id, picture)
    return await user_service.create_user(
        db,
        email=email,
        full_name=full_name,
        google_id=google_id,
        avatar_url=picture,
    )
