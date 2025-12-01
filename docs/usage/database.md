# Database Configuration

This guide covers SQLAlchemy setup and connection pooling best practices for production use.

## Installation

Install the SQLAlchemy extra:

```bash
pip install fastapi-api-key[sqlalchemy]
```

## Basic Setup

The `SqlAlchemyApiKeyRepository` requires an `AsyncSession`:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository

# Create async engine
engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/db")

# Create session factory
async_session = async_sessionmaker(engine, expire_on_commit=False)

# Use in your application
async with async_session() as session:
    repo = SqlAlchemyApiKeyRepository(session)
    # ... use repository
    await session.commit()
```

## Connection Pooling

SQLAlchemy uses connection pooling by default. For production, configure the pool explicitly.

### PostgreSQL (asyncpg)

```python
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/db",
    pool_size=5,           # Number of persistent connections
    max_overflow=10,       # Additional connections when pool is exhausted
    pool_timeout=30,       # Seconds to wait for a connection
    pool_recycle=1800,     # Recycle connections after 30 minutes
    pool_pre_ping=True,    # Verify connections before use
)
```

### SQLite (aiosqlite)

SQLite doesn't benefit from connection pooling. Use `NullPool` for async SQLite:

```python
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

engine = create_async_engine(
    "sqlite+aiosqlite:///./api_keys.db",
    poolclass=NullPool,
)
```

### MySQL (aiomysql)

```python
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    "mysql+aiomysql://user:pass@localhost/db",
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600,     # MySQL default wait_timeout is 8 hours
    pool_pre_ping=True,
)
```

## Pool Size Guidelines

| Scenario | pool_size | max_overflow |
|----------|-----------|--------------|
| Development | 2 | 5 |
| Small app (<100 req/s) | 5 | 10 |
| Medium app (100-1000 req/s) | 10 | 20 |
| Large app (>1000 req/s) | 20+ | 40+ |

!!! tip "Rule of Thumb"
    A good starting point is `pool_size = (2 * CPU cores) + effective_spindle_count`.
    For cloud databases, start with 5-10 and monitor.

## FastAPI Integration

Use a dependency to manage sessions per request:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from fastapi_api_key import ApiKeyService
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository

# Engine with connection pooling
engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/db",
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: optionally create tables
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.create_all)
        pass
    yield
    # Shutdown: dispose of the connection pool
    await engine.dispose()


app = FastAPI(lifespan=lifespan)


async def get_session():
    async with async_session() as session:
        yield session


async def get_api_key_service(session: AsyncSession = Depends(get_session)):
    repo = SqlAlchemyApiKeyRepository(session)
    return ApiKeyService(repo=repo)
```

## Connection Health

### Pre-ping

Enable `pool_pre_ping=True` to test connections before use. This handles:

- Database restarts
- Network interruptions
- Idle connection timeouts

### Pool Recycling

Set `pool_recycle` to a value less than your database's connection timeout:

| Database | Default Timeout | Recommended `pool_recycle` |
|----------|-----------------|---------------------------|
| PostgreSQL | No limit | 1800 (30 min) |
| MySQL | 8 hours | 3600 (1 hour) |
| MariaDB | 8 hours | 3600 (1 hour) |

## Monitoring

Log pool statistics for debugging:

```python
import logging

logging.getLogger("sqlalchemy.pool").setLevel(logging.DEBUG)
```

Check pool status programmatically:

```python
pool = engine.pool
print(f"Pool size: {pool.size()}")
print(f"Checked out: {pool.checkedout()}")
print(f"Overflow: {pool.overflow()}")
print(f"Checked in: {pool.checkedin()}")
```

## Common Issues

### "QueuePool limit reached"

The pool is exhausted. Solutions:

1. Increase `pool_size` and `max_overflow`
2. Ensure sessions are properly closed (use context managers)
3. Reduce query execution time

### "Connection reset by peer"

The database closed an idle connection. Solutions:

1. Enable `pool_pre_ping=True`
2. Set `pool_recycle` to a lower value
3. Check database idle timeout settings

### High latency on first request

The pool creates connections lazily. Pre-warm the pool:

```python
async def warm_pool():
    """Pre-create connections to avoid cold start latency."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
```
