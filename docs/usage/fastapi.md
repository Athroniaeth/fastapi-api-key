# FastAPI

Mount CRUD endpoints that expose your key store over HTTP. The router wires the service, repository, and hashers
together using FastAPI dependency injection.

## Features

- One call to `create_api_keys_router` registers create/list/get/update/delete routes.
- Depends on an async session factory (see `async_sessionmaker`).
- Shares a single `ApiKeyHasher` instance across requests.

## Example

This is the canonical example from `examples/example_fastapi.py`:

!!! tip "Always set a pepper"
    The default pepper is a placeholder. Set `API_KEY_PEPPER` (or pass it explicitly to the hashers) in every environment.

```python
--8<-- "examples/example_fastapi.py"

```

I recommend you to create your own `Base` and models instead of reusing the example code.
```python
--8<-- "examples/example_fastapi_v2.py"
```

### Endpoints exposed

| Method | Path           | Description                                        |
|--------|----------------|----------------------------------------------------|
| POST   | /api-keys      | Create a key and return the plaintext secret once. |
| GET    | /api-keys      | List keys with offset/limit pagination.            |
| GET    | /api-keys/{id} | Retrieve a key by identifier.                      |
| PATCH  | /api-keys/{id} | Update name, description, or activation flag.      |
| DELETE | /api-keys/{id} | Remove a key.                                      |

