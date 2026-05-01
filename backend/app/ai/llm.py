"""Singleton OpenAI client wired to the Amzur LiteLLM proxy.

Import the client and tracking helper from here in services / chains:

    from app.ai.llm import get_llm_client, tracking_kwargs
"""
import json
from functools import lru_cache

import httpx
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from openai import OpenAI

from app.core.config import settings


@lru_cache
def get_llm_client() -> OpenAI:
    """Return an OpenAI SDK client pointing at the LiteLLM proxy."""
    http_client = httpx.Client(
        verify=True,
        timeout=60.0,
        headers={"User-Agent": "amzur-ai-chat/0.1"},
    )
    return OpenAI(
        api_key=settings.LITELLM_API_KEY,
        base_url=settings.LITELLM_PROXY_URL,
        http_client=http_client,
    )


def tracking_kwargs(test_type: str = "api") -> dict:
    """Return `user`, `extra_body`, and `extra_headers` for utilization tracking."""
    user_id = settings.LITELLM_USER_ID or "anonymous"
    metadata = {
        "department": settings.LITELLM_DEPARTMENT,
        "environment": settings.LITELLM_ENVIRONMENT,
        "application": settings.APP_NAME,
        "test_type": test_type,
    }
    spend_logs_metadata = json.dumps(
        {
            "end_user": user_id,
            "department": metadata["department"],
            "environment": metadata["environment"],
        }
    )
    return {
        "user": user_id,
        "extra_body": {"metadata": metadata},
        "extra_headers": {"x-litellm-spend-logs-metadata": spend_logs_metadata},
    }


@lru_cache
def get_chat_llm() -> ChatOpenAI:
    """LangChain chat LLM bound to the LiteLLM proxy. Use for LCEL chains."""
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        base_url=settings.LITELLM_PROXY_URL,
        api_key=settings.LITELLM_API_KEY,
        timeout=30,
        max_retries=2,
    )


@lru_cache
def get_embeddings() -> OpenAIEmbeddings:
    """LangChain embeddings bound to the LiteLLM proxy."""
    return OpenAIEmbeddings(
        model=settings.LITELLM_EMBEDDING_MODEL,
        base_url=settings.LITELLM_PROXY_URL,
        api_key=settings.LITELLM_API_KEY,
    )
