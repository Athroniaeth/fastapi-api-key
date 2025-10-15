# Fastapi Api Key

![Python Version from PEP 621 TOML](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2FAthroniaeth%2Ffastapi-api-key%2Fmain%2Fpyproject.toml)
[![Tested with pytest](https://img.shields.io/badge/tests-pytest-informational.svg)](https://pytest.org/)
![Coverage](https://img.shields.io/badge/coverage-72%25-brightgreen.svg)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-4B32C3.svg)](https://docs.astral.sh/ruff/)
[![Security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://bandit.readthedocs.io/)
[![Deps: uv](https://img.shields.io/badge/deps-managed%20with%20uv-3E4DD8.svg)](https://docs.astral.sh/uv/)
[![Commitizen friendly](https://img.shields.io/badge/commitizen-friendly-brightgreen.svg)](https://commitizen-tools.github.io/commitizen/)

`fastapi-api-key` provides reusable building blocks to issue, persist, and verify API keys in FastAPI applications. It
ships with a domain model, hashing helpers, repository contracts, and an optional FastAPI router for CRUD management of
keys.

## Features

- **Security-first**: secrets are hashed with a salt and a pepper, and never logged or returned after creation
- **Ready-to-use**: just create your repository (storage) and use service
- **Prod-ready**: services and repositories are async, and battle-tested

- **Agnostic hasher**: you can use any async-compatible hashing strategy (default: Argon2)
- **Agnostic backend**: you can use any async-compatible database (default: SQLAlchemy)
- **Factory**: create a Typer, FastAPI router wired to api key systems (only SQLAlchemy for now)

## Standards compliance

This library try to follow best practices and relevant RFCs for API key management and authentication:

- **[RFC 9110/7235](https://www.rfc-editor.org/rfc/rfc9110.html)**: Router raise 401 for missing/invalid keys, 403 for valid but inactive/expired keys
- **[RFC 6750](https://datatracker.ietf.org/doc/html/rfc6750)**: Supports `Authorization: Bearer <api_key>` header for key transmission (also supports deprecated `X-API-Key` header and `api_key` query param)


## Installation

This project is not published to PyPI. Use a tool like [uv](https://docs.astral.sh/uv/) to manage dependencies.

```bash
uv add fastapi-api-key
uv pip install fastapi-api-key
```

## Development installation

Clone or fork the repository and install the project with the extras that fit your stack. Examples below use `uv`:

```bash
uv sync --extra all  # fastapi + sqlalchemy + argon2 + bcrypt
uv pip install -e ".[all]"
```

For lighter setups you can choose individual extras:

| Installation mode           | Command                       | Description                                                                      |
|-----------------------------|-------------------------------|----------------------------------------------------------------------------------|
| **Base installation**       | `fastapi-api-key`             | Installs the core package without any optional dependencies.                     |
| **With bcrypt support**     | `fastapi-api-key[bcrypt]`     | Adds support for password hashing using **bcrypt** (`bcrypt>=5.0.0`).            |
| **With Argon2 support**     | `fastapi-api-key[argon2]`     | Adds support for password hashing using **Argon2** (`argon2-cffi>=25.1.0`).      |
| **With SQLAlchemy support** | `fastapi-api-key[sqlalchemy]` | Adds database integration via **SQLAlchemy** (`sqlalchemy>=2.0.43`).             |
| **Core setup**              | `fastapi-api-key[core]`       | Installs the **core dependencies** (SQLAlchemy + Argon2 + bcrypt).               |
| **FastAPI only**            | `fastapi-api-key[fastapi]`    | Installs **FastAPI** as an optional dependency (`fastapi>=0.118.0`).             |
| **Full installation**       | `fastapi-api-key[all]`        | Installs **all optional dependencies**: FastAPI, SQLAlchemy, Argon2, and bcrypt. |

```bash
uv add fastapi-api-key[sqlalchemy]
uv pip install fastapi-api-key[sqlalchemy]
uv sync --extra sqlalchemy
uv pip install -e ".[sqlalchemy]"
```

Development dependencies (pytest, ruff, etc.) are available under the `dev` group:

```bash
uv sync --extra dev
uv pip install -e ".[dev]"
```

## Quick start

### Use the service with an in-memory repository

```python
import asyncio

from fastapi_api_key import ApiKeyService, ApiKey
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository


async def main():
    repo = InMemoryApiKeyRepository()
    service = ApiKeyService(repo=repo)  # default hasher is Argon2 with a default pepper (to be changed in prod)
    entity = ApiKey(name="docs")

    entity, api_key = await service.create(entity)
    print("Give this secret to the client:", api_key)

    verified = await service.verify_key(api_key)
    print("Verified key belongs to:", verified.id_)


asyncio.run(main())
```

Override the default pepper in production:

```python
import os
from fastapi_api_key import ApiKeyService
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository

pepper = os.environ["API_KEY_PEPPER"]
hasher = Argon2ApiKeyHasher(pepper=pepper)

repo = InMemoryApiKeyRepository()
service = ApiKeyService(
    repo=repo,
    hasher=hasher,
)
```

### How API Keys Work

This is a classic API key if you don't modify the service behavior:

`ak-7a74caa323a5410d-mAfP3l6yAxqFz0FV2LOhu2tPCqL66lQnj3Ubd08w9RyE4rV4skUcpiUVIfsKEbzw`

- "-" separators so that systems can easily split
- Prefix `ak` (for "Api Key"), to identify the key type (useful to indicate that it is an API key).
- 16 first characters are the identifier (UUIDv4 without dashes)
- 48 last characters are the secret (random URL-safe base64 string)

When verifying an API key, the service extracts the identifier, retrieves the corresponding record from the repository, and compares the hashed secret. If found, it hashes the provided secret (with the same salt and pepper) and compares it to the stored hash.
If they match, the key is valid.

### Mount the FastAPI router

This example uses SQLAlchemy with FastAPI. It creates the database tables at startup if they do not exist.

```python
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
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
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

```

The router exposes:

- `POST /api-keys` - create a key and return the plaintext secret once.
- `GET /api-keys` - list keys with offset/limit pagination.
- `GET /api-keys/{id}` - fetch a key by identifier.
- `PATCH /api-keys/{id}` - update name, description, or active flag.
- `DELETE /api-keys/{id}` - remove a key.

## Contributing

- Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to contribute to the project, also respect
  the [Code of Conduct](CODE_OF_CONDUCT.md).
- Please see [SECURITY.md](SECURITY.md) for security-related information.
- Please see [LICENSE](LICENSE) for details on the license.

## Additional notes

- Python 3.9+ is required.
- The library issues warnings if you keep the default pepper; always configure a secret value outside source control.
- Never log peppers or plaintext API keys, change the pepper of prod will prevent you from reading API keys
