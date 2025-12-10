import typing
from dataclasses import field, dataclass
from datetime import datetime, timezone
from typing import Optional, List

from fastapi_api_key.domain.base import ApiKeyEntity
from fastapi_api_key.domain.errors import KeyExpired, KeyInactive, InvalidScopes, KeyHashNotSet, KeySecretNotSet
from fastapi_api_key.utils import (
    uuid_factory,
    datetime_factory,
    key_id_factory,
)


@typing.overload
def _normalize_datetime(value: None) -> None: ...


@typing.overload
def _normalize_datetime(value: datetime) -> datetime: ...


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
    scopes: List[str] = field(default_factory=list)

    # Init aliases: use public names (key_hash, key_secret, etc.) at init,
    # stored internally as private attributes
    _key_hash: Optional[str] = field(default=None, metadata={"alias": "key_hash"})
    _key_secret: Optional[str] = field(default=None, repr=False, metadata={"alias": "key_secret"})
    _key_secret_first: Optional[str] = field(default=None, repr=False, metadata={"alias": "key_secret_first"})
    _key_secret_last: Optional[str] = field(default=None, repr=False, metadata={"alias": "key_secret_last"})

    def __init__(
        self,
        id_: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: bool = True,
        expires_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
        last_used_at: Optional[datetime] = None,
        key_id: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        key_hash: Optional[str] = None,
        key_secret: Optional[str] = None,
        key_secret_first: Optional[str] = None,
        key_secret_last: Optional[str] = None,
    ) -> None:
        self.id_ = id_ or uuid_factory()
        self.name = name
        self.description = description
        self.is_active = is_active
        self.expires_at = _normalize_datetime(expires_at)
        self.created_at = _normalize_datetime(created_at) or datetime_factory()
        self.last_used_at = _normalize_datetime(last_used_at)
        self.key_id = key_id or key_id_factory()
        self.scopes = scopes or []
        self._key_hash = key_hash
        self._key_secret = key_secret
        self._key_secret_first = key_secret_first
        self._key_secret_last = key_secret_last

    @property
    def key_hash(self) -> str:
        """The hashed part of the API key used for verification."""
        if self._key_hash is not None:
            return self._key_hash

        raise KeyHashNotSet("Key hash is not set")

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

        raise KeySecretNotSet("Key secret is not set")

    @property
    def key_secret_last(self) -> str:
        """Last part of the secret for display purposes/give the user a clue as to which key we are talking about."""
        if self._key_secret_last is not None:
            return self._key_secret_last

        if self._key_secret is not None:
            return self._key_secret[-4:]

        raise KeySecretNotSet("Key secret is not set")

    @staticmethod
    def get_api_key(
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

    def ensure_valid(self, scopes: List[str]) -> None:
        self.ensure_can_authenticate()
        self.ensure_valid_scopes(scopes)

    def __repr__(self):
        return (
            f"ApiKey(id_={self.id_!r}, name={self.name!r}, description={self.description!r}, "
            f"is_active={self.is_active!r}, expires_at={self.expires_at!r}, created_at={self.created_at!r}, "
            f"last_used_at={self.last_used_at!r}, key_id={self.key_id!r}, scopes={self.scopes!r}, "
            f"key_hash={'*****...' if self._key_hash else None})"
        )

    def __str__(self):
        return self.__repr__()
