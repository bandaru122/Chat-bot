"""JWT + password helpers + get_current_user dependency."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Response, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import get_db
from app.models import User
from app.services import user_service

JWT_ALG = "HS256"
COOKIE_NAME = "amzur_session"

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expire}, settings.SECRET_KEY, algorithm=JWT_ALG)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    amzur_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> User:
    if not amzur_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(amzur_session, settings.SECRET_KEY, algorithms=[JWT_ALG])
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError) as e:
        raise HTTPException(status_code=401, detail="Invalid session") from e
    user = await user_service.get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return user
