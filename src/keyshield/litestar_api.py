"""Litestar integration for keyshield.

Provides:
- ``create_api_keys_router`` – builds a :class:`litestar.Router` with full CRUD
  management endpoints (identical contract to the FastAPI counterpart).
- ``create_api_key_guard`` – returns a Litestar *guard* callable that verifies
  the ``Authorization: Bearer <api-key>`` header on any route.

Example::

    from litestar import Litestar
    from litestar.di import Provide
    from keyshield.litestar_api import create_api_keys_router, create_api_key_guard
    from keyshield.services.base import ApiKeyService
    from keyshield.repositories.in_memory import InMemoryApiKeyRepository
    from keyshield.hasher.argon2 import Argon2ApiKeyHasher

    async def provide_svc() -> ApiKeyService:
        return ApiKeyService(repo=InMemoryApiKeyRepository(), hasher=Argon2ApiKeyHasher())

    router = create_api_keys_router(provide_svc=provide_svc)
    guard  = create_api_key_guard(provide_svc=provide_svc)

    app = Litestar(route_handlers=[router])
"""

try:
    import litestar  # noqa: F401
except ModuleNotFoundError as e:  # pragma: no cover
    raise ImportError(
        "Litestar integration requires 'litestar'. Install it with: uv add keyshield[litestar]"
    ) from e

from typing import Awaitable, Callable, List, Optional

from litestar import Controller, Router, delete, get, patch, post
from litestar.connection import ASGIConnection
from litestar.di import Provide
from litestar.exceptions import (
    NotAuthorizedException,
    NotFoundException,
    PermissionDeniedException,
)
from litestar.handlers.base import BaseRouteHandler
from litestar.params import Parameter
from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
)
from typing_extensions import Annotated

from keyshield.domain.entities import ApiKey
from keyshield.domain.errors import (
    InvalidKey,
    InvalidScopes,
    KeyExpired,
    KeyInactive,
    KeyNotFound,
    KeyNotProvided,
)
from keyshield.services.base import AbstractApiKeyService
from keyshield._schemas import (
    ApiKeyCountOut,
    ApiKeyCreateIn,
    ApiKeyCreatedOut,
    ApiKeyOut,
    ApiKeySearchIn,
    ApiKeySearchOut,
    ApiKeyUpdateIn,
    ApiKeyVerifyIn,
    _to_out,
)


async def _handle_verify_key(
    svc: AbstractApiKeyService,
    api_key: str,
    required_scopes: Optional[List[str]] = None,
) -> ApiKey:
    """Run ``svc.verify_key`` and map domain errors to Litestar HTTP exceptions."""
    try:
        return await svc.verify_key(api_key, required_scopes=required_scopes)
    except KeyNotProvided as exc:
        raise NotAuthorizedException(detail="API key missing") from exc
    except (InvalidKey, KeyNotFound) as exc:
        raise NotAuthorizedException(detail="API key invalid") from exc
    except KeyInactive as exc:
        raise PermissionDeniedException(detail="API key inactive") from exc
    except KeyExpired as exc:
        raise PermissionDeniedException(detail="API key expired") from exc
    except InvalidScopes as exc:
        scopes_str = ", ".join([f"'{s}'" for s in (required_scopes or [])])
        raise PermissionDeniedException(detail=f"API key missing required scopes {scopes_str}") from exc


