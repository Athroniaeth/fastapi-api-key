import asyncio
import math
import os
import time
from contextlib import contextmanager

from fastapi_api_key import ApiKeyService, ApiKey
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key.services.cached import CachedApiKeyService

# Set env var to override default pepper
# Using a strong, unique pepper is crucial for security
# Default pepper is insecure and should not be used in production
pepper = os.getenv("API_KEY_PEPPER", "change_me")
hasher = Argon2ApiKeyHasher(pepper=pepper)

# default hasher is Argon2 with a default pepper (to be changed in prod)
repo = InMemoryApiKeyRepository()


@contextmanager
def benchmark(n: int):
    time_start = time.perf_counter()
    yield
    time_end = time.perf_counter()
    time_elapsed = time_end - time_start

    ops_per_sec = math.trunc(n / time_elapsed)
    print(f"  Elapsed time: {time_elapsed:.6f} seconds ({ops_per_sec:,} ops/sec)\n")


async def main():
    n = 100

    for service in [
        # Must use Bcrypt hash each call
        ApiKeyService(repo=repo, hasher=hasher),
        # Use Bcrypt once and cache the result
        CachedApiKeyService(repo=repo, hasher=hasher),
    ]:
        print(f"{service.__class__.__name__}")
        print("- First operation (uncached):")

        entity = ApiKey(name="dev")
        _, api_key = await service.create(entity)

        with benchmark(1):
            await service.verify_key(api_key)

        print(f"- Subsequent {n} operations (cached where applicable):")

        with benchmark(n):
            for _ in range(n):
                await service.verify_key(api_key)


if __name__ == "__main__":
    asyncio.run(main())
