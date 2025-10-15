from typing import Optional, Type, Tuple

from fastapi_api_key.domain.base import D
from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.hasher.base import ApiKeyHasher
from fastapi_api_key.domain.errors import KeyNotFound, KeyNotProvided, InvalidKey
from fastapi_api_key.repositories.base import AbstractApiKeyRepository
from fastapi_api_key.services.base import AbstractApiKeyService
from fastapi_api_key.utils import datetime_factory, key_secret_factory

DEFAULT_SEPARATOR = "-"
"""
Default separator between key_type, key_id, key_secret in the API key string. 
Must be not in `token_urlsafe` alphabet. (like '.', ':', '~", '|')
"""


class ApiKeyService(AbstractApiKeyService[D]):
    """Generic service contract for a domain aggregate."""

    def __init__(
        self,
        repo: AbstractApiKeyRepository[D],
        hasher: Optional[ApiKeyHasher] = None,
        domain_cls: Optional[Type[D]] = None,
        separator: str = DEFAULT_SEPARATOR,
        global_prefix: str = "ak",
    ) -> None:
        domain_cls = domain_cls or ApiKey
        super().__init__(
            repo=repo,
            hasher=hasher,
            domain_cls=domain_cls,
            separator=separator,
            global_prefix=global_prefix,
        )

    async def get_by_id(self, id_: str) -> D:
        if id_.strip() == "":
            raise KeyNotProvided("No API key provided")

        entity = await self._repo.get_by_id(id_)

        if entity is None:
            raise KeyNotFound(f"API key with ID '{id_}' not found")

        return entity

    async def get_by_key_id(self, key_id: str) -> D:
        if not key_id.strip():
            raise KeyNotProvided("No API key key_id provided (key_id cannot be empty)")

        entity = await self._repo.get_by_key_id(key_id)

        if entity is None:
            raise KeyNotFound(f"API key with key_id '{key_id}' not found")

        return entity

    async def create(self, entity: D, key_secret: Optional[str] = None) -> Tuple[D, str]:
        if entity.expires_at and entity.expires_at < datetime_factory():
            raise ValueError("Expiration date must be in the future")

        key_secret = key_secret or entity.key_secret or key_secret_factory()

        full_key_secret = entity.full_key_secret(
            self.global_prefix,
            self.separator,
            key_secret=key_secret,
        )
        entity.key_hash = self._hasher.hash(key_secret)
        entity._key_secret = key_secret
        return await self._repo.create(entity), full_key_secret

    async def update(self, entity: D) -> D:
        result = await self._repo.update(entity)

        if result is None:
            raise KeyNotFound(f"API key with ID '{entity.id_}' not found")

        return result

    async def delete_by_id(self, id_: str) -> bool:
        result = await self._repo.delete_by_id(id_)

        if not result:
            raise KeyNotFound(f"API key with ID '{id_}' not found")

        return result

    async def list(self, limit: int = 100, offset: int = 0) -> list[D]:
        return await self._repo.list(limit=limit, offset=offset)

    async def verify_key(self, api_key: Optional[str] = None) -> D:
        if api_key is None:
            raise KeyNotProvided("Api key must be provided (not given)")

        if api_key.strip() == "":
            raise KeyNotProvided("Api key must be provided (empty)")

        # Global key_id "ak" for "api key"
        if not api_key.startswith(self.global_prefix):
            raise InvalidKey("Api key is invalid (missing global key_id)")

        # Get the key_id part from the plain key
        try:
            parts = api_key.split(self.separator)

            if len(parts) != 3:
                raise InvalidKey("API key format is invalid (wrong number of segments).")

            global_prefix, prefix, secret = parts
        except Exception as e:
            raise InvalidKey(f"API key format is invalid: {str(e)}") from e

        # Search entity by a key_id (can't brute force hashes)
        entity = await self.get_by_key_id(prefix)

        # Check if the entity can be used for authentication
        # and refresh last_used_at if verified
        entity.ensure_can_authenticate()

        key_hash = entity.key_hash

        if not secret:
            raise InvalidKey("API key is invalid (empty secret)")

        if not self._hasher.verify(key_hash, secret):
            raise InvalidKey("API key is invalid (hash mismatch)")

        entity.touch()
        updated = await self._repo.update(entity)
        return updated
