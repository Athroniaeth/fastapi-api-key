import os
from dataclasses import field, dataclass
from pathlib import Path
from typing import Optional, Type

from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase

from fastapi_api_key import ApiKeyService
from fastapi_api_key.domain.entities import ApiKey as OldApiKey
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.repositories.sql import (
    SqlAlchemyApiKeyRepository,
    ApiKeyModelMixin,
)
import asyncio


class Base(DeclarativeBase): ...


@dataclass
class ApiKey(OldApiKey):
    notes: Optional[str] = field(default=None)


class ApiKeyModel(Base, ApiKeyModelMixin):
    notes: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )


class ApiKeyRepository(SqlAlchemyApiKeyRepository[ApiKey, ApiKeyModel]):
    def __init__(
        self,
        async_session: AsyncSession,
        model_cls: Type[ApiKeyModel] = ApiKeyModel,
        domain_cls: Type[ApiKey] = ApiKey,
    ) -> None:
        super().__init__(
            async_session=async_session,
            model_cls=model_cls,
            domain_cls=domain_cls,
        )

    @staticmethod
    def to_model(
        entity: ApiKey,
        model_cls: Type[ApiKeyModel],
        target: Optional[ApiKeyModel] = None,
    ) -> ApiKeyModel:
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
                notes=entity.notes,
            )

        # Update existing model
        target.name = entity.name
        target.description = entity.description
        target.is_active = entity.is_active
        target.expires_at = entity.expires_at
        target.last_used_at = entity.last_used_at
        target.key_id = entity.key_id
        target.key_hash = entity.key_hash  # type: ignore[invalid-assignment]
        target.notes = entity.notes

        return target

    @staticmethod
    def to_domain(
        model: Optional[ApiKeyModel],
        model_cls: Type[ApiKey],
    ) -> Optional[ApiKey]:
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
            notes=model.notes,
        )


# Set env var to override default pepper
# Using a strong, unique pepper is crucial for security
# Default pepper is insecure and should not be used in production
pepper = os.getenv("API_KEY_PEPPER")
hasher = Argon2ApiKeyHasher(pepper=pepper)

path = Path(__file__).parent / "db.sqlite3"
database_url = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{path}")

async_engine = create_async_engine(database_url, future=True)
async_session_maker = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def main():
    async with async_session_maker() as session:
        repo = SqlAlchemyApiKeyRepository(session)

        # Don't need to create Base and ApiKeyModel, the repository does it for you
        await repo.ensure_table()

        service = ApiKeyService(repo=repo, hasher=hasher)
        entity = ApiKey(name="persistent")

        # Entity have updated id after creation
        entity, secret = await service.create(entity)
        print("Stored key", entity.id_, "secret", secret)

        # Don't forget to commit the session to persist the key
        # You can also use a transaction `async with session.begin():`
        await session.commit()


asyncio.run(main())
