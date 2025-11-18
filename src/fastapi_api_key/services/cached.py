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


class CachedApiKeyService(ApiKeyService[D]):
    """API Key service with caching support (only for verify_key)."""

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

    def _get_cache_key(self, key_id: str) -> str:
        return f"{self.cache_prefix}:{key_id}"

    def _hash_api_key(self, entity: D) -> str:
        """Hash the API key to use as cache key (don't store raw keys) with SHA256 (faster that Bcrypt)."""
        # buffer = api_key.encode()
        # _, key_prefix, _ = api_key.partition(DEFAULT_SEPARATOR)
        # buffer = key_prefix.encode()
        # return hashlib.sha256(buffer).hexdigest()
        key_id, key_hash = entity.key_id, entity.key_hash
        buffer = f"{key_id}{key_hash}".encode()
        return hashlib.sha256(buffer).hexdigest()

    async def _initialize_cache(self, entity: D) -> D:
        """Helper to initialize cache for an entity, to use after any update of the entity."""
        hash_api_key = self._hash_api_key(entity)
        await self.cache.delete(hash_api_key)
        return entity

    async def update(self, entity: D) -> D:
        # Delete cache entry on update (useful when changing scopes or disabling)
        entity = await super().update(entity)
        return await self._initialize_cache(entity)

    async def delete_by_id(self, id_: str) -> bool:
        result = await self._repo.get_by_id(id_)

        if result is None:
            raise KeyNotFound(f"API key with ID '{id_}' not found")

        # Delete cache entry on delete
        # Todo: Found more optimized way to do this (delete_by_id return directly entity, or delete method)
        await super().delete_by_id(id_)
        await self._initialize_cache(result)
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

        # Search entity by a key_id (can't brute force hashes)
        entity = await self.get_by_key_id(key_id)

        hash_api_key = self._hash_api_key(entity)
        cached_entity = await self.cache.get(hash_api_key)

        if cached_entity:
            return cached_entity

        # Check if the entity can be used for authentication
        # and refresh last_used_at if verified
        entity.ensure_can_authenticate()

        key_hash = entity.key_hash

        if not key_secret:
            raise InvalidKey("API key is invalid (empty secret)")

        if not self._hasher.verify(key_hash, key_secret):
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

        await self.cache.set(hash_api_key, updated)
        return updated
