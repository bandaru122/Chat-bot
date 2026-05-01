"""Quick connectivity test for Supabase Postgres via SQLAlchemy + asyncpg."""
import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

load_dotenv()

URL = os.environ["DATABASE_URL"]
print(f"Connecting to: {URL.split('@')[-1]}")


async def main() -> int:
    engine = create_async_engine(URL, echo=False)
    try:
        async with engine.connect() as conn:
            version = (await conn.execute(text("select version()"))).scalar_one()
            print("OK ->", version)
        return 0
    except Exception as e:
        print(f"FAILED ({type(e).__name__}): {e}")
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
