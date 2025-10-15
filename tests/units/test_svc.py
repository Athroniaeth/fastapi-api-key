import asyncio
from datetime import timedelta, datetime, timezone
from unittest.mock import AsyncMock, create_autospec

import pytest

from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.hasher.base import ApiKeyHasher
from fastapi_api_key.repositories.base import AbstractApiKeyRepository
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key.services.service import (
    ApiKeyService,
)
from fastapi_api_key.domain.errors import (
    KeyNotFound,
    KeyNotProvided,
    KeyInactive,
    KeyExpired,
    InvalidKey,
)
from fastapi_api_key.utils import datetime_factory, key_id_factory, key_secret_factory


def _full_key(
    key_id: str,
    secret: str,
    separator: str,
    global_prefix: str,
) -> str:
    """Compose a full API key from parts."""
    return f"{global_prefix}{separator}{key_id}{separator}{secret}"


@pytest.fixture(scope="function")
def service(
    repository: AbstractApiKeyRepository[ApiKey],
    fixed_salt_hasher: ApiKeyHasher,
) -> ApiKeyService[ApiKey]:
    """Service under test with mocked hasher and parametrized repository."""
    return ApiKeyService(
        repo=repository,
        hasher=fixed_salt_hasher,
        domain_cls=ApiKey,
        separator=".",
        global_prefix="ak",
    )


@pytest.mark.asyncio
async def test_create_success(
    service: ApiKeyService[ApiKey],
    repository: AbstractApiKeyRepository[ApiKey],
    fixed_salt_hasher: ApiKeyHasher,
) -> None:
    """create(): should persist entity and return full plain key with expected format."""
    prefix = key_id_factory()
    secret = key_secret_factory()
    expires_at = datetime_factory() + timedelta(days=7)
    entity = ApiKey(
        name="svc-key",
        description="created via service",
        is_active=True,
        expires_at=expires_at,
        key_id=prefix,
    )
    created_entity, full_key = await service.create(entity, secret)
    expected_hash = fixed_salt_hasher.hash(secret)

    assert full_key == _full_key(prefix, secret, global_prefix="ak", separator=".")
    assert created_entity.key_id == prefix
    assert created_entity.key_hash == expected_hash

    # Double-check it was persisted
    fetched = await repository.get_by_id(created_entity.id_)
    assert fetched is not None
    assert fetched.id_ == created_entity.id_


@pytest.mark.asyncio
async def test_create_bad_expired_at_raises(service: ApiKeyService[ApiKey]) -> None:
    """create(): should reject past expiration dates."""
    with pytest.raises(ValueError):
        expired_at = datetime_factory() - timedelta(seconds=1)
        entity = ApiKey(name="expired", expires_at=expired_at)
        await service.create(entity)


@pytest.mark.asyncio
async def test_get_by_id_success(service: ApiKeyService[ApiKey]) -> None:
    """get_by_id(): should return entity when it exists."""
    entity = ApiKey(name="expired")
    assert entity.id_ is not None

    entity, _ = await service.create(entity)
    got = await service.get_by_id(entity.id_)
    assert got.id_ == entity.id_


@pytest.mark.asyncio
async def test_get_by_id_empty_raises(service: ApiKeyService[ApiKey]) -> None:
    """get_by_id(): should raise KeyNotProvided on empty input."""
    with pytest.raises(KeyNotProvided):
        await service.get_by_id("  ")


@pytest.mark.asyncio
async def test_get_by_id_not_found_raises(service: ApiKeyService[ApiKey]) -> None:
    """get_by_id(): should raise KeyNotFound when repository returns None."""

    with pytest.raises(KeyNotFound):
        await service.get_by_id("missing-id")


