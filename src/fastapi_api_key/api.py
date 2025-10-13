from typing_extensions import deprecated

from fastapi_api_key.hasher.base import ApiKeyHasher
from fastapi_api_key.service import AbstractApiKeyService

try:
    import fastapi  # noqa: F401
    import sqlalchemy  # noqa: F401
except ModuleNotFoundError as e:
    raise ImportError(
        "FastAPI and SQLAlchemy backend requires 'fastapi' and 'sqlalchemy'. "
        "Install it with: uv add fastapi_api_key[fastapi]"
    ) from e

from datetime import datetime
from typing import Annotated, Awaitable, Callable, List, Optional, TypeVar, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_api_key import ApiKeyService
from fastapi_api_key.domain.entities import ApiKey, ApiKeyEntity
from fastapi_api_key.domain.errors import (
    InvalidKey,
    KeyExpired,
    KeyInactive,
    KeyNotFound,
    KeyNotProvided,
)
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository

D = TypeVar("D", bound=ApiKeyEntity)


class ApiKeyCreateIn(BaseModel):
    """Payload to create a new API key.

    Attributes:
        name: Human-friendly display name.
        description: Optional description to document the purpose of the key.
        is_active: Whether the key is active upon creation.
    """

    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=1024)
    is_active: bool = Field(default=True)


