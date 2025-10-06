from __future__ import annotations

import os
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fastapi_api_key import Argon2ApiKeyHasher, ApiKeyService, create_api_keys_cli
from fastapi_api_key.domain.hasher.base import DEFAULT_PEPPER
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository

DB_PATH = Path(__file__).parent / "db.sqlite3"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

PEPPER = os.environ.get("API_KEY_PEPPER", DEFAULT_PEPPER)
if PEPPER == DEFAULT_PEPPER:
    warnings.warn(
        "Using the default pepper is insecure. Set API_KEY_PEPPER for production usage.",
        UserWarning,
    )

ENGINE = create_async_engine(DATABASE_URL, future=True)
SESSION_MAKER = async_sessionmaker(
    ENGINE,
    class_=AsyncSession,
    expire_on_commit=False,
)
HASHER = Argon2ApiKeyHasher(pepper=PEPPER)


@asynccontextmanager
async def service_factory() -> AsyncIterator[ApiKeyService]:
    """Yield an ApiKeyService backed by the SQLite SQLAlchemy repository."""
    async with SESSION_MAKER() as session:
        repo = SqlAlchemyApiKeyRepository(async_session=session)
        await repo.ensure_table()
        service = ApiKeyService(repo=repo, hasher=HASHER)
        try:
            yield service
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app = create_api_keys_cli(service_factory)


if __name__ == "__main__":
    app()
