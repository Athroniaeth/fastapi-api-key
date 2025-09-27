from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generic, Optional, Type, Tuple, List

from fastapi_api_key.domain.entities import ApiKeyHasher, D, Argon2ApiKeyHasher, ApiKey
from fastapi_api_key.repositories.base import ApiKeyRepository
from fastapi_api_key.utils import plain_key_factory, datetime_factory, prefix_factory

DEFAULT_SEPARATOR = "."
"""
Default separator between key_id and key in the API key string. 
Must be not in `token_urlsafe` alphabet. (like '.', ':', '~", '|')
"""


class ApiKeyError(Exception):
    """Base class for all API key related errors."""

    ...


class KeyNotFound(ApiKeyError):
    """Raised when no API key with the requested ID exists."""

    ...


class KeyNotProvided(ApiKeyError):
    """Raised when an API key is required but not provided."""

    ...


class KeyInactive(ApiKeyError):
    """Raised when an API key exists but is marked as inactive."""

    ...


class KeyExpired(ApiKeyError):
    """Raised when an API key exists but is expired."""

    ...


class InvalidKey(ApiKeyError):
    """Raised when an API key is invalid (key key_id matches but hash does not)."""

    ...


class AbstractApiKeyService(ABC, Generic[D]):
    """Generic service contract for a domain aggregate.

    Notes:
        The global key_id is pure cosmetic, it is not used for anything else.
        It is useful to quickly identify the string as an API key, and not
        another kind of token (like JWT, OAuth token, etc).
    """

    def __init__(
        self,
        repo: ApiKeyRepository[D],
        hasher: ApiKeyHasher,
        domain_cls: Optional[Type[D]] = None,
        separator: str = DEFAULT_SEPARATOR,
        global_prefix: str = "ak",
    ) -> None:
        # Warning developer that separator is automatically added to the global key_id
        if separator in global_prefix:
            raise ValueError("Separator must not be in the global key_id")

        self._repo = repo
        self._hasher = hasher
        self.domain_cls = domain_cls or D
        self.separator = separator
        self.global_prefix = global_prefix

    @abstractmethod
    async def get_by_id(self, id_: str) -> D:
        """Get the entity by its ID, or None if not found."""
        ...

    @abstractmethod
    async def create(self, entity: D) -> D:
        """Create a new entity and return the created version."""
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
    async def verify_key(self, plain_key: str) -> D:
        """Verify the provided plain key and return the corresponding entity if valid, else raise."""
        ...


