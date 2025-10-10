import asyncio
import os

from fastapi_api_key import ApiKeyService, ApiKey
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository

# Set env var to override default pepper
# Using a strong, unique pepper is crucial for security
# Default pepper is insecure and should not be used in production
pepper = os.getenv("API_KEY_PEPPER")
hasher = Argon2ApiKeyHasher(pepper=pepper)

# default hasher is Argon2 with a default pepper (to be changed in prod)
repo = InMemoryApiKeyRepository()
service = ApiKeyService(
    repo=repo,
    hasher=hasher,
)


async def main():
    entity = ApiKey(name="development")
    entity, api_key = await service.create(entity)
    print("Give this secret to the client:", api_key)

    verified = await service.verify_key(api_key)
    print("Verified key belongs to:", verified.id_)


asyncio.run(main())
