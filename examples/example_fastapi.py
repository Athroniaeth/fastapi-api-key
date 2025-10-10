import os
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Depends, APIRouter
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from fastapi_api_key import ApiKey, ApiKeyService
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository
from fastapi_api_key.api import create_api_keys_router, create_depends_api_key

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

app = FastAPI(title="API with API Key Management")


async def async_session() -> AsyncIterator[AsyncSession]:
    """Dependency to provide an active SQLAlchemy async session."""
    async with async_session_maker() as session:
        async with session.begin():
            yield session


async def inject_svc_api_keys(async_session: AsyncSession = Depends(async_session)) -> ApiKeyService:
    """Dependency to inject the API key service with an active SQLAlchemy async session."""
    repo = SqlAlchemyApiKeyRepository(async_session)
    await repo.ensure_table()
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
