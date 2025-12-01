"""Shared fixtures for tests.

Provides:
- Database fixtures (async engine, session)
- Simple hasher fixture (MockApiKeyHasher for speed)
- make_api_key() factory function
"""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Iterator, Optional
import hashlib

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.hasher.base import MockApiKeyHasher, ApiKeyHasher
from fastapi_api_key.repositories.sql import Base
from fastapi_api_key._types import AsyncSessionMaker
from fastapi_api_key.utils import datetime_factory, key_id_factory, key_secret_factory


@pytest_asyncio.fixture(scope="session")
async def async_engine() -> AsyncIterator[AsyncEngine]:
    """Create an in-memory SQLite async engine for the test session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def async_session_maker(async_engine: AsyncEngine) -> AsyncIterator[AsyncSessionMaker]:
    """Provide an async session maker bound to the test engine."""
    maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    yield maker


@pytest_asyncio.fixture(scope="session")
async def async_session(async_session_maker: AsyncSessionMaker) -> AsyncIterator[AsyncSession]:
    """Provide an async session for a single test."""
    async with async_session_maker() as session:
        yield session


@pytest.fixture
def hasher() -> Iterator[ApiKeyHasher]:
    """Provide a fast MockApiKeyHasher for unit tests."""
    yield MockApiKeyHasher(pepper="test-pepper")


#
def make_api_key(
    key_id: Optional[str] = None,
    is_active: bool = True,
    scopes: Optional[list[str]] = None,
) -> ApiKey:
    """Create a fresh ApiKey domain entity with unique key_id/hash.

    Args:
        key_id: Optional key_id. If None, generates a new one.
        is_active: Whether the key is active. Default True.
        scopes: Optional scopes. Default ["read", "write"].

    Returns:
        A new ApiKey entity ready for testing.
    """
    key_id = key_id or key_id_factory()
    key_secret = key_secret_factory()
    key_hash = hashlib.sha256(key_secret.encode()).hexdigest()

    return ApiKey(
        name="test-key",
        description="A test API key",
        is_active=is_active,
        expires_at=datetime_factory() + timedelta(days=30),
        created_at=datetime_factory(),
        key_id=key_id,
        key_secret=key_secret,
        key_hash=key_hash,
        scopes=scopes if scopes is not None else ["read", "write"],
    )