class ApiKeyUpdateIn(BaseModel):
    """Partial update payload for an API key.

    Attributes:
        name: New display name.
        description: New description.
        is_active: Toggle active state.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=1024)
    is_active: Optional[bool] = None


class ApiKeyOut(BaseModel):
    """Public representation of an API key entity.

    Note:
        Timestamps are optional to avoid coupling to a particular repository
        schema. If your entity guarantees those fields, they will be populated.
    """

    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ApiKeyCreatedOut(BaseModel):
    """Response returned after creating a key.

    Attributes:
        api_key: The plaintext API key value (only returned once!). Store it
            securely client-side; it cannot be retrieved again.
        entity: Public representation of the stored entity.
    """

    api_key: str
    entity: ApiKeyOut


class DeletedResponse(BaseModel):
    status: Literal["deleted"] = "deleted"


def _to_out(entity: ApiKey) -> ApiKeyOut:
    """Map an `ApiKey` entity to the public `ApiKeyOut` schema."""
    return ApiKeyOut(
        id=str(entity.id_),
        name=entity.name,
        description=entity.description,
        is_active=entity.is_active,
        created_at=entity.created_at,
        updated_at=entity.last_used_at,
    )


def create_api_keys_router(
    depends_svc_api_keys: Callable[[...], Awaitable[AbstractApiKeyService[D]]],
    router: Optional[APIRouter] = None,
) -> APIRouter:
    """Create and configure the API Keys router.

    Args:
        depends_svc_api_keys: Dependency callable that provides an `ApiKeyService`.
        router: Optional `APIRouter` instance. If not provided, a new one is created.

    Returns:
        Configured `APIRouter` ready to be included into a FastAPI app.
    """
    router = router or APIRouter(prefix="/api-keys", tags=["API Keys"])

    @router.post(
        path="/",
        response_model=ApiKeyCreatedOut,
        status_code=status.HTTP_201_CREATED,
        summary="Create a new API key",
    )
    async def create_api_key(
        payload: ApiKeyCreateIn,
        svc: ApiKeyService = Depends(depends_svc_api_keys),
    ) -> ApiKeyCreatedOut:
        """Create an API key and return the plaintext secret once.

        Args:
            payload: Creation parameters.
            svc: Injected `ApiKeyService`.

        Returns:
            `ApiKeyCreatedOut` with the plaintext API key and the created entity.
        """

        entity = ApiKey(
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
        )
        entity, api_key = await svc.create(entity)
        return ApiKeyCreatedOut(api_key=api_key, entity=_to_out(entity))

    @router.get(
        path="/",
        response_model=List[ApiKeyOut],
        status_code=status.HTTP_200_OK,
        summary="List API keys",
    )
    async def list_api_keys(
        svc: ApiKeyService = Depends(depends_svc_api_keys),
        offset: Annotated[int, Query(ge=0, description="Items to skip")] = 0,
        limit: Annotated[int, Query(gt=0, le=100, description="Page size")] = 50,
    ) -> List[ApiKeyOut]:
        """List API keys with basic offset/limit pagination.

        Args:
            svc: Injected `ApiKeyService`.
            offset: Number of items to skip.
            limit: Max number of items to return.

        Returns:
            A page of API keys.
        """
        items = await svc.list(offset=offset, limit=limit)
        return [_to_out(e) for e in items]

    @router.get(
        "/{api_key_id}",
        response_model=ApiKeyOut,
        status_code=status.HTTP_200_OK,
        summary="Get an API key by ID",
    )
    async def get_api_key(
        api_key_id: str,
        svc: ApiKeyService = Depends(depends_svc_api_keys),
    ) -> ApiKeyOut:
        """Retrieve an API key by its identifier.

        Args:
            api_key_id: Unique identifier of the API key.
            svc: Injected `ApiKeyService`.

        Raises:
            HTTPException: 404 if the key does not exist.
        """
        try:
            entity = await svc.get_by_id(api_key_id)
        except KeyNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found") from exc

        return _to_out(entity)

    @router.patch(
        "/{api_key_id}",
        response_model=ApiKeyOut,
        status_code=status.HTTP_200_OK,
        summary="Update an API key",
    )
    async def update_api_key(
        api_key_id: str,
        payload: ApiKeyUpdateIn,
        svc: ApiKeyService = Depends(depends_svc_api_keys),
    ) -> ApiKeyOut:
        """Partially update an API key.

        Args:
            api_key_id: Unique identifier of the API key to update.
            payload: Fields to update.
            svc: Injected `ApiKeyService`.

        Raises:
            HTTPException: 404 if the key does not exist.
        """
        try:
            current = await svc.get_by_id(api_key_id)
        except KeyNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found") from exc

        current.name = payload.name or current.name
        current.description = payload.description or current.description
        current.is_active = payload.is_active if payload.is_active is not None else current.is_active
        try:
            updated = await svc.update(current)
        except KeyNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found") from exc
        return _to_out(updated)

    @router.delete(
        "/{api_key_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Delete an API key",
    )
    async def delete_api_key(
        api_key_id: str,
        svc: ApiKeyService = Depends(depends_svc_api_keys),
    ) -> DeletedResponse:
        """Delete an API key by ID.

        Args:
            api_key_id: Unique identifier of the API key to delete.
            svc: Injected `ApiKeyService`.

        Raises:
            HTTPException: 404 if the key does not exist.
        """
        try:
            await svc.delete_by_id(api_key_id)
        except KeyNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found") from exc

        return DeletedResponse()

    @router.post("/{api_key_id}/activate", response_model=ApiKeyOut)
    async def activate_api_key(
        api_key_id: str,
        svc: ApiKeyService = Depends(depends_svc_api_keys),
    ) -> ApiKeyOut:
        """Activate an API key by ID.

        Args:
            api_key_id: Unique identifier of the API key to activate.
            svc: Injected `ApiKeyService`.

        Raises:
            HTTPException: 404 if the key does not exist.
        """
        try:
            entity = await svc.get_by_id(api_key_id)
        except KeyNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found") from exc

        if entity.is_active:
            return _to_out(entity)  # Already active

        entity.is_active = True
        updated = await svc.update(entity)
        return _to_out(updated)

    @router.post("/{api_key_id}/deactivate", response_model=ApiKeyOut)
    async def deactivate_api_key(
        api_key_id: str,
        svc: ApiKeyService = Depends(depends_svc_api_keys),
    ) -> ApiKeyOut:
        """Deactivate an API key by ID.

        Args:
            api_key_id: Unique identifier of the API key to deactivate.
            svc: Injected `ApiKeyService`.

        Raises:
            HTTPException: 404 if the key does not exist.
        """
        try:
            entity = await svc.get_by_id(api_key_id)
        except KeyNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found") from exc

        if not entity.is_active:
            return _to_out(entity)  # Already inactive

        entity.is_active = False
        updated = await svc.update(entity)
        return _to_out(updated)

    # @router.post("/{api_key_id}/rotate", response_model=ApiKeyCreatedOut)
    # async def rotate_api_key(api_key_id: str, svc: ApiKeyService = Depends(get_service)) -> ApiKeyCreatedOut:
    #     ...

    return router


@deprecated(
    "`create_api_key_security` is deprecated and will be removed in a future release. Use `create_depends_api_key` instead."
)
def create_api_key_security(
    async_session_maker: async_sessionmaker[AsyncSession],
    hasher: Optional[ApiKeyHasher] = None,
    header_name: str = "X-API-Key",
    scheme_name: str = "API Key",
    auto_error: bool = True,
) -> Callable[[str], Awaitable[ApiKey]]:
    """Create a FastAPI security dependency that verifies API keys.

    Args:
        async_session_maker: SQLAlchemy async session factory.
        hasher: Optional hasher instance. Defaults to `Argon2ApiKeyHasher`.
        header_name: HTTP header to read the API key from.
        scheme_name: OpenAPI scheme name advertised in docs.
        auto_error: Forward to :class:`fastapi.security.APIKeyHeader`.

    Returns:
        A dependency callable that yields a verified :class:`ApiKey` entity or
        raises an :class:`fastapi.HTTPException` when verification fails.
    """
    hasher = hasher or Argon2ApiKeyHasher()
    api_key_header = APIKeyHeader(
        name=header_name,
        scheme_name=scheme_name,
        auto_error=auto_error,
    )

    async def dependency(api_key: str = Security(api_key_header)) -> ApiKey:
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key missing",
                headers={"WWW-Authenticate": scheme_name},
            )

        async with async_session_maker() as async_session:
            async with async_session.begin():
                repo = SqlAlchemyApiKeyRepository(async_session)
                svc = ApiKeyService(repo=repo, hasher=hasher)

                try:
                    return await svc.verify_key(api_key)
                except KeyNotProvided as exc:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="API key missing",
                        headers={"WWW-Authenticate": scheme_name},
                    ) from exc
                except (InvalidKey, KeyNotFound) as exc:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="API key invalid",
                        headers={"WWW-Authenticate": scheme_name},
                    ) from exc
                except KeyInactive as exc:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="API key inactive",
                    ) from exc
                except KeyExpired as exc:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="API key expired",
                    ) from exc

    return dependency


async def _handle_verify_key(
    svc: AbstractApiKeyService[D],
    api_key: str,
) -> D:
    """Async context manager to handle key verification errors."""
    try:
        return await svc.verify_key(api_key)
    except KeyNotProvided as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key missing",
        ) from exc
    except (InvalidKey, KeyNotFound) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key invalid",
        ) from exc
    except KeyInactive as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key inactive",
        ) from exc
    except KeyExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key expired",
        ) from exc


def create_depends_api_key(
    depends_svc_api_keys: Callable[[...], Awaitable[AbstractApiKeyService[D]]],
    header_scheme: Optional[APIKeyHeader] = None,
) -> Callable[[str], Awaitable[D]]:
    """Create a FastAPI security dependency that verifies API keys.

    Args:
        header_scheme: Pre-configured `APIKeyHeader` instance.
        depends_svc_api_keys: Dependency callable that provides an `ApiKeyService`.

    Returns:
        A dependency callable that yields a verified :class:`ApiKey` entity or
        raises an :class:`fastapi.HTTPException` when verification fails.
    """
    header_scheme = header_scheme or APIKeyHeader(
        name="X-API-Key",
        scheme_name="API Key",
        auto_error=False,
    )

    async def _valid_api_key(
        api_key: str = Security(header_scheme),
        svc: AbstractApiKeyService[D] = Depends(depends_svc_api_keys),
    ) -> D:
        # Faster check for missing key (avoid prepare transaction etc)
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key missing",
                headers={"WWW-Authenticate": header_scheme.scheme_name},
            )

        return await _handle_verify_key(svc, api_key)

    return _valid_api_key
