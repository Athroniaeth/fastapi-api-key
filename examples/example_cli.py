import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fastapi_api_key import ApiKeyService
from fastapi_api_key.cli import create_api_keys_cli
from fastapi_api_key.domain.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository

pepper = os.environ.get("API_KEY_PEPPER")
db_path = Path(__file__).parent / "db.sqlite3"
database_url = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

print(f"Using database URL: {database_url}")
async_engine = create_async_engine(database_url)
async_session_maker = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
hasher = Argon2ApiKeyHasher(pepper=pepper)


@asynccontextmanager
async def service_factory() -> AsyncIterator[ApiKeyService]:
    """Yield an ApiKeyService backed by the SQLite SQLAlchemy repository."""
    async with async_session_maker() as async_session:
        repo = SqlAlchemyApiKeyRepository(async_session=async_session)
        await repo.ensure_table()
        service = ApiKeyService(repo=repo, hasher=hasher)
        try:
            yield service
            await async_session.commit()
        except Exception:
            await async_session.rollback()
            raise


app = create_api_keys_cli(service_factory)


if __name__ == "__main__":
    # Run the CLI with `uv run examples/example_cli.py`
    app()
