# Fastapi Api Key

  [![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
  [![Tested with pytest](https://img.shields.io/badge/tests-pytest-informational.svg)](https://pytest.org/)
  [![Coverage](https://img.shields.io/badge/coverage-89%25-brightgreen.svg)](#)  <!-- remplace 100% par ta valeur -->
  [![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-4B32C3.svg)](https://docs.astral.sh/ruff/)
  [![Security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://bandit.readthedocs.io/)
  [![Deps: uv](https://img.shields.io/badge/deps-managed%20with%20uv-3E4DD8.svg)](https://docs.astral.sh/uv/)
  [![Docs](https://img.shields.io/badge/docs-mkdocs%20material-00A4CC.svg)](https://athroniaeth.github.io/fastapi-api-key/)  <!-- adapte l’URL si besoin -->
  [![Commitizen friendly](https://img.shields.io/badge/commitizen-friendly-brightgreen.svg)](https://commitizen-tools.github.io/commitizen/)

`fastapi-api-key` provides reusable building blocks to issue, persist, and verify API keys in FastAPI applications. It ships with a domain model, hashing helpers, repository contracts, and an optional FastAPI router for CRUD management of keys.

## Features
- Domain-driven `ApiKey` dataclass with activation, expiration, and usage tracking helpers.
- Async `ApiKeyService` that creates, lists, updates, deletes, and verifies keyed entities while keeping secrets hashed.
- Pluggable persistence: in-memory repository for tests and prototypes, plus a SQLAlchemy repository with ready-to-use ORM mixins.
- Hashing strategies powered by Argon2 (default) or BCrypt, each supporting configurable peppers.
- FastAPI router factory that wires the service to async SQLAlchemy sessions, exposing create/list/read/update/delete endpoints.
- Utility factory functions for generating UUID primary keys, public `key_id` values, and secure random secrets.

## Installation
Clone the repository and install the project with the extras that fit your stack. Examples below use `uv`, but `pip` works the same.

```bash
uv sync --extra all  # fastapi + sqlalchemy + argon2 + bcrypt
```

For lighter setups you can choose individual extras such as `argon`, `bcrypt`, or `sqlalchemy`. Development dependencies (pytest, ruff, etc.) are available under the `dev` group:

```bash
uv sync --extra all --group dev
```

## Quick start

### Use the service with an in-memory repository

```python
import asyncio
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key import ApiKeyService, ApiKey

async def main():
    repo = InMemoryApiKeyRepository()
    service = ApiKeyService(repo=repo)  # Argon2 hasher with a default pepper
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
from fastapi_api_key import Argon2ApiKeyHasher, ApiKeyService
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository

repo = InMemoryApiKeyRepository()
service = ApiKeyService(
    repo=repo,
    hasher=Argon2ApiKeyHasher(pepper=os.environ["API_KEY_PEPPER"]),
)
```

### Mount the FastAPI router

```python
import os

import uvicorn
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fastapi_api_key.repositories.sql import Base
from fastapi_api_key.router import create_api_keys_router


async def main():
    engine = create_async_engine("sqlite+aiosqlite:///./keys.db", future=True)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = FastAPI()
    app.include_router(
        create_api_keys_router(
            async_session_maker=SessionLocal,
            pepper=os.environ["API_KEY_PEPPER"],
            prefix="/api-keys",
        )
    )
    uvicorn.run(app, host="localhost", port=8000)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
```

The router exposes:

- `POST /api-keys` - create a key and return the plaintext secret once.
- `GET /api-keys` - list keys with offset/limit pagination.
- `GET /api-keys/{id}` - fetch a key by identifier.
- `PATCH /api-keys/{id}` - update name, description, or active flag.
- `DELETE /api-keys/{id}` - remove a key.

Commented helpers are available for activation or rotation if you extend the service.

## Concepts

- `ApiKey` entity stores metadata, a generated `key_id`, and a hashed secret. It tracks activity and enforces expiration via `ensure_can_authenticate()`.
- `ApiKeyService` coordinates repositories and hashers. `create()` returns the persisted entity plus the full secret (`{global_prefix}{separator}{key_id}{separator}{secret}`).
- Repository contract (`AbstractApiKeyRepository`) defines async CRUD operations. The SQLAlchemy repository uses an `ApiKeyModelMixin` you can extend with custom columns.
- Hashers (`Argon2ApiKeyHasher`, `BcryptApiKeyHasher`) apply an application-wide pepper and validate secrets without leaking information.

## Testing and quality

Run the automated suite (unit, regression, and doctests) with coverage:

```bash
uv run pytest
```

`pyproject.toml` configures coverage reports (`htmlcov/`, `coverage.xml`) automatically. Development helpers are available via the console scripts:

```bash
uv run test  # pytest with coverage reports
uv run lint  # ruff format + lint, ty type-check, bandit
```

## Additional notes

- Python 3.13+ is required.
- The library issues warnings if you keep the default pepper; always configure a secret value outside source control.
- `SqlAlchemyApiKeyRepository.ensure_table()` can create the default table for simple deployments; production systems should manage migrations explicitly.
- Secrets are never logged or returned after creation. Tests cover negative paths such as invalid formats, expired keys, and hash mismatches to guard against regressions.
