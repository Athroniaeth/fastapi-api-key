from fastapi_api_key.domain.base import D

try:
    import sqlalchemy  # noqa: F401
except ModuleNotFoundError as e:
    raise ImportError(
        "SQLAlchemy backend requires 'sqlalchemy'. Install it with: uv add fastapi_api_key[sqlalchemy]"
    ) from e


from dataclasses import fields as dataclass_fields, is_dataclass
from datetime import datetime
from typing import Callable, Generic, Type, TypeVar, List, overload, Set, Dict, Any
from typing import Optional

from sqlalchemy import String, Text, Boolean, DateTime, JSON, func, inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase

from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.repositories.base import AbstractApiKeyRepository, ApiKeyFilter
from fastapi_api_key.utils import datetime_factory


NoneType = type(None)


class Base(DeclarativeBase): ...


class ApiKeyModelMixinV1:
    """SQLAlchemy ORM model mixin for API keys (v0.5.x).

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
        String(128),
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


class ApiKeyModelMixin(ApiKeyModelMixinV1):
    """Concrete SQLAlchemy ORM model for API keys."""

    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)


class ApiKeyModel(ApiKeyModelMixin, Base):
    """Concrete SQLAlchemy ORM model for API keys."""

    ...


M = TypeVar("M", bound=ApiKeyModelMixin)  # SQLAlchemy row type
ToModel = Callable[[D, Type[M]], M]
ToDomain = Callable[[Optional[M], Type[D]], Optional[D]]

# Mapping between domain private fields and model public fields
# For entity -> model: we skip private fields that have public property equivalents
_DOMAIN_SKIP_FIELDS: Set[str] = {
    "_key_secret_first",  # Use property key_secret_first instead
    "_key_secret_last",  # Use property key_secret_last instead
    "_key_secret",  # Not stored in model
}

# For entity -> model: additional properties to read from entity
_DOMAIN_PROPERTIES_TO_MODEL: Dict[str, str] = {
    "key_secret_first": "key_secret_first",  # property -> column
    "key_secret_last": "key_secret_last",  # property -> column
}

# For model -> domain: mapping model columns to private entity fields
_MODEL_TO_DOMAIN_FIELD_MAP: Dict[str, str] = {
    "key_secret_first": "_key_secret_first",
    "key_secret_last": "_key_secret_last",
}


def _get_model_columns(model_cls: Type[M]) -> Set[str]:
    """Get all attribute names from a SQLAlchemy model class.

    Uses mapper.attrs to get Python attribute names (e.g., 'id_')
    rather than SQL column names (e.g., 'id').
    """
    mapper = sa_inspect(model_cls)
    return {attr.key for attr in mapper.attrs}


def _get_entity_fields(entity_cls: Type[D]) -> Set[str]:
    """Get all field names from a dataclass entity."""
    if not is_dataclass(entity_cls):
        # Fallback for non-dataclass entities
        return set(vars(entity_cls()).keys()) if callable(entity_cls) else set()
    return {f.name for f in dataclass_fields(entity_cls)}


def _auto_to_model(
    entity: D,
    model_cls: Type[M],
    target: Optional[M] = None,
) -> M:
    """Automatically map entity fields to model columns.

    This function introspects both the entity and model to find common fields
    and maps them automatically, handling private field name conversions.
    """
    model_columns = _get_model_columns(model_cls)

    # Build kwargs for model creation/update
    kwargs: Dict[str, Any] = {}

    # Get entity as dict (handle both dataclass and regular objects)
    if is_dataclass(entity):
        entity_data = {f.name: getattr(entity, f.name) for f in dataclass_fields(entity)}
    else:
        entity_data = vars(entity)

    for field_name, value in entity_data.items():
        # Skip private fields that have property equivalents
        if field_name in _DOMAIN_SKIP_FIELDS:
            continue
        elif field_name in model_columns:
            # Direct mapping
            kwargs[field_name] = value

    # Add properties that should be mapped to model columns
    for prop_name, model_field in _DOMAIN_PROPERTIES_TO_MODEL.items():
        if model_field in model_columns:
            try:
                kwargs[model_field] = getattr(entity, prop_name)
            except (ValueError, AttributeError):
                # Property might raise if secret is not set
                pass

    if target is None:
        return model_cls(**kwargs)

    # Update existing model
    for key, value in kwargs.items():
        setattr(target, key, value)
    return target


def _auto_to_domain(
    model: M,
    domain_cls: Type[D],
) -> D:
    """Automatically map model columns to entity fields.

    This function introspects both the model and entity to find common fields
    and maps them automatically, handling private field name conversions.
    """
    entity_fields = _get_entity_fields(domain_cls)

    # Build kwargs for entity creation
    kwargs: Dict[str, Any] = {}

    # Get all model column values
    model_columns = _get_model_columns(type(model))

    for col_name in model_columns:
        value = getattr(model, col_name)

        # Check if this model column maps to a private entity field
        if col_name in _MODEL_TO_DOMAIN_FIELD_MAP:
            entity_field = _MODEL_TO_DOMAIN_FIELD_MAP[col_name]
            if entity_field in entity_fields:
                kwargs[entity_field] = value
        elif col_name in entity_fields:
            # Direct mapping
            kwargs[col_name] = value

    return domain_cls(**kwargs)


class SqlAlchemyApiKeyRepository(AbstractApiKeyRepository[D], Generic[D, M]):
    def __init__(
        self,
        async_session: AsyncSession,
        model_cls: Optional[Type[M]] = None,
        domain_cls: Optional[Type[D]] = None,
    ) -> None:
        self._async_session = async_session
        self.model_cls = model_cls or ApiKeyModel
        self.domain_cls = domain_cls or ApiKey

    async def ensure_table(self) -> None:
        """Ensure the database table for API keys exists.

        Notes:
            This method creates the table if it does not exist.
            Only useful if using ApiKeyModel directly without use mixins.
        """
        async with self._async_session.bind.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @staticmethod
    def to_model(
        entity: D,
        model_cls: Type[M],
        target: Optional[M] = None,
    ) -> M:
        """Convert a domain entity to a SQLAlchemy model instance.

        This method uses automatic introspection to map entity fields to model
        columns. Custom fields added to both the entity and model are automatically
        included without needing to override this method.

        Notes:
            If `target` is provided, it will be updated with the entity's data.
            Otherwise, a new model instance will be created.
        """
        return _auto_to_model(entity, model_cls, target)

    @overload
    def to_domain(self, model: M, model_cls: Type[D]) -> D: ...

    @overload
    def to_domain(self, model: NoneType, model_cls: Type[D]) -> NoneType: ...

    def to_domain(self, model: Optional[M], model_cls: Type[D]) -> Optional[D]:
        """Convert a SQLAlchemy model instance to a domain entity.

        This method uses automatic introspection to map model columns to entity
        fields. Custom fields added to both the model and entity are automatically
        included without needing to override this method.
        """
        if model is None:
            return None

        return _auto_to_domain(model, model_cls)

    async def get_by_id(self, id_: str) -> Optional[D]:
        stmt = select(self.model_cls).where(self.model_cls.id_ == id_)
        result = await self._async_session.execute(stmt)
        model = result.scalar_one_or_none()
        return self.to_domain(model, self.domain_cls)

    async def get_by_key_id(self, key_id: str) -> Optional[D]:
        stmt = select(self.model_cls).where(self.model_cls.key_id == key_id)
        result = await self._async_session.execute(stmt)
        model = result.scalar_one_or_none()
        return self.to_domain(model, self.domain_cls)

    async def create(self, entity: D) -> D:
        model = self.to_model(entity, self.model_cls)
        self._async_session.add(model)
        await self._async_session.flush()
        return self.to_domain(model, self.domain_cls)

    async def update(self, entity: D) -> Optional[D]:
        stmt = select(self.model_cls).where(self.model_cls.id_ == entity.id_)
        result = await self._async_session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return None

        # update fields...
        model = self.to_model(entity, self.model_cls, target=model)

        self._async_session.add(model)
        await self._async_session.flush()
        return self.to_domain(model, self.domain_cls)

    async def delete_by_id(self, id_: str) -> Optional[D]:
        stmt = select(self.model_cls).where(self.model_cls.id_ == id_)
        result = await self._async_session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return None

        await self._async_session.delete(model)
        await self._async_session.flush()
        return self.to_domain(model, self.domain_cls)

    async def list(self, limit: int = 100, offset: int = 0) -> List[D]:
        stmt = select(self.model_cls).order_by(self.model_cls.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)
        result = await self._async_session.execute(stmt)
        models = result.scalars().all()
        return [self.to_domain(m, self.domain_cls) for m in models]

    def _apply_filter(self, stmt, filter: ApiKeyFilter):
        """Apply filter criteria to a SQLAlchemy statement."""
        # Boolean filters
        if filter.is_active is not None:
            stmt = stmt.where(self.model_cls.is_active == filter.is_active)

        # Date filters
        if filter.expires_before is not None:
            stmt = stmt.where(self.model_cls.expires_at < filter.expires_before)

        if filter.expires_after is not None:
            stmt = stmt.where(self.model_cls.expires_at > filter.expires_after)

        if filter.created_before is not None:
            stmt = stmt.where(self.model_cls.created_at < filter.created_before)

        if filter.created_after is not None:
            stmt = stmt.where(self.model_cls.created_at > filter.created_after)

        if filter.last_used_before is not None:
            stmt = stmt.where(self.model_cls.last_used_at < filter.last_used_before)

        if filter.last_used_after is not None:
            stmt = stmt.where(self.model_cls.last_used_at > filter.last_used_after)

        if filter.never_used is not None:
            if filter.never_used:
                stmt = stmt.where(self.model_cls.last_used_at.is_(None))
            else:
                stmt = stmt.where(self.model_cls.last_used_at.isnot(None))

        # Scope filters - using JSON operations
        # Note: SQLite JSON support is limited, we filter in Python for scopes
        # For production with PostgreSQL, use proper JSONB operators

        # Text filters
        if filter.name_contains:
            stmt = stmt.where(self.model_cls.name.ilike(f"%{filter.name_contains}%"))

        if filter.name_exact:
            stmt = stmt.where(self.model_cls.name == filter.name_exact)

        return stmt

    async def find(self, filter: ApiKeyFilter) -> List[D]:
        stmt = select(self.model_cls)
        stmt = self._apply_filter(stmt, filter)

        # Sorting
        order_column = getattr(self.model_cls, filter.order_by)
        if filter.order_desc:
            stmt = stmt.order_by(order_column.desc())
        else:
            stmt = stmt.order_by(order_column.asc())

        # Pagination
        stmt = stmt.limit(filter.limit).offset(filter.offset)

        result = await self._async_session.execute(stmt)
        models = result.scalars().all()
        entities = [self.to_domain(m, self.domain_cls) for m in models]

        # Apply scope filters in Python (SQLite JSON support is limited)
        if filter.scopes_contain_all:
            entities = [e for e in entities if all(s in e.scopes for s in filter.scopes_contain_all)]

        if filter.scopes_contain_any:
            entities = [e for e in entities if any(s in e.scopes for s in filter.scopes_contain_any)]

        return entities

    async def count(self, filter: Optional[ApiKeyFilter] = None) -> int:
        stmt = select(func.count(self.model_cls.id_))

        if filter:
            # Apply same filters as find() but without pagination
            # Boolean filters
            if filter.is_active is not None:
                stmt = stmt.where(self.model_cls.is_active == filter.is_active)

            if filter.expires_before is not None:
                stmt = stmt.where(self.model_cls.expires_at < filter.expires_before)

            if filter.expires_after is not None:
                stmt = stmt.where(self.model_cls.expires_at > filter.expires_after)

            if filter.created_before is not None:
                stmt = stmt.where(self.model_cls.created_at < filter.created_before)

            if filter.created_after is not None:
                stmt = stmt.where(self.model_cls.created_at > filter.created_after)

            if filter.last_used_before is not None:
                stmt = stmt.where(self.model_cls.last_used_at < filter.last_used_before)

            if filter.last_used_after is not None:
                stmt = stmt.where(self.model_cls.last_used_at > filter.last_used_after)

            if filter.never_used is not None:
                if filter.never_used:
                    stmt = stmt.where(self.model_cls.last_used_at.is_(None))
                else:
                    stmt = stmt.where(self.model_cls.last_used_at.isnot(None))

            if filter.name_contains:
                stmt = stmt.where(self.model_cls.name.ilike(f"%{filter.name_contains}%"))

            if filter.name_exact:
                stmt = stmt.where(self.model_cls.name == filter.name_exact)

            # For scope filters, we need to count differently since we filter in Python
            if filter.scopes_contain_all or filter.scopes_contain_any:
                # Fall back to find() and count results
                entities = await self.find(
                    ApiKeyFilter(
                        is_active=filter.is_active,
                        expires_before=filter.expires_before,
                        expires_after=filter.expires_after,
                        created_before=filter.created_before,
                        created_after=filter.created_after,
                        last_used_before=filter.last_used_before,
                        last_used_after=filter.last_used_after,
                        never_used=filter.never_used,
                        scopes_contain_all=filter.scopes_contain_all,
                        scopes_contain_any=filter.scopes_contain_any,
                        name_contains=filter.name_contains,
                        name_exact=filter.name_exact,
                        limit=999999,
                        offset=0,
                    )
                )
                return len(entities)

        result = await self._async_session.execute(stmt)
        return result.scalar_one()
