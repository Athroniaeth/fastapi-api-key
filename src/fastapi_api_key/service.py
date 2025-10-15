from abc import ABC, abstractmethod
from typing import Generic, Optional, Type, Tuple, List

from fastapi_api_key.domain.entities import D, ApiKey
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.hasher.base import ApiKeyHasher
from fastapi_api_key.domain.errors import KeyNotFound, KeyNotProvided, InvalidKey
from fastapi_api_key.repositories.base import AbstractApiKeyRepository
from fastapi_api_key.utils import datetime_factory, key_secret_factory

DEFAULT_SEPARATOR = "-"
"""
Default separator between key_type, key_id, key_secret in the API key string. 
Must be not in `token_urlsafe` alphabet. (like '.', ':', '~", '|')
"""


class AbstractApiKeyService(ABC, Generic[D]):
    """Generic service contract for a domain aggregate.

    Notes:
        The global key_id is pure cosmetic, it is not used for anything else.
        It is useful to quickly identify the string as an API key, and not
        another kind of token (like JWT, OAuth token, etc).
    """

    def __init__(
        self,
        repo: AbstractApiKeyRepository[D],
        hasher: Optional[ApiKeyHasher] = None,
        domain_cls: Optional[Type[D]] = None,
        separator: str = DEFAULT_SEPARATOR,
        global_prefix: str = "ak",
    ) -> None:
        # Warning developer that separator is automatically added to the global key_id
        if separator in global_prefix:
            raise ValueError("Separator must not be in the global key_id")

        self._repo = repo
        self._hasher = hasher or Argon2ApiKeyHasher()
        self.domain_cls = domain_cls or D
        self.separator = separator
        self.global_prefix = global_prefix

    @abstractmethod
    async def get_by_id(self, id_: str) -> D:
        """Get the entity by its ID, or raise if not found.

        Args:
            id_: The unique identifier of the API key.

        Raises:
            KeyNotProvided: If no ID is provided (empty).
            KeyNotFound: If no API key with the given ID exists.
        """
        ...

    @abstractmethod
    async def get_by_key_id(self, key_id: str) -> D:
        """Get the entity by its key_id, or raise if not found.

        Notes:
            Prefix is usefully because the full key is not stored in
            the DB for security reasons. The hash of the key is stored,
            but with salt and hashing algorithm, we cannot retrieve the
            original key from the hash without brute-forcing.

            So we add a key_id column to quickly find the model by key_id, then verify
            the hash. We use UUID for avoiding collisions.

        Args:
            key_id: The key_id part of the API key.

        Raises:
            KeyNotProvided: If no key_id is provided (empty).
            KeyNotFound: If no API key with the given key_id exists.
        """

    @abstractmethod
    async def create(self, entity: D, key_secret: Optional[str] = None) -> Tuple[D, str]:
        """Create and persist a new API key.

        Args:
            entity: The entity api to create.
            key_secret: Optional raw key secret to use. If None, a new random one will be generated.

        Notes:
            The api_key is the only time the raw key is available, it will be hashed
            before being stored. The api key should be securely stored by the caller,
            as it will not be retrievable later.

        Returns:
            A tuple of the created entity and the full plain key string to be given to the user.
        """
        ...

    @abstractmethod
    async def update(self, entity: D) -> D:
        """Update an existing entity and return the updated version, or None if it failed.

        Notes:
            Update the model identified by entity.id using values from entity.
            Return the updated entity, or None if the model doesn't exist.
        """
        ...

    @abstractmethod
    async def delete_by_id(self, id_: str) -> bool:
        """Delete the model by ID and return True if deleted, False if not found."""
        ...

    @abstractmethod
    async def list(self, limit: int = 100, offset: int = 0) -> List[D]:
        """List entities with pagination support."""
        ...

    @abstractmethod
    async def verify_key(self, api_key: str) -> D:
        """Verify the provided plain key and return the corresponding entity if valid, else raise.

        Args:
            api_key: The raw API key string to verify.

        Raises:
            KeyNotProvided: If no API key is provided (empty).
            KeyNotFound: If no API key with the given key_id exists.
            InvalidKey: If the API key is invalid (hash mismatch).
            KeyInactive: If the API key is inactive.
            KeyExpired: If the API key is expired.

        Returns:
            The corresponding entity if the key is valid.

        Notes:
            This method extracts the key_id from the provided plain key,
            retrieves the corresponding entity, and verifies the hash.
            If the entity is inactive or expired, an exception is raised.
            If the check between the provided plain key and the stored hash fails,
            an InvalidKey exception is raised. Else, the entity is returned.
        """
        ...


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
