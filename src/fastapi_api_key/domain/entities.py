from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, runtime_checkable, Protocol

from fastapi_api_key.domain.errors import ApiKeyDisabledError, ApiKeyExpiredError
from fastapi_api_key.utils import uuid_factory, datetime_factory


@runtime_checkable
class ApiKeyEntity(Protocol):
    """Protocol for an API key entity."""

    id_: str
    name: Optional[str]
    description: Optional[str]
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime
    last_used_at: Optional[datetime]
    key_prefix: str
    key_hash: str


@dataclass
class ApiKey(ApiKeyEntity):
    """Domain entity representing an API key."""

    id_: str = field(default_factory=uuid_factory)
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime_factory)
    last_used_at: Optional[datetime] = None
    key_prefix: str = field(default="")
    key_hash: str = field(default="")

    def disable(self) -> None:
        """Disable the API key."""
        self.is_active = False

    def enable(self) -> None:
        """Enable the API key."""
        self.is_active = True

    def touch(self) -> None:
        """Mark the key as used now."""
        self.last_used_at = datetime.now(timezone.utc)

    def ensure_can_authenticate(self) -> None:
        """Raise domain errors if this key cannot be used for authentication."""
        if not self.is_active:
            raise ApiKeyDisabledError("API key is disabled.")

        if self.expires_at and self.expires_at < datetime.now(timezone.utc):
            raise ApiKeyExpiredError("API key is expired.")