@pytest.mark.asyncio
async def test_get_by_key_id_success(service: ApiKeyService[ApiKey]) -> None:
    """get_by_prefix(): should find by key_id."""
    key_id = key_id_factory()
    key_secret = key_secret_factory()

    entity = ApiKey(name="by-key_id", key_id=key_id)
    entity, _ = await service.create(
        entity=entity,
        key_secret=key_secret,
    )
    got = await service.get_by_key_id(key_id)
    assert got.id_ == entity.id_


@pytest.mark.asyncio
async def test_get_by_key_id_not_found_raises(service: ApiKeyService[ApiKey]) -> None:
    """get_by_prefix(): should raise KeyNotFound when not present."""
    with pytest.raises(KeyNotFound):
        await service.get_by_key_id("nope")


@pytest.mark.asyncio
async def test_get_by_prefix_empty_raises(service: ApiKeyService[ApiKey]) -> None:
    """get_by_prefix(): should raise KeyNotProvided on empty."""
    with pytest.raises(KeyNotProvided):
        await service.get_by_key_id("  ")


@pytest.mark.asyncio
async def test_get_by_prefix_not_found_raises(service: ApiKeyService[ApiKey]) -> None:
    """get_by_prefix(): should raise KeyNotFound when not present."""

    with pytest.raises(KeyNotFound):
        await service.get_by_key_id("nope")


@pytest.mark.asyncio
async def test_update_success(service: ApiKeyService[ApiKey]) -> None:
    """update(): should persist modifications."""
    entity = ApiKey(name="to-update")
    entity, _ = await service.create(entity)
    entity.name = "updated-name"
    updated = await service.update(entity)
    assert updated.name == "updated-name"


@pytest.mark.asyncio
async def test_update_not_found_raises(service: ApiKeyService[ApiKey]) -> None:
    """update(): should raise KeyNotFound when repository returns None."""

    dummy = ApiKey(
        id_="nonexistent-id",
        name="x",
        description="",
        is_active=True,
        expires_at=None,
        created_at=datetime_factory(),
        key_id=key_id_factory(),
        key_hash="hash::whatever",
    )
    # Force an ID to look realistic
    assert dummy.id_ is not None

    with pytest.raises(KeyNotFound):
        await service.update(dummy)


@pytest.mark.asyncio
async def test_delete_by_id_success(service: ApiKeyService[ApiKey]) -> None:
    """delete_by_id(): should delete and then get_by_id should fail."""
    entity = ApiKey(name="to-delete")
    entity, _ = await service.create(entity)
    assert await service.delete_by_id(entity.id_) is True

    with pytest.raises(KeyNotFound):
        await service.get_by_id(entity.id_)


@pytest.mark.asyncio
async def test_delete_by_id_not_found_raises(service: ApiKeyService[ApiKey]) -> None:
    """delete_by_id(): should raise KeyNotFound when repository returns False."""

    with pytest.raises(KeyNotFound):
        await service.delete_by_id("missing")


@pytest.mark.asyncio
async def test_list_success(service: ApiKeyService[ApiKey]) -> None:
    """list(): should return created entities."""
    entity_1 = ApiKey(name="k1")
    entity_2 = ApiKey(name="k2")
    await service.create(entity_1)
    await service.create(entity_2)

    items = await service.list(limit=10, offset=0)
    assert len(items) >= 2


@pytest.mark.asyncio
async def test_list_empty_success(service: ApiKeyService[ApiKey]) -> None:
    """list(): should return empty list when no entities exist."""
    items = await service.list(limit=10, offset=0)
    assert len(items) == 0


@pytest.mark.asyncio
async def test_verify_key_success(service: ApiKeyService[ApiKey]) -> None:
    """verify_key(): should return entity when key is valid."""
    key_id = key_id_factory()
    key_secret = key_secret_factory()

    entity = ApiKey(name="to-verify", key_id=key_id)
    entity, full = await service.create(
        entity=entity,
        key_secret=key_secret,
    )
    today = datetime.now(timezone.utc)
    last_used_before = entity.last_used_at
    assert last_used_before is None

    got = await service.verify_key(full)
    assert got.id_ == entity.id_
    assert got.name == entity.name
    assert got.last_used_at is not None
    assert got.last_used_at != last_used_before
    # Check that api key was "touched" recently
    assert (got.last_used_at - today) < timedelta(seconds=5)


