# Django Integration

`fastapi-api-key` supports [Django](https://www.djangoproject.com/) 4.1+ via the
`fastapi_api_key.django` package.

The integration provides:

| Component | Purpose |
|---|---|
| `DjangoApiKeyRepository` | Django ORM repository (replaces SQLAlchemy) |
| `ApiKeyListCreateView` / `ApiKeyDetailView` / … | Async class-based views for CRUD management |
| `create_api_keys_urlpatterns` | URL pattern factory |
| `require_api_key` | Async view decorator for route protection |

## Installation

```bash
uv add fastapi_api_key[django]
```

## Setup

Add the app to `INSTALLED_APPS` in your Django settings:

```python
# settings.py
INSTALLED_APPS = [
    ...
    "fastapi_api_key.django",
]
```

Then run migrations to create the `api_keys` table:

```bash
python manage.py makemigrations fastapi_api_key_django
python manage.py migrate
```

## Quick start

```python
# myapp/api_keys.py
from fastapi_api_key.django import DjangoApiKeyRepository
from fastapi_api_key.services.base import ApiKeyService
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher

async def get_service() -> ApiKeyService:
    return ApiKeyService(
        repo=DjangoApiKeyRepository(),
        hasher=Argon2ApiKeyHasher(pepper="your-secret-pepper"),
    )
```

Register the management endpoints in your URL configuration:

```python
# myapp/urls.py
from django.urls import path, include
from fastapi_api_key.django.urls import create_api_keys_urlpatterns
from myapp.api_keys import get_service

urlpatterns = [
    path("api-keys/", include(create_api_keys_urlpatterns(svc_factory=get_service))),
]
```

## Protecting views

Use the `require_api_key` decorator on any async view:

```python
from django.http import JsonResponse
from fastapi_api_key.django.decorators import require_api_key
from myapp.api_keys import get_service

@require_api_key(svc_factory=get_service)
async def my_protected_view(request):
    key = request.api_key   # verified ApiKey entity
    return JsonResponse({"key_id": key.key_id})
```

### Scope-restricted views

```python
@require_api_key(svc_factory=get_service, required_scopes=["admin"])
async def admin_view(request):
    return JsonResponse({"admin": True})
```

## Management endpoints

`create_api_keys_urlpatterns` mounts these routes:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api-keys/` | Create a new key (returns plaintext once) |
| `GET` | `/api-keys/` | List keys (paginated with `?offset=` / `?limit=`) |
| `GET` | `/api-keys/<id>/` | Get a key by ID |
| `PATCH` | `/api-keys/<id>/` | Partially update a key |
| `DELETE` | `/api-keys/<id>/` | Delete a key |
| `POST` | `/api-keys/<id>/activate/` | Activate a key |
| `POST` | `/api-keys/<id>/deactivate/` | Deactivate a key |
| `POST` | `/api-keys/search/` | Search with filters |
| `POST` | `/api-keys/count/` | Count keys matching a filter |
| `POST` | `/api-keys/verify/` | Verify a key |

## Custom service factory

Django's `as_view(svc_factory=...)` pattern is used for dependency injection.
You can wire up any service factory, including one backed by caching:

```python
from fastapi_api_key.services.cached import CachedApiKeyService

async def get_service() -> CachedApiKeyService:
    return CachedApiKeyService(
        repo=DjangoApiKeyRepository(),
        hasher=Argon2ApiKeyHasher(pepper="pepper"),
        cache_ttl=300,
    )
```

## Dev mode (`.env` keys)

```python
import os
os.environ["API_KEY_DEV"] = "ak-mydevkeyid-mysecret64chars"

async def get_service() -> ApiKeyService:
    svc = ApiKeyService(repo=DjangoApiKeyRepository(), hasher=Argon2ApiKeyHasher())
    await svc.load_dotenv(envvar_prefix="API_KEY_")
    return svc
```

## Notes

- All views are `async` and require Django 4.1+ (native async ORM support).
- The repository uses Django's default database connection — no session management needed.
- Scope filters (`scopes_contain_all`, `scopes_contain_any`) are applied in Python after fetching, ensuring compatibility across SQLite, PostgreSQL, and MySQL.
