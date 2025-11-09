# Cache

When user give his api key to access your services, you often need to verify it against the stored hash. You must
calculate the hash of the provided key and compare it to the stored hash. This operation can be computationally
expensive, especially if you are using strong hashing algorithms like Argon2 or bcrypt. To improve performance, you can
implement a caching layer that stores the results of previous hash verifications. This way, if the same API key is
verified multiple times, you can retrieve the result from the cache instead of recalculating the hash each time.

We use `aiocache` to provide caching capabilities. This library have agnostic backends (in-memory, redis, memcached, etc.) and
supports async operations.

## Example

This is the canonical example from `examples/example_inmemory_env.py`:

!!! warning "Always set a pepper"
    The default pepper is a placeholder. Set `API_KEY_PEPPER` (or pass it explicitly to the hashers) in every environment.

```python
--8<-- "examples/example_inmemory_env.py"
```

