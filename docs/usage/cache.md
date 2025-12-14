# Cache

When user give his api key to access your services, you often need to verify it against the stored hash. You must
calculate the hash of the provided key and compare it to the stored hash. This operation can be computationally
expensive, especially if you are using strong hashing algorithms like Argon2 or bcrypt. To improve performance, you can
implement a caching layer that stores the results of previous hash verifications. This way, if the same API key is
verified multiple times, you can retrieve the result from the cache instead of recalculating the hash each time.

We use `aiocache` to provide caching capabilities. This library has backend-agnostic support (in-memory, Redis, etc.) and
supports async operations.

## Security Model

The `CachedApiKeyService` uses a secure caching strategy that maintains the same security guarantees as the non-cached service:

**Cache key = SHA256(full_api_key)**

This ensures that:

- Only requests with the **complete and correct API key** can hit the cache
- An attacker who only knows the `key_id` (visible in the API key format) **cannot exploit the cache**
- The cached entity is only returned if the caller proves knowledge of the full secret

A **secondary index** (`key_id → cache_key`) enables cache invalidation when updating or deleting API keys, even though the service doesn't store the plain secret.

![Cache API Key System](../mermaid-cache-api-key-system.png)

## Configuration

### Cache Backend

You can use any `aiocache` backend. Configure TTL via the service:

```python
from aiocache import SimpleMemoryCache
from aiocache import Cache

# In-memory (default)
memory_cache = SimpleMemoryCache()
service = CachedApiKeyService(repo=repo, hasher=hasher, cache=memory_cache, cache_ttl=300)

# Redis backend
redis_cache = Cache(Cache.REDIS, endpoint="localhost", port=6379, namespace="api_keys")
service = CachedApiKeyService(repo=repo, hasher=hasher, cache=redis_cache, cache_ttl=600)
```

## Example

This is the canonical example from `examples/example_cached.py`:

!!! warning "Always set a pepper"
    The default pepper is a placeholder. Set `SECRET_PEPPER` (or pass it explicitly to the hashers) in every environment.

```python
--8<-- "examples/example_cached.py"
```

## Cache Invalidation

The cache is automatically invalidated when:

- An API key is **updated** (e.g., scopes changed, deactivated)
- An API key is **deleted**

This ensures that changes to API keys take effect immediately, even for cached entries.
