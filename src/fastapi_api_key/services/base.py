import asyncio
import os
from dataclasses import dataclass
from datetime import datetime
from random import SystemRandom
from abc import ABC, abstractmethod
from typing import Generic, Optional, Tuple, List, Any, Callable

from fastapi_api_key.domain.entities import default_api_key_factory
from fastapi_api_key.domain.base import D
from fastapi_api_key.domain.errors import KeyNotProvided, KeyNotFound, InvalidKey
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.hasher.base import ApiKeyHasher
from fastapi_api_key.repositories.base import AbstractApiKeyRepository, ApiKeyFilter
from fastapi_api_key.utils import datetime_factory, key_secret_factory, key_id_factory

DEFAULT_SEPARATOR = "-"
"""
Default separator between key_type, key_id, key_secret in the API key string.
Must be not in `token_urlsafe` alphabet. (like '.', ':', '~", '|')
"""
DEFAULT_GLOBAL_PREFIX = "ak"


@dataclass
class ParsedApiKey:
    """Result of parsing an API key string.

    Attributes:
        global_prefix: The prefix identifying the key type (e.g., "ak").
        key_id: The public identifier part of the API key.
        key_secret: The secret part of the API key.
        raw: The original full API key string.
    """

    global_prefix: str
    key_id: str
    key_secret: str
    raw: str


