import sys
import typing

try:
    import sqlalchemy  # noqa: F401
except ModuleNotFoundError as e:
    raise ImportError(
        "SQLAlchemy backend requires 'sqlalchemy'. Install it with: uv add fastapi_api_key[sqlalchemy]"
    ) from e


from datetime import datetime
from typing import List, Optional, Sequence

from sqlalchemy import String, Text, Boolean, DateTime, JSON, func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase

from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.repositories.base import AbstractApiKeyRepository, ApiKeyFilter
from fastapi_api_key.utils import datetime_factory


class Base(DeclarativeBase): ...  # pragma: no cover


class ApiKeyModelMixin:
    """SQLAlchemy ORM model mixin for API keys.

    Notes:
        This is a mixin to allow easy extension of the model with additional fields.
    """

    __tablename__ = "api_keys"

    id_: Mapped[str] = mapped_column(
        String(36),
        name="id",
        primary_key=True,
    )
    name: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text(),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=True,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime_factory,
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    key_id: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        unique=True,
        index=True,
    )
    key_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )
    key_secret_first: Mapped[str] = mapped_column(
        String(4),
        nullable=False,
    )
    key_secret_last: Mapped[str] = mapped_column(
        String(4),
        nullable=False,
    )
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)


class ApiKeyModel(ApiKeyModelMixin, Base):
    """Concrete SQLAlchemy ORM model for API keys."""

    ...


