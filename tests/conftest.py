import hashlib
import os
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Iterator

import pytest
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastapi_api_key import InMemoryApiKeyRepository, SqlAlchemyApiKeyRepository
from fastapi_api_key.domain.entities import ApiKey, D, Argon2ApiKeyHasher, ApiKeyHasher
from fastapi_api_key.repositories.base import ApiKeyRepository
from fastapi_api_key.repositories.sql import Base


import pytest_asyncio

from fastapi_api_key.utils import datetime_factory, key_id_factory, key_secret_factory


@pytest_asyncio.fixture(scope="function")
async def async_engine() -> AsyncIterator[AsyncEngine]:
    """Create an in-memory SQLite async engine."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Provide an AsyncSession bound to the in-memory engine."""
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session


def make_api_key() -> ApiKey:
    """Create a fresh ApiKey domain entity with unique key_id/hash."""
    return ApiKey(
        name="test-key",
        description="A test API key",
        is_active=True,
        expires_at=datetime_factory() + timedelta(days=30),
        created_at=datetime_factory(),
        key_id=key_id_factory(),
        key_hash=key_secret_factory(),
    )


@pytest.fixture(params=["memory", "sqlalchemy"], scope="function")
def repository(request, async_session: AsyncSession) -> Iterator[ApiKeyRepository[D]]:
    """Fixture to provide different ApiKeyRepository implementations."""
    if request.param == "memory":
        yield InMemoryApiKeyRepository()
    elif request.param == "sqlalchemy":
        yield SqlAlchemyApiKeyRepository(async_session=async_session)
    else:
        raise ValueError(f"Unknown repository type: {request.param}")


class MockPasswordHasher(PasswordHasher):
    """Mock implementation of Argon2 PasswordHasher with fake salting.

    This mock is designed for unit testing. It simulates hashing with a random
    salt and verification against the stored hash. The raw password is never
    stored in plain form inside the hash.
    """

    def __init__(self, fixed_salt: bool = True) -> None:
        super().__init__()

        # Generate fixed salt for replicate hash for mock purposes
        self._fixed_salt = fixed_salt
        self._salt = os.urandom(8).hex()

    def hash(self, password: str | bytes, *, salt: bytes | None = None) -> str:
        if not self._fixed_salt:
            self._salt = os.urandom(8).hex()
        if isinstance(password, bytes):
            password_bytes = password
        else:
            password_bytes = password.encode()
        digest = hashlib.sha256(password_bytes + self._salt.encode()).hexdigest()
        return f"hashed-{digest}:{self._salt}"

    def verify(self, hash: str, password: str | bytes) -> bool:
        try:
            digest, salt = hash.replace("hashed-", "").split(":")
        except ValueError:
            raise VerifyMismatchError("Malformed hash format")

        if isinstance(password, bytes):
            password_bytes = password
        else:
            password_bytes = password.encode()

        expected = hashlib.sha256(password_bytes + salt.encode()).hexdigest()
        if digest == expected:
            return True
        raise VerifyMismatchError("Mock mismatch")


@pytest.fixture(scope="function")
def api_key_hasher() -> ApiKeyHasher:
    """Factory for mock api key hasher."""
    return Argon2ApiKeyHasher(
        pepper="unit-test-pepper",
        password_hasher=MockPasswordHasher(),
    )
