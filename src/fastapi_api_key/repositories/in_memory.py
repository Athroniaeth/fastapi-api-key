import sys
from datetime import datetime
from typing import Optional, List

from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.repositories.base import AbstractApiKeyRepository, ApiKeyFilter


class InMemoryApiKeyRepository(AbstractApiKeyRepository):
    """In-memory implementation of the AbstractApiKeyRepository.

    Notes:
        This implementation is not thread-safe, don't use
        in production. This implementation don't have
        persistence and will lose all data when the
        application stops.
    """

    def __init__(self) -> None:
        self._store: dict[str, ApiKey] = {}

    async def get_by_id(self, id_: str) -> Optional[ApiKey]:
        return self._store.get(id_)

    async def get_by_key_id(self, key_id: str) -> Optional[ApiKey]:
        for v in self._store.values():
            if v.key_id == key_id:
                return v

        return None

    async def create(self, entity: ApiKey) -> ApiKey:
        # Ensure that any existing entity with the same key_id is overwritten
        if entity.id_ in self._store:
            raise ValueError(f"Entity with id {entity.id_} already exists.")

        if any(v.key_id == entity.key_id for v in self._store.values()):
            raise ValueError(f"Entity with key_id {entity.key_id} already exists.")

        self._store[entity.id_] = entity
        return entity

    async def update(self, entity: ApiKey) -> Optional[ApiKey]:
        if entity.id_ not in self._store:
            return None

        self._store[entity.id_] = entity
        return entity

    async def delete_by_id(self, id_: str) -> Optional[ApiKey]:
        if id_ not in self._store:
            return None

        entity = self._store[id_]
        del self._store[id_]
        return entity

    async def list(self, limit: int = 100, offset: int = 0) -> List[ApiKey]:
        items = list(
            sorted(
                self._store.values(),
                key=lambda x: x.created_at,
                reverse=True,
            )
        )
        return items[offset : offset + limit]

    async def find(self, filter_: ApiKeyFilter) -> List[ApiKey]:
        results = list(self._store.values())

        # Boolean filters
        if filter_.is_active is not None:
            results = [e for e in results if e.is_active == filter_.is_active]

        # Date filters
        if filter_.expires_before is not None:
            results = [e for e in results if e.expires_at and e.expires_at < filter_.expires_before]

        if filter_.expires_after is not None:
            results = [e for e in results if e.expires_at and e.expires_at > filter_.expires_after]

        if filter_.created_before is not None:
            results = [e for e in results if e.created_at < filter_.created_before]

        if filter_.created_after is not None:
            results = [e for e in results if e.created_at > filter_.created_after]

        if filter_.last_used_before is not None:
            results = [e for e in results if e.last_used_at and e.last_used_at < filter_.last_used_before]

        if filter_.last_used_after is not None:
            results = [e for e in results if e.last_used_at and e.last_used_at > filter_.last_used_after]

        if filter_.never_used is not None:
            if filter_.never_used:
                results = [e for e in results if e.last_used_at is None]
            else:
                results = [e for e in results if e.last_used_at is not None]

        # Scope filters
        if filter_.scopes_contain_all:
            results = [e for e in results if all(s in e.scopes for s in filter_.scopes_contain_all)]

        if filter_.scopes_contain_any:
            results = [e for e in results if any(s in e.scopes for s in filter_.scopes_contain_any)]

        # Text filters
        if filter_.name_contains:
            results = [e for e in results if e.name and filter_.name_contains.lower() in e.name.lower()]

        if filter_.name_exact:
            results = [e for e in results if e.name == filter_.name_exact]

        # Sorting
        reverse = filter_.order_desc
        results.sort(key=lambda e: getattr(e, filter_.order_by) or datetime.min, reverse=reverse)

        # Pagination
        return results[filter_.offset : filter_.offset + filter_.limit]

    async def count(self, filter_: Optional[ApiKeyFilter] = None) -> int:
        if filter_ is None:
            return len(self._store)

        # Reuse find() logic without pagination
        unlimited_filter = ApiKeyFilter(
            is_active=filter_.is_active,
            expires_before=filter_.expires_before,
            expires_after=filter_.expires_after,
            created_before=filter_.created_before,
            created_after=filter_.created_after,
            last_used_before=filter_.last_used_before,
            last_used_after=filter_.last_used_after,
            never_used=filter_.never_used,
            scopes_contain_all=filter_.scopes_contain_all,
            scopes_contain_any=filter_.scopes_contain_any,
            name_contains=filter_.name_contains,
            name_exact=filter_.name_exact,
            limit=sys.maxsize,
            offset=0,
        )
        return len(await self.find(unlimited_filter))
