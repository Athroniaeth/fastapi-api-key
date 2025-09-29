from abc import ABC, abstractmethod
from typing import Generic, Optional, List, Type, Any

from fastapi_api_key.domain.entities import D


class AbstractApiKeyRepository(ABC, Generic[D]):
    """Generic repository contract for a domain aggregate."""

    @staticmethod
    def to_model(
        entity: D,
        model_cls: Type[Any],
        target: Optional[Any] = None,
    ) -> Any:
        """Convert a domain entity to a SQLAlchemy model instance.

        Notes:
            If `target` is provided, it will be updated with the entity's data.
            Otherwise, a new model instance will be created.
        """
        if target is None:
            return model_cls(
                id_=entity.id_,
                name=entity.name,
                description=entity.description,
                is_active=entity.is_active,
                expires_at=entity.expires_at,
                created_at=entity.created_at,
                last_used_at=entity.last_used_at,
                key_id=entity.key_id,
                key_hash=entity.key_hash,
            )

        # Update existing model
        target.name = entity.name
        target.description = entity.description
        target.is_active = entity.is_active
        target.expires_at = entity.expires_at
        target.last_used_at = entity.last_used_at
        target.key_id = entity.key_id
        target.key_hash = entity.key_hash

        return target

    @staticmethod
    def to_domain(model: Optional[Any], model_cls: Type[D]) -> Optional[D]:
        """Convert a SQLAlchemy model instance to a domain entity."""
        if model is None:
            return None

        return model_cls(
            id_=model.id_,
            name=model.name,
            description=model.description,
            is_active=model.is_active,
            expires_at=model.expires_at,
            created_at=model.created_at,
            last_used_at=model.last_used_at,
            key_id=model.key_id,
            key_hash=model.key_hash,
        )

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
