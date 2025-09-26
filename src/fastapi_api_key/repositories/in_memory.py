from typing import Optional, List

from fastapi_api_key.repositories.base import ApiKeyRepository, D


class InMemoryApiKeyRepository(ApiKeyRepository[D]):
    """In-memory implementation of the ApiKeyRepository.

    Notes:
        This implementation is not thread-safe, don't use
        in production. This implementation don't have
        persistence and will lose all data when the
        application stops.
    """

    def __init__(self) -> None:
        self._store: dict[str, D] = {}

    async def get_by_id(self, id_: str) -> Optional[D]:
        return self._store.get(id_)

    async def get_by_prefix(self, prefix: str) -> Optional[D]:
        for v in self._store.values():
            if v.key_prefix == prefix:
                return v

        return None

    async def create(self, entity: D) -> D:
        self._store[entity.id_] = entity
        return entity

    async def update(self, entity: D) -> Optional[D]:
        if entity.id_ not in self._store:
            return None

        self._store[entity.id_] = entity
        return entity

    async def delete(self, id_: str) -> bool:
        """Return True if deleted, None if not found (aligns with abstract docstring)."""
        if id_ not in self._store:
            return False

        del self._store[id_]
        return True

    async def list(self, limit: int = 100, offset: int = 0) -> List[D]:
        items = list(
            sorted(
                self._store.values(),
                key=lambda x: x.created_at,
                reverse=True,
            )
        )
        return items[offset : offset + limit]
