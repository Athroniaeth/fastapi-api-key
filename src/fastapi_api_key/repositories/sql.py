from datetime import datetime
from typing import Callable, Generic, Type, TypeVar, List
from typing import Optional

from sqlalchemy import String, Text, Boolean, DateTime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase

from fastapi_api_key.domain.entities import ApiKey, D
from fastapi_api_key.repositories.base import AbstractApiKeyRepository
from fastapi_api_key.utils import datetime_factory


class Base(DeclarativeBase): ...


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
        default=datetime_factory(),
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    key_id: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
    )
    key_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
    )


class ApiKeyModel(Base, ApiKeyModelMixin):
    """Concrete SQLAlchemy ORM model for API keys."""

    ...


M = TypeVar("M", bound=ApiKeyModelMixin)  # SQLAlchemy row type
ToModel = Callable[[D, Type[M]], M]
ToDomain = Callable[[Optional[M], Type[D]], Optional[D]]


def to_model(entity: D, model_cls: Type[M]) -> M:
    """Convert a domain entity to a SQLAlchemy model instance."""
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


def to_domain(model: Optional[M], model_cls: Type[D]) -> Optional[D]:
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


class SqlAlchemyApiKeyRepository(AbstractApiKeyRepository[D], Generic[D, M]):
    def __init__(
        self,
        async_session: AsyncSession,
        model_cls: Optional[Type[M]] = None,
        domain_cls: Optional[Type[D]] = None,
        to_model_fn: Optional[ToModel] = None,
        to_domain_fn: Optional[ToDomain] = None,
    ) -> None:
        self._async_session = async_session
        self.model_cls = model_cls or ApiKeyModel
        self.domain_cls = domain_cls or ApiKey

        self.to_model = to_model_fn or to_model
        self.to_domain = to_domain_fn or to_domain

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
        model.name = entity.name
        model.description = entity.description
        model.is_active = entity.is_active
        model.expires_at = entity.expires_at
        model.last_used_at = entity.last_used_at
        model.key_id = entity.key_id
        model.key_hash = entity.key_hash

        self._async_session.add(model)
        await self._async_session.flush()
        return self.to_domain(model, self.domain_cls)

    async def delete_by_id(self, id_: str) -> bool:
        stmt = select(self.model_cls).where(self.model_cls.id_ == id_)
        result = await self._async_session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return False

        await self._async_session.delete(model)
        await self._async_session.flush()
        return True

    async def list(self, limit: int = 100, offset: int = 0) -> List[D]:
        stmt = select(self.model_cls).order_by(self.model_cls.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)
        result = await self._async_session.execute(stmt)
        models = result.scalars().all()
        return [self.to_domain(m, self.domain_cls) for m in models]
