# In-memory Prototype

Use this variant when you want to exercise the domain and service layers without touching a database. Everything lives in a dictionary behind the repository interface.

## When to use

- Unit tests that focus on hashing and validation behaviour.
- Demo scripts or workshops where persisting secrets is unnecessary.
- As a starting point before wiring a real repository implementation.

## Example

The script below is the same file shipped under `benchmark/example_inmemory.py`. It creates a key, prints the secret once, then verifies it.

```python
--8<-- "benchmark/example_inmemory.py"
```

### What happens

1. A random pepper is generated (or pulled from `API_KEY_PEPPER`).
2. `ApiKeyService.create()` hashes the secret and stores the entity in memory.
3. `ApiKeyService.verify_key()` reconstructs the key id and validates the hash.

!!! note "No persistence"
    The repository keeps data inside an in-memory dictionary. Keys disappear as soon as the process stops.
