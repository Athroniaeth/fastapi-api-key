"""Unit tests for ApiKeyService.

Tests service logic with InMemoryRepository and MockApiKeyHasher.
Focus on business rules, not repository/hasher implementation details.
"""

import asyncio
import os
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from fastapi_api_key import ApiKeyService
from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.domain.errors import (
    ConfigurationError,
    InvalidKey,
    InvalidScopes,
    KeyExpired,
    KeyInactive,
    KeyNotFound,
    KeyNotProvided,
)
from fastapi_api_key.hasher.base import MockApiKeyHasher
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key.utils import datetime_factory, key_id_factory, key_secret_factory


@pytest.fixture
def service() -> ApiKeyService:
    """Create a service with mock hasher and in-memory repo."""
    return ApiKeyService(
        repo=InMemoryApiKeyRepository(),
        hasher=MockApiKeyHasher(pepper="test-pepper"),
        separator=".",
        global_prefix="ak",
        min_delay=0,
        max_delay=0,
    )


def _full_key(key_id: str, key_secret: str) -> str:
    """Compose a full API key from parts."""
    return f"ak.{key_id}.{key_secret}"


class TestServiceCreate:
    """Tests for create() method."""

    @pytest.mark.asyncio
    async def test_create_returns_entity_and_key(self, service: ApiKeyService):
        """create() returns entity and full API key."""
        entity, full_key = await service.create(name="test-key")

        assert entity.id_ is not None
        assert entity.name == "test-key"
        assert full_key.startswith("ak.")
        assert entity.key_id in full_key

    @pytest.mark.asyncio
    async def test_create_with_custom_secret(self, service: ApiKeyService):
        """create() uses provided key_secret."""
        secret = key_secret_factory()
        entity, full_key = await service.create(name="custom", key_secret=secret)

        assert secret in full_key

    @pytest.mark.asyncio
    async def test_create_with_scopes(self, service: ApiKeyService):
        """create() sets scopes correctly."""
        entity, _ = await service.create(name="scoped", scopes=["read", "write"])

        assert entity.scopes == ["read", "write"]

    @pytest.mark.asyncio
    async def test_create_with_past_expiration_raises(self, service: ApiKeyService):
        """create() rejects past expiration date."""
        past = datetime_factory() - timedelta(seconds=1)

        with pytest.raises(ValueError, match="future"):
            await service.create(name="expired", expires_at=past)


class TestServiceGet:
    """Tests for get_by_id() and get_by_key_id() methods."""

    @pytest.mark.asyncio
    async def test_get_by_id_success(self, service: ApiKeyService):
        """get_by_id() returns entity."""
        entity, _ = await service.create(name="test")

        result = await service.get_by_id(entity.id_)
        assert result.id_ == entity.id_

    @pytest.mark.asyncio
    async def test_get_by_id_not_found_raises(self, service: ApiKeyService):
        """get_by_id() raises KeyNotFound for missing ID."""
        with pytest.raises(KeyNotFound):
            await service.get_by_id("missing-id")

    @pytest.mark.asyncio
    async def test_get_by_key_id_success(self, service: ApiKeyService):
        """get_by_key_id() returns entity."""
        entity, _ = await service.create(name="test")

        result = await service.get_by_key_id(entity.key_id)
        assert result.key_id == entity.key_id

    @pytest.mark.asyncio
    async def test_get_by_key_id_not_found_raises(self, service: ApiKeyService):
        """get_by_key_id() raises KeyNotFound for missing key_id."""
        with pytest.raises(KeyNotFound):
            await service.get_by_key_id("missing")


class TestServiceUpdate:
    """Tests for update() method."""

    @pytest.mark.asyncio
    async def test_update_success(self, service: ApiKeyService):
        """update() modifies entity."""
        entity, _ = await service.create(name="original")
        entity.name = "updated"
        entity.scopes = ["admin"]

        updated = await service.update(entity)

        assert updated.name == "updated"
        assert updated.scopes == ["admin"]

    @pytest.mark.asyncio
    async def test_update_preserves_key_hash(self, service: ApiKeyService):
        """update() does not change key_hash."""
        entity, _ = await service.create(name="test")
        original_hash = entity.key_hash

        entity.name = "updated"
        updated = await service.update(entity)

        assert updated.key_hash == original_hash

    @pytest.mark.asyncio
    async def test_update_not_found_raises(self, service: ApiKeyService):
        """update() raises KeyNotFound for missing entity."""
        fake_entity = ApiKey(
            id_="nonexistent",
            key_id=key_id_factory(),
            key_hash="fake-hash",
        )

        with pytest.raises(KeyNotFound):
            await service.update(fake_entity)


