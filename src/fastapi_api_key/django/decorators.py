"""Django async view decorator for API key authentication.

Usage::

    from fastapi_api_key.django.decorators import require_api_key

    @require_api_key(svc_factory=get_service)
    async def my_view(request):
        key = request.api_key   # verified ApiKey entity
        return JsonResponse({"key_id": key.key_id})
"""

from functools import wraps
from typing import Any, Awaitable, Callable, List, Optional

try:
    from django.http import HttpRequest, JsonResponse
except ModuleNotFoundError as e:  # pragma: no cover
    raise ImportError(
        "Django integration requires 'django'. "
        "Install it with: uv add fastapi_api_key[django]"
    ) from e

from fastapi_api_key.domain.errors import (
    InvalidKey,
    InvalidScopes,
    KeyExpired,
    KeyInactive,
    KeyNotFound,
    KeyNotProvided,
)
from fastapi_api_key.services.base import AbstractApiKeyService


def require_api_key(
    svc_factory: Callable[..., Awaitable[AbstractApiKeyService]],
    required_scopes: Optional[List[str]] = None,
) -> Callable:
    """Async view decorator that verifies the ``Authorization: Bearer`` header.

    On success, sets ``request.api_key`` to the verified
    :class:`~fastapi_api_key.domain.entities.ApiKey` entity.

    Args:
        svc_factory: Async callable returning an
            :class:`~fastapi_api_key.services.base.AbstractApiKeyService`.
        required_scopes: Optional list of scopes the key must possess.

    Example::

        @require_api_key(svc_factory=get_service, required_scopes=["read"])
        async def my_view(request):
            return JsonResponse({"key_id": request.api_key.key_id})
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        async def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            auth = request.headers.get("Authorization", "")
            if not auth.lower().startswith("bearer "):
                return JsonResponse({"detail": "API key missing"}, status=401)

            api_key_str = auth[7:]
            svc = await svc_factory()

            try:
                entity = await svc.verify_key(api_key_str, required_scopes=required_scopes)
            except KeyNotProvided:
                return JsonResponse({"detail": "API key missing"}, status=401)
            except (InvalidKey, KeyNotFound):
                return JsonResponse({"detail": "API key invalid"}, status=401)
            except KeyInactive:
                return JsonResponse({"detail": "API key inactive"}, status=403)
            except KeyExpired:
                return JsonResponse({"detail": "API key expired"}, status=403)
            except InvalidScopes:
                scopes_str = ", ".join([f"'{s}'" for s in (required_scopes or [])])
                return JsonResponse(
                    {"detail": f"API key missing required scopes {scopes_str}"},
                    status=403,
                )

            request.api_key = entity  # type: ignore[attr-defined]
            return await view_func(request, *args, **kwargs)

        return wrapped

    return decorator
