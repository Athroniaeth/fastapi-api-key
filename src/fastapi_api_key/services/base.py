import asyncio
import os
import warnings
from dataclasses import dataclass
from datetime import datetime
from random import SystemRandom
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.domain.errors import KeyNotProvided, KeyNotFound, InvalidKey, ConfigurationError
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


class AbstractApiKeyService(ABC):
    """Abstract service contract for API key management.

    Args:
        repo: Repository for persisting API key entities.
        hasher: Hasher for hashing secrets. Defaults to Argon2ApiKeyHasher.
        separator: Separator in API key format. Defaults to "-".
        global_prefix: Prefix for API keys. Defaults to "ak".
        rrd: Deprecated random response delay. Ignored if provided.
        min_delay: Minimum delay (seconds) applied to all verify responses.
        max_delay: Maximum delay (seconds) applied to all verify responses.

    Notes:
        The global key_id is pure cosmetic, it is not used for anything else.
        It is useful to quickly identify the string as an API key, and not
        another kind of token (like JWT, OAuth token, etc).
    """

    def __init__(
        self,
        repo: AbstractApiKeyRepository,
        hasher: ApiKeyHasher,
        separator: str = DEFAULT_SEPARATOR,
        global_prefix: str = DEFAULT_GLOBAL_PREFIX,
        rrd: Optional[float] = None,
        min_delay: float = 0.1,
        max_delay: float = 0.3,
    ) -> None:
        # Warning developer that separator is automatically added to the global key_id
        if separator in global_prefix:
            raise ValueError("Separator must not be in the global key_id")

        if rrd is not None:
            warnings.warn(
                "rrd is deprecated and ignored. Use min_delay/max_delay instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        if min_delay < 0 or max_delay < 0:
            raise ValueError("min_delay and max_delay must be non-negative")

        if max_delay < min_delay:
            raise ValueError("max_delay must be greater than or equal to min_delay")

        self._repo = repo
        self._hasher = hasher

        self.rrd = rrd
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.separator = separator
        self.global_prefix = global_prefix
        self._system_random = SystemRandom()

    @abstractmethod
    async def get_by_id(self, id_: str) -> ApiKey:
        """Get the entity by its ID, or raise if not found.

        Args:
            id_: The unique identifier of the API key.

        Raises:
            KeyNotProvided: If no ID is provided (empty).
            KeyNotFound: If no API key with the given ID exists.
        """
        ...

    @abstractmethod
    async def get_by_key_id(self, key_id: str) -> ApiKey:
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
    ) -> Tuple[ApiKey, str]:
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
    async def update(self, entity: ApiKey) -> ApiKey:
        """Update an existing entity and return the updated version, or None if it failed.

        Notes:
            Update the model identified by entity.id using values from entity.
            Return the updated entity, or None if the model doesn't exist.
        """
        ...

    @abstractmethod
    async def delete_by_id(self, id_: str) -> ApiKey:
        """Delete the entity by ID and return the deleted entity.

        Args:
            id_: The unique identifier of the API key to delete.

        Returns:
            The deleted entity.

        Raises:
            KeyNotFound: If no API key with the given ID exists.
        """
        ...

    @abstractmethod
    async def list(self, limit: int = 100, offset: int = 0) -> List[ApiKey]:
        """List entities with pagination support."""
        ...

    @abstractmethod
    async def find(self, filter_: ApiKeyFilter) -> List[ApiKey]:
        """Search entities by filtering criteria.

        Args:
            filter_: Filtering criteria and pagination options.

        Returns:
            List of entities matching the criteria.
        """
        ...

    @abstractmethod
    async def count(self, filter_: Optional[ApiKeyFilter] = None) -> int:
        """Count entities matching the criteria.

        Args:
            filter_: Filtering criteria (pagination is ignored). None = count all.

        Returns:
            Number of matching entities.
        """
        ...

    async def verify_key(self, api_key: str, required_scopes: Optional[List[str]] = None) -> ApiKey:
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
            A randomized delay is always applied to reduce timing signals.
        """
        try:
            result = await self._verify_key(api_key, required_scopes)
        except Exception as exc:
            await self._apply_delay()
            raise exc

        await self._apply_delay()
        return result

    async def _apply_delay(self) -> None:
        """Apply a randomized delay to reduce timing signals."""
        wait = self._system_random.uniform(self.min_delay, self.max_delay)
        await asyncio.sleep(wait)

    @abstractmethod
    async def _verify_key(self, api_key: str, required_scopes: Optional[List[str]] = None) -> ApiKey:
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
            A randomized delay is always applied to reduce timing signals.
        """
        ...

    async def load_dotenv(self, envvar_prefix: str = "API_KEY_") -> None:
        """Load environment variables into the service configuration.

        Args:
            envvar_prefix: The prefix to use for environment variables.
        """
        ...