class SqlAlchemyApiKeyRepository(AbstractApiKeyRepository):
    """SQLAlchemy implementation of the API key repository."""

    def __init__(self, async_session: AsyncSession) -> None:
        self._async_session = async_session

    async def ensure_table(self, async_engine: AsyncEngine) -> None:
        """Ensure the database table for API keys exists.

        Notes:
            This method creates the table if it does not exist.
        """
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @staticmethod
    def _to_model(entity: ApiKey, target: Optional[ApiKeyModel] = None) -> ApiKeyModel:
        """Convert a domain entity to a SQLAlchemy model instance."""
        if target is None:
            return ApiKeyModel(
                id_=entity.id_,
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

        # Update existing model
        target.name = entity.name
        target.description = entity.description
        target.is_active = entity.is_active
        target.expires_at = entity.expires_at
        target.last_used_at = entity.last_used_at
        target.scopes = entity.scopes
        return target

    @staticmethod
    @typing.overload
    def _to_domain(model: None) -> None: ...

    @staticmethod
    @typing.overload
    def _to_domain(model: ApiKeyModel) -> ApiKey: ...

    @staticmethod
    def _to_domain(model: Optional[ApiKeyModel]) -> Optional[ApiKey]:
        """Convert a SQLAlchemy model instance to a domain entity."""
        if model is None:
            return None

        return ApiKey(
            id_=model.id_,
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
            scopes=model.scopes,
        )

    async def get_by_id(self, id_: str) -> Optional[ApiKey]:
        stmt = select(ApiKeyModel).where(ApiKeyModel.id_ == id_)
        result = await self._async_session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model)

    async def get_by_key_id(self, key_id: str) -> Optional[ApiKey]:
        stmt = select(ApiKeyModel).where(ApiKeyModel.key_id == key_id)
        result = await self._async_session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model)

    async def create(self, entity: ApiKey) -> ApiKey:
        model = self._to_model(entity)
        self._async_session.add(model)
        await self._async_session.flush()

        result = self._to_domain(model)
        assert result is not None, "Model was just created, domain entity must exist"  # nosec B101
        return result

    async def update(self, entity: ApiKey) -> Optional[ApiKey]:
        stmt = select(ApiKeyModel).where(ApiKeyModel.id_ == entity.id_)
        result = await self._async_session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return None

        model = self._to_model(entity, target=model)

        self._async_session.add(model)
        await self._async_session.flush()
        return self._to_domain(model)

    async def delete_by_id(self, id_: str) -> Optional[ApiKey]:
        stmt = select(ApiKeyModel).where(ApiKeyModel.id_ == id_)
        result = await self._async_session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return None

        await self._async_session.delete(model)
        await self._async_session.flush()
        return self._to_domain(model)

    async def list(self, limit: int = 100, offset: int = 0) -> List[ApiKey]:
        stmt = select(ApiKeyModel).order_by(ApiKeyModel.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)
        result = await self._async_session.execute(stmt)
        models: Sequence[ApiKeyModel] = result.scalars().all()

        entities = [self._to_domain(m) for m in models]
        return entities

    def _apply_filter(self, stmt: sqlalchemy.Select, filter_: ApiKeyFilter) -> sqlalchemy.Select:
        """Apply filter criteria to a SQLAlchemy statement."""
        # Boolean filters
        if filter_.is_active is not None:
            stmt = stmt.where(ApiKeyModel.is_active == filter_.is_active)

        # Date filters
        if filter_.expires_before is not None:
            stmt = stmt.where(ApiKeyModel.expires_at < filter_.expires_before)

        if filter_.expires_after is not None:
            stmt = stmt.where(ApiKeyModel.expires_at > filter_.expires_after)

        if filter_.created_before is not None:
            stmt = stmt.where(ApiKeyModel.created_at < filter_.created_before)

        if filter_.created_after is not None:
            stmt = stmt.where(ApiKeyModel.created_at > filter_.created_after)

        if filter_.last_used_before is not None:
            stmt = stmt.where(ApiKeyModel.last_used_at < filter_.last_used_before)

        if filter_.last_used_after is not None:
            stmt = stmt.where(ApiKeyModel.last_used_at > filter_.last_used_after)

        if filter_.never_used is not None:
            if filter_.never_used:
                stmt = stmt.where(ApiKeyModel.last_used_at.is_(None))
            else:
                stmt = stmt.where(ApiKeyModel.last_used_at.isnot(None))

        # Text filters
        if filter_.name_contains:
            stmt = stmt.where(ApiKeyModel.name.ilike(f"%{filter_.name_contains}%"))

        if filter_.name_exact:
            stmt = stmt.where(ApiKeyModel.name == filter_.name_exact)

        return stmt

    async def find(self, filter_: ApiKeyFilter) -> List[ApiKey]:
        """Search entities by filtering criteria.

        Note:
            Scope filters (scopes_contain_all, scopes_contain_any) are applied
            in Python after pagination due to limited JSON support in SQLite.
            This means when using scope filters, fewer results than `limit`
            may be returned even if more matching records exist.
        """
        stmt = select(ApiKeyModel)
        stmt = self._apply_filter(stmt, filter_)

        order_column = getattr(ApiKeyModel, filter_.order_by)
        if filter_.order_desc:
            stmt = stmt.order_by(order_column.desc())
        else:
            stmt = stmt.order_by(order_column.asc())

        # Pagination
        stmt = stmt.limit(filter_.limit).offset(filter_.offset)

        result = await self._async_session.execute(stmt)
        models: Sequence[ApiKeyModel] = result.scalars().all()
        entities = [self._to_domain(m) for m in models]

        # Apply scope filters in Python (SQLite JSON support is limited).
        # Note: This happens after pagination, so results may be fewer than limit.
        if filter_.scopes_contain_all:
            entities = [e for e in entities if all(s in e.scopes for s in filter_.scopes_contain_all)]

        if filter_.scopes_contain_any:
            entities = [e for e in entities if any(s in e.scopes for s in filter_.scopes_contain_any)]

        return entities

    async def count(self, filter_: Optional[ApiKeyFilter] = None) -> int:
        stmt = func.count(ApiKeyModel.id_)
        stmt = select(stmt)

        if filter_:
            # Apply same filters as find() but without pagination
            # Boolean filters
            stmt = self._apply_filter(stmt, filter_)

            # For scope filters, we need to count differently since we filter in Python
            if filter_.scopes_contain_all or filter_.scopes_contain_any:
                # Fall back to find() and count results
                entities = await self.find(
                    ApiKeyFilter(
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
                )
                return len(entities)

        result = await self._async_session.execute(stmt)
        return result.scalar_one()
