# tests/services/test_api_key_service.py
from __future__ import annotations

from datetime import timedelta
from typing import Iterator
from unittest.mock import AsyncMock, create_autospec

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_api_key.domain.entities import ApiKey, ApiKeyHasher
from fastapi_api_key.repositories.base import ApiKeyRepository
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository
from fastapi_api_key.utils import datetime_factory, prefix_factory, key_secret_factory

# Adaptez l'import ci-dessous à l'emplacement réel de votre service.
from fastapi_api_key.services.base import (
    ApiKeyService,
    KeyNotFound,
    KeyNotProvided,
    InvalidKey,
    KeyInactive,
    KeyExpired,
)


def _full_key(prefix: str, secret: str, sep: str = ".", gp: str = "ak") -> str:
    """Compose a full API key from parts."""
    return f"{gp}{sep}{prefix}{sep}{secret}"


@pytest.fixture(params=["memory", "sqlalchemy"], scope="function")
def repository(
    request,
    async_session: AsyncSession,
) -> Iterator[ApiKeyRepository[ApiKey]]:
    """Provide different ApiKeyRepository implementations (memory / sqlalchemy)."""
    if request.param == "memory":
        yield InMemoryApiKeyRepository()
    elif request.param == "sqlalchemy":
        yield SqlAlchemyApiKeyRepository(async_session=async_session)
    else:
        raise ValueError(f"Unknown repository type: {request.param}")


@pytest.fixture(scope="function")
def hasher_mock() -> ApiKeyHasher:
    """Mocked hasher to keep tests fast and to assert protocol correctness.

    Protocol expectation:
      - hash(secret) -> "hash::" + secret
      - verify(stored_hash, candidate_secret) -> stored_hash == "hash::" + candidate_secret
    """
    h = create_autospec(ApiKeyHasher, instance=True)
    h.hash.side_effect = lambda secret: f"hash::{secret}"
    h.verify.side_effect = lambda stored, candidate: stored == f"hash::{candidate}"
    return h


@pytest.fixture(scope="function")
def service(
    repository: ApiKeyRepository[ApiKey],
    hasher_mock: ApiKeyHasher,
) -> ApiKeyService[ApiKey]:
    """Service under test with mocked hasher and parametrized repository."""
    return ApiKeyService(
        repo=repository,
        hasher=hasher_mock,
        domain_cls=ApiKey,
        separator=".",
        global_prefix="ak",
    )


# ---------- create ----------


@pytest.mark.parametrize("repository", ["memory", "sqlalchemy"], indirect=True)
@pytest.mark.asyncio
async def test_create_returns_entity_and_full_key(
    service: ApiKeyService[ApiKey],
    repository: ApiKeyRepository[ApiKey],
    hasher_mock: ApiKeyHasher,
) -> None:
    """create(): should persist entity and return full plain key with expected format."""
    prefix = prefix_factory()
    secret = key_secret_factory()
    expires_at = datetime_factory() + timedelta(days=7)

    created_entity, full_key = await service.create(
        name="svc-key",
        description="created via service",
        is_active=True,
        expires_at=expires_at,
        key_id=prefix,
        key_secret=secret,
    )

    assert full_key == _full_key(prefix, secret)
    assert created_entity.key_id == prefix
    assert created_entity.key_hash == f"hash::{secret}"  # hashed via mocked hasher

    # Double-check it was persisted
    fetched = await repository.get_by_id(created_entity.id_)
    assert fetched is not None
    assert fetched.id_ == created_entity.id_


@pytest.mark.asyncio
async def test_create_rejects_past_expiration(service: ApiKeyService[ApiKey]) -> None:
    """create(): should reject past expiration dates."""
    with pytest.raises(ValueError):
        await service.create(
            name="expired",
            expires_at=datetime_factory() - timedelta(seconds=1),
        )


# ---------- get_by_id ----------


@pytest.mark.parametrize("repository", ["memory", "sqlalchemy"], indirect=True)
@pytest.mark.asyncio
async def test_get_by_id_success(service: ApiKeyService[ApiKey]) -> None:
    """get_by_id(): should return entity when it exists."""
    # Create one to fetch
    ent, _ = await service.create(name="to-fetch")
    got = await service.get_by_id(ent.id_)
    assert got.id_ == ent.id_


@pytest.mark.asyncio
async def test_get_by_id_empty_raises(service: ApiKeyService[ApiKey]) -> None:
    """get_by_id(): should raise KeyNotProvided on empty input."""
    with pytest.raises(KeyNotProvided):
        await service.get_by_id("")


@pytest.mark.asyncio
async def test_get_by_id_not_found_raises(hasher_mock: ApiKeyHasher) -> None:
    """get_by_id(): should raise KeyNotFound when repository returns None."""
    # Mock repository for the error path
    repo = create_autospec(ApiKeyRepository[ApiKey], instance=True)
    repo.get_by_id = AsyncMock(return_value=None)
    svc = ApiKeyService(repo=repo, hasher=hasher_mock, domain_cls=ApiKey)

    with pytest.raises(KeyNotFound):
        await svc.get_by_id("missing-id")