class TestServiceDelete:
    """Tests for delete_by_id() method."""

    @pytest.mark.asyncio
    async def test_delete_success(self, service: ApiKeyService):
        """delete_by_id() removes entity."""
        entity, _ = await service.create(name="to-delete")

        deleted = await service.delete_by_id(entity.id_)
        assert deleted.id_ == entity.id_

        with pytest.raises(KeyNotFound):
            await service.get_by_id(entity.id_)

    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self, service: ApiKeyService):
        """delete_by_id() raises KeyNotFound for missing ID."""
        with pytest.raises(KeyNotFound):
            await service.delete_by_id("missing")


class TestServiceVerifyKey:
    """Tests for verify_key() method."""

    @pytest.mark.asyncio
    async def test_verify_success(self, service: ApiKeyService):
        """verify_key() returns entity for valid key."""
        entity, full_key = await service.create(name="to-verify")

        result = await service.verify_key(full_key)

        assert result.id_ == entity.id_
        assert result.last_used_at is not None

    @pytest.mark.asyncio
    async def test_verify_updates_last_used_at(self, service: ApiKeyService):
        """verify_key() updates last_used_at."""
        entity, full_key = await service.create(name="test")
        assert entity.last_used_at is None

        result = await service.verify_key(full_key)

        assert result.last_used_at is not None

    @pytest.mark.asyncio
    async def test_verify_none_raises(self, service: ApiKeyService):
        """verify_key() raises KeyNotProvided for None."""
        with pytest.raises(KeyNotProvided, match="not given"):
            await service.verify_key(None)  # type: ignore

    @pytest.mark.asyncio
    async def test_verify_empty_raises(self, service: ApiKeyService):
        """verify_key() raises InvalidKey for empty/whitespace string."""
        with pytest.raises(KeyNotProvided, match=r"Api key must be provided \(not given\)"):
            await service.verify_key("   ")

    @pytest.mark.asyncio
    async def test_verify_wrong_prefix_raises(self, service: ApiKeyService):
        """verify_key() raises InvalidKey for wrong prefix."""
        with pytest.raises(InvalidKey, match="wrong global prefix"):
            await service.verify_key("bad.key_id.secret")

    @pytest.mark.asyncio
    async def test_verify_wrong_format_raises(self, service: ApiKeyService):
        """verify_key() raises InvalidKey for malformed key."""
        with pytest.raises(InvalidKey, match="wrong number of segments"):
            await service.verify_key("ak.too.many.segments")

    @pytest.mark.asyncio
    async def test_verify_empty_segment_raises(self, service: ApiKeyService):
        """verify_key() raises InvalidKey for empty segments."""
        with pytest.raises(InvalidKey, match="empty segment"):
            await service.verify_key("ak..secret")  # empty key_id

        with pytest.raises(InvalidKey, match="empty segment"):
            await service.verify_key(".key_id.secret")  # empty prefix

        with pytest.raises(InvalidKey, match="empty segment"):
            await service.verify_key("ak.key_id.")  # empty secret

    @pytest.mark.asyncio
    async def test_verify_not_found_raises(self, service: ApiKeyService):
        """verify_key() raises KeyNotFound for unknown key_id."""
        fake_key = _full_key(key_id_factory(), key_secret_factory())

        with pytest.raises(KeyNotFound):
            await service.verify_key(fake_key)

    @pytest.mark.asyncio
    async def test_verify_wrong_secret_raises(self, service: ApiKeyService):
        """verify_key() raises InvalidKey for wrong secret."""
        entity, _ = await service.create(name="test")
        bad_key = _full_key(entity.key_id, key_secret_factory())

        with pytest.raises(InvalidKey, match="hash mismatch"):
            await service.verify_key(bad_key)

    @pytest.mark.asyncio
    async def test_verify_inactive_raises(self, service: ApiKeyService):
        """verify_key() raises KeyInactive for disabled key."""
        secret = key_secret_factory()
        entity, _ = await service.create(name="inactive", is_active=False, key_secret=secret)
        full_key = _full_key(entity.key_id, secret)

        with pytest.raises(KeyInactive):
            await service.verify_key(full_key)

    @pytest.mark.asyncio
    async def test_verify_expired_raises(self, service: ApiKeyService):
        """verify_key() raises KeyExpired for expired key."""
        secret = key_secret_factory()
        expires_at = datetime_factory() + timedelta(milliseconds=1)
        entity, _ = await service.create(name="expired", expires_at=expires_at, key_secret=secret)
        full_key = _full_key(entity.key_id, secret)

        await asyncio.sleep(0.002)  # Wait for expiration

        with pytest.raises(KeyExpired):
            await service.verify_key(full_key)


