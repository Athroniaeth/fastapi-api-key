# Quickstart

This walk-through mirrors the flow covered in the benchmarks folder and gets you from installation to a verified API key in three steps.

## 1. Install dependencies

Choose an extras group that matches the repository backend you plan to use. The examples below rely on the full async stack (FastAPI + SQLAlchemy + Argon2 + BCrypt).

```bash
uv sync --extra all --group dev
```

For quick experiments, the `argon` extra plus the in-memory repository is enough:

```bash
uv sync --extra argon --group dev
```

## 2. Create your first key

Spin up the service with the in-memory repository. The script mirrors `examples/example_inmemory.py`.

```python
import asyncio
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key import ApiKeyService, ApiKey

async def main():
    repo = InMemoryApiKeyRepository()
    service = ApiKeyService(repo=repo)
    entity = ApiKey(name="quickstart")
    entity, secret = await service.create(entity)
    print("Give this secret to the client:", secret)
    verified = await service.verify_key(secret)
    print("Verified key belongs to:", verified.id_)

asyncio.run(main())
```

## 3. Persist keys with SQLAlchemy

Swap the repository for the SQL implementation and connect it to an async engine. This mirrors `examples/example_sql.py`.

```python
import asyncio
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fastapi_api_key import ApiKeyService, ApiKey
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository

async def main():
    path = Path('db.sqlite3')
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}", future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with Session() as session:
        repo = SqlAlchemyApiKeyRepository(session)
        await repo.ensure_table()
        service = ApiKeyService(repo=repo)
        entity, secret = await service.create(ApiKey(name="persistent"))
        await session.commit()
        print("Stored key", entity.id_, "secret", secret)

asyncio.run(main())
```

Next, explore the detailed usage guides which embed the full example scripts from the repository.