# ---------- get_by_prefix ----------


@pytest.mark.parametrize("repository", ["memory", "sqlalchemy"], indirect=True)
@pytest.mark.asyncio
async def test_get_by_prefix_success(service: ApiKeyService[ApiKey]) -> None:
    """get_by_prefix(): should find by key_id."""
    prefix = prefix_factory()
    secret = key_secret_factory()
    ent, _ = await service.create(name="by-key_id", key_id=prefix, key_secret=secret)
    got = await service.get_by_key_id(prefix)
    assert got.id_ == ent.id_


@pytest.mark.asyncio
async def test_get_by_prefix_empty_raises(service: ApiKeyService[ApiKey]) -> None:
    """get_by_prefix(): should raise KeyNotProvided on empty."""
    with pytest.raises(KeyNotProvided):
        await service.get_by_key_id("   ")


@pytest.mark.asyncio
async def test_get_by_prefix_not_found_raises(hasher_mock: ApiKeyHasher) -> None:
    """get_by_prefix(): should raise KeyNotFound when not present."""
    repo = create_autospec(ApiKeyRepository[ApiKey], instance=True)
    repo.get_by_key_id = AsyncMock(return_value=None)
    svc = ApiKeyService(repo=repo, hasher=hasher_mock, domain_cls=ApiKey)

    with pytest.raises(KeyNotFound):
        await svc.get_by_key_id("nope")


# ---------- update ----------


@pytest.mark.parametrize("repository", ["memory", "sqlalchemy"], indirect=True)
@pytest.mark.asyncio
async def test_update_success(service: ApiKeyService[ApiKey]) -> None:
    """update(): should persist modifications."""
    ent, _ = await service.create(name="to-update")
    ent.name = "updated-name"
    updated = await service.update(ent)
    assert updated.name == "updated-name"


@pytest.mark.asyncio
async def test_update_not_found_raises(hasher_mock: ApiKeyHasher) -> None:
    """update(): should raise KeyNotFound when repository returns None."""
    repo = create_autospec(ApiKeyRepository[ApiKey], instance=True)
    repo.update = AsyncMock(return_value=None)
    svc = ApiKeyService(repo=repo, hasher=hasher_mock, domain_cls=ApiKey)

    dummy = ApiKey(
        name="x",
        description="",
        is_active=True,
        expires_at=None,
        created_at=datetime_factory(),
        key_id=prefix_factory(),
        key_hash="hash::whatever",
    )
    # Force an ID to look realistic
    assert dummy.id_ is not None

    with pytest.raises(KeyNotFound):
        await svc.update(dummy)


# ---------- delete_by_id ----------


@pytest.mark.parametrize("repository", ["memory", "sqlalchemy"], indirect=True)
@pytest.mark.asyncio
async def test_delete_by_id_success(service: ApiKeyService[ApiKey]) -> None:
    """delete_by_id(): should delete and then get_by_id should fail."""
    ent, _ = await service.create(name="to-delete")
    assert await service.delete_by_id(ent.id_) is True

    with pytest.raises(KeyNotFound):
        await service.get_by_id(ent.id_)


@pytest.mark.asyncio
async def test_delete_by_id_not_found_raises(hasher_mock: ApiKeyHasher) -> None:
    """delete_by_id(): should raise KeyNotFound when repository returns False."""
    repo = create_autospec(ApiKeyRepository[ApiKey], instance=True)
    repo.delete_by_id = AsyncMock(return_value=False)
    svc = ApiKeyService(repo=repo, hasher=hasher_mock, domain_cls=ApiKey)

    with pytest.raises(KeyNotFound):
        await svc.delete_by_id("missing")


# ---------- list ----------


@pytest.mark.parametrize("repository", ["memory", "sqlalchemy"], indirect=True)
@pytest.mark.asyncio
async def test_list_returns_entities(service: ApiKeyService[ApiKey]) -> None:
    """list(): should return created entities."""
    await service.create(name="k1")
    await service.create(name="k2")

    items = await service.list(limit=10, offset=0)
    assert len(items) >= 2


# ---------- verify_key ----------


@pytest.mark.parametrize("repository", ["memory", "sqlalchemy"], indirect=True)
@pytest.mark.asyncio
async def test_verify_key_success_calls_hasher_with_secret(
    service: ApiKeyService[ApiKey],
    hasher_mock: ApiKeyHasher,
) -> None:
    """verify_key(): success path; should call hasher.verify with the secret part only.

    This asserts protocol correctness: the *service* extracts the secret and passes it to hasher.verify.
    """
    prefix = prefix_factory()
    secret = key_secret_factory()
    ent, full = await service.create(name="verify-ok", key_id=prefix, key_secret=secret)

    got = await service.verify_key(full)
    assert got.id_ == ent.id_

    # Ensure we passed the secret (not the full token) to the hasher
    assert hasher_mock.verify.call_count == 1
    args, _ = hasher_mock.verify.call_args
    assert args[0] == f"hash::{secret}"  # stored hash
    assert args[1] == secret  # candidate SECRET only


