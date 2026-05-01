"""ChromaDB client + collection helpers (RAG layer).

Embeddings always go through the LiteLLM proxy (per setup-doc §6).
"""
from functools import lru_cache
from typing import Iterable

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from app.ai.llm import get_llm_client
from app.core.config import settings


class LiteLLMEmbedder(EmbeddingFunction):
    def __init__(self, model: str) -> None:
        self.model = model
        self._client = get_llm_client()

    def __call__(self, input: Documents) -> Embeddings:
        resp = self._client.embeddings.create(model=self.model, input=list(input))
        return [d.embedding for d in resp.data]


@lru_cache
def get_chroma_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)


def get_user_collection(user_id: str | int):
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=f"user_{user_id}",
        embedding_function=LiteLLMEmbedder(settings.LITELLM_EMBEDDING_MODEL),
    )


def add_documents(user_id: str | int, ids: Iterable[str], texts: Iterable[str]) -> None:
    coll = get_user_collection(user_id)
    coll.add(ids=list(ids), documents=list(texts))


def query(user_id: str | int, q: str, n: int = 3):
    coll = get_user_collection(user_id)
    return coll.query(query_texts=[q], n_results=n)
