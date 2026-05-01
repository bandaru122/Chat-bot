"""/api/models — Available LLM models."""
from fastapi import APIRouter

from app.ai.models import get_available_models

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
async def list_available_models():
    """Get list of available chat models from LiteLLM proxy."""
    models = await get_available_models()
    return {"data": models}