@pytest.mark.asyncio
async def test_verify_key_rejects_missing_global_prefix(
    service: ApiKeyService[ApiKey],
) -> None:
    """verify_key(): should reject keys without the required global key_id."""
    bad = _full_key(prefix_factory(), key_secret_factory()).replace("ak.", "xx.")
    with pytest.raises(InvalidKey):
        await service.verify_key(bad)


@pytest.mark.asyncio
async def test_verify_key_rejects_malformed_token(
    service: ApiKeyService[ApiKey],
) -> None:
    """verify_key(): should reject malformed tokens (bad separators/segments)."""
    # Missing one segment
    malformed = "ak." + prefix_factory()
    with pytest.raises(InvalidKey):
        await service.verify_key(malformed)


@pytest.mark.asyncio
async def test_verify_key_id_not_found_raises(hasher_mock: ApiKeyHasher) -> None:
    """verify_key(): should raise KeyNotFound if key_id lookup yields nothing."""
    repo = create_autospec(ApiKeyRepository[ApiKey], instance=True)
    repo.get_by_key_id = AsyncMock(return_value=None)

    svc = ApiKeyService(repo=repo, hasher=hasher_mock, domain_cls=ApiKey)
    with pytest.raises(KeyNotFound):
        await svc.verify_key(_full_key(prefix_factory(), key_secret_factory()))


@pytest.mark.asyncio
async def test_verify_key_inactive_raises(hasher_mock: ApiKeyHasher) -> None:
    """verify_key(): should raise KeyInactive when entity cannot authenticate."""
    # Arrange a fake entity that raises on ensure_can_authenticate
    prefix = prefix_factory()
    secret = key_secret_factory()

    class _E:
        id_ = "id1"
        key_id = prefix
        key_hash = f"hash::{secret}"

        @staticmethod
        def ensure_can_authenticate() -> None:
            raise KeyInactive("inactive")

    repo = create_autospec(ApiKeyRepository[ApiKey], instance=True)
    repo.get_by_key_id = AsyncMock(return_value=_E())

    svc = ApiKeyService(repo=repo, hasher=hasher_mock, domain_cls=ApiKey)

    with pytest.raises(KeyInactive):
        await svc.verify_key(_full_key(prefix, secret))


@pytest.mark.asyncio
async def test_verify_key_expired_raises(hasher_mock: ApiKeyHasher) -> None:
    """verify_key(): should raise KeyExpired when entity is expired."""
    prefix = prefix_factory()
    secret = key_secret_factory()

    class _E:
        id_ = "id1"
        key_id = prefix
        key_hash = f"hash::{secret}"

        @staticmethod
        def ensure_can_authenticate() -> None:
            raise KeyExpired("expired")

    repo = create_autospec(ApiKeyRepository[ApiKey], instance=True)
    repo.get_by_key_id = AsyncMock(return_value=_E())

    svc = ApiKeyService(repo=repo, hasher=hasher_mock, domain_cls=ApiKey)

    with pytest.raises(KeyExpired):
        await svc.verify_key(_full_key(prefix, secret))


@pytest.mark.asyncio
async def test_verify_key_hash_mismatch_raises(hasher_mock: ApiKeyHasher) -> None:
    """verify_key(): should raise InvalidKey on hash mismatch."""
    prefix = prefix_factory()
    stored_secret = "correct-secret"
    provided_secret = "wrong-secret"

    class _E:
        id_ = "id1"
        key_id = prefix
        key_hash = f"hash::{stored_secret}"

        @staticmethod
        def ensure_can_authenticate() -> None:
            return None

    repo = create_autospec(ApiKeyRepository[ApiKey], instance=True)
    repo.get_by_key_id = AsyncMock(return_value=_E())

    svc = ApiKeyService(repo=repo, hasher=hasher_mock, domain_cls=ApiKey)

    with pytest.raises(InvalidKey):
        await svc.verify_key(_full_key(prefix, provided_secret))


# ---------- construction / config ----------


def test_constructor_rejects_separator_in_global_prefix(
    hasher_mock: ApiKeyHasher,
) -> None:
    """Service constructor: should reject a global_prefix that contains the separator."""
    with pytest.raises(ValueError):
        ApiKeyService(
            repo=InMemoryApiKeyRepository(),
            hasher=hasher_mock,
            domain_cls=ApiKey,
            separator=".",
            global_prefix="ak.",  # invalid: contains separator
        )


@pytest.mark.asyncio
async def test_full_key_format_with_custom_separator_and_prefix(
    hasher_mock: ApiKeyHasher,
) -> None:
    """Full key format should respect custom global_prefix and separator."""
    repo = InMemoryApiKeyRepository()
    svc = ApiKeyService(
        repo=repo,
        hasher=hasher_mock,
        domain_cls=ApiKey,
        separator=":",
        global_prefix="APIKEY",
    )
    prefix = prefix_factory()
    secret = key_secret_factory()
    _, full = await svc.create(name="custom", key_id=prefix, key_secret=secret)
    assert full == f"APIKEY:{prefix}:{secret}"
