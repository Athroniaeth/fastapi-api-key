from dataclasses import field, dataclass
from datetime import datetime, timezone
from typing import Optional, List, Any

from fastapi_api_key.domain.base import ApiKeyEntity
from fastapi_api_key.domain.errors import KeyExpired, KeyInactive, InvalidScopes
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

    Important:
        Use ``ApiKeyService.create()`` to create new API keys. The service handles
        key_id generation, secret hashing, and ensures the entity is valid for storage.

    Notes:
        The full API key is not stored in the database for security reasons.
        Instead, a key_id and a hashed version of the key (key_hash) are stored.
        The full key is constructed as: {global_prefix}{separator}{key_id}{separator}{key_secret}
        where key_secret is the secret part known only to the user.

    Example::

        service = ApiKeyService(repo=repo, hasher=hasher)
        entity, api_key = await service.create(name="my-key", scopes=["read"])
        print(api_key)  # Give this to the user (shown only once)
    """

    id_: str = field(default_factory=uuid_factory)
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime_factory)
    last_used_at: Optional[datetime] = None
    key_id: str = field(default_factory=key_id_factory)
    key_hash: Optional[str] = field(default=None)
    scopes: List[str] = field(default_factory=list)
    _key_secret: Optional[str] = field(default=None, repr=False)
    _key_secret_first: Optional[str] = field(default=None, repr=False)
    _key_secret_last: Optional[str] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.created_at = _normalize_datetime(self.created_at) or datetime_factory()
        self.expires_at = _normalize_datetime(self.expires_at)
        self.last_used_at = _normalize_datetime(self.last_used_at)

    @property
    def key_secret(self) -> Optional[str]:
        """The secret part of the API key, only available at creation time.

        Warning:
            This property clears the secret after first access for security.
            The secret will only be returned once.
        """
        key_secret = self._key_secret
        self._key_secret = None  # Clear after first access
        return key_secret

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

    @staticmethod
    def full_key_secret(
        global_prefix: str,
        key_id: str,
        key_secret: str,
        separator: str,
    ) -> str:
        """Construct the full API key string to be given to the user."""
        return f"{global_prefix}{separator}{key_id}{separator}{key_secret}"

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

    def ensure_valid_scopes(self, required_scopes: List[str]) -> None:
        if required_scopes:
            missing_scopes = [scope for scope in required_scopes if scope not in self.scopes]
            missing_scopes_str = ", ".join(missing_scopes)
            if missing_scopes:
                raise InvalidScopes(f"API key is missing required scopes: {missing_scopes_str}")


def default_api_key_factory(
    key_id: str,
    key_hash: str,
    key_secret: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    is_active: bool = True,
    expires_at: Optional[datetime] = None,
    scopes: Optional[List[str]] = None,
    **kwargs: Any,
) -> ApiKey:
    """Default factory for creating ApiKey entities.

    This factory is used by ApiKeyService when no custom factory is provided.
    Extra kwargs are ignored to maintain compatibility.

    Args:
        key_id: Public identifier for the key.
        key_hash: Hashed secret (computed by the service).
        key_secret: Plain secret (will be cleared after first access).
        name: Human-friendly name.
        description: Description of the key's purpose.
        is_active: Whether the key is active.
        expires_at: Expiration datetime.
        scopes: List of scopes/permissions.
        **kwargs: Ignored (for forward compatibility).

    Returns:
        A new ApiKey instance.
    """
    return ApiKey(
        key_id=key_id,
        key_hash=key_hash,
        _key_secret=key_secret,
        name=name,
        description=description,
        is_active=is_active,
        expires_at=expires_at,
        scopes=scopes or [],
    )
