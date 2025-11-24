try:
    import aiocache  # noqa: F401
except ModuleNotFoundError as e:
    raise ImportError(
        "CachedApiKeyService requires 'aiocache'. Install it with: uv add fastapi_api_key[aiocache]"
    ) from e

import hashlib
from typing import Optional, Type, List

import aiocache
from aiocache import BaseCache

from fastapi_api_key import ApiKeyService
from fastapi_api_key.domain.base import D
from fastapi_api_key.domain.errors import KeyNotProvided, InvalidKey, InvalidScopes, KeyNotFound
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


class CachedApiKeyService(ApiKeyService[D]):
    """API Key service with caching support (only for verify_key).

    Security Model:
        The cache uses SHA256(full_api_key) as the cache key, ensuring that
        only requests with the correct complete API key can hit the cache.
        A secondary index (key_id → cache_key) enables cache invalidation
        when only the entity is available (e.g., during update/delete).

    Attributes:
        cache: The aiocache backend instance (configure TTL on the cache itself).
        cache_prefix: Prefix for index keys (default: "api_key").
    """

    cache: aiocache.BaseCache

    def __init__(
        self,
        repo: AbstractApiKeyRepository[D],
        cache: Optional[BaseCache] = None,
        cache_prefix: str = "api_key",
        hasher: Optional[ApiKeyHasher] = None,
        domain_cls: Optional[Type[D]] = None,
        separator: str = DEFAULT_SEPARATOR,
        global_prefix: str = "ak",
        rrd: float = 1 / 3,
    ):
        super().__init__(
            repo=repo,
            hasher=hasher,
            domain_cls=domain_cls,
            separator=separator,
            global_prefix=global_prefix,
            rrd=rrd,
        )
        self.cache_prefix = cache_prefix
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

    async def update(self, entity: D) -> D:
        # Delete cache entry on update (useful when changing scopes or disabling)
        entity = await super().update(entity)
        await self._invalidate_cache(entity.key_id)
        return entity

    async def delete_by_id(self, id_: str) -> bool:
        # Todo : optimize db calls by returning deleted entity from repo
        result = await self._repo.get_by_id(id_)

        if result is None:
            raise KeyNotFound(f"API key with ID '{id_}' not found")

        # Delete cache entry on delete
        await super().delete_by_id(id_)
        await self._invalidate_cache(result.key_id)
        return True

    async def _verify_key(self, api_key: Optional[str] = None, required_scopes: Optional[List[str]] = None) -> D:
        required_scopes = required_scopes or []

        if api_key is None:
            raise KeyNotProvided("Api key must be provided (not given)")

        if api_key.strip() == "":
            raise KeyNotProvided("Api key must be provided (empty)")

        # Get the key_id part from the plain key
        global_prefix, key_id, key_secret = self._get_parts(api_key)

        # Global key_id "ak" for "api key"
        if global_prefix != self.global_prefix:
            raise InvalidKey("Api key is invalid (wrong global prefix)")

        # Compute cache key from the full API key (secure: requires complete key)
        cache_key = _compute_cache_key(api_key)
        cached_entity = await self.cache.get(cache_key)

        if cached_entity:
            # Cache hit: the full API key is correct (hash matched)
            cached_entity.ensure_can_authenticate()

            # Check scopes on cache hit
            if required_scopes:
                missing_scopes = [scope for scope in required_scopes if scope not in cached_entity.scopes]
                if missing_scopes:
                    missing_scopes_str = ", ".join(missing_scopes)
                    raise InvalidScopes(f"API key is missing required scopes: {missing_scopes_str}")

            cached_entity.touch()
            updated = await self._repo.update(cached_entity)

            if updated is None:
                raise KeyNotFound(f"API key with ID '{cached_entity.id_}' not found during touch update")

            return updated

        # Cache miss: perform full verification (Argon2/bcrypt)
        entity = await self.get_by_key_id(key_id)
        entity.ensure_can_authenticate()

        assert entity.key_hash is not None, "key_hash must be set for existing API keys"  # nosec B101

        if not key_secret:
            raise InvalidKey("API key is invalid (empty secret)")

        if not self._hasher.verify(entity.key_hash, key_secret):
            raise InvalidKey("API key is invalid (hash mismatch)")

        if required_scopes:
            missing_scopes = [scope for scope in required_scopes if scope not in entity.scopes]
            missing_scopes_str = ", ".join(missing_scopes)
            if missing_scopes:
                raise InvalidScopes(f"API key is missing required scopes: {missing_scopes_str}")

        entity.touch()
        updated = await self._repo.update(entity)

        if updated is None:
            raise KeyNotFound(f"API key with ID '{entity.id_}' not found during touch update")

        # Store in cache + create secondary index for invalidation
        index_key = self._get_index_key(key_id)
        await self.cache.set(cache_key, updated)
        await self.cache.set(index_key, cache_key)

        return updated
