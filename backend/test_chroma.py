"""Smoke test for ChromaDB + LiteLLM embeddings (setup doc §5 + §6)."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import settings  # noqa: E402
from app.ai.rag.vectorstore import add_documents, query, get_user_collection  # noqa: E402


def main() -> int:
    persist = Path(settings.CHROMA_PERSIST_DIR)
    print(f"Persist dir: {persist.resolve()}")

    user_id = 999  # ephemeral test user
    coll = get_user_collection(user_id)

    docs = [
        "FastAPI is a modern Python web framework for building APIs.",
        "Alembic manages SQLAlchemy schema migrations over time.",
        "ChromaDB is a local vector database that persists to disk.",
        "Supabase provides hosted Postgres with auth and storage.",
    ]
    ids = [f"doc-{i}" for i in range(len(docs))]
    add_documents(user_id, ids, docs)
    print(f"Added {coll.count()} docs to collection 'user_{user_id}'")

    res = query(user_id, "What stores embeddings on disk?", n=2)
    top = res["documents"][0]
    print("Top match:", top[0])

    # Clean up the test collection so re-runs stay deterministic.
    from app.ai.rag.vectorstore import get_chroma_client
    get_chroma_client().delete_collection(f"user_{user_id}")
    print("Cleaned up test collection.")

    print(f"\n{'OK' if persist.exists() else 'FAILED'} — persist dir exists: {persist.exists()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
