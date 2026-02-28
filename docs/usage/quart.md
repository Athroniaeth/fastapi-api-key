# Quart Integration

`keyshield` supports [Quart](https://quart.palletsprojects.com/) — the
async-native reimplementation of Flask — via `keyshield.quart_api`.

The integration exposes two helpers:

| Helper | Purpose |
|---|---|
| `create_api_keys_blueprint` | Full CRUD management Blueprint |
| `require_api_key` | Async decorator that verifies `Authorization: Bearer <key>` |

## Installation

```bash
uv add keyshield[quart]
```

## Quick start

```python
from quart import Quart
from keyshield.quart_api import create_api_keys_blueprint, require_api_key
from keyshield.services.base import ApiKeyService
from keyshield.repositories.in_memory import InMemoryApiKeyRepository
from keyshield.hasher.argon2 import Argon2ApiKeyHasher

_svc = ApiKeyService(
    repo=InMemoryApiKeyRepository(),
    hasher=Argon2ApiKeyHasher(pepper="your-secret-pepper"),
)

async def get_service() -> ApiKeyService:
    return _svc

app = Quart(__name__)
app.register_blueprint(create_api_keys_blueprint(svc_factory=get_service))
```

## Protecting routes

```python
from quart import g

@app.get("/protected")
@require_api_key(svc_factory=get_service)
async def protected():
    key = g.api_key   # verified ApiKey entity
    return {"key_id": key.key_id}
```

### Scope-restricted routes

```python
@app.get("/admin")
@require_api_key(svc_factory=get_service, required_scopes=["admin"])
async def admin():
    return {"admin": True}
```

## Management endpoints

The Blueprint registered by `create_api_keys_blueprint` mounts these routes
(prefix defaults to `/api-keys`):

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api-keys/` | Create a new key (returns plaintext once) |
| `GET` | `/api-keys/` | List keys (paginated with `?offset=` / `?limit=`) |
| `GET` | `/api-keys/<id>` | Get a key by ID |
| `PATCH` | `/api-keys/<id>` | Partially update a key |
| `DELETE` | `/api-keys/<id>` | Delete a key |
| `POST` | `/api-keys/<id>/activate` | Activate a key |
| `POST` | `/api-keys/<id>/deactivate` | Deactivate a key |
| `POST` | `/api-keys/search` | Search with filters |
| `POST` | `/api-keys/count` | Count keys matching a filter |
| `POST` | `/api-keys/verify` | Verify a key |

## SQLAlchemy repository

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from keyshield.repositories.sql import SqlAlchemyApiKeyRepository

engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/db")
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_service() -> ApiKeyService:
    async with SessionLocal() as session:
        async with session.begin():
            repo = SqlAlchemyApiKeyRepository(session)
            return ApiKeyService(repo=repo, hasher=Argon2ApiKeyHasher(pepper="pepper"))
```

## Caching

```python
from keyshield.services.cached import CachedApiKeyService

async def get_service() -> CachedApiKeyService:
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

async def get_service() -> ApiKeyService:
    svc = ApiKeyService(repo=InMemoryApiKeyRepository(), hasher=Argon2ApiKeyHasher())
    await svc.load_dotenv(envvar_prefix="API_KEY_")
    return svc
```

## Custom URL prefix

```python
app.register_blueprint(
    create_api_keys_blueprint(svc_factory=get_service, url_prefix="/v1/keys")
)
```