class TestServiceScopeVerification:
    """Tests for scope verification in verify_key()."""

    @pytest.mark.asyncio
    async def test_verify_with_matching_scopes(self, service: ApiKeyService):
        """verify_key() passes when key has required scopes."""
        entity, full_key = await service.create(name="scoped", scopes=["read", "write"])

        result = await service.verify_key(full_key, required_scopes=["read", "write"])
        assert result.id_ == entity.id_

    @pytest.mark.asyncio
    async def test_verify_with_extra_scopes(self, service: ApiKeyService):
        """verify_key() passes when key has more than required scopes."""
        entity, full_key = await service.create(name="scoped", scopes=["read", "write", "admin"])

        result = await service.verify_key(full_key, required_scopes=["read"])
        assert result.id_ == entity.id_

    @pytest.mark.asyncio
    async def test_verify_missing_scope_raises(self, service: ApiKeyService):
        """verify_key() raises InvalidScopes for missing scope."""
        entity, full_key = await service.create(name="limited", scopes=["read"])

        with pytest.raises(InvalidScopes, match="write"):
            await service.verify_key(full_key, required_scopes=["read", "write"])

    @pytest.mark.asyncio
    async def test_verify_no_required_scopes(self, service: ApiKeyService):
        """verify_key() passes when no scopes required."""
        entity, full_key = await service.create(name="test", scopes=["read"])

        result = await service.verify_key(full_key)
        assert result.id_ == entity.id_


