import os
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from fastapi_api_key import ApiKey, ApiKeyService
from fastapi_api_key.domain.errors import InvalidScopes
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
    async with async_session_maker() as async_session:
        repo = SqlAlchemyApiKeyRepository(async_session)

        # Necessary if you don't use your own DeclarativeBase
        await repo.ensure_table()

        svc = ApiKeyService(repo=repo, hasher=hasher)

        # Create an API key without scopes
        bad_entity = ApiKey(name="no-scope-key", scopes=["read"])
        good_entity = ApiKey(name="with-scope-key", scopes=["write"])

        _, bad_api_key = await svc.create(bad_entity)
        _, good_api_key = await svc.create(good_entity)

        print(f"Bad API Key (no required scopes): '{bad_api_key}'")
        print(f"Good API Key (with required scopes): '{good_api_key}'")

        await svc.verify_key(good_api_key, required_scopes=["write"])
        print("Successfully verified good API key with required scopes.")

        try:
            await svc.verify_key(bad_api_key, required_scopes=["write"])
        except InvalidScopes as e:
            print(f"Failed to verify bad API key with required scopes: {e}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
