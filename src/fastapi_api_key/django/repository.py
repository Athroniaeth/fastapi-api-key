"""Django ORM implementation of ``AbstractApiKeyRepository``.

Requires Django 4.1+ for native async ORM support (``aget``, ``asave``,
``adelete``, etc.).

The mapping between the Django model and the domain entity is intentionally
simple and symmetric – the same fields, same types.  Scope filtering is applied
in Python for portability across databases (SQLite, PostgreSQL, MySQL) because
JSON-path support varies.
"""

import sys
from typing import List, Optional

try:
    from django.db import models as _dj  # noqa: F401
except ModuleNotFoundError as e:  # pragma: no cover
    raise ImportError("Django integration requires 'django'. Install it with: uv add fastapi_api_key[django]") from e


from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.repositories.base import AbstractApiKeyRepository, ApiKeyFilter
from fastapi_api_key.django.models import ApiKeyModel


class DjangoApiKeyRepository(AbstractApiKeyRepository):
    """Django ORM implementation of the API key repository.

    All public methods are ``async`` and use Django's native async ORM API
    (``aget``, ``afilter``, ``asave``, ``adelete``, etc.) available from
    Django 4.1+.

    Notes:
        This repository is **not** tied to a specific database session; it uses
        Django's default database connection managed by the framework.
    """

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(model: ApiKeyModel) -> ApiKey:
        return ApiKey(
            id_=model.record_id,
            name=model.name,
            description=model.description,
            is_active=model.is_active,
            expires_at=model.expires_at,
            created_at=model.created_at,
            last_used_at=model.last_used_at,
            key_id=model.key_id,
            key_hash=model.key_hash,
            key_secret_first=model.key_secret_first,
            key_secret_last=model.key_secret_last,
            scopes=model.scopes or [],
        )

    @staticmethod
    def _to_model(entity: ApiKey, target: Optional[ApiKeyModel] = None) -> ApiKeyModel:
        if target is None:
            return ApiKeyModel(
                record_id=entity.id_,
                name=entity.name,
                description=entity.description,
                is_active=entity.is_active,
                expires_at=entity.expires_at,
                created_at=entity.created_at,
                last_used_at=entity.last_used_at,
                key_id=entity.key_id,
                key_hash=entity.key_hash,
                key_secret_first=entity.key_secret_first,
                key_secret_last=entity.key_secret_last,
                scopes=entity.scopes,
            )

        # In-place update of an existing model instance
        target.name = entity.name
        target.description = entity.description
        target.is_active = entity.is_active
        target.expires_at = entity.expires_at
        target.last_used_at = entity.last_used_at
        target.scopes = entity.scopes
        return target

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def get_by_id(self, id_: str) -> Optional[ApiKey]:
        try:
            model = await ApiKeyModel.objects.aget(record_id=id_)
            return self._to_domain(model)
        except ApiKeyModel.DoesNotExist:
            return None

    async def get_by_key_id(self, key_id: str) -> Optional[ApiKey]:
        try:
            model = await ApiKeyModel.objects.aget(key_id=key_id)
            return self._to_domain(model)
        except ApiKeyModel.DoesNotExist:
            return None

    async def create(self, entity: ApiKey) -> ApiKey:
        model = self._to_model(entity)
        await model.asave()
        return self._to_domain(model)

    async def update(self, entity: ApiKey) -> Optional[ApiKey]:
        try:
            existing = await ApiKeyModel.objects.aget(record_id=entity.id_)
        except ApiKeyModel.DoesNotExist:
            return None

        model = self._to_model(entity, target=existing)
        await model.asave()
        return self._to_domain(model)

    async def delete_by_id(self, id_: str) -> Optional[ApiKey]:
        try:
            model = await ApiKeyModel.objects.aget(record_id=id_)
        except ApiKeyModel.DoesNotExist:
            return None

        domain = self._to_domain(model)
        await model.adelete()
        return domain

    async def list(self, limit: int = 100, offset: int = 0) -> List[ApiKey]:
        qs = ApiKeyModel.objects.order_by("-created_at")[offset : offset + limit]
        return [self._to_domain(m) async for m in qs]

    # ------------------------------------------------------------------
    # Find / Count
    # ------------------------------------------------------------------

    def _build_queryset(self, filter_: ApiKeyFilter):
        """Build a filtered (but unpaginated) QuerySet from an ApiKeyFilter."""
        qs = ApiKeyModel.objects.all()

        if filter_.is_active is not None:
            qs = qs.filter(is_active=filter_.is_active)

        if filter_.expires_before is not None:
            qs = qs.filter(expires_at__lt=filter_.expires_before)

        if filter_.expires_after is not None:
            qs = qs.filter(expires_at__gt=filter_.expires_after)

        if filter_.created_before is not None:
            qs = qs.filter(created_at__lt=filter_.created_before)

        if filter_.created_after is not None:
            qs = qs.filter(created_at__gt=filter_.created_after)

        if filter_.last_used_before is not None:
            qs = qs.filter(last_used_at__lt=filter_.last_used_before)

        if filter_.last_used_after is not None:
            qs = qs.filter(last_used_at__gt=filter_.last_used_after)

        if filter_.never_used is not None:
            if filter_.never_used:
                qs = qs.filter(last_used_at__isnull=True)
            else:
                qs = qs.filter(last_used_at__isnull=False)

        if filter_.name_contains:
            qs = qs.filter(name__icontains=filter_.name_contains)

        if filter_.name_exact:
            qs = qs.filter(name=filter_.name_exact)

        # Ordering
        order_field = filter_.order_by.value  # e.g. "created_at"
        # Map id_ → the DB column name "id_"
        if order_field == "id_":
            order_field = "id_"
        order_expr = f"-{order_field}" if filter_.order_desc else order_field
        qs = qs.order_by(order_expr)

        return qs

    async def find(self, filter_: ApiKeyFilter) -> List[ApiKey]:
        """Search entities by filtering criteria.

        Notes:
            Scope filters (``scopes_contain_all``, ``scopes_contain_any``) are
            applied in Python after fetching because JSON-path query syntax
            differs across databases.  Pagination is applied *before* scope
            filtering, so fewer than ``limit`` results may be returned when
            scope filters are active.
        """
        qs = self._build_queryset(filter_)
        qs = qs[filter_.offset : filter_.offset + filter_.limit]
        entities = [self._to_domain(m) async for m in qs]

        if filter_.scopes_contain_all:
            entities = [e for e in entities if all(s in e.scopes for s in filter_.scopes_contain_all)]

        if filter_.scopes_contain_any:
            entities = [e for e in entities if any(s in e.scopes for s in filter_.scopes_contain_any)]

        return entities

    async def count(self, filter_: Optional[ApiKeyFilter] = None) -> int:
        if filter_ is None:
            return await ApiKeyModel.objects.acount()

        # Scope filters require a Python-level count (same caveat as find())
        if filter_.scopes_contain_all or filter_.scopes_contain_any:
            unlimited = ApiKeyFilter(
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
            return len(await self.find(unlimited))

        qs = self._build_queryset(filter_)
        return await qs.acount()
