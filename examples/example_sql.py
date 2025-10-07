import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from fastapi_api_key import ApiKeyService
from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.domain.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository

# Set env var to override default pepper
# Using a strong, unique pepper is crucial for security
# Default pepper is insecure and should not be used in production
pepper = os.environ.get("API_KEY_PEPPER")
db_path = Path(__file__).parent / "db.sqlite3"
database_url = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")


async def main():
    print(f"Using database URL: {database_url}")

    async_engine = create_async_engine(database_url)
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as async_session:
        hasher = Argon2ApiKeyHasher(pepper=pepper)
        repo = SqlAlchemyApiKeyRepository(async_session)
        await repo.ensure_table()  # Ensure the table exists

        svc = ApiKeyService(repo=repo, hasher=hasher)
        entity = ApiKey(
            name="my-first-key",
            description="This is my first API key",
            is_active=True,
        )
        entity, api_key = await svc.create(entity)
        print(f"Created entity: {entity}")
        print(f"Created api_key: {api_key}\n")

        # Commit the transaction to persist the data
        await async_session.commit()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