@pytest.mark.asyncio
async def test_verify_key_none_raises(service: ApiKeyService[ApiKey]) -> None:
    """verify_key(): should raise KeyNotProvided when key is None."""
    with pytest.raises(KeyNotProvided, match=r"Api key must be provided \(not given\)"):
        await service.verify_key(None)


@pytest.mark.asyncio
async def test_verify_key_empty_raises(service: ApiKeyService[ApiKey]) -> None:
    """verify_key(): should raise KeyNotProvided when key is empty."""
    with pytest.raises(KeyNotProvided, match=r"Api key must be provided \(empty\)"):
        await service.verify_key("   ")


@pytest.mark.parametrize(
    "api_key",
    [
        "ak.",  # Missing key id, secret
        "ak.key_id",  # Missing secret
        "ak..key_secret",  # Missing key id
        "ak.key_id.key_secret.",  # Too many segments
        "aa.key_id.key_secret",  # Bad global prefix
        "ak-key_id-key_secret",  # Bad separator
        "ak.key_id-key_secret",  # Bad separator
        "ak-key_id.key_secret",  # Bad separator
        "ak.key_id.key_secret.",  # Too many segments
        ".ak.key_id.key_secret",  # Too many segments
    ],
)
@pytest.mark.asyncio
async def test_verify_key_split_invalid(service: ApiKeyService[ApiKey], api_key: str) -> None:
    """verify_key(): should raise InvalidKey when key format is invalid."""
    with pytest.raises((InvalidKey, KeyNotProvided)):  # type: ignore
        await service.verify_key(api_key)


@pytest.mark.asyncio
async def test_verify_key_id_not_found_raises(service: ApiKeyService[ApiKey]) -> None:
    """verify_key(): should raise KeyNotFound if key_id lookup yields nothing."""

    key_id = key_id_factory()
    key_secret = key_secret_factory()
    bad = _full_key(
        key_id,
        key_secret,
        global_prefix="ak",
        separator=".",
    )

    with pytest.raises(KeyNotFound):
        await service.verify_key(bad)


@pytest.mark.asyncio
async def test_verify_key_inactive_raises(service: ApiKeyService[ApiKey]) -> None:
    """verify_key(): should raise KeyInactive when entity cannot authenticate."""
    # Arrange a fake entity that raises on ensure_can_authenticate
    prefix = key_id_factory()
    key_secret = key_secret_factory()

    entity = ApiKey(name="inactive", key_id=prefix, is_active=False)
    await service.create(
        entity=entity,
        key_secret=key_secret,
    )
    bad = _full_key(prefix, key_secret, global_prefix="ak", separator=".")

    with pytest.raises(KeyInactive):
        await service.verify_key(bad)


@pytest.mark.asyncio
async def test_verify_key_expired_raises(service: ApiKeyService[ApiKey]) -> None:
    """verify_key(): should raise KeyExpired when entity is expired."""
    prefix = key_id_factory()
    key_secret = key_secret_factory()
    expires_at = datetime_factory() + timedelta(microseconds=300)

    entity = ApiKey(
        name="expired",
        key_id=prefix,
        expires_at=expires_at,
    )
    await service.create(
        entity=entity,
        key_secret=key_secret,
    )
    bad = _full_key(prefix, key_secret, global_prefix="ak", separator=".")

    await asyncio.sleep(0.3)  # Wait to ensure the key is expired
    with pytest.raises(KeyExpired, match=r"API key is expired."):
        await service.verify_key(bad)


