try:
    import aiocache  # noqa: F401
except ModuleNotFoundError as e:
    raise ImportError(
        "CachedApiKeyService requires 'aiocache'. Install it with: uv add fastapi_api_key[aiocache]"
    ) from e

import hashlib
from typing import List, Optional

import aiocache
from aiocache import BaseCache

from fastapi_api_key import ApiKeyService
from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.hasher.base import ApiKeyHasher
from fastapi_api_key.repositories.base import AbstractApiKeyRepository
from fastapi_api_key.services.base import DEFAULT_SEPARATOR

INDEX_PREFIX = "idx"
"""Prefix for the secondary index mapping key_id to cache_key."""


def _compute_cache_key(full_api_key: str) -> str:
    """Compute cache key from the full API key using SHA256.

    This ensures the cache can only be hit if the caller knows the complete
    API key (including the secret), providing security equivalent to the
    non-cached verification path.
    """
    buffer = full_api_key.encode()
    return hashlib.sha256(buffer).hexdigest()


class CachedApiKeyService(ApiKeyService):
    """API Key service with caching support (only for verify_key).

    Security Model:
        The cache uses SHA256(full_api_key) as the cache key, ensuring that
        only requests with the correct complete API key can hit the cache.
        A secondary index (key_id → cache_key) enables cache invalidation
        when only the entity is available (e.g., during update/delete).

    Attributes:
        cache: The aiocache backend instance.
        cache_prefix: Prefix for index keys (default: "api_key").
        cache_ttl: Time-to-live for cached entries in seconds (default: 300).
    """

    cache: aiocache.BaseCache
    cache_ttl: int

    def __init__(
        self,
        repo: AbstractApiKeyRepository,
        hasher: ApiKeyHasher,
        cache: Optional[BaseCache] = None,
        cache_prefix: str = "api_key",
        cache_ttl: int = 300,
        separator: str = DEFAULT_SEPARATOR,
        global_prefix: str = "ak",
        rrd: Optional[float] = None,
        min_delay: float = 0.1,
        max_delay: float = 0.3,
    ):
        super().__init__(
            repo=repo,
            hasher=hasher,
            separator=separator,
            global_prefix=global_prefix,
            rrd=rrd,
            min_delay=min_delay,
            max_delay=max_delay,
        )
        self.cache_prefix = cache_prefix
        self.cache_ttl = cache_ttl
        self.cache = cache or aiocache.SimpleMemoryCache()

    def _get_index_key(self, key_id: str) -> str:
        """Build the secondary index key for a given key_id."""
        return f"{self.cache_prefix}:{INDEX_PREFIX}:{key_id}"

    async def _invalidate_cache(self, key_id: str) -> None:
        """Invalidate cache entry using the secondary index.

        This method retrieves the cache_key from the secondary index and
        deletes both the main cache entry and the index entry.
        """
        index_key = self._get_index_key(key_id)

        # Retrieve the cache_key via the secondary index
        cache_key = await self.cache.get(index_key)

        if cache_key:
            # Delete the main cache entry and the index
            await self.cache.delete(cache_key)
            await self.cache.delete(index_key)

    async def update(self, entity: ApiKey) -> ApiKey:
        # Delete cache entry on update (useful when changing scopes or disabling)
        entity = await super().update(entity)
        await self._invalidate_cache(entity.key_id)
        return entity

    async def delete_by_id(self, id_: str) -> ApiKey:
        # Delete cache entry on delete
        entity = await super().delete_by_id(id_)
        await self._invalidate_cache(entity.key_id)
        return entity

    async def _verify_key(self, api_key: Optional[str] = None, required_scopes: Optional[List[str]] = None) -> ApiKey:
        required_scopes = required_scopes or []

        # Use parent's helper for parsing and validation
        parsed = self._parse_and_validate_key(api_key)

        # Compute cache key from the full API key (secure: requires complete key)
        cache_key = _compute_cache_key(parsed.raw)
        cached_entity: Optional[ApiKey] = await self.cache.get(cache_key)

        if cached_entity:
            # Cache hit: the full API key is correct (hash matched)
            cached_entity.ensure_valid(scopes=required_scopes)
            return await self.touch(cached_entity)

        # Cache miss: perform full verification via parent's helper
        entity = await self.get_by_key_id(parsed.key_id)
        entity = await self._verify_entity(entity, parsed.key_secret, required_scopes)

        # Store in cache + create secondary index for invalidation
        index_key = self._get_index_key(parsed.key_id)
        await self.cache.set(cache_key, entity, ttl=self.cache_ttl)
        await self.cache.set(index_key, cache_key, ttl=self.cache_ttl)

        return entity
