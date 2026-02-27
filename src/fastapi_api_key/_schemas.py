"""Shared Pydantic schemas used by all framework integrations.

These models are framework-agnostic and shared between FastAPI, Litestar
and Quart integrations to avoid duplication.
"""

try:
    from pydantic import BaseModel, Field
except ModuleNotFoundError as e:  # pragma: no cover
    raise ImportError(
        "Pydantic is required for framework integrations. "
        "Install it via any supported framework extra, e.g.: "
        "uv add fastapi_api_key[fastapi] or uv add fastapi_api_key[litestar]"
    ) from e

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.repositories.base import ApiKeyFilter, SortableColumn
from fastapi_api_key.utils import datetime_factory


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
    """Map an ``ApiKey`` entity to the public ``ApiKeyOut`` schema."""
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
