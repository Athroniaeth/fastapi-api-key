import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from fastapi_api_key import ApiKeyService
from fastapi_api_key.cli import create_api_keys_cli
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository, ApiKeyModelMixin


class Base(DeclarativeBase): ...


class ApiKeyModel(Base, ApiKeyModelMixin): ...


# Set env var to override default pepper
# Using a strong, unique pepper is crucial for security
# Default pepper is insecure and should not be used in production
pepper = os.getenv("API_KEY_PEPPER")
hasher = Argon2ApiKeyHasher(pepper=pepper)

path = Path(__file__).parent / "db.sqlite3"
database_url = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{path}")

async_engine = create_async_engine(database_url, future=True)
async_session_maker = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def service_factory() -> AsyncIterator[ApiKeyService]:
    """Yield an ApiKeyService backed by the SQLite SQLAlchemy repository."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as async_session:
        repo = SqlAlchemyApiKeyRepository(async_session=async_session)
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
