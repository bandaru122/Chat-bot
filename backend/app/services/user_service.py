"""User CRUD + linking helpers."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    res = await db.execute(select(User).where(User.id == user_id))
    return res.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    res = await db.execute(select(User).where(User.email == email.lower()))
    return res.scalar_one_or_none()


async def get_user_by_google_id(db: AsyncSession, google_id: str) -> User | None:
    res = await db.execute(select(User).where(User.google_id == google_id))
    return res.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    email: str,
    *,
    hashed_password: str | None = None,
    full_name: str | None = None,
    google_id: str | None = None,
    avatar_url: str | None = None,
) -> User:
    user = User(
        email=email.lower(),
        hashed_password=hashed_password,
        full_name=full_name,
        google_id=google_id,
        avatar_url=avatar_url,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def link_google(
    db: AsyncSession, user: User, google_id: str, avatar_url: str | None
) -> User:
    user.google_id = google_id
    if avatar_url and not user.avatar_url:
        user.avatar_url = avatar_url
    await db.commit()
    await db.refresh(user)
    return user
