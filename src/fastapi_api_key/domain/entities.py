from dataclasses import field, dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi_api_key.domain.base import ApiKeyEntity
from fastapi_api_key.domain.errors import KeyExpired, KeyInactive
from fastapi_api_key.utils import (
    uuid_factory,
    datetime_factory,
    key_id_factory,
)


def _normalize_datetime(value: Optional[datetime]) -> Optional[datetime]:
    """Ensure datetimes are timezone-aware (UTC)."""
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value


@dataclass
class ApiKey(ApiKeyEntity):
    """Domain entity representing an API key.

    Notes:
        The key hash must be computed in service, if this attribute is None,
        the entity is considered invalid for storage.

        The full API key is not stored in the database for security reasons.
        Instead, a key_id and a hashed version of the key (key_hash) are stored.
        The full key is constructed as: {global_prefix}{separator}{key_id}{separator}{key_secret}
        where key_secret is the secret part known only to the user.
    """

    id_: str = field(default_factory=uuid_factory)
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime_factory)
    last_used_at: Optional[datetime] = None
    key_id: str = field(default_factory=key_id_factory)
    key_hash: Optional[str] = None
    _key_secret: Optional[str] = field(default=None, repr=False)
    _key_secret_first: Optional[str] = field(default=None, repr=False)
    _key_secret_last: Optional[str] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.created_at = _normalize_datetime(self.created_at) or datetime_factory()
        self.expires_at = _normalize_datetime(self.expires_at)
        self.last_used_at = _normalize_datetime(self.last_used_at)

    @property
    def key_secret_first(self) -> str:
        """First part of the secret for display purposes/give the user a clue as to which key we are talking about."""
        if self._key_secret_first is not None:
            return self._key_secret_first

        if self._key_secret is not None:
            return self._key_secret[:4]

        raise ValueError("Key secret is not set")

    @property
    def key_secret_last(self) -> str:
        """Last part of the secret for display purposes/give the user a clue as to which key we are talking about."""
        if self._key_secret_last is not None:
            return self._key_secret_last

        if self._key_secret is not None:
            return self._key_secret[-4:]

        raise ValueError("Key secret is not set")

    def full_key_secret(
        self,
        global_prefix: str,
        separator: str,
        key_secret: str,
    ) -> str:
        """Construct the full API key string to be given to the user."""
        return f"{global_prefix}{separator}{self.key_id}{separator}{key_secret}"

    def disable(self) -> None:
        self.is_active = False

    def enable(self) -> None:
        self.is_active = True

    def touch(self) -> None:
        self.last_used_at = datetime_factory()

    def ensure_can_authenticate(self) -> None:
        if not self.is_active:
            raise KeyInactive("API key is disabled.")

        if self.expires_at and self.expires_at < datetime_factory():
            raise KeyExpired("API key is expired.")
