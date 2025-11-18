import asyncio
from datetime import timedelta, datetime, timezone
from typing import Type
from unittest.mock import AsyncMock, create_autospec, patch

import pytest

from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.hasher.base import ApiKeyHasher
from fastapi_api_key.repositories.base import AbstractApiKeyRepository
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key import ApiKeyService
from fastapi_api_key.domain.errors import (
    KeyNotFound,
    KeyNotProvided,
    KeyInactive,
    KeyExpired,
    InvalidKey,
    ApiKeyError,
    InvalidScopes,
)
from fastapi_api_key.services.cached import CachedApiKeyService
from fastapi_api_key.utils import datetime_factory, key_id_factory, key_secret_factory

# test_cached_api_key_service.py
import hashlib
from unittest.mock import MagicMock

from fastapi_api_key.services.base import DEFAULT_SEPARATOR


def _full_key(
    key_id: str,
    secret: str,
    separator: str,
    global_prefix: str,
) -> str:
    """Compose a full API key from parts."""
    return f"{global_prefix}{separator}{key_id}{separator}{secret}"


@pytest.mark.asyncio
async def test_create_success(
    service: ApiKeyService[ApiKey],
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
    created_entity, full_key = await service.create(entity, key_secret=secret)
    expected_hash = fixed_salt_hasher.hash(secret)

    assert full_key == _full_key(prefix, secret, global_prefix="ak", separator=".")
    assert created_entity.key_id == prefix
    assert created_entity.key_hash == expected_hash

    # Double-check it was persisted
    fetched = await service._repo.get_by_id(created_entity.id_)
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

    got = await service._verify_key(full)
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
        await service._verify_key(None)


@pytest.mark.asyncio
async def test_verify_key_empty_raises(service: ApiKeyService[ApiKey]) -> None:
    """verify_key(): should raise KeyNotProvided when key is empty."""
    with pytest.raises(KeyNotProvided, match=r"Api key must be provided \(empty\)"):
        await service._verify_key("   ")


@pytest.mark.parametrize(
    [
        "exception",
        "api_key",
    ],
    [
        [InvalidKey, "ak."],  # Missing key id, secret
        [InvalidKey, "ak.key_id"],  # Missing secret
        [KeyNotProvided, "ak..key_secret"],  # Missing key id
        [InvalidKey, "ak.key_id.key_secret."],  # Too many segments
        [InvalidKey, "aa.key_id.key_secret"],  # Bad global prefix
        [InvalidKey, "aks.key_id.key_secret"],  # Bad global prefix
        [InvalidKey, "ak-key_id-key_secret"],  # Bad separator
        [InvalidKey, "ak.key_id-key_secret"],  # Bad separator
        [InvalidKey, "ak-key_id.key_secret"],  # Bad separator
        [InvalidKey, "ak.key_id.key_secret."],  # Too many segments
        [InvalidKey, ".ak.key_id.key_secret"],  # Too many segments
    ],
)
@pytest.mark.asyncio
async def test_verify_key_malformed_raises(
    service: ApiKeyService[ApiKey],
    exception: Type[ApiKeyError],
    api_key: str,
) -> None:
    """verify_key(): should raise ApiKeyError on malformed keys."""
    with pytest.raises(exception):
        await service._verify_key(api_key)


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
        await service._verify_key(bad)


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
        await service._verify_key(bad)


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
        await service._verify_key(bad)


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
        await service._verify_key(bad)


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
        await service._verify_key(bad)


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
        await svc._verify_key(f"ak.{p}.{provided}")

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


# --- Cached ---


@pytest.mark.asyncio
async def test_verify_key_hashes_key_and_writes_to_cache_on_miss(
    monkeypatch: pytest.MonkeyPatch,
    fixed_salt_hasher: ApiKeyHasher,
):
    """Ensure the API key is hashed before cache access and that a cache miss stores the entity.

    Steps:
      1) Cache.get -> None (cache miss)
      2) super().verify_key -> returns a fake entity
      3) Cache.set is called with the SHA256 hash key and the returned entity
    """
    # Mock cache with async get/set
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()

    # Build service
    repo_mock = InMemoryApiKeyRepository()
    service = CachedApiKeyService(
        repo=repo_mock,
        cache=cache,
        cache_prefix="api_key",
        hasher=fixed_salt_hasher,
        domain_cls=ApiKey,
        separator=DEFAULT_SEPARATOR,
        global_prefix="ak",
    )

    entity = ApiKey(name="test")
    entity, api_key = await service.create(entity)

    expected_hash = hashlib.sha256(f"{entity.key_id}{entity.key_hash}".encode()).hexdigest()
    await service._verify_key(api_key)

    # cache.get must be called with the hashed key only (never the raw key)
    cache.get.assert_awaited_once_with(expected_hash)
    cache.set.assert_awaited_once_with(expected_hash, entity)


@pytest.mark.asyncio
async def test_verify_key_returns_cached_when_present(
    monkeypatch: pytest.MonkeyPatch,
    fixed_salt_hasher: ApiKeyHasher,
):
    """If the cache already contains the entity, return it and do NOT call the repo/super."""
    entity = ApiKey(name="test")

    cache = AsyncMock()
    cache.get = AsyncMock(return_value=entity)
    cache.set = AsyncMock()

    # Even if patched, it must NOT be called in this scenario
    super_verify_mock = AsyncMock()
    monkeypatch.setattr(ApiKeyService, "verify_key", super_verify_mock)

    repo_mock = InMemoryApiKeyRepository()
    service = CachedApiKeyService(
        repo=repo_mock,
        cache=cache,
        hasher=fixed_salt_hasher,
    )

    entity, api_key = await service.create(entity)
    expected_hash = hashlib.sha256(f"{entity.key_id}{entity.key_hash}".encode()).hexdigest()

    await service._verify_key(api_key)
    cache.get.assert_awaited_once_with(expected_hash)
    super_verify_mock.assert_not_awaited()
    cache.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_key_raises_when_missing_key(fixed_salt_hasher: ApiKeyHasher):
    """If no API key is provided, a KeyNotProvided error must be raised."""
    service = CachedApiKeyService(
        repo=MagicMock(),
        cache=MagicMock(),
        hasher=fixed_salt_hasher,
    )

    with pytest.raises(KeyNotProvided):
        await service._verify_key(None)


@pytest.mark.asyncio
async def test_verify_key_good_scope_success(service: ApiKeyService[ApiKey]):
    """verify_key(): should pass when no required_scopes are given."""
    entity = ApiKey(scopes=["read"], name="to-verify")
    entity, api_key = await service.create(entity=entity)
    await service._verify_key(api_key, required_scopes=["read"])


@pytest.mark.asyncio
async def test_verify_key_good_scopes_success(service: ApiKeyService[ApiKey]):
    """verify_key(): should pass when no required_scopes are given."""
    entity = ApiKey(scopes=["read", "write"], name="to-verify")
    entity, api_key = await service.create(entity=entity)
    await service._verify_key(api_key, required_scopes=["read", "write"])


@pytest.mark.asyncio
async def test_verify_key_good_and_more_scopes_success(service: ApiKeyService[ApiKey]):
    """verify_key(): should pass when no required_scopes are given."""
    entity = ApiKey(scopes=["read", "write", "delete", "all"], name="to-verify")
    entity, api_key = await service.create(entity=entity)
    await service._verify_key(api_key, required_scopes=["read", "write"])


@pytest.mark.asyncio
async def test_verify_key_no_scopes_passes(service: ApiKeyService[ApiKey]):
    """verify_key(): should pass when no required_scopes are given."""
    entity = ApiKey(scopes=["read", "write"], name="to-verify")
    entity, api_key = await service.create(entity=entity)
    await service._verify_key(api_key)


@pytest.mark.asyncio
async def test_verify_key_raises_when_bad_scope(service: ApiKeyService[ApiKey]):
    """verify_key(): should raise InvalidKey when secret does not match."""
    entity = ApiKey(name="to-verify", scopes=["read"])
    entity, api_key = await service.create(entity=entity)

    with pytest.raises(InvalidScopes, match=r"API key is missing required scopes: write"):
        await service._verify_key(api_key, required_scopes=["write"])


@pytest.mark.asyncio
async def test_verify_key_raises_when_partial_scopes(service: ApiKeyService[ApiKey]):
    """verify_key(): should raise InvalidScopes when required_scopes are not all present."""
    entity = ApiKey(name="to-verify", scopes=["read"])
    entity, api_key = await service.create(entity=entity)

    with pytest.raises(InvalidScopes, match=r"API key is missing required scopes: write, delete"):
        await service._verify_key(api_key, required_scopes=["read", "write", "delete"])


@pytest.mark.parametrize(
    "exception",
    [
        KeyNotFound(),
        KeyInactive(),
        KeyExpired(),
        InvalidKey(),
        InvalidScopes(),
    ],
)
@pytest.mark.asyncio
async def test_rrd_work_when_raises(
    service: ApiKeyService[ApiKey],
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
):
    """Ensure that read-during-write operations still work when an error is raised."""
    # The fixture service have rdd enabled with 0.5s delay
    service.rrd = 0.5

    def fake_method(*args, **kwargs):
        raise exception

    api_key = ApiKey.full_key_secret(
        global_prefix="ak",
        key_id=key_id_factory(),
        key_secret=key_secret_factory(),
        separator="-",
    )

    monkeypatch.setattr(service, "_verify_key", fake_method)

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(type(exception)):
            await service.verify_key(api_key)

        mock_sleep.assert_awaited_once_with(0.5)
