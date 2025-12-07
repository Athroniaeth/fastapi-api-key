from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, List

from fastapi_api_key.domain.entities import ApiKey


class SortableColumn(str, Enum):
    """Valid columns for sorting API keys."""

    ID = "id_"
    NAME = "name"
    CREATED_AT = "created_at"
    EXPIRES_AT = "expires_at"
    LAST_USED_AT = "last_used_at"
    IS_ACTIVE = "is_active"
    KEY_ID = "key_id"


@dataclass
class ApiKeyFilter:
    """Filtering criteria for searching API keys.

    All criteria are optional. Only non-None criteria are applied (AND logic).

    Example:
        ```python
        # Find active keys with "admin" scope
        filter = ApiKeyFilter(
            is_active=True,
            scopes_contain_all=["admin"],
        )
        keys = await repo.find(filter)
        ```
    """

    # Boolean filters
    is_active: Optional[bool] = None

    # Date filters
    expires_before: Optional[datetime] = None
    expires_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    created_after: Optional[datetime] = None
    last_used_before: Optional[datetime] = None
    last_used_after: Optional[datetime] = None
    never_used: Optional[bool] = None  # True = last_used_at IS NULL

    # Scope filters
    scopes_contain_all: Optional[List[str]] = None  # AND: must have all these scopes
    scopes_contain_any: Optional[List[str]] = None  # OR: must have at least one scope

    # Text filters
    name_contains: Optional[str] = None  # LIKE %name% (case-insensitive)
    name_exact: Optional[str] = None  # = name (exact match)

    # Pagination
    limit: int = 100
    offset: int = 0

    # Sorting
    order_by: SortableColumn = SortableColumn.CREATED_AT
    order_desc: bool = True  # True = DESC, False = ASC


class AbstractApiKeyRepository(ABC):
    """Repository contract for API key persistence."""

    @abstractmethod
    async def get_by_id(self, id_: str) -> Optional[ApiKey]:
        """Get the entity by its ID, or None if not found."""
        ...

    @abstractmethod
    async def get_by_key_id(self, key_id: str) -> Optional[ApiKey]:
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
    async def create(self, entity: ApiKey) -> ApiKey:
        """Create a new entity and return the created version."""
        ...

    @abstractmethod
    async def update(self, entity: ApiKey) -> Optional[ApiKey]:
        """Update an existing entity and return the updated version, or None if it failed.

        Notes:
            Update the model identified by entity.id using values from entity.
            Return the updated entity, or None if the model doesn't exist.
        """
        ...

    @abstractmethod
    async def delete_by_id(self, id_: str) -> Optional[ApiKey]:
        """Delete the model by ID and return the deleted entity, or None if not found."""
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

        Example:
            ```python
            # Find active keys expiring in the next 7 days
            soon = datetime.now(timezone.utc) + timedelta(days=7)
            filter = ApiKeyFilter(
                is_active=True,
                expires_before=soon,
                expires_after=datetime.now(timezone.utc),
            )
            expiring_keys = await repo.find(filter)
            ```
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
