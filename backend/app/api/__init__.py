"""HTTP routers — no business logic, delegate to app/services."""
from fastapi import APIRouter

from app.api import auth as auth_routes
from app.api import chat as chat_routes
from app.api import models as models_routes
from app.api import notes as notes_routes
from app.api import sheets as sheets_routes
from app.api import threads as thread_routes

api_router = APIRouter()
api_router.include_router(auth_routes.router)
api_router.include_router(thread_routes.router)
api_router.include_router(models_routes.router)
api_router.include_router(notes_routes.router)
api_router.include_router(chat_routes.router)
api_router.include_router(sheets_routes.router)

__all__ = ["api_router"]
