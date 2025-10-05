# Service API

`ApiKeyService` orchestrates hashing, repository access, and validation. It inherits from `AbstractApiKeyService` and provides concrete implementations for each method.

## Constructor

```python
ApiKeyService(repo, hasher=None, domain_cls=None, separator='-', global_prefix='ak')
```

- `repo`: implementation of the repository protocol (in-memory, SQLAlchemy, or your own).
- `hasher`: optional; defaults to `Argon2ApiKeyHasher`.
- `domain_cls`: override if you subclass `ApiKey`.
- `separator` / `global_prefix`: control the printable format returned to clients.

## Lifecycle methods

| Method | Purpose | Exceptions |
| --- | --- | --- |
| `create(entity, key_secret=None)` | Hashes the secret (or generates one) then persists the entity. Returns `(entity, plaintext_secret)`. | `ValueError` (past expiration). |
| `list(limit=100, offset=0)` | Reads a page of keys, ordered by creation descending. | – |
| `get_by_id(id_)` | Fetches a key by UUID. | `KeyNotProvided`, `KeyNotFound`. |
| `get_by_key_id(key_id)` | Looks up by the short public identifier. | `KeyNotProvided`, `KeyNotFound`. |
| `update(entity)` | Persists changes; raises if the record is missing. | `KeyNotFound`. |
| `delete_by_id(id_)` | Removes an entity. | `KeyNotFound`. |

## Verification flow

1. Validates the incoming string format and extracts `key_id` / secret using the configured separator.
2. Loads the entity via `get_by_key_id()` and ensures it is active and not expired.
3. Verifies the hash with the configured hasher and updates `last_used_at` via `touch()`.
4. Persists the refreshed entity and returns it to the caller.

!!! warning "Pepper hygiene"
    Hashers append the configured pepper before hashing. Rotate peppers carefully and re-issue keys when needed.