class ApiKeyService(AbstractApiKeyService):
    """Concrete implementation of the API key service.

    This service handles key creation, verification, and lifecycle management.

    Example:
        Basic usage::

            repo = InMemoryApiKeyRepository()
            service = ApiKeyService(repo=repo)
            entity, key = await service.create(name="my-key")
    """

    def __init__(
        self,
        repo: AbstractApiKeyRepository,
        hasher: ApiKeyHasher,
        separator: str = DEFAULT_SEPARATOR,
        global_prefix: str = DEFAULT_GLOBAL_PREFIX,
        rrd: Optional[float] = None,
        min_delay: float = 0.1,
        max_delay: float = 0.3,
    ) -> None:
        super().__init__(
            repo=repo,
            hasher=hasher,
            separator=separator,
            global_prefix=global_prefix,
            rrd=rrd,
            min_delay=min_delay,
            max_delay=max_delay,
        )

    async def load_dotenv(self, envvar_prefix: str = "API_KEY_"):
        list_keys = [key for key in os.environ.keys() if key.startswith(envvar_prefix)]
        list_api_key = [os.environ[key] for key in list_keys]

        if not list_api_key:
            raise ConfigurationError(f"No environment variables found with prefix '{envvar_prefix}'")

        for key, api_key in zip(list_keys, list_api_key):
            parsed = self._get_parts(api_key)

            await self.create(
                name=key,
                key_id=parsed.key_id,
                key_secret=parsed.key_secret,
            )

    async def get_by_id(self, id_: str) -> ApiKey:
        entity = await self._repo.get_by_id(id_)

        if entity is None:
            raise KeyNotFound(f"API key with ID '{id_}' not found")

        return entity

    async def get_by_key_id(self, key_id: str) -> ApiKey:
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
    ) -> Tuple[ApiKey, str]:
        """Create and persist a new API key.

        Args:
            name: Optional human-friendly name for the key.
            description: Optional description of the key's purpose.
            is_active: Whether the key is active (default True).
            expires_at: Optional expiration datetime.
            scopes: Optional list of scopes/permissions.
            key_id: Optional key identifier to use. If None, a new random one will be generated.
            key_secret: Optional raw key secret to use. If None, a new random one will be generated.

        Returns:
            A tuple of the created entity and the full plain key string.

        Raises:
            ValueError: If expires_at is in the past.
        """
        if expires_at and expires_at < datetime_factory():
            raise ValueError("Expiration date must be in the future")

        scopes = scopes or []
        key_id = key_id or key_id_factory()
        key_secret = key_secret or key_secret_factory()
        key_hash = self._hasher.hash(key_secret=key_secret)

        entity = ApiKey(
            key_id=key_id,
            key_hash=key_hash,
            key_secret=key_secret,
            name=name,
            description=description,
            is_active=is_active,
            expires_at=expires_at,
            scopes=scopes,
        )

        full_key_secret = entity.get_api_key(
            global_prefix=self.global_prefix,
            key_id=key_id,
            key_secret=key_secret,
            separator=self.separator,
        )

        return await self._repo.create(entity), full_key_secret

    async def update(self, entity: ApiKey) -> ApiKey:
        result = await self._repo.update(entity)

        if result is None:
            raise KeyNotFound(f"API key with ID '{entity.id_}' not found")

        return result

    async def delete_by_id(self, id_: str) -> ApiKey:
        result = await self._repo.delete_by_id(id_)

        if result is None:
            raise KeyNotFound(f"API key with ID '{id_}' not found")

        return result

    async def list(self, limit: int = 100, offset: int = 0) -> list[ApiKey]:
        return await self._repo.list(limit=limit, offset=offset)

    async def find(self, filter_: ApiKeyFilter) -> List[ApiKey]:
        return await self._repo.find(filter_)

    async def count(self, filter_: Optional[ApiKeyFilter] = None) -> int:
        return await self._repo.count(filter_)

    async def _verify_key(self, api_key: Optional[str] = None, required_scopes: Optional[List[str]] = None) -> ApiKey:
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
        if api_key is None or api_key.strip() == "":
            raise KeyNotProvided("Api key must be provided (not given)")

        return self._get_parts(api_key)

    async def _verify_entity(self, entity: ApiKey, key_secret: str, required_scopes: List[str]) -> ApiKey:
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
        # Todo: IDK if this line ise usefully
        # assert entity.key_hash is not None, "key_hash must be set for existing API keys"  # nosec B101

        entity.ensure_valid(scopes=required_scopes)

        if not self._hasher.verify(entity.key_hash, key_secret):
            raise InvalidKey("API key is invalid (hash mismatch)")

        return await self.touch(entity)

    def _get_parts(self, api_key: str) -> ParsedApiKey:
        """Extract the parts of the API key string.

        Args:
            api_key: The full API key string.

        Returns:
            A tuple of (global_prefix, key_id, key_secret).

        Raises:
            InvalidKey: If the API key format is invalid.
        """
        parts = api_key.split(self.separator)

        if len(parts) != 3:
            raise InvalidKey("API key format is invalid (wrong number of segments).")

        if not all(p.strip() for p in parts):
            raise InvalidKey("API key format is invalid (empty segment).")

        parsed_api_key = ParsedApiKey(
            global_prefix=parts[0],
            key_id=parts[1],
            key_secret=parts[2],
            raw=api_key,
        )

        if parsed_api_key.global_prefix != self.global_prefix:
            raise InvalidKey("Api key is invalid (wrong global prefix)")

        return parsed_api_key

    async def touch(self, entity: ApiKey) -> ApiKey:
        """Update last_used_at to now and persist the change."""
        entity.touch()
        await self._repo.update(entity)
        return entity