def create_api_keys_router(
    provide_svc: Callable[..., Awaitable[AbstractApiKeyService]],
    path: str = "/api-keys",
) -> Router:
    """Build a Litestar ``Router`` with full API key management endpoints.

    Args:
        provide_svc: Async callable (or coroutine function) that returns an
            :class:`~keyshield.services.base.AbstractApiKeyService` instance.
            It is registered as a Litestar *dependency* named ``svc``.
        path: URL prefix for all routes (default ``"/api-keys"``).

    Returns:
        A :class:`litestar.Router` ready to be passed to :class:`litestar.Litestar`.
    """

    class ApiKeyController(Controller):
        path = "/"

        @post("/", status_code=HTTP_201_CREATED, summary="Create a new API key")
        async def create_api_key(self, data: ApiKeyCreateIn, svc: AbstractApiKeyService) -> ApiKeyCreatedOut:
            """Create an API key and return the plaintext secret **once**.

            Args:
                data: Creation parameters.
                svc: Injected API key service.

            Returns:
                ``ApiKeyCreatedOut`` with the plaintext API key and the created entity.
            """
            entity, api_key_str = await svc.create(
                name=data.name,
                description=data.description,
                is_active=data.is_active,
                scopes=data.scopes,
                expires_at=data.expires_at,
            )
            return ApiKeyCreatedOut(api_key=api_key_str, entity=_to_out(entity))

        @get("/", status_code=HTTP_200_OK, summary="List API keys")
        async def list_api_keys(
            self,
            svc: AbstractApiKeyService,
            offset: Annotated[int, Parameter(ge=0, description="Items to skip")] = 0,
            limit: Annotated[int, Parameter(gt=0, le=100, description="Page size")] = 50,
        ) -> List[ApiKeyOut]:
            """List API keys with basic offset/limit pagination.

            Args:
                svc: Injected API key service.
                offset: Number of items to skip.
                limit: Max number of items to return.
            """
            items = await svc.list(offset=offset, limit=limit)
            return [_to_out(e) for e in items]

        @post("/search", status_code=HTTP_200_OK, summary="Search API keys with filters")
        async def search_api_keys(
            self,
            data: ApiKeySearchIn,
            svc: AbstractApiKeyService,
            offset: Annotated[int, Parameter(ge=0, description="Items to skip")] = 0,
            limit: Annotated[int, Parameter(gt=0, le=100, description="Page size")] = 50,
        ) -> ApiKeySearchOut:
            """Search API keys with advanced filtering criteria.

            Args:
                data: Search criteria (all optional, AND logic).
                svc: Injected API key service.
                offset: Number of items to skip.
                limit: Max number of items to return.
            """
            filter_ = data.to_filter(limit=limit, offset=offset)
            items = await svc.find(filter_)
            total = await svc.count(filter_)
            return ApiKeySearchOut(
                items=[_to_out(e) for e in items],
                total=total,
                limit=limit,
                offset=offset,
            )

        @post("/count", status_code=HTTP_200_OK, summary="Count API keys with filters")
        async def count_api_keys(self, data: ApiKeySearchIn, svc: AbstractApiKeyService) -> ApiKeyCountOut:
            """Count API keys matching the given filter criteria.

            Args:
                data: Filter criteria (all optional, AND logic).
                svc: Injected API key service.
            """
            filter_ = data.to_filter(limit=0, offset=0)
            total = await svc.count(filter_)
            return ApiKeyCountOut(total=total)

        @post("/verify", status_code=HTTP_200_OK, summary="Verify an API key")
        async def verify_api_key(self, data: ApiKeyVerifyIn, svc: AbstractApiKeyService) -> ApiKeyOut:
            """Verify an API key and return its details if valid.

            Args:
                data: Verification parameters.
                svc: Injected API key service.

            Raises:
                NotAuthorizedException: 401 if the key is invalid or not found.
                PermissionDeniedException: 403 if the key is inactive, expired, or
                    missing required scopes.
            """
            entity = await _handle_verify_key(
                svc=svc,
                api_key=data.api_key,
                required_scopes=data.required_scopes,
            )
            return _to_out(entity)

        @get("/{api_key_id:str}", status_code=HTTP_200_OK, summary="Get an API key by ID")
        async def get_api_key(self, api_key_id: str, svc: AbstractApiKeyService) -> ApiKeyOut:
            """Retrieve an API key by its identifier.

            Args:
                api_key_id: Unique identifier of the API key.
                svc: Injected API key service.

            Raises:
                NotFoundException: 404 if the key does not exist.
            """
            try:
                entity = await svc.get_by_id(api_key_id)
            except KeyNotFound as exc:
                raise NotFoundException(detail="API key not found") from exc
            return _to_out(entity)

        @patch("/{api_key_id:str}", status_code=HTTP_200_OK, summary="Update an API key")
        async def update_api_key(self, api_key_id: str, data: ApiKeyUpdateIn, svc: AbstractApiKeyService) -> ApiKeyOut:
            """Partially update an API key.

            Args:
                api_key_id: Unique identifier of the API key to update.
                data: Fields to update.
                svc: Injected API key service.

            Raises:
                NotFoundException: 404 if the key does not exist.
            """
            try:
                current = await svc.get_by_id(api_key_id)
            except KeyNotFound as exc:
                raise NotFoundException(detail="API key not found") from exc

            if data.name is not None:
                current.name = data.name
            if data.description is not None:
                current.description = data.description
            if data.is_active is not None:
                current.is_active = data.is_active
            if data.scopes is not None:
                current.scopes = data.scopes
            if data.clear_expires:
                current.expires_at = None
            elif data.expires_at is not None:
                current.expires_at = data.expires_at

            try:
                updated = await svc.update(current)
            except KeyNotFound as exc:
                raise NotFoundException(detail="API key not found") from exc

            return _to_out(updated)

        @delete("/{api_key_id:str}", status_code=HTTP_204_NO_CONTENT, summary="Delete an API key")
        async def delete_api_key(self, api_key_id: str, svc: AbstractApiKeyService) -> None:
            """Delete an API key by ID.

            Args:
                api_key_id: Unique identifier of the API key to delete.
                svc: Injected API key service.

            Raises:
                NotFoundException: 404 if the key does not exist.
            """
            try:
                await svc.delete_by_id(api_key_id)
            except KeyNotFound as exc:
                raise NotFoundException(detail="API key not found") from exc

        @post("/{api_key_id:str}/activate", status_code=HTTP_200_OK, summary="Activate an API key")
        async def activate_api_key(self, api_key_id: str, svc: AbstractApiKeyService) -> ApiKeyOut:
            """Activate an API key by ID.

            Args:
                api_key_id: Unique identifier of the API key to activate.
                svc: Injected API key service.

            Raises:
                NotFoundException: 404 if the key does not exist.
            """
            try:
                entity = await svc.get_by_id(api_key_id)
            except KeyNotFound as exc:
                raise NotFoundException(detail="API key not found") from exc

            if entity.is_active:
                return _to_out(entity)

            entity.is_active = True
            updated = await svc.update(entity)
            return _to_out(updated)

        @post("/{api_key_id:str}/deactivate", status_code=HTTP_200_OK, summary="Deactivate an API key")
        async def deactivate_api_key(self, api_key_id: str, svc: AbstractApiKeyService) -> ApiKeyOut:
            """Deactivate an API key by ID.

            Args:
                api_key_id: Unique identifier of the API key to deactivate.
                svc: Injected API key service.

            Raises:
                NotFoundException: 404 if the key does not exist.
            """
            try:
                entity = await svc.get_by_id(api_key_id)
            except KeyNotFound as exc:
                raise NotFoundException(detail="API key not found") from exc

            if not entity.is_active:
                return _to_out(entity)

            entity.is_active = False
            updated = await svc.update(entity)
            return _to_out(updated)

    return Router(
        path=path,
        route_handlers=[ApiKeyController],
        dependencies={"svc": Provide(provide_svc)},
    )


