try:
    import aiocache  # noqa: F401
except ModuleNotFoundError as e:
    raise ImportError(
        "CachedApiKeyService requires 'aiocache'. Install it with: uv add fastapi_api_key[aiocache]"
    ) from e

import hashlib
from typing import Optional, Type

import aiocache
from aiocache import BaseCache

from fastapi_api_key import ApiKeyService
from fastapi_api_key.domain.base import D
from fastapi_api_key.domain.errors import KeyNotProvided
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
    ):
        super().__init__(
            repo=repo,
            hasher=hasher,
            domain_cls=domain_cls,
            separator=separator,
            global_prefix=global_prefix,
        )
        self.cache_prefix = cache_prefix
        self.cache = cache or aiocache.SimpleMemoryCache()

    def _get_cache_key(self, key_id: str) -> str:
        return f"{self.cache_prefix}:{key_id}"

    @staticmethod
    def _hash_api_key(api_key: str) -> str:
        """Hash the API key to use as cache key (don't store raw keys) with SHA256 (faster that Bcrypt)."""
        buffer = api_key.encode()
        return hashlib.sha256(buffer).hexdigest()

    async def verify_key(self, api_key: Optional[str] = None) -> D:
        if api_key is None:
            raise KeyNotProvided("Api key must be provided (not given)")

        hash_api_key = self._hash_api_key(api_key)
        cached_entity = await self.cache.get(hash_api_key)

        if cached_entity:
            return cached_entity

        entity = await super().verify_key(api_key)

        await self.cache.set(hash_api_key, entity)
        return entity
