"""/api/auth — register, login, logout, Google OAuth, /me."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    clear_session_cookie,
    create_access_token,
    get_current_user,
    set_session_cookie,
)
from app.db import get_db
from app.models import User
from app.schemas import LoginRequest, RegisterRequest, UserOut
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue_session(response: Response, user: User) -> None:
    set_session_cookie(response, create_access_token(user.id))


@router.post("/register", response_model=UserOut)
async def register(req: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await auth_service.register_employee(db, req.email, req.password, req.full_name)
    _issue_session(response, user)
    return user


@router.post("/login", response_model=UserOut)
async def login(req: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await auth_service.login_employee(db, req.email, req.password)
    _issue_session(response, user)
    return user


@router.post("/logout")
async def logout(response: Response):
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(current: User = Depends(get_current_user)):
    return current


# ----- Google OAuth -----

@router.get("/google/login")
async def google_login(request: Request):
    state = auth_service.make_state()
    url = auth_service.google_authorize_url(state)
    response = RedirectResponse(url)
    response.set_cookie(
        "google_oauth_state",
        state,
        httponly=True,
        samesite="lax",
        max_age=600,
        path="/",
    )
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    saved = request.cookies.get("google_oauth_state")
    if not code or not state or not saved or saved != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    user = await auth_service.google_exchange_and_login(db, code)
    redirect = RedirectResponse(url=settings.FRONTEND_ORIGIN)
    set_session_cookie(redirect, create_access_token(user.id))
    redirect.delete_cookie("google_oauth_state", path="/")
    return redirect
