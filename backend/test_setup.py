"""Validate every required piece from the External Service Setup Checklist."""
import os
import sys
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

REQUIRED = [
    "SECRET_KEY", "DATABASE_URL", "LITELLM_PROXY_URL", "LITELLM_API_KEY",
    "LITELLM_EMBEDDING_MODEL", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REDIRECT_URI", "CHROMA_PERSIST_DIR", "MAX_UPLOAD_MB", "UPLOAD_DIR",
]

REQUIRED_MODELS = {
    "gpt-4o", "gemini/gemini-2.5-flash",
    "text-embedding-3-large", "gemini/imagen-4.0-fast-generate-001",
}

ok, fail = [], []


def check(name: str, cond: bool, detail: str = ""):
    (ok if cond else fail).append(f"{'✅' if cond else '❌'} {name}{(' — ' + detail) if detail else ''}")


# 1. Required env vars present
for var in REQUIRED:
    val = os.getenv(var)
    check(f"env: {var}", bool(val), "missing" if not val else "")

# 2. DATABASE_URL prefix
db_url = os.getenv("DATABASE_URL", "")
check("DATABASE_URL uses postgresql+asyncpg://", db_url.startswith("postgresql+asyncpg://"))

# 3. GOOGLE_CLIENT_ID format
cid = os.getenv("GOOGLE_CLIENT_ID", "")
check("GOOGLE_CLIENT_ID format", cid.endswith(".apps.googleusercontent.com"))

# 4. GOOGLE_CLIENT_SECRET format
sec = os.getenv("GOOGLE_CLIENT_SECRET", "")
check("GOOGLE_CLIENT_SECRET format", sec.startswith("GOCSPX-"))

# 5. GOOGLE_REDIRECT_URI exact value
check(
    "GOOGLE_REDIRECT_URI exact",
    os.getenv("GOOGLE_REDIRECT_URI") == "http://localhost:8000/api/auth/google/callback",
)

# 6. LiteLLM /v1/models reachable + has all 4 required models
try:
    r = httpx.get(
        f"{os.environ['LITELLM_PROXY_URL']}/v1/models",
        headers={"Authorization": f"Bearer {os.environ['LITELLM_API_KEY']}"},
        timeout=15.0,
    )
    r.raise_for_status()
    available = {m["id"] for m in r.json()["data"]}
    missing = REQUIRED_MODELS - available
    check("LiteLLM models reachable", True, f"{len(available)} models")
    check("All 4 required models present", not missing, f"missing: {missing}" if missing else "")
except Exception as e:
    check("LiteLLM /v1/models", False, f"{type(e).__name__}: {e}")

# 7. Supabase Postgres reachable
async def db_ping():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    eng = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with eng.connect() as c:
            v = (await c.execute(text("select version()"))).scalar_one()
        return True, v.split(",")[0]
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    finally:
        await eng.dispose()

ok_db, msg = asyncio.run(db_ping())
check("Supabase Postgres connection", ok_db, msg)

# Report
print("\n".join(ok + fail))
print(f"\n{len(ok)} passed, {len(fail)} failed")
sys.exit(0 if not fail else 1)
