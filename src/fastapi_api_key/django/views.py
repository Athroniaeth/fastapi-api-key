"""Django async class-based views for API key management.

All views are ``async`` and require Django 4.1+.  They accept/return JSON and
follow the same REST contract as the FastAPI, Litestar, and Quart integrations.

Dependency injection follows Django's ``as_view(svc_factory=...)`` pattern.

Example::

    from django.urls import path
    from fastapi_api_key.django.views import (
        ApiKeyListCreateView,
        ApiKeyDetailView,
        ApiKeyActivateView,
        ApiKeyDeactivateView,
        ApiKeySearchView,
        ApiKeyCountView,
        ApiKeyVerifyView,
    )

    urlpatterns = [
        path("api-keys/", ApiKeyListCreateView.as_view(svc_factory=get_service)),
        path("api-keys/<str:pk>/", ApiKeyDetailView.as_view(svc_factory=get_service)),
        ...
    ]
"""

import json
from typing import Any, Awaitable, Callable

try:
    from django.http import HttpRequest, JsonResponse
    from django.views import View
except ModuleNotFoundError as e:  # pragma: no cover
    raise ImportError("Django integration requires 'django'. Install it with: uv add fastapi_api_key[django]") from e

from pydantic import ValidationError

from fastapi_api_key.domain.errors import KeyNotFound
from fastapi_api_key.services.base import AbstractApiKeyService
from fastapi_api_key._schemas import (
    ApiKeyCountOut,
    ApiKeyCreateIn,
    ApiKeyCreatedOut,
    ApiKeySearchIn,
    ApiKeySearchOut,
    ApiKeyUpdateIn,
    ApiKeyVerifyIn,
    _to_out,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _json_response(data: Any, status: int = 200) -> JsonResponse:
    """Serialize a Pydantic model or dict/list to a JsonResponse."""
    if hasattr(data, "model_dump"):
        return JsonResponse(data.model_dump(mode="json"), status=status)
    return JsonResponse(data, status=status, safe=False)


def _parse_body(request: HttpRequest, model_class: Any) -> Any:
    """Parse and validate the request body with the given Pydantic model.

    Returns the parsed model instance, or raises ``JsonResponse`` 400/422.
    """
    try:
        raw = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        raise _HttpError(400, "Invalid JSON body")
    try:
        return model_class(**raw)
    except (ValidationError, TypeError) as exc:
        raise _HttpError(422, str(exc))


class _HttpError(Exception):
    """Internal sentinel to short-circuit view logic with an HTTP error."""

    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail


def _error(status: int, detail: str) -> JsonResponse:
    return JsonResponse({"detail": detail}, status=status)


# ---------------------------------------------------------------------------
# Base view
# ---------------------------------------------------------------------------


class _BaseApiKeyView(View):
    """Shared base for all API key views."""

    # Must be declared here so Django's as_view(svc_factory=...) works.
    svc_factory: Callable[..., Awaitable[AbstractApiKeyService]] = None  # type: ignore[assignment]

    async def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        try:
            return await super().dispatch(request, *args, **kwargs)
        except _HttpError as exc:
            return _error(exc.status, exc.detail)
        except KeyNotFound:
            return _error(404, "API key not found")

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]


# ---------------------------------------------------------------------------
# GET+POST /api-keys/
# ---------------------------------------------------------------------------


class ApiKeyListCreateView(_BaseApiKeyView):
    """``GET /api-keys/`` – list with pagination.

    ``POST /api-keys/`` – create a new key.
    """

    async def get(self, request: HttpRequest) -> JsonResponse:
        try:
            offset = int(request.GET.get("offset", 0))
            limit = int(request.GET.get("limit", 50))
        except ValueError:
            return _error(400, "offset and limit must be integers")

        if offset < 0 or limit <= 0 or limit > 100:
            return _error(400, "offset >= 0 and 0 < limit <= 100")

        svc = await self.svc_factory()
        items = await svc.list(offset=offset, limit=limit)
        return _json_response([_to_out(e).model_dump(mode="json") for e in items])

    async def post(self, request: HttpRequest) -> JsonResponse:
        payload: ApiKeyCreateIn = _parse_body(request, ApiKeyCreateIn)
        svc = await self.svc_factory()
        entity, api_key_str = await svc.create(
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
            scopes=payload.scopes,
            expires_at=payload.expires_at,
        )
        out = ApiKeyCreatedOut(api_key=api_key_str, entity=_to_out(entity))
        return _json_response(out, status=201)


# ---------------------------------------------------------------------------
# GET+PATCH+DELETE /api-keys/<pk>/
# ---------------------------------------------------------------------------


