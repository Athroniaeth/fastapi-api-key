"""Unit tests for CachedApiKeyService.

Tests the caching layer behavior:
- Cache hits and misses
- Cache invalidation on update/delete
- Security (cache key is hash of full API key)
"""

import hashlib
from unittest.mock import AsyncMock

import pytest

from fastapi_api_key.domain.errors import InvalidKey, InvalidScopes, KeyInactive
from fastapi_api_key.hasher.base import MockApiKeyHasher
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key.services.cached import CachedApiKeyService, _compute_cache_key
from fastapi_api_key.utils import key_secret_factory


@pytest.fixture
def mock_cache() -> AsyncMock:
    """Create a mock cache with async methods."""
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    cache.delete = AsyncMock()
    return cache


@pytest.fixture
def service(mock_cache: AsyncMock) -> CachedApiKeyService:
    """Create a cached service with mock cache."""
    return CachedApiKeyService(
        repo=InMemoryApiKeyRepository(),
        cache=mock_cache,
        cache_prefix="test",
        hasher=MockApiKeyHasher(pepper="test-pepper"),
        separator="-",
        global_prefix="ak",
        min_delay=0,
        max_delay=0,
    )


class TestCacheKeyComputation:
    """Tests for _compute_cache_key function."""

    def test_compute_cache_key_returns_sha256(self):
        """_compute_cache_key returns SHA256 hash of input."""
        api_key = "ak-abc123-secretXYZ"
        result = _compute_cache_key(api_key)

        expected = hashlib.sha256(api_key.encode()).hexdigest()
        assert result == expected

    def test_compute_cache_key_different_inputs(self):
        """Different inputs produce different cache keys."""
        key1 = _compute_cache_key("ak-abc-secret1")
        key2 = _compute_cache_key("ak-abc-secret2")
        assert key1 != key2


class TestCacheMiss:
    """Tests for cache miss scenarios."""

    @pytest.mark.asyncio
    async def test_verify_cache_miss_stores_entity(
        self,
        service: CachedApiKeyService,
        mock_cache: AsyncMock,
    ):
        """On cache miss, entity is stored in cache with index."""
        entity, api_key = await service.create(name="test")
        mock_cache.get.return_value = None  # Cache miss

        await service.verify_key(api_key)

        # Should call cache.set twice: entity + index
        assert mock_cache.set.await_count == 2

        # First call: entity cache
        expected_cache_key = _compute_cache_key(api_key)
        first_call = mock_cache.set.await_args_list[0]
        assert first_call.args[0] == expected_cache_key

        # Second call: index
        expected_index_key = f"test:idx:{entity.key_id}"
        second_call = mock_cache.set.await_args_list[1]
        assert second_call.args[0] == expected_index_key
        assert second_call.args[1] == expected_cache_key

    @pytest.mark.asyncio
    async def test_verify_cache_miss_validates_key(
        self,
        service: CachedApiKeyService,
        mock_cache: AsyncMock,
    ):
        """On cache miss, full verification is performed."""
        entity, correct_key = await service.create(name="test")
        mock_cache.get.return_value = None

        # Wrong secret should fail
        bad_key = f"ak-{entity.key_id}-wrongsecret"
        with pytest.raises(InvalidKey):
            await service.verify_key(bad_key)


class TestCacheHit:
    """Tests for cache hit scenarios."""

    @pytest.mark.asyncio
    async def test_verify_cache_hit_returns_entity(
        self,
        service: CachedApiKeyService,
        mock_cache: AsyncMock,
    ):
        """On cache hit, cached entity is returned."""
        entity, api_key = await service.create(name="test")
        expected_cache_key = _compute_cache_key(api_key)

        # Simulate cache hit
        mock_cache.get.return_value = entity

        result = await service.verify_key(api_key)

        assert result.id_ == entity.id_
        mock_cache.get.assert_awaited_with(expected_cache_key)
        mock_cache.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_verify_cache_hit_validates_authentication(
        self,
        service: CachedApiKeyService,
        mock_cache: AsyncMock,
    ):
        """On cache hit, authentication state is validated."""
        entity, api_key = await service.create(name="test", is_active=True)

        # Disable entity and put in cache
        entity.is_active = False
        mock_cache.get.return_value = entity

        with pytest.raises(KeyInactive):
            await service.verify_key(api_key)

    @pytest.mark.asyncio
    async def test_verify_cache_hit_validates_scopes(
        self,
        service: CachedApiKeyService,
        mock_cache: AsyncMock,
    ):
        """On cache hit, scopes are validated."""
        entity, api_key = await service.create(name="test", scopes=["read"])
        mock_cache.get.return_value = entity

        with pytest.raises(InvalidScopes, match="write"):
            await service.verify_key(api_key, required_scopes=["read", "write"])