class ApiKeyService(AbstractApiKeyService[D]):
    """Generic service contract for a domain aggregate."""

    def __init__(
        self,
        repo: ApiKeyRepository[D],
        hasher: Optional[ApiKeyHasher] = None,
        domain_cls: Optional[Type[D]] = None,
        separator: str = DEFAULT_SEPARATOR,
        global_prefix: str = "ak",
    ) -> None:
        hasher = hasher or Argon2ApiKeyHasher()
        domain_cls = domain_cls or ApiKey
        super().__init__(
            repo=repo,
            hasher=hasher,
            domain_cls=domain_cls,
            separator=separator,
            global_prefix=global_prefix,
        )

    async def get_by_id(self, id_: str) -> D:
        """Get the entity by its ID, or raise if not found.

        Args:
            id_: The unique identifier of the API key.

        Raises:
            KeyNotProvided: If no ID is provided (empty).
            KeyNotFound: If no API key with the given ID exists.
        """
        if (id_ is None) or (id_.strip() == ""):
            raise KeyNotProvided("No API key provided")

        entity = await self._repo.get_by_id(id_)

        if entity is None:
            raise KeyNotFound(f"API key with ID '{id_}' not found")

        return entity

    async def get_by_prefix(self, prefix: str) -> D:
        """Get the entity by its key_id, or raise if not found.

        Notes:
            Prefix is usefully because the full key is not stored in
            the DB for security reasons. The hash of the key is stored,
            but with salt and hashing algorithm, we cannot retrieve the
            original key from the hash without brute-forcing.

            So we add a key_id column to quickly find the model by key_id, then verify
            the hash. We use UUID for avoiding collisions.

        Args:
            prefix: The key_id part of the API key.

        Raises:
            KeyNotProvided: If no key_id is provided (empty).
            KeyNotFound: If no API key with the given key_id exists.
        """
        if not prefix.strip():
            raise KeyNotProvided("No API key key_id provided (key_id cannot be empty)")

        entity = await self._repo.get_by_key_id(prefix)

        if entity is None:
            raise KeyNotFound(f"API key with key_id '{prefix}' not found")

        return entity

    async def create(
        self,
        name: str,
        description: str = "",
        is_active: bool = True,
        expires_at: Optional[datetime] = None,
        key_id: Optional[str] = None,
        plain_key: Optional[str] = None,
    ) -> Tuple[D, str]:
        """Create and persist a new API key.

        Args:
            name: Desired unique name.
            description: Optional description.
            is_active: Whether the key should be active.
            expires_at: Optional expiration datetime.
            key_id: Optional key_id for the key, if not provided a new one will be generated.
            plain_key: Optional plain key, if not provided a new one will be generated.

        Notes:
            The plain_key is the only time the raw key is available, it will be hashed
            before being stored. The plain_key should be securely stored by the caller,
            as it will not be retrievable later.

        Returns:
            A tuple of the created entity and the full plain key string to be given to the user
        """
        if expires_at and expires_at < datetime_factory():
            raise ValueError("Expiration date must be in the future")

        key_id = key_id or prefix_factory()
        plain_key = plain_key or plain_key_factory()
        hashed_key = self._hasher.hash(plain_key)

        entity = self.domain_cls(
            name=name,
            description=description,
            is_active=is_active,
            expires_at=expires_at,
            key_id=key_id,
            key_hash=hashed_key,
        )

        full_plain_key = (
            f"{self.global_prefix}{self.separator}{key_id}{self.separator}{plain_key}"
        )
        return await self._repo.create(entity), full_plain_key

    async def update(self, entity: D) -> D:
        """Update an existing entity and return the updated version, or None if it failed.

        Notes:
            Update the model identified by entity.id using values from entity.
            Return the updated entity, or None if the model doesn't exist.
        """
        result = await self._repo.update(entity)

        if result is None:
            raise KeyNotFound(f"API key with ID '{entity.id_}' not found")

        return result

    async def delete_by_id(self, id_: str) -> bool:
        """Delete the model by ID and return True if deleted, False if not found."""
        result = await self._repo.delete_by_id(id_)

        if not result:
            raise KeyNotFound(f"API key with ID '{id_}' not found")

        return result

    async def list(self, limit: int = 100, offset: int = 0) -> list[D]:
        """List entities with pagination support."""
        return await self._repo.list(limit=limit, offset=offset)

    async def verify_key(self, plain_key: str) -> D:
        """Verify the provided plain key and return the corresponding entity if valid, else None.

        Args:
            plain_key: The raw API key string to verify.
        Returns:
            The corresponding entity if the key is valid, else None.
        Notes:
            This method extracts the key_id from the provided plain key,
            retrieves the corresponding entity, and verifies the hash.
            If the entity is inactive or expired, None is returned.
        """
        # Global key_id "ak" for "api key"
        if not plain_key.startswith(self.global_prefix):
            raise InvalidKey("API key is invalid (missing global key_id)")

        # Get the key_id part from the plain key
        try:
            global_prefix, prefix, secret = plain_key.split(self.separator)
        except ValueError:
            raise InvalidKey(
                "API key format is invalid (don't recognize full plain key)"
            )

        # Search entity by a key_id (can't brute force hashes)
        entity = await self.get_by_prefix(prefix)

        # Check if the entity can be used for authentication
        # and refresh last_used_at if verified
        entity.ensure_can_authenticate()

        if not self._hasher.verify(entity.key_hash, secret):
            raise InvalidKey("API key is invalid (hash mismatch)")

        return entity
