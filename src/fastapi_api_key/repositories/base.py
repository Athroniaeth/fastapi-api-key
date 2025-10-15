from abc import ABC, abstractmethod
from typing import Generic, Optional, List

from fastapi_api_key.domain.base import D


class AbstractApiKeyRepository(ABC, Generic[D]):
    """Generic repository contract for a domain aggregate."""

    @abstractmethod
    async def get_by_id(self, id_: str) -> Optional[D]:
        """Get the entity by its ID, or None if not found."""
        ...

    @abstractmethod
    async def get_by_key_id(self, key_id: str) -> Optional[D]:
        """Get the entity by its key_id, or None if not found.

        Notes:
            Prefix is usefully because the full key is not stored in
            the DB for security reasons. The hash of the key is stored,
            but with salt and hashing algorithm, we cannot retrieve the
            original key from the hash without brute-forcing.

            So we add a key_id column to quickly find the model by key_id, then verify
            the hash. We use UUID for avoiding collisions.
        """
        ...

    @abstractmethod
    async def create(self, entity: D) -> D:
        """Create a new entity and return the created version."""
        ...

    @abstractmethod
    async def update(self, entity: D) -> Optional[D]:
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