class AbstractApiKeyService(ABC, Generic[D]):
    """Generic service contract for a domain aggregate.

    Args:
        repo: Repository for persisting API key entities.
        hasher: Hasher for hashing secrets. Defaults to Argon2ApiKeyHasher.
        entity_factory: Factory for creating entities. Defaults to default_api_key_factory.
        separator: Separator in API key format. Defaults to "-".
        global_prefix: Prefix for API keys. Defaults to "ak".
        rrd: Random response delay for timing attack mitigation. Defaults to 1/3.

    Notes:
        The global key_id is pure cosmetic, it is not used for anything else.
        It is useful to quickly identify the string as an API key, and not
        another kind of token (like JWT, OAuth token, etc).
    """

    def __init__(
        self,
        repo: AbstractApiKeyRepository[D],
        hasher: Optional[ApiKeyHasher] = None,
        entity_factory: Optional[Callable[..., D]] = None,
        separator: str = DEFAULT_SEPARATOR,
        global_prefix: str = "ak",
        rrd: float = 1 / 3,
    ) -> None:
        # Warning developer that separator is automatically added to the global key_id
        if separator in global_prefix:
            raise ValueError("Separator must not be in the global key_id")

        self._repo = repo
        self._hasher = hasher or Argon2ApiKeyHasher()
        self._entity_factory: Callable[..., D] = entity_factory or default_api_key_factory

        self.separator = separator
        self.global_prefix = global_prefix
        self.rrd = rrd
        self._system_random = SystemRandom()

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
    async def create(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: bool = True,
        expires_at: Optional[datetime] = None,
        scopes: Optional[List[str]] = None,
        key_id: Optional[str] = None,
        key_secret: Optional[str] = None,
    ) -> Tuple[D, str]:
        """Create and persist a new API key.

        Args:
            name: Optional human-friendly name for the key.
            description: Optional description of the key's purpose.
            is_active: Whether the key is active (default True).
            expires_at: Optional expiration datetime.
            scopes: Optional list of scopes/permissions.
            key_id: Optional key identifier to use. If None, a new random one will be generated.
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
    async def find(self, filter: ApiKeyFilter) -> List[D]:
        """Search entities by filtering criteria.

        Args:
            filter: Filtering criteria and pagination options.

        Returns:
            List of entities matching the criteria.
        """
        ...

    @abstractmethod
    async def count(self, filter: Optional[ApiKeyFilter] = None) -> int:
        """Count entities matching the criteria.

        Args:
            filter: Filtering criteria (pagination is ignored). None = count all.

        Returns:
            Number of matching entities.
        """
        ...

    async def verify_key(self, api_key: str, required_scopes: Optional[List[str]] = None) -> D:
        """Verify the provided plain key and return the corresponding entity if valid, else raise.

        Args:
            api_key: The raw API key string to verify.
            required_scopes: Optional list of required scopes to check against the key's scopes.

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
        try:
            return await self._verify_key(api_key, required_scopes)
        except Exception as e:
            # Add a small jitter to make timing-based probing harder to profile.
            wait = self._system_random.uniform(self.rrd, self.rrd * 2)
            await asyncio.sleep(wait)
            raise e

    @abstractmethod
    async def _verify_key(self, api_key: str, required_scopes: Optional[List[str]] = None) -> D:
        """Verify the provided plain key and return the corresponding entity if valid, else raise.

        Args:
            api_key: The raw API key string to verify.
            required_scopes: Optional list of required scopes to check against the key's scopes.

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
    """Concrete implementation of the API key service.

    This service handles key creation, verification, and lifecycle management.
    It uses a factory pattern for entity creation, allowing customization.

    Example:
        Basic usage::

            repo = InMemoryApiKeyRepository()
            service = ApiKeyService(repo=repo)
            entity, key = await service.create(name="my-key")

        With custom factory::

            def tenant_factory(key_id, key_hash, key_secret, tenant_id="default", **kwargs):
                return TenantApiKey(
                    key_id=key_id,
                    key_hash=key_hash,
                    _key_secret=key_secret,
                    tenant_id=tenant_id,
                    **kwargs,
                )

            service = ApiKeyService(repo=repo, entity_factory=tenant_factory)
            entity, key = await service.create(name="my-key", tenant_id="tenant-123")
    """

    def __init__(
        self,
        repo: AbstractApiKeyRepository[D],
        hasher: Optional[ApiKeyHasher] = None,
        entity_factory: Optional[Callable[..., D]] = None,
        separator: str = DEFAULT_SEPARATOR,
        global_prefix: str = "ak",
        rrd: float = 1 / 3,
    ) -> None:
        super().__init__(
            repo=repo,
            hasher=hasher,
            entity_factory=entity_factory,
            separator=separator,
            global_prefix=global_prefix,
            rrd=rrd,
        )

    async def load_dotenv(self, envvar_prefix: str = "API_KEY_"):
        """Load environment variables into the service configuration.

        Args:
            envvar_prefix: The prefix to use for environment variables.
        """
        list_keys = [key for key in os.environ.keys() if key.startswith(envvar_prefix)]
        list_api_key = [os.environ[key] for key in list_keys]

        if not list_api_key:
            raise Exception(f"Don't have envvar with prefix '{envvar_prefix}'")

        for key, api_key in zip(list_keys, list_api_key):
            global_prefix, key_id, key_secret = self._get_parts(
                api_key,
            )

            await self.create(
                name=key,
                key_secret=key_secret,
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

    async def create(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: bool = True,
        expires_at: Optional[datetime] = None,
        scopes: Optional[List[str]] = None,
        key_id: Optional[str] = None,
        key_secret: Optional[str] = None,
        **kwargs: Any,
    ) -> Tuple[D, str]:
        """Create and persist a new API key.

        Args:
            name: Optional human-friendly name for the key.
            description: Optional description of the key's purpose.
            is_active: Whether the key is active (default True).
            expires_at: Optional expiration datetime.
            scopes: Optional list of scopes/permissions.
            key_id: Optional key identifier to use. If None, a new random one will be generated.
            key_secret: Optional raw key secret to use. If None, a new random one will be generated.
            **kwargs: Additional arguments passed to the entity factory.

        Returns:
            A tuple of the created entity and the full plain key string.

        Raises:
            ValueError: If expires_at is in the past.
        """
        if expires_at and expires_at < datetime_factory():
            raise ValueError("Expiration date must be in the future")

        key_id = key_id or key_id_factory()
        key_secret = key_secret or key_secret_factory()

        key_hash = self._hasher.hash(key_secret)
        entity = self._entity_factory(
            key_id=key_id,
            key_hash=key_hash,
            key_secret=key_secret,
            name=name,
            description=description,
            is_active=is_active,
            expires_at=expires_at,
            scopes=scopes,
            **kwargs,
        )

        full_key_secret = entity.full_key_secret(
            global_prefix=self.global_prefix,
            key_id=key_id,
            key_secret=key_secret,
            separator=self.separator,
        )

        return await self._repo.create(entity), full_key_secret

    async def update(self, entity: D) -> D:
        result = await self._repo.update(entity)

        if result is None:
            raise KeyNotFound(f"API key with ID '{entity.id_}' not found")

        return result

    async def delete_by_id(self, id_: str) -> D:
        result = await self._repo.delete_by_id(id_)

        if result is None:
            raise KeyNotFound(f"API key with ID '{id_}' not found")

        return result

    async def list(self, limit: int = 100, offset: int = 0) -> list[D]:
        return await self._repo.list(limit=limit, offset=offset)

    async def find(self, filter: ApiKeyFilter) -> List[D]:
        return await self._repo.find(filter)

    async def count(self, filter: Optional[ApiKeyFilter] = None) -> int:
        return await self._repo.count(filter)

    async def _verify_key(self, api_key: Optional[str] = None, required_scopes: Optional[List[str]] = None) -> D:
        required_scopes = required_scopes or []

        parsed = self._parse_and_validate_key(api_key)
        entity = await self.get_by_key_id(parsed.key_id)

        return await self._verify_entity(entity, parsed.key_secret, required_scopes)

    def _parse_and_validate_key(self, api_key: Optional[str]) -> ParsedApiKey:
        """Parse and validate the API key format.

        Args:
            api_key: The raw API key string to parse.

        Returns:
            ParsedApiKey containing the parsed parts.

        Raises:
            KeyNotProvided: If the key is None or empty.
            InvalidKey: If the format or prefix is invalid.
        """
        if api_key is None:
            raise KeyNotProvided("Api key must be provided (not given)")

        if api_key.strip() == "":
            raise KeyNotProvided("Api key must be provided (empty)")

        global_prefix, key_id, key_secret = self._get_parts(api_key)

        if global_prefix != self.global_prefix:
            raise InvalidKey("Api key is invalid (wrong global prefix)")

        return ParsedApiKey(
            global_prefix=global_prefix,
            key_id=key_id,
            key_secret=key_secret,
            raw=api_key,
        )

    async def _verify_entity(self, entity: D, key_secret: str, required_scopes: List[str]) -> D:
        """Verify that an entity can authenticate with the provided secret.

        Args:
            entity: The API key entity retrieved from the repository.
            key_secret: The secret to verify against the stored hash.
            required_scopes: The required scopes to check.

        Returns:
            The entity with updated last_used_at.

        Raises:
            KeyInactive: If the key is disabled.
            KeyExpired: If the key is expired.
            InvalidKey: If the hash does not match.
            InvalidScopes: If scopes are insufficient.
        """
        assert entity.key_hash is not None, "key_hash must be set for existing API keys"  # nosec B101

        entity.ensure_can_authenticate()

        if not key_secret:
            raise InvalidKey("API key is invalid (empty secret)")

        if not self._hasher.verify(entity.key_hash, key_secret):
            raise InvalidKey("API key is invalid (hash mismatch)")

        entity.ensure_valid_scopes(required_scopes)

        return await self.touch(entity)

    def _get_parts(self, api_key: str) -> Tuple[str, str, str]:
        """Extract the parts of the API key string.

        Args:
            api_key: The full API key string.

        Returns:
            A tuple of (global_prefix, key_id, key_secret).

        Raises:
            InvalidKey: If the API key format is invalid.
        """
        try:
            parts = api_key.split(self.separator)
        except Exception as e:
            raise InvalidKey(f"API key format is invalid: {e}") from e

        if len(parts) != 3:
            raise InvalidKey("API key format is invalid (wrong number of segments).")

        return parts[0], parts[1], parts[2]

    async def touch(self, entity: D) -> D:
        """Update last_used_at to now and persist the change."""
        entity.touch()
        await self._repo.update(entity)
        return entity
