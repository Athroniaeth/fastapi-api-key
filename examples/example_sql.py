import asyncio
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fastapi_api_key import ApiKeyService, ApiKey
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository

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


async def main():
    async with async_session_maker() as session:
        repo = SqlAlchemyApiKeyRepository(session)

        # Don't need to create Base and ApiKeyModel, the repository does it for you
        await repo.ensure_table()

        service = ApiKeyService(repo=repo, hasher=hasher)
        entity = ApiKey(name="persistent")

        # Entity have updated id after creation
        entity, secret = await service.create(entity)
        print("Stored key", entity.id_, "secret", secret)

        # Don't forget to commit the session to persist the key
        # You can also use a transaction `async with session.begin():`
        await session.commit()


asyncio.run(main())
