"""Fetch and manage available models from LiteLLM proxy."""
import httpx
from app.core.config import settings


async def get_available_models() -> list[dict]:
    """Fetch available models from LiteLLM proxy and filter for chat models."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.LITELLM_PROXY_URL}/v1/models",
                headers={"Authorization": f"Bearer {settings.LITELLM_API_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()

            # Filter for chat-capable models (exclude embeddings and image generation)
            models = data.get("data", [])
            chat_models = []

            for model in models:
                model_id = model.get("id", "")
                # Include models that are chat-capable
                # Exclude embedding and image models
                if not any(
                    x in model_id.lower()
                    for x in ["embedding", "imagen", "image", "embed"]
                ):
                    chat_models.append(
                        {
                            "id": model_id,
                            "name": model_id.replace("gemini/", "").replace("-", " ").title(),
                            "provider": (
                                "Google"
                                if "gemini" in model_id.lower()
                                else "OpenAI"
                                if "gpt" in model_id.lower()
                                else "Other"
                            ),
                        }
                    )

            return chat_models
    except Exception as e:
        print(f"Error fetching models from LiteLLM: {e}")
        # Fallback to default models
        return [
            {"id": "gpt-4o", "name": "GPT-4o", "provider": "OpenAI"},
            {
                "id": "gemini/gemini-2.5-flash",
                "name": "Gemini 2.5 Flash",
                "provider": "Google",
            },
        ]
