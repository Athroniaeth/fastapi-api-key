import os

from argon2 import PasswordHasher

from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key.services.base import ApiKeyService
from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.domain.hasher.argon2 import Argon2ApiKeyHasher

# Set env var to override default pepper
# Using a strong, unique pepper is crucial for security
# Default pepper is insecure and should not be used in production
pepper = os.environ.get("API_KEY_PEPPER")


async def main():
    password_hasher = PasswordHasher()
    hasher = Argon2ApiKeyHasher(
        pepper=pepper,
        password_hasher=password_hasher,
    )
    repo = InMemoryApiKeyRepository()

    svc = ApiKeyService(repo=repo, hasher=hasher)
    entity = ApiKey(
        name="my-first-key",
        description="This is my first API key",
        is_active=True,
    )
    entity, api_key = await svc.create(entity)
    print(f"Created entity: {entity}")
    print(f"Created api_key: {api_key} ({len(api_key)})\n")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
