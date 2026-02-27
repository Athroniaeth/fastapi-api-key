# Litestar Integration

`fastapi-api-key` provides first-class support for [Litestar](https://litestar.dev/) via
`fastapi_api_key.litestar_api`.  The integration exposes two helpers:

| Helper | Purpose |
|---|---|
| `create_api_keys_router` | Full CRUD management router (same contract as the FastAPI counterpart) |
| `create_api_key_guard` | Litestar *guard* that verifies `Authorization: Bearer <key>` on any route |

## Installation

```bash
uv add fastapi_api_key[litestar]
```

## Quick start

```python
from litestar import Litestar
from fastapi_api_key.litestar_api import create_api_keys_router, create_api_key_guard
from fastapi_api_key.services.base import ApiKeyService
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher

# Shared service provider (called once per request by Litestar DI)
async def provide_svc() -> ApiKeyService:
    return ApiKeyService(
        repo=InMemoryApiKeyRepository(),
        hasher=Argon2ApiKeyHasher(pepper="your-secret-pepper"),
    )

# Management router (CRUD on /api-keys/*)
mgmt_router = create_api_keys_router(provide_svc=provide_svc)

app = Litestar(route_handlers=[mgmt_router])
```

## Protecting routes with a guard

```python
from litestar import Litestar, get
from litestar.connection import Request
from fastapi_api_key.litestar_api import create_api_key_guard

guard = create_api_key_guard(provide_svc=provide_svc)

# Apply to a single route
@get("/protected", guards=[guard])
async def protected_route(request: Request) -> dict:
    key = request.state.api_key   # verified ApiKey entity
    return {"key_id": key.key_id}

# Apply globally to the whole app
app = Litestar(route_handlers=[protected_route], guards=[guard])
```

### Scope-restricted guard

```python
admin_guard = create_api_key_guard(
    provide_svc=provide_svc,
    required_scopes=["admin"],
)

@get("/admin", guards=[admin_guard])
async def admin_route() -> dict:
    return {"admin": True}
```

## Management endpoints

The router mounted by `create_api_keys_router` exposes the same REST API as
the FastAPI integration:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api-keys/` | Create a new key (returns plaintext once) |
| `GET` | `/api-keys/` | List keys (paginated) |
| `GET` | `/api-keys/{id}` | Get a key by ID |
| `PATCH` | `/api-keys/{id}` | Partially update a key |
| `DELETE` | `/api-keys/{id}` | Delete a key |
| `POST` | `/api-keys/{id}/activate` | Activate a key |
| `POST` | `/api-keys/{id}/deactivate` | Deactivate a key |
| `POST` | `/api-keys/search` | Search with filters (paginated) |
| `POST` | `/api-keys/count` | Count keys matching a filter |
| `POST` | `/api-keys/verify` | Verify a key |

## SQLAlchemy repository

Use `SqlAlchemyApiKeyRepository` exactly as with FastAPI — Litestar's async
lifecycle handles session management transparently:

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository, Base

engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/db")
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def provide_svc() -> ApiKeyService:
    async with SessionLocal() as session:
        async with session.begin():
            repo = SqlAlchemyApiKeyRepository(session)
            return ApiKeyService(repo=repo, hasher=Argon2ApiKeyHasher(pepper="pepper"))
```

## Caching

The `CachedApiKeyService` from `fastapi_api_key.services.cached` works
identically in Litestar:

```python
from fastapi_api_key.services.cached import CachedApiKeyService

async def provide_svc() -> CachedApiKeyService:
    return CachedApiKeyService(
        repo=InMemoryApiKeyRepository(),
        hasher=Argon2ApiKeyHasher(pepper="pepper"),
        cache_ttl=300,
    )
```

## Dev mode (`.env` keys)

```python
import os
os.environ["API_KEY_DEV"] = "ak-mydevkeyid-mysecret64chars"

async def provide_svc() -> ApiKeyService:
    svc = ApiKeyService(repo=InMemoryApiKeyRepository(), hasher=Argon2ApiKeyHasher())
    await svc.load_dotenv(envvar_prefix="API_KEY_")
    return svc
```
