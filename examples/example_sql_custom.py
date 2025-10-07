import os
from dataclasses import field, dataclass
from pathlib import Path
from typing import Optional, Type

from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase

from fastapi_api_key import ApiKeyService
from fastapi_api_key.domain.entities import ApiKey as OldApiKey
from fastapi_api_key.domain.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.repositories.sql import (
    SqlAlchemyApiKeyRepository,
    ApiKeyModelMixin,
)

# Set env var to override default pepper
# Using a strong, unique pepper is crucial for security
# Default pepper is insecure and should not be used in production
pepper = os.environ.get("API_KEY_PEPPER")
db_path = Path(__file__).parent / "db.sqlite3"
database_url = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")


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


async def main():
    print(f"Using database URL: {database_url}")

    async_engine = create_async_engine(database_url)
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as async_session:
        # No need to use ensure_table; table is created above
        # and this method only works with the default model_cls
        hasher = Argon2ApiKeyHasher(pepper=pepper)
        repo = ApiKeyRepository(async_session=async_session, domain_cls=ApiKey)
        svc = ApiKeyService(repo=repo, hasher=hasher, domain_cls=ApiKey)

        entity = ApiKey(
            name="my-first-key",
            description="This is my first API key",
            is_active=True,
        )

        entity, api_key = await svc.create(entity)
        entity.notes = "These are some notes about the API key"
        entity = await svc.update(entity)
        print(f"Notes : {entity.notes}")
        print(f"Created entity: {entity}")
        print(f"Created api_key: {api_key}")

        # Commit the transaction to persist the data
        await async_session.commit()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
