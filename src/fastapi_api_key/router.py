try:
    import fastapi  # noqa: F401
    import sqlalchemy  # noqa: F401
except ModuleNotFoundError as e:
    raise ImportError(
        "FastAPI and SQLAlchemy backend requires 'fastapi' and 'sqlalchemy'. "
        "Install it with: uv add fastapi_api_key[fastapi]"
    ) from e

from datetime import datetime
from typing import Annotated, List, Optional, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_api_key import ApiKeyService
from fastapi_api_key.domain.entities import Argon2ApiKeyHasher, ApiKey
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository


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
        api_key: The *plaintext* API key value (only returned once!). Store it
            securely client-side; it cannot be retrieved again.
        entity: Public representation of the stored entity.
    """

    api_key: str
    entity: ApiKeyOut


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
    async_session_maker: async_sessionmaker[AsyncSession],
    pepper: str,
    prefix: str = "/api-keys",
    tag: str = "API Keys",
) -> APIRouter:
    """Create and configure the API Keys router.

    Args:
        async_session_maker: SQLAlchemy async session factory.
        pepper: Secret pepper used by the Argon2 hasher. Use a strong, unique
            value from configuration or environment.
        prefix: Route prefix to mount the router under.
        tag: Tag label for OpenAPI grouping.

    Returns:
        Configured `APIRouter` ready to be included into a FastAPI app.
    """

    router = APIRouter(prefix=prefix, tags=[tag])
    hasher = Argon2ApiKeyHasher(pepper=pepper)

    async def get_db() -> AsyncIterator[AsyncSession]:
        """Provide a transactional scope around a series of operations."""
        async with async_session_maker() as session:
            async with session.begin():
                yield session

    async def get_service(
        async_session: AsyncSession = Depends(get_db),
    ) -> ApiKeyService:
        """Provide an `ApiKeyService` instance, wired with SQLAlchemy and Argon2."""
        repo = SqlAlchemyApiKeyRepository(async_session)
        return ApiKeyService(repo=repo, hasher=hasher)

    @router.post(
        "",
        response_model=ApiKeyCreatedOut,
        status_code=status.HTTP_201_CREATED,
        summary="Create a new API key",
    )
    async def create_api_key(
        payload: ApiKeyCreateIn,
        svc: ApiKeyService = Depends(get_service),
    ) -> ApiKeyCreatedOut:
        """Create an API key and return the plaintext secret *once*.

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
        "",
        response_model=List[ApiKeyOut],
        status_code=status.HTTP_200_OK,
        summary="List API keys",
    )
    async def list_api_keys(
        svc: ApiKeyService = Depends(get_service),
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
        svc: ApiKeyService = Depends(get_service),
    ) -> ApiKeyOut:
        """Retrieve an API key by its identifier.

        Args:
            api_key_id: Unique identifier of the API key.
            svc: Injected `ApiKeyService`.

        Raises:
            HTTPException: 404 if the key does not exist.
        """
        entity = await svc.get_by_id(api_key_id)

        if entity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="API key not found"
            )

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
        svc: ApiKeyService = Depends(get_service),
    ) -> ApiKeyOut:
        """Partially update an API key.

        Args:
            api_key_id: Unique identifier of the API key to update.
            payload: Fields to update.
            svc: Injected `ApiKeyService`.

        Raises:
            HTTPException: 404 if the key does not exist.
        """

        current = await svc.get_by_id(api_key_id)  # type: ignore[attr-defined]

        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="API key not found"
            )

        current.name = payload.name or current.name
        current.description = payload.description or current.description
        current.is_active = (
            payload.is_active if payload.is_active is not None else current.is_active
        )

        updated = await svc.update(current)
        return _to_out(updated)

    @router.delete(
        "/{api_key_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Delete an API key",
    )
    async def delete_api_key(
        api_key_id: str,
        svc: ApiKeyService = Depends(get_service),
    ):
        """Delete an API key by ID.

        Args:
            api_key_id: Unique identifier of the API key to delete.
            svc: Injected `ApiKeyService`.

        Raises:
            HTTPException: 404 if the key does not exist.
        """
        result = await svc.delete_by_id(api_key_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="API key not found"
            )

        return {"status": "deleted"}

    # Optional: activation helpers (commented by default)
    # Uncomment if your `ApiKeyService` exposes these methods.
    #
    # @router.post("/{api_key_id}/activate", response_model=ApiKeyOut)
    # async def activate_api_key(api_key_id: str, svc: ApiKeyService = Depends(get_service)) -> ApiKeyOut:
    #     entity = await svc.activate(api_key_id)
    #     return _to_out(entity)
    #
    # @router.post("/{api_key_id}/deactivate", response_model=ApiKeyOut)
    # async def deactivate_api_key(api_key_id: str, svc: ApiKeyService = Depends(get_service)) -> ApiKeyOut:
    #     entity = await svc.deactivate(api_key_id)
    #     return _to_out(entity)
    #
    # @router.post("/{api_key_id}/rotate", response_model=ApiKeyCreatedOut)
    # async def rotate_api_key(api_key_id: str, svc: ApiKeyService = Depends(get_service)) -> ApiKeyCreatedOut:
    #     entity, api_key = await svc.rotate(api_key_id)
    #     return ApiKeyCreatedOut(api_key=api_key, entity=_to_out(entity))

    return router