def create_api_key_guard(
    provide_svc: Callable[..., Awaitable[AbstractApiKeyService]],
    required_scopes: Optional[List[str]] = None,
) -> Callable[[ASGIConnection, BaseRouteHandler], Awaitable[None]]:
    """Create a Litestar *guard* that verifies the ``Authorization: Bearer`` header.

    The verified :class:`~keyshield.domain.entities.ApiKey` entity is
    stored in ``connection.state.api_key`` for downstream access.

    Args:
        provide_svc: Async callable returning an
            :class:`~keyshield.services.base.AbstractApiKeyService` instance.
        required_scopes: Optional list of scopes the key must possess.

    Returns:
        A guard callable suitable for ``guards=[...]`` on any Litestar route,
        controller, or app.

    Example::

        guard = create_api_key_guard(provide_svc=provide_svc, required_scopes=["read"])

        @get("/protected", guards=[guard])
        async def protected(request: Request) -> dict:
            key = request.state.api_key
            return {"key_id": key.key_id}
    """

    async def guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
        auth_header = connection.headers.get("Authorization", "")
        if not auth_header.lower().startswith("bearer "):
            raise NotAuthorizedException(detail="API key missing")

        api_key_str = auth_header[7:]
        svc = await provide_svc()
        entity = await _handle_verify_key(svc=svc, api_key=api_key_str, required_scopes=required_scopes)
        connection.state.api_key = entity

    return guard
