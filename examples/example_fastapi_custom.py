import os
from contextlib import asynccontextmanager
from dataclasses import field, dataclass
from pathlib import Path
from typing import AsyncIterator
from typing import Optional, Type

from fastapi import FastAPI, Depends, APIRouter
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase

from fastapi_api_key import ApiKeyService
from fastapi_api_key.api import create_api_keys_router, create_depends_api_key
from fastapi_api_key.domain.entities import ApiKey as OldApiKey
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository, ApiKeyModelMixin


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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Create the database tables
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


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


app = FastAPI(title="API with API Key Management", lifespan=lifespan)


async def async_session() -> AsyncIterator[AsyncSession]:
    """Dependency to provide an active SQLAlchemy async session."""
    async with async_session_maker() as session:
        async with session.begin():
            yield session


async def inject_svc_api_keys(async_session: AsyncSession = Depends(async_session)) -> ApiKeyService:
    """Dependency to inject the API key service with an active SQLAlchemy async session."""
    # No need to ensure table here, done in lifespan
    repo = SqlAlchemyApiKeyRepository(
        async_session=async_session,
        model_cls=ApiKeyModel,
        domain_cls=ApiKey,
    )
    return ApiKeyService(
        repo=repo,
        hasher=hasher,
        domain_cls=ApiKey,
    )


security = create_depends_api_key(inject_svc_api_keys)
router_protected = APIRouter(prefix="/protected", tags=["Protected"])

router = APIRouter(prefix="/api-keys", tags=["API Keys"])
router_api_keys = create_api_keys_router(
    inject_svc_api_keys,
    router=router,
)


@router_protected.get("/")
async def read_protected_data(api_key: ApiKey = Depends(security)):
    return {
        "message": "This is protected data",
        "apiKey": {
            "id": api_key.id_,
            "name": api_key.name,
            "description": api_key.description,
            "isActive": api_key.is_active,
            "createdAt": api_key.created_at,
            "expiresAt": api_key.expires_at,
            "lastUsedAt": api_key.last_used_at,
        },
    }


app.include_router(router_api_keys)
app.include_router(router_protected)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="localhost", port=8000)
