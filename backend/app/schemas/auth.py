"""Auth, user, thread, message Pydantic schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    avatar_url: str | None = None


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class ThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ThreadDetail(ThreadOut):
    messages: list[MessageOut] = []


class ThreadCreate(BaseModel):
    title: str | None = None


class ThreadUpdate(BaseModel):
    title: str


class SendMessageRequest(BaseModel):
    content: str
    model: str | None = None