@pytest.mark.asyncio
async def test_verify_key_empty_secret_raises(
    service: ApiKeyService[ApiKey],
) -> None:
    """verify_key(): should raise InvalidKey when secret does not match."""
    prefix = key_id_factory()
    good_secret = key_secret_factory()
    bad_secret = ""

    entity = ApiKey(name="to-verify", key_id=prefix)
    await service.create(
        entity=entity,
        key_secret=good_secret,
    )
    bad = _full_key(prefix, bad_secret, global_prefix="ak", separator=".")

    with pytest.raises(InvalidKey, match=r"API key is invalid \(empty secret\)"):
        await service.verify_key(bad)


@pytest.mark.asyncio
async def test_verify_key_bad_secret_raises(
    service: ApiKeyService[ApiKey],
) -> None:
    """verify_key(): should raise InvalidKey when secret does not match."""
    prefix = key_id_factory()
    good_secret = key_secret_factory()
    bad_secret = key_secret_factory()

    entity = ApiKey(name="to-verify", key_id=prefix)
    await service.create(
        entity=entity,
        key_secret=good_secret,
    )
    bad = _full_key(prefix, bad_secret, global_prefix="ak", separator=".")

    with pytest.raises(InvalidKey, match=r"API key is invalid \(hash mismatch\)"):
        await service.verify_key(bad)


def test_constructor_separator_in_gp_raises(
    hasher: ApiKeyHasher,
) -> None:
    """Service constructor: should reject a global_prefix that contains the separator."""
    with pytest.raises(ValueError):
        ApiKeyService(
            repo=InMemoryApiKeyRepository(),
            hasher=hasher,
            domain_cls=ApiKey,
            separator=".",
            global_prefix="ak.",  # invalid: contains separator ('.' sep in 'ak.')
        )


@pytest.mark.asyncio
async def test_create_custom_success(hasher: ApiKeyHasher) -> None:
    """Full key format should respect custom global_prefix and separator."""
    repo = InMemoryApiKeyRepository()
    svc = ApiKeyService(
        repo=repo,
        hasher=hasher,
        domain_cls=ApiKey,
        separator=":",
        global_prefix="APIKEY",
    )
    prefix = key_id_factory()
    key_secret = key_secret_factory()

    entity = ApiKey(name="custom", key_id=prefix)
    _, full = await svc.create(
        entity=entity,
        key_secret=key_secret,
    )
    assert full == _full_key(
        prefix,
        key_secret,
        ":",
        "APIKEY",
    )


@pytest.mark.asyncio
async def test_errors_do_not_leak_secret(hasher) -> None:
    """Les messages d'erreur ne doivent pas révéler le secret."""
    p, provided = key_id_factory(), "supersecret"

    class _E:
        id_ = "id1"
        key_id = p
        key_hash = "hash::other"

        @staticmethod
        def ensure_can_authenticate() -> None:
            return None

    repo = create_autospec(AbstractApiKeyRepository[ApiKey], instance=True)
    repo.get_by_key_id = AsyncMock(return_value=_E())
    svc = ApiKeyService(repo=repo, hasher=hasher, domain_cls=ApiKey)

    with pytest.raises(InvalidKey) as exc:
        await svc.verify_key(f"ak.{p}.{provided}")

    assert "supersecret" not in str(exc.value)


@pytest.mark.asyncio
async def test_create_can_be_inactive(service: ApiKeyService[ApiKey]) -> None:
    """create(): must don't raise when creating an inactive key."""
    entity = ApiKey(name="inactive", is_active=False)
    entity, _ = await service.create(entity=entity)
    assert entity.is_active is False


@pytest.mark.asyncio
async def test_update_does_not_change_key_hash(service: ApiKeyService[ApiKey]) -> None:
    """update(): must not change key_hash."""
    entity = ApiKey(name="to-update")
    entity, _ = await service.create(entity=entity)
    old_hash = entity.key_hash
    entity.description = "new desc"
    updated = await service.update(entity)
    assert updated.key_hash == old_hash
