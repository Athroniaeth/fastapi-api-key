import warnings


from fastapi_api_key.services.base import AbstractApiKeyService
from fastapi_api_key._types import SecurityHTTPBearer, SecurityAPIKeyHeader
from fastapi_api_key.utils import datetime_factory

try:
    import fastapi  # noqa: F401
    import sqlalchemy  # noqa: F401
except ModuleNotFoundError as e:  # pragma: no cover
    raise ImportError(
        "FastAPI and SQLAlchemy backend requires 'fastapi' and 'sqlalchemy'. "
        "Install it with: uv add fastapi_api_key[fastapi]"
    ) from e

from datetime import datetime, timedelta
from typing import Annotated, Awaitable, Callable, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from fastapi_api_key.repositories.base import ApiKeyFilter, SortableColumn
from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.domain.errors import (
    InvalidKey,
    KeyExpired,
    KeyInactive,
    KeyNotFound,
    KeyNotProvided,
    InvalidScopes,
)


class ApiKeyCreateIn(BaseModel):
    """Payload to create a new API key.

    Attributes:
        name: Human-friendly display name.
        description: Optional description to document the purpose of the key.
        is_active: Whether the key is active upon creation.
        scopes: List of scopes to assign to the key.
        expires_at: Optional expiration datetime (ISO 8601 format).
    """

    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=1024)
    is_active: bool = Field(default=True)
    scopes: List[str] = Field(default_factory=list)
    expires_at: Optional[datetime] = Field(
        default=None,
        examples=[(datetime_factory() + timedelta(days=30)).isoformat()],
        description="Expiration datetime (ISO 8601)",
    )


class ApiKeyUpdateIn(BaseModel):
    """Partial update payload for an API key.

    Attributes:
        name: New display name.
        description: New description.
        is_active: Toggle active state.
        scopes: New list of scopes.
        expires_at: New expiration datetime (ISO 8601 format).
        clear_expires: Set to true to remove expiration (takes precedence over expires_at).
    """

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=1024)
    is_active: Optional[bool] = None
    scopes: Optional[List[str]] = None
    expires_at: Optional[datetime] = Field(None, description="New expiration datetime (ISO 8601)")
    clear_expires: bool = Field(False, description="Remove expiration date")


class ApiKeyOut(BaseModel):
    """Public representation of an API key entity.

    Note:
        Timestamps are optional to avoid coupling to a particular repository
        schema. If your entity guarantees those fields, they will be populated.

    Attributes:
        id: Unique identifier of the API key.
        key_id: Public key identifier (used for lookup, visible in the API key string).
        name: Human-friendly display name.
        description: Optional description documenting the key's purpose.
        is_active: Whether the key is currently active.
        created_at: When the key was created.
        last_used_at: When the key was last used for authentication.
        expires_at: When the key expires (None means no expiration).
        scopes: List of scopes assigned to this key.
    """

    id: str
    key_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    scopes: List[str] = Field(default_factory=list)


class ApiKeyCreatedOut(BaseModel):
    """Response returned after creating a key.

    Attributes:
        api_key: The plaintext API key value (only returned once!). Store it
            securely client-side; it cannot be retrieved again.
        entity: Public representation of the stored entity.
    """

    api_key: str
    entity: ApiKeyOut