class TestServiceTimingAttackMitigation:
    """Tests for response delay timing attack mitigation."""

    @pytest.mark.asyncio
    async def test_delay_applies_on_error(self):
        """verify_key() adds random delay on verification failure."""
        service = ApiKeyService(
            repo=InMemoryApiKeyRepository(),
            hasher=MockApiKeyHasher(pepper="test"),
            min_delay=0.1,
            max_delay=0.3,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(InvalidKey):
                await service.verify_key("ak.fake.secret")

            mock_sleep.assert_awaited_once()
            assert mock_sleep.await_args, "Expected sleep to be called"
            delay = mock_sleep.await_args.args[0]
            assert 0.1 <= delay <= 0.3

    @pytest.mark.asyncio
    async def test_delay_applies_on_success(self):
        """verify_key() adds random delay on successful verification."""
        service = ApiKeyService(
            repo=InMemoryApiKeyRepository(),
            hasher=MockApiKeyHasher(pepper="test"),
            min_delay=0.1,
            max_delay=0.3,
        )
        _, full_key = await service.create(name="ok")

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await service.verify_key(full_key)

            mock_sleep.assert_awaited_once()
            assert mock_sleep.await_args, "Expected sleep to be called"
            delay = mock_sleep.await_args.args[0]
            assert 0.1 <= delay <= 0.3

    def test_rrd_warns_and_is_ignored(self):
        """rrd emits a deprecation warning when provided."""
        with pytest.warns(DeprecationWarning, match="rrd is deprecated"):
            ApiKeyService(
                repo=InMemoryApiKeyRepository(),
                hasher=MockApiKeyHasher(pepper="test"),
                rrd=0.1,
            )


class TestServiceConstructor:
    """Tests for service constructor validation."""

    def test_separator_in_prefix_raises(self):
        """Constructor rejects separator in global_prefix."""
        with pytest.raises(ValueError, match="Separator"):
            ApiKeyService(
                repo=InMemoryApiKeyRepository(),
                hasher=MockApiKeyHasher(pepper="test"),
                separator=".",
                global_prefix="ak.",
            )

    def test_custom_prefix_and_separator(self):
        """Constructor accepts custom prefix and separator."""
        service = ApiKeyService(
            repo=InMemoryApiKeyRepository(),
            hasher=MockApiKeyHasher(pepper="test"),
            separator=":",
            global_prefix="KEY",
            min_delay=0,
            max_delay=0,
        )

        assert service.separator == ":"
        assert service.global_prefix == "KEY"

    def test_negative_delay_raises(self):
        """Constructor rejects negative delay values."""
        with pytest.raises(ValueError, match="non-negative"):
            ApiKeyService(
                repo=InMemoryApiKeyRepository(),
                hasher=MockApiKeyHasher(pepper="test"),
                min_delay=-0.1,
                max_delay=0.1,
            )

    def test_max_delay_less_than_min_raises(self):
        """Constructor rejects max_delay below min_delay."""
        with pytest.raises(ValueError, match="greater than or equal"):
            ApiKeyService(
                repo=InMemoryApiKeyRepository(),
                hasher=MockApiKeyHasher(pepper="test"),
                min_delay=0.2,
                max_delay=0.1,
            )


class TestServiceListFindCount:
    """Tests for list(), find(), count() methods."""

    @pytest.fixture
    def service(self) -> ApiKeyService:
        return ApiKeyService(
            repo=InMemoryApiKeyRepository(),
            hasher=MockApiKeyHasher(pepper="test"),
            min_delay=0,
            max_delay=0,
        )

    @pytest.mark.asyncio
    async def test_list_returns_entities(self, service: ApiKeyService):
        """list() returns created entities."""
        await service.create(name="k1")
        await service.create(name="k2")

        result = await service.list(limit=10, offset=0)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_find_delegates_to_repo(self, service: ApiKeyService):
        """find() delegates to repository."""
        await service.create(name="active", is_active=True)
        await service.create(name="inactive", is_active=False)

        from fastapi_api_key.repositories.base import ApiKeyFilter

        result = await service.find(ApiKeyFilter(is_active=True))
        assert len(result) == 1
        assert result[0].name == "active"

    @pytest.mark.asyncio
    async def test_count_delegates_to_repo(self, service: ApiKeyService):
        """count() delegates to repository."""
        await service.create(name="k1")
        await service.create(name="k2")
        await service.create(name="k3")

        assert await service.count() == 3

    @pytest.mark.asyncio
    async def test_count_with_filter(self, service: ApiKeyService):
        """count() with filter delegates to repository."""
        await service.create(name="active", is_active=True)
        await service.create(name="inactive", is_active=False)

        from fastapi_api_key.repositories.base import ApiKeyFilter

        assert await service.count(ApiKeyFilter(is_active=True)) == 1


class TestServiceLoadDotenv:
    """Tests for load_dotenv() method."""

    @pytest.mark.asyncio
    async def test_load_dotenv_creates_keys(self, monkeypatch: pytest.MonkeyPatch):
        """load_dotenv() creates keys from environment variables."""
        service = ApiKeyService(
            repo=InMemoryApiKeyRepository(),
            hasher=MockApiKeyHasher(pepper="test"),
            separator="-",
            global_prefix="ak",
            min_delay=0,
            max_delay=0,
        )

        # Set environment variables
        monkeypatch.setenv("API_KEY_DEV", "ak-abc123def456ghij-secretsecretsecretsecretsecretsecretsecretsecret12")
        monkeypatch.setenv("API_KEY_PROD", "ak-xyz789uvw012mnop-anothersecretanothersecretanothersecretanoth12")

        await service.load_dotenv()

        # Should have created 2 keys
        keys = await service.list()
        assert len(keys) == 2

        names = {k.name for k in keys}
        assert "API_KEY_DEV" in names
        assert "API_KEY_PROD" in names

    @pytest.mark.asyncio
    async def test_load_dotenv_no_keys_raises(self, monkeypatch: pytest.MonkeyPatch):
        """load_dotenv() raises when no matching env vars."""
        service = ApiKeyService(
            repo=InMemoryApiKeyRepository(),
            hasher=MockApiKeyHasher(pepper="test"),
            min_delay=0,
            max_delay=0,
        )

        # Clear any existing API_KEY_ vars
        for key in list(os.environ.keys()):
            if key.startswith("API_KEY_"):
                monkeypatch.delenv(key, raising=False)

        with pytest.raises(ConfigurationError, match="No environment variables found"):
            await service.load_dotenv()

    @pytest.mark.asyncio
    async def test_load_dotenv_custom_prefix(self, monkeypatch: pytest.MonkeyPatch):
        """load_dotenv() uses custom prefix."""
        service = ApiKeyService(
            repo=InMemoryApiKeyRepository(),
            hasher=MockApiKeyHasher(pepper="test"),
            separator="-",
            global_prefix="ak",
            min_delay=0,
            max_delay=0,
        )

        monkeypatch.setenv("MYAPP_KEY_TEST", "ak-abc123def456ghij-secretsecretsecretsecretsecretsecretsecretsecret12")

        await service.load_dotenv(envvar_prefix="MYAPP_KEY_")

        keys = await service.list()
        assert len(keys) == 1
        assert keys[0].name == "MYAPP_KEY_TEST"


class TestServiceEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def service(self) -> ApiKeyService:
        return ApiKeyService(
            repo=InMemoryApiKeyRepository(),
            hasher=MockApiKeyHasher(pepper="test"),
            separator=".",
            global_prefix="ak",
            min_delay=0,
            max_delay=0,
        )

    @pytest.mark.asyncio
    async def test_verify_empty_secret_raises(self, service: ApiKeyService):
        """verify_key() raises InvalidKey for empty secret part."""
        # Create a key, then try to verify with empty secret
        entity, _ = await service.create(name="test")

        # Manually construct key with empty secret
        bad_key = f"ak.{entity.key_id}."

        with pytest.raises(InvalidKey):
            await service.verify_key(bad_key)
