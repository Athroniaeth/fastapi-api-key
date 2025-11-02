import asyncio
import os

from fastapi_api_key import ApiKeyService
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
# You can use load_dotenv for loading from .env
# from dotenv import load_dotenv
# load_dotenv()

# Ensure that you respect the format of service
os.environ["API_KEY_DEV"] = "ak-92f5326fb9b44ab7-fSvBMig0r2vY3WR2SmGoZwM949loPU7Yy1JkjIz3RzfCEkQrprQWqQuToLbM2FzN"


async def main():
    # Load api keys from os.environ
    await service.load_dotenv()  # envvar_prefix="API_KEY_"

    # Get api key for tests purposes
    api_key = os.environ["API_KEY_DEV"]

    verified = await service.verify_key(api_key)
    print("Verified key belongs to:", verified.name)


asyncio.run(main())
