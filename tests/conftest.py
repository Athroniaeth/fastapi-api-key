import hashlib
import os
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Iterator, Type, Union, Optional

import pytest
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastapi_api_key.domain.base import D
from fastapi_api_key.hasher.bcrypt import BcryptApiKeyHasher
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository, Base
from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.hasher.argon2 import (
    Argon2ApiKeyHasher,
)
from fastapi_api_key.hasher.base import ApiKeyHasher, MockApiKeyHasher
from fastapi_api_key.repositories.base import AbstractApiKeyRepository


import pytest_asyncio

from fastapi_api_key.types import AsyncSessionMaker
from fastapi_api_key.utils import datetime_factory, key_id_factory, key_secret_factory


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

    def hash(self, password: Union[str, bytes], salt: Optional[bytes] = None) -> str:
        if not self._fixed_salt:
            self._salt = os.urandom(8).hex()
        if isinstance(password, bytes):
            password_bytes = password
        else:
            password_bytes = password.encode()
        digest = hashlib.sha256(password_bytes + self._salt.encode()).hexdigest()
        return f"hashed-{digest}:{self._salt}"

    def verify(self, hash: str, password: Union[str, bytes]) -> bool:
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


@pytest_asyncio.fixture(scope="session")
async def async_engine() -> AsyncIterator[AsyncEngine]:
    """Create an in-memory SQLite async engine."""
    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield async_engine
    finally:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await async_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session_maker(async_engine: AsyncEngine) -> AsyncIterator[AsyncSessionMaker]:
    """Provide an AsyncSession bound to the in-memory engine."""
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    yield async_session_maker


@pytest_asyncio.fixture(scope="function")
async def async_session(async_session_maker: AsyncSessionMaker) -> AsyncIterator[AsyncSession]:
    """Provide an AsyncSession bound to the in-memory engine."""
    async with async_session_maker() as session:
        yield session


def make_api_key() -> ApiKey:
    """Create a fresh ApiKey domain entity with unique key_id/hash."""
    key_secret = key_secret_factory()
    key_hash = hashlib.sha256(key_secret.encode()).hexdigest()

    api_key = ApiKey(
        name="test-key",
        description="A test API key",
        is_active=True,
        expires_at=datetime_factory() + timedelta(days=30),
        created_at=datetime_factory(),
        key_id=key_id_factory(),
        _key_secret=key_secret_factory(),
        key_hash=key_hash,
    )
    return api_key


@pytest.fixture(params=["argon2", "bcrypt", "mock"], scope="function")
def hasher_class(request: pytest.FixtureRequest) -> Type[ApiKeyHasher]:
    """Helper to get the hasher class from the request parameter."""
    if request.param == "argon2":
        return Argon2ApiKeyHasher
    elif request.param == "bcrypt":
        return BcryptApiKeyHasher
    elif request.param == "mock":
        return MockApiKeyHasher
    else:
        raise ValueError(f"Unknown hasher type: {request.param}")


@pytest.fixture()
def hasher(hasher_class: Type[ApiKeyHasher]) -> Iterator[ApiKeyHasher]:
    """Fixture providing different ApiKeyHasher implementations."""
    pepper = "unit-test-pepper"

    if issubclass(hasher_class, Argon2ApiKeyHasher):
        hasher_class: Type[Argon2ApiKeyHasher]
        ph = MockPasswordHasher(fixed_salt=False)
        yield hasher_class(pepper=pepper, password_hasher=ph)

    elif issubclass(hasher_class, BcryptApiKeyHasher):
        hasher_class: Type[BcryptApiKeyHasher]
        yield hasher_class(pepper=pepper, rounds=4)

    elif issubclass(hasher_class, MockApiKeyHasher):
        hasher_class: Type[MockApiKeyHasher]
        yield hasher_class(pepper=pepper)

    else:
        raise ValueError(f"Unknown hasher type: {hasher_class}")


@pytest.fixture()
def fixed_salt_hasher(request: pytest.FixtureRequest) -> ApiKeyHasher:
    """Fixture providing different ApiKeyHasher implementations.

    Args:
        request: Pytest internal fixture providing the parameter.

    Yields:
        ApiKeyHasher: A concrete implementation of the hashing protocol.
    """
    pepper = "unit-test-pepper"
    ph = MockPasswordHasher(fixed_salt=True)
    return Argon2ApiKeyHasher(pepper=pepper, password_hasher=ph)


@pytest.fixture(params=["memory", "sqlalchemy"], scope="function")
def repository(request: pytest.FixtureRequest, async_session: AsyncSession) -> Iterator[AbstractApiKeyRepository[D]]:
    """Fixture to provide different AbstractApiKeyRepository implementations."""
    if request.param == "memory":
        yield InMemoryApiKeyRepository()
    elif request.param == "sqlalchemy":
        yield SqlAlchemyApiKeyRepository(async_session=async_session)
    else:
        raise ValueError(f"Unknown repository type: {request.param}")
