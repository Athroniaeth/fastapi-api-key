# SQLAlchemy (async)

Persist API keys in a relational database using SQLAlchemy's async ORM integration. This is the most common production scenario.

## Highlights

- Uses `SqlAlchemyApiKeyRepository` to map the domain entity to a database table.
- Calls `ensure_table()` to bootstrap the schema for prototypes.
- Commits the transaction only after the key has been created.
- Reuses `Argon2ApiKeyHasher` with a custom pepper.

## Example

This is the canonical example from `examples/example_sql.py`:

```python
--8<-- "examples/example_sql.py"
```

### Tips

- Store the generated secret returned by `ApiKeyService.create()` right away; it cannot be retrieved later.
- The helper `ensure_table()` lets you bootstrap the bundled schema quickly so you don't have to re-declare the ORM model unless you want custom fields.
- You can override the SQLAlchemy model via `ApiKeyModelMixin`—see the advanced section for a full example.