class ApiKeySearchIn(BaseModel):
    """Search criteria for filtering API keys.

    All criteria are optional. Only provided criteria are applied (AND logic).
    """

    is_active: Optional[bool] = Field(None, description="Filter by active status")
    expires_before: Optional[datetime] = Field(None, description="Keys expiring before this date")
    expires_after: Optional[datetime] = Field(None, description="Keys expiring after this date")
    created_before: Optional[datetime] = Field(None, description="Keys created before this date")
    created_after: Optional[datetime] = Field(None, description="Keys created after this date")
    last_used_before: Optional[datetime] = Field(None, description="Keys last used before this date")
    last_used_after: Optional[datetime] = Field(None, description="Keys last used after this date")
    never_used: Optional[bool] = Field(None, description="True = never used keys, False = used keys")
    scopes_contain_all: Optional[List[str]] = Field(None, description="Keys must have ALL these scopes")
    scopes_contain_any: Optional[List[str]] = Field(None, description="Keys must have at least ONE of these scopes")
    name_contains: Optional[str] = Field(None, description="Name contains this substring (case-insensitive)")
    name_exact: Optional[str] = Field(None, description="Exact name match")
    order_by: SortableColumn = Field(SortableColumn.CREATED_AT, description="Field to sort by")
    order_desc: bool = Field(True, description="Sort descending (True) or ascending (False)")

    def to_filter(self, limit: int = 100, offset: int = 0) -> ApiKeyFilter:
        """Convert to ApiKeyFilter with pagination."""
        return ApiKeyFilter(
            is_active=self.is_active,
            expires_before=self.expires_before,
            expires_after=self.expires_after,
            created_before=self.created_before,
            created_after=self.created_after,
            last_used_before=self.last_used_before,
            last_used_after=self.last_used_after,
            never_used=self.never_used,
            scopes_contain_all=self.scopes_contain_all,
            scopes_contain_any=self.scopes_contain_any,
            name_contains=self.name_contains,
            name_exact=self.name_exact,
            order_by=self.order_by,
            order_desc=self.order_desc,
            limit=limit,
            offset=offset,
        )


class ApiKeySearchOut(BaseModel):
    """Paginated search results."""

    items: List[ApiKeyOut] = Field(description="List of matching API keys")
    total: int = Field(description="Total number of matching keys (ignoring pagination)")
    limit: int = Field(description="Page size used")
    offset: int = Field(description="Offset used")


class ApiKeyVerifyIn(BaseModel):
    """Payload to verify an API key.

    Attributes:
        api_key: The full API key string to verify.
        required_scopes: Optional list of scopes the key must have.
    """

    api_key: str = Field(..., min_length=1, description="Full API key string to verify")
    required_scopes: Optional[List[str]] = Field(None, description="Scopes the key must have")


class ApiKeyCountOut(BaseModel):
    """Response for counting API keys.

    Attributes:
        total: Total number of keys matching the filter criteria.
    """

    total: int = Field(description="Total number of matching keys")


def _to_out(entity: ApiKey) -> ApiKeyOut:
    """Map an `ApiKey` entity to the public `ApiKeyOut` schema."""
    return ApiKeyOut(
        id=entity.id_,
        key_id=entity.key_id,
        name=entity.name,
        description=entity.description,
        is_active=entity.is_active,
        created_at=entity.created_at,
        last_used_at=entity.last_used_at,
        expires_at=entity.expires_at,
        scopes=entity.scopes,
    )


