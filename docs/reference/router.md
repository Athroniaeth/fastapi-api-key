# Router Endpoints

The router returned by `create_api_keys_router` exposes a small CRUD surface backed by `ApiKeyService`.

## Dependencies

- Async SQLAlchemy session factory (`async_sessionmaker`).
- Pepper-aware hasher (`Argon2ApiKeyHasher`).
- FastAPI dependency injection for per-request scoping.

## Routes

| Method | Path | Summary | Notes |
| --- | --- | --- | --- |
| POST | /api-keys | Create an API key. | Returns `ApiKeyCreatedOut` with the plaintext secret. |
| GET | /api-keys | List API keys. | Supports `offset` / `limit` query params. |
| GET | /api-keys/{api_key_id} | Retrieve by ID. | Raises HTTP 404 when the key is missing. |
| PATCH | /api-keys/{api_key_id} | Update metadata. | Partial updates on name, description, active flag. |
| DELETE | /api-keys/{api_key_id} | Delete a key. | Returns an empty 204 response on success. |

## Error handling

- Domain exceptions such as `KeyNotFound` are translated to HTTP 404 responses.
- Invalid payloads raise FastAPI validation errors automatically.
- The service raises `InvalidKey` during verification; map it to 401/403 if you expose an auth dependency.

!!! example "Mounting the router"
    See the [FastAPI Router guide](../usage/router.md) for the full wiring sample.