class TestCacheInvalidation:
    """Tests for cache invalidation on update/delete."""

    @pytest.mark.asyncio
    async def test_update_invalidates_cache(
        self,
        service: CachedApiKeyService,
        mock_cache: AsyncMock,
    ):
        """update() invalidates cache entry via secondary index."""
        entity, api_key = await service.create(name="test")
        expected_cache_key = _compute_cache_key(api_key)
        expected_index_key = f"test:idx:{entity.key_id}"

        # Simulate index returns cache_key
        mock_cache.get.return_value = expected_cache_key

        entity.name = "updated"
        await service.update(entity)

        # Should lookup index
        mock_cache.get.assert_awaited_with(expected_index_key)

        # Should delete both cache entry and index
        assert mock_cache.delete.await_count == 2
        deleted_keys = [call.args[0] for call in mock_cache.delete.await_args_list]
        assert expected_cache_key in deleted_keys
        assert expected_index_key in deleted_keys

    @pytest.mark.asyncio
    async def test_delete_invalidates_cache(
        self,
        service: CachedApiKeyService,
        mock_cache: AsyncMock,
    ):
        """delete_by_id() invalidates cache entry via secondary index."""
        entity, api_key = await service.create(name="test")
        expected_cache_key = _compute_cache_key(api_key)

        mock_cache.get.return_value = expected_cache_key

        await service.delete_by_id(entity.id_)

        # Should delete both cache entry and index
        assert mock_cache.delete.await_count == 2

    @pytest.mark.asyncio
    async def test_invalidation_handles_missing_index(
        self,
        service: CachedApiKeyService,
        mock_cache: AsyncMock,
    ):
        """Invalidation handles case where index doesn't exist."""
        entity, _ = await service.create(name="test")

        # Index not found
        mock_cache.get.return_value = None

        entity.name = "updated"
        await service.update(entity)

        # Should not crash, no deletes
        mock_cache.delete.assert_not_awaited()


class TestCacheSecurity:
    """Tests for cache security properties."""

    @pytest.mark.asyncio
    async def test_wrong_secret_does_not_hit_cache(
        self,
        service: CachedApiKeyService,
        mock_cache: AsyncMock,
    ):
        """Cache cannot be hit with wrong secret (different hash)."""
        entity, correct_key = await service.create(name="test")

        # First verify populates cache
        mock_cache.get.return_value = None
        await service.verify_key(correct_key)

        mock_cache.reset_mock()

        # Try with wrong secret - should compute different cache key
        wrong_key = f"ak-{entity.key_id}-{key_secret_factory()}"
        wrong_cache_key = _compute_cache_key(wrong_key)
        correct_cache_key = _compute_cache_key(correct_key)

        # These should be different
        assert wrong_cache_key != correct_cache_key

        # Lookup will be for wrong_cache_key, not correct_cache_key
        mock_cache.get.return_value = None  # Cache miss (different key)

        with pytest.raises(InvalidKey, match="hash mismatch"):
            await service.verify_key(wrong_key)


class TestCacheTTL:
    """Tests for cache TTL behavior."""

    @pytest.mark.asyncio
    async def test_cache_set_uses_default_ttl(
        self,
        mock_cache: AsyncMock,
    ):
        """cache.set() is called with default TTL (300 seconds)."""
        service = CachedApiKeyService(
            repo=InMemoryApiKeyRepository(),
            cache=mock_cache,
            hasher=MockApiKeyHasher(pepper="test"),
            min_delay=0,
            max_delay=0,
        )
        entity, api_key = await service.create(name="test")
        mock_cache.get.return_value = None  # Cache miss

        await service.verify_key(api_key)

        # Both cache.set calls should include ttl=300
        for call in mock_cache.set.await_args_list:
            assert call.kwargs.get("ttl") == 300

    @pytest.mark.asyncio
    async def test_cache_set_uses_custom_ttl(
        self,
        mock_cache: AsyncMock,
    ):
        """cache.set() uses custom TTL when provided."""
        service = CachedApiKeyService(
            repo=InMemoryApiKeyRepository(),
            cache=mock_cache,
            cache_ttl=60,
            hasher=MockApiKeyHasher(pepper="test"),
            min_delay=0,
            max_delay=0,
        )
        entity, api_key = await service.create(name="test")
        mock_cache.get.return_value = None

        await service.verify_key(api_key)

        for call in mock_cache.set.await_args_list:
            assert call.kwargs.get("ttl") == 60

    def test_default_ttl_is_300(self):
        """Default cache_ttl is 300 seconds (5 minutes)."""
        service = CachedApiKeyService(
            repo=InMemoryApiKeyRepository(),
            hasher=MockApiKeyHasher(pepper="test"),
            min_delay=0,
            max_delay=0,
        )
        assert service.cache_ttl == 300