def create_api_keys_router(
    depends_svc_api_keys: Callable[..., Awaitable[AbstractApiKeyService]],
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
        svc: AbstractApiKeyService = Depends(depends_svc_api_keys),
    ) -> ApiKeyCreatedOut:
        """Create an API key and return the plaintext secret once.

        Args:
            payload: Creation parameters.
            svc: Injected API key service.

        Returns:
            `ApiKeyCreatedOut` with the plaintext API key and the created entity.
        """

        entity, api_key = await svc.create(
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
            scopes=payload.scopes,
            expires_at=payload.expires_at,
        )
        return ApiKeyCreatedOut(api_key=api_key, entity=_to_out(entity))

    @router.get(
        path="/",
        response_model=List[ApiKeyOut],
        status_code=status.HTTP_200_OK,
        summary="List API keys",
    )
    async def list_api_keys(
        svc: AbstractApiKeyService = Depends(depends_svc_api_keys),
        offset: Annotated[int, Query(ge=0, description="Items to skip")] = 0,
        limit: Annotated[int, Query(gt=0, le=100, description="Page size")] = 50,
    ) -> List[ApiKeyOut]:
        """List API keys with basic offset/limit pagination.

        Args:
            svc: Injected API key service.
            offset: Number of items to skip.
            limit: Max number of items to return.

        Returns:
            A page of API keys.
        """
        items = await svc.list(offset=offset, limit=limit)
        return [_to_out(e) for e in items]

    @router.post(
        path="/search",
        response_model=ApiKeySearchOut,
        status_code=status.HTTP_200_OK,
        summary="Search API keys with filters",
    )
    async def search_api_keys(
        payload: ApiKeySearchIn,
        svc: AbstractApiKeyService = Depends(depends_svc_api_keys),
        offset: Annotated[int, Query(ge=0, description="Items to skip")] = 0,
        limit: Annotated[int, Query(gt=0, le=100, description="Page size")] = 50,
    ) -> ApiKeySearchOut:
        """Search API keys with advanced filtering criteria.

        Args:
            payload: Search criteria (all optional, AND logic).
            svc: Injected API key service.
            offset: Number of items to skip.
            limit: Max number of items to return.

        Returns:
            Paginated search results with total count.
        """
        filter = payload.to_filter(limit=limit, offset=offset)
        items = await svc.find(filter)
        total = await svc.count(filter)

        return ApiKeySearchOut(
            items=[_to_out(e) for e in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    @router.get(
        "/{api_key_id}",
        response_model=ApiKeyOut,
        status_code=status.HTTP_200_OK,
        summary="Get an API key by ID",
    )
    async def get_api_key(
        api_key_id: str,
        svc: AbstractApiKeyService = Depends(depends_svc_api_keys),
    ) -> ApiKeyOut:
        """Retrieve an API key by its identifier.

        Args:
            api_key_id: Unique identifier of the API key.
            svc: Injected API key service.

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
        svc: AbstractApiKeyService = Depends(depends_svc_api_keys),
    ) -> ApiKeyOut:
        """Partially update an API key.

        Args:
            api_key_id: Unique identifier of the API key to update.
            payload: Fields to update.
            svc: Injected API key service.

        Raises:
            HTTPException: 404 if the key does not exist.
        """
        try:
            current = await svc.get_by_id(api_key_id)
        except KeyNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found") from exc

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
        svc: AbstractApiKeyService = Depends(depends_svc_api_keys),
    ) -> None:
        """Delete an API key by ID.

        Args:
            api_key_id: Unique identifier of the API key to delete.
            svc: Injected API key service.

        Raises:
            HTTPException: 404 if the key does not exist.
        """
        try:
            await svc.delete_by_id(api_key_id)
        except KeyNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found") from exc

    @router.post("/{api_key_id}/activate", response_model=ApiKeyOut)
    async def activate_api_key(
        api_key_id: str,
        svc: AbstractApiKeyService = Depends(depends_svc_api_keys),
    ) -> ApiKeyOut:
        """Activate an API key by ID.

        Args:
            api_key_id: Unique identifier of the API key to activate.
            svc: Injected API key service.

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
        svc: AbstractApiKeyService = Depends(depends_svc_api_keys),
    ) -> ApiKeyOut:
        """Deactivate an API key by ID.

        Args:
            api_key_id: Unique identifier of the API key to deactivate.
            svc: Injected API key service.

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

    @router.post(
        path="/verify",
        response_model=ApiKeyOut,
        status_code=status.HTTP_200_OK,
        summary="Verify an API key",
    )
    async def verify_api_key(
        payload: ApiKeyVerifyIn,
        svc: AbstractApiKeyService = Depends(depends_svc_api_keys),
    ) -> ApiKeyOut:
        """Verify an API key and return its details if valid.

        This endpoint validates the API key format, checks if it exists,
        verifies it's active, not expired, and optionally checks required scopes.

        Args:
            payload: Verification parameters including the API key and optional scopes.
            svc: Injected API key service.

        Returns:
            The API key entity if verification succeeds.

        Raises:
            HTTPException: 401 if the key is invalid or not found.
            HTTPException: 403 if the key is inactive, expired, or missing required scopes.
        """
        try:
            entity = await svc.verify_key(
                api_key=payload.api_key,
                required_scopes=payload.required_scopes,
            )
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
        except InvalidScopes as exc:
            required_scopes_str = ", ".join([f"'{scope}'" for scope in (payload.required_scopes or [])])
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key missing required scopes {required_scopes_str}",
            ) from exc

        return _to_out(entity)

    @router.post(
        path="/count",
        response_model=ApiKeyCountOut,
        status_code=status.HTTP_200_OK,
        summary="Count API keys with filters",
    )
    async def count_api_keys(
        payload: ApiKeySearchIn,
        svc: AbstractApiKeyService = Depends(depends_svc_api_keys),
    ) -> ApiKeyCountOut:
        """Count API keys matching the given filter criteria.

        Uses the same filter criteria as the search endpoint but only returns
        the count without fetching the actual entities.

        Args:
            payload: Filter criteria (all optional, AND logic).
            svc: Injected API key service.

        Returns:
            Total count of matching API keys.
        """
        filter_ = payload.to_filter(limit=0, offset=0)
        total = await svc.count(filter_)
        return ApiKeyCountOut(total=total)

    return router


async def _handle_verify_key(
    svc: AbstractApiKeyService,
    api_key: str,
    scheme_name: str = "API Key",
    required_scopes: Optional[List[str]] = None,
) -> ApiKey:
    """Async context manager to handle key verification errors."""
    try:
        return await svc.verify_key(api_key, required_scopes=required_scopes)
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
            headers={"WWW-Authenticate": scheme_name},
        ) from exc
    except KeyExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key expired",
            headers={"WWW-Authenticate": scheme_name},
        ) from exc
    except InvalidScopes as exc:
        assert required_scopes is not None, "required_scopes should not be None here"  # nosec: B101  # Just for typing tools
        required_scopes_str = ", ".join([f"'{scope}'" for scope in required_scopes])

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API key missing required scopes {required_scopes_str}",
            headers={"WWW-Authenticate": scheme_name},
        ) from exc


def create_depends_api_key(
    depends_svc_api_keys: Callable[..., Awaitable[AbstractApiKeyService]],
    security: Optional[Union[HTTPBearer, APIKeyHeader]] = None,
    required_scopes: Optional[List[str]] = None,
) -> Union[SecurityHTTPBearer, SecurityAPIKeyHeader]:
    """Create a FastAPI security dependency that verifies API keys.

    Args:
        depends_svc_api_keys: Dependency callable that provides an `ApiKeyService`.
        security: Optional FastAPI security scheme (e.g., `APIKeyHeader` or `HTTPBearer`). defaults to `HTTPBearer`.
        required_scopes: Optional list of scopes required for the API key.

    Returns:
        A dependency callable that yields a verified :class:`ApiKey` entity or
        raises an :class:`fastapi.HTTPException` when verification fails.
    """
    security = security or HTTPBearer(
        auto_error=False,
        scheme_name="API Key",
        description="API key required in the `Authorization` header as a Bearer token.",
    )

    if security.auto_error:
        raise ValueError("The provided security scheme must have auto_error=False")

    if isinstance(security, APIKeyHeader):
        warnings.warn(
            "Please note that the use of ApiKeyHeader is no longer standard "
            "according to RFC 6750: https://datatracker.ietf.org/doc/html/rfc6750"
        )

        async def _valid_api_key(
            api_key: str = Security(security),
            svc: AbstractApiKeyService = Depends(depends_svc_api_keys),
        ) -> ApiKey:
            # Faster check for missing key (avoid prepare transaction etc)
            if not api_key:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key missing",
                    headers={"WWW-Authenticate": security.scheme_name},
                )

            return await _handle_verify_key(
                svc=svc,
                api_key=api_key,
                scheme_name=security.scheme_name,
                required_scopes=required_scopes,
            )

    elif isinstance(security, HTTPBearer):

        async def _valid_api_key(
            api_key: HTTPAuthorizationCredentials = Security(security),
            svc: AbstractApiKeyService = Depends(depends_svc_api_keys),
        ) -> ApiKey:
            # Faster check for missing key (avoid prepare transaction etc)
            if not api_key:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key missing",
                    headers={"WWW-Authenticate": security.scheme_name},
                )

            return await _handle_verify_key(
                svc=svc,
                api_key=api_key.credentials,
                scheme_name=security.scheme_name,
                required_scopes=required_scopes,
            )
    else:
        raise ValueError("The provided security scheme must be either HTTPBearer or APIKeyHeader")

    return _valid_api_key
