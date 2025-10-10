# Fastapi Api Key

![Python Version from PEP 621 TOML](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2FAthroniaeth%2Ffastapi-api-key%2Fmain%2Fpyproject.toml)
[![Tested with pytest](https://img.shields.io/badge/tests-pytest-informational.svg)](https://pytest.org/)
[![Coverage](https://img.shields.io/badge/coverage-67%25-brightgreen.svg)](#)
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

## Installation

This projet does not publish to PyPI. Use a tool like [uv](https://docs.astral.sh/uv/) to manage dependencies.

```bash
uv add git+https://github.com/Athroniaeth/fastapi-api-key
uv pip install git+https://github.com/Athroniaeth/fastapi-api-key
```

## Development installation

Clone the repository and install the project with the extras that fit your stack. Examples below use `uv`:

```bash
uv sync --extra all  # fastapi + sqlalchemy + argon2 + bcrypt
uv pip install -e ".[all]"
```

For lighter setups you can choose individual extras such as `argon2`, `bcrypt`, or `sqlalchemy`.

```bash
uv add git+https://github.com/Athroniaeth/fastapi-api-key[sqlalchemy]
uv pip install git+https://github.com/Athroniaeth/fastapi-api-key[sqlalchemy]
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
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key import ApiKeyService, ApiKey


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
from fastapi_api_key.domain.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository

pepper = os.environ["API_KEY_PEPPER"]
hasher = Argon2ApiKeyHasher(pepper=pepper)

repo = InMemoryApiKeyRepository()
service = ApiKeyService(
    repo=repo,
    hasher=hasher,
)
```

### Mount the FastAPI router

class DeclarativeBase:
pass

```python
import os

import uvicorn
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fastapi_api_key.api import create_api_keys_router
from fastapi_api_key.domain.hasher.argon2 import Argon2ApiKeyHasher
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    ...


pepper = os.getenv("API_KEY_PEPPER")
hasher = Argon2ApiKeyHasher(pepper=pepper)

async_engine = create_async_engine("sqlite+aiosqlite:///./keys.db", future=True)
async_session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def lifespan(app: FastAPI):
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(lifespan=lifespan)
router = create_api_keys_router(
    hasher=hasher,
    async_session_maker=async_session_maker,
)
app.include_router(router, prefix="/api-keys")
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
