import os

from fastapi import FastAPI, Depends, APIRouter
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from fastapi_api_key import Argon2ApiKeyHasher, ApiKey
from fastapi_api_key.router import create_api_keys_router, create_api_key_security

# Create the async engine and session maker
DATABASE_URL = "sqlite+aiosqlite:///./db.sqlite3"
async_engine = create_async_engine(DATABASE_URL, future=True)
async_session_maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)

pepper = os.environ.get("API_KEY_PEPPER")

app = FastAPI(title="API with API Key Management")
hasher = Argon2ApiKeyHasher(pepper=pepper)
security = create_api_key_security(async_session_maker, hasher=hasher)

router = APIRouter(prefix="/api-keys", tags=["API Keys"])
router_protected = APIRouter(prefix="/protected", tags=["Protected"])


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


router_api_keys = create_api_keys_router(async_session_maker, hasher=hasher, router=router)
app.include_router(router_api_keys)
app.include_router(router_protected)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="localhost", port=8000)