class ApiKeyDetailView(_BaseApiKeyView):
    """``GET /api-keys/<pk>/`` – retrieve.

    ``PATCH /api-keys/<pk>/`` – partial update.

    ``DELETE /api-keys/<pk>/`` – delete.
    """

    async def get(self, request: HttpRequest, pk: str) -> JsonResponse:
        svc = await self.svc_factory()
        entity = await svc.get_by_id(pk)  # raises KeyNotFound → caught by dispatch
        return _json_response(_to_out(entity))

    async def patch(self, request: HttpRequest, pk: str) -> JsonResponse:
        payload: ApiKeyUpdateIn = _parse_body(request, ApiKeyUpdateIn)
        svc = await self.svc_factory()
        current = await svc.get_by_id(pk)

        if payload.name is not None:
            current.name = payload.name
        if payload.description is not None:
            current.description = payload.description
        if payload.is_active is not None:
            current.is_active = payload.is_active
        if payload.scopes is not None:
            current.scopes = payload.scopes
        if payload.clear_expires:
            current.expires_at = None
        elif payload.expires_at is not None:
            current.expires_at = payload.expires_at

        updated = await svc.update(current)
        return _json_response(_to_out(updated))

    async def delete(self, request: HttpRequest, pk: str) -> JsonResponse:
        svc = await self.svc_factory()
        await svc.delete_by_id(pk)
        return JsonResponse({}, status=204)


# ---------------------------------------------------------------------------
# POST /api-keys/<pk>/activate
# POST /api-keys/<pk>/deactivate
# ---------------------------------------------------------------------------


class ApiKeyActivateView(_BaseApiKeyView):
    """``POST /api-keys/<pk>/activate`` – activate a key."""

    async def post(self, request: HttpRequest, pk: str) -> JsonResponse:
        svc = await self.svc_factory()
        entity = await svc.get_by_id(pk)
        if entity.is_active:
            return _json_response(_to_out(entity))
        entity.is_active = True
        updated = await svc.update(entity)
        return _json_response(_to_out(updated))


class ApiKeyDeactivateView(_BaseApiKeyView):
    """``POST /api-keys/<pk>/deactivate`` – deactivate a key."""

    async def post(self, request: HttpRequest, pk: str) -> JsonResponse:
        svc = await self.svc_factory()
        entity = await svc.get_by_id(pk)
        if not entity.is_active:
            return _json_response(_to_out(entity))
        entity.is_active = False
        updated = await svc.update(entity)
        return _json_response(_to_out(updated))


# ---------------------------------------------------------------------------
# POST /api-keys/search
# ---------------------------------------------------------------------------


class ApiKeySearchView(_BaseApiKeyView):
    """``POST /api-keys/search`` – advanced search with filters."""

    async def post(self, request: HttpRequest) -> JsonResponse:
        payload: ApiKeySearchIn = _parse_body(request, ApiKeySearchIn)
        try:
            offset = int(request.GET.get("offset", 0))
            limit = int(request.GET.get("limit", 50))
        except ValueError:
            return _error(400, "offset and limit must be integers")

        svc = await self.svc_factory()
        filter_ = payload.to_filter(limit=limit, offset=offset)
        items = await svc.find(filter_)
        total = await svc.count(filter_)
        out = ApiKeySearchOut(
            items=[_to_out(e) for e in items],
            total=total,
            limit=limit,
            offset=offset,
        )
        return _json_response(out)


# ---------------------------------------------------------------------------
# POST /api-keys/count
# ---------------------------------------------------------------------------


class ApiKeyCountView(_BaseApiKeyView):
    """``POST /api-keys/count`` – count keys matching a filter."""

    async def post(self, request: HttpRequest) -> JsonResponse:
        payload: ApiKeySearchIn = _parse_body(request, ApiKeySearchIn)
        svc = await self.svc_factory()
        filter_ = payload.to_filter(limit=0, offset=0)
        total = await svc.count(filter_)
        return _json_response(ApiKeyCountOut(total=total))


# ---------------------------------------------------------------------------
# POST /api-keys/verify
# ---------------------------------------------------------------------------


class ApiKeyVerifyView(_BaseApiKeyView):
    """``POST /api-keys/verify`` – verify a key and return its details."""

    async def post(self, request: HttpRequest) -> JsonResponse:
        from fastapi_api_key.domain.errors import (
            InvalidKey,
            InvalidScopes,
            KeyExpired,
            KeyInactive,
            KeyNotProvided,
        )

        payload: ApiKeyVerifyIn = _parse_body(request, ApiKeyVerifyIn)
        svc = await self.svc_factory()

        try:
            entity = await svc.verify_key(
                api_key=payload.api_key,
                required_scopes=payload.required_scopes,
            )
        except (InvalidKey, KeyNotFound):
            return _error(401, "API key invalid")
        except KeyNotProvided:
            return _error(401, "API key missing")
        except KeyInactive:
            return _error(403, "API key inactive")
        except KeyExpired:
            return _error(403, "API key expired")
        except InvalidScopes:
            scopes_str = ", ".join([f"'{s}'" for s in (payload.required_scopes or [])])
            return _error(403, f"API key missing required scopes {scopes_str}")

        return _json_response(_to_out(entity))
