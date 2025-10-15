import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Depends, APIRouter
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from fastapi_api_key import ApiKey, ApiKeyService
from fastapi_api_key.api import create_api_keys_router, create_depends_api_key
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository, ApiKeyModelMixin


class Base(DeclarativeBase): ...


class ApiKeyModel(Base, ApiKeyModelMixin): ...


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
    repo = SqlAlchemyApiKeyRepository(async_session)
    return ApiKeyService(repo=repo, hasher=hasher)


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
        "apiKey": api_key,
    }


app.include_router(router_api_keys)
app.include_router(router_protected)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="localhost", port=8000)
