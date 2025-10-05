# Repository Contracts

Repositories implement `AbstractApiKeyRepository` and encapsulate persistence concerns. Two ready-to-use implementations ship with the library: in-memory for tests and SQLAlchemy for production.

## Interface

| Method | Description |
| --- | --- |
| `get_by_id(id_)` | Return the entity by UUID or `None`. |
| `get_by_key_id(key_id)` | Lookup using the short identifier embedded in plaintext keys. |
| `create(entity)` | Persist a new entity and return the stored version. |
| `update(entity)` | Replace existing values; returns `None` when the record is missing. |
| `delete_by_id(id_)` | Delete the entity and return `True` on success. |
| `list(limit=100, offset=0)` | Fetch a paginated list ordered by creation time descending. |

## InMemoryApiKeyRepository

- Keeps entities in a simple Python dictionary keyed by `id_`.
- Perfect for unit tests and prototyping.
- Not thread-safe and offers no persistence guarantees.

## SqlAlchemyApiKeyRepository

- Accepts an async `AsyncSession` and lazily creates ORM models.
- Provides `ensure_table()` to create the default schema (override with migrations later).
- Exposes `to_model` / `to_domain` helpers so you can map custom dataclasses.
- Ships with `ApiKeyModelMixin` to ease model extension.

!!! info "Custom columns"
    Combine the mixin with your own SQLAlchemy base class to inject additional columns or relationships.
