# FastAPI Router

Mount CRUD endpoints that expose your key store over HTTP. The router wires the service, repository, and hashers together using FastAPI dependency injection.

## Features

- One call to `create_api_keys_router` registers create/list/get/update/delete routes.
- Depends on an async session factory (see `async_sessionmaker`).
- Shares a single `Argon2ApiKeyHasher` instance across requests.

## Example

Drop the snippet from `benchmark/example_fastapi.py` into your project and set `API_KEY_PEPPER` via environment variable:

```python
--8<-- "benchmark/example_fastapi.py"
```

### Endpoints exposed

| Method | Path | Description |
| --- | --- | --- |
| POST | /api-keys | Create a key and return the plaintext secret once. |
| GET | /api-keys | List keys with offset/limit pagination. |
| GET | /api-keys/{id} | Retrieve a key by identifier. |
| PATCH | /api-keys/{id} | Update name, description, or activation flag. |
| DELETE | /api-keys/{id} | Remove a key. |

### Authenticating requests

Use `create_api_key_security` to produce a FastAPI dependency that validates API keys via the service and repository stack:

```python
from fastapi import Depends, FastAPI
from fastapi_api_key.router import create_api_key_security

security = create_api_key_security(async_session_maker=SessionLocal, pepper=PEPPER)

app = FastAPI()

@app.get("/protected")
async def protected_route(key = Depends(security)):
    return {"key_id": key.key_id}
```

!!! tip "Secure the pepper"
    Provide `API_KEY_PEPPER` through your secret manager or environment—never check it into source control.
