# Custom Domain Model

Extend the default dataclass and SQLAlchemy model to capture application-specific metadata (notes, scopes, tags, etc.).

## Overview

- Subclass `ApiKey` to add fields such as `notes` or `scopes`.
- Derive a SQLAlchemy model from `ApiKeyModelMixin` and add new mapped columns.
- Override `SqlAlchemyApiKeyRepository` to translate between the two.

## Full example

Pulled straight from `benchmark/example_sql_custom.py`:

```python
--8<-- "benchmark/example_sql_custom.py"
```

### Key takeaways

1. The dataclass extends `ApiKey` with a `notes` field.
2. `ApiKeyModel` inherits from `ApiKeyModelMixin` and maps the new column.
3. The repository overrides `to_model` and `to_domain` to keep the new data in sync.

!!! info "Migrations"
    Because you own the SQLAlchemy model, creating migrations with Alembic or your favourite tool is straightforward.
