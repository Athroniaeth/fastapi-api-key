from datetime import datetime
from typing import Optional, runtime_checkable, Protocol, TypeVar


@runtime_checkable
class ApiKeyEntity(Protocol):
    """Protocol for an API key entity.

    Attributes:
        id_ (str): Unique identifier for the API key.
        name (Optional[str]): Optional name for the API key.
        description (Optional[str]): Optional description for the API key.
        is_active (bool): Indicates if the API key is active.
        expires_at (Optional[datetime]): Optional expiration datetime for the API key.
        created_at (datetime): Datetime when the API key was created.
        last_used_at (Optional[datetime]): Optional datetime when the API key was last used.
        key_id (str): Public identifier part of the API key.
        key_hash (Optional[str]): Hashed secret part of the API key.
        _key_secret (str): The secret part of the API key, only available at creation time.
        _key_secret_first (str): First part of the secret for display purposes.
        _key_secret_last (str): Last part of the secret for display purposes.
    """

    id_: str
    name: Optional[str]
    description: Optional[str]
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime
    last_used_at: Optional[datetime]
    key_id: str
    key_hash: Optional[str]
    _key_secret: Optional[str]
    _key_secret_first: Optional[str]
    _key_secret_last: Optional[str]

    @property
    def key_secret(self) -> Optional[str]:
        """The secret part of the API key, only available at creation time."""
        key_secret = self._key_secret
        self._key_secret = None  # Clear after first access
        return key_secret

    @property
    def key_secret_first(self) -> str:
        """First part of the secret for display purposes/give the user a clue as to which key we are talking about."""
        ...

    @property
    def key_secret_last(self) -> str:
        """Last part of the secret for display purposes/give the user a clue as to which key we are talking about."""
        ...

    def full_key_secret(
        self,
        global_prefix: str,
        separator: str,
        key_secret: str,
    ) -> str:
        """Construct the full API key string to be given to the user."""
        ...

    def disable(self) -> None:
        """Disable the API key so it cannot be used for authentication."""
        ...

    def enable(self) -> None:
        """Enable the API key so it can be used for authentication."""
        ...

    def touch(self) -> None:
        """Mark the key as used now. Trigger for each ensured authentication."""
        ...

    def ensure_can_authenticate(self) -> None:
        """Raise domain errors if this key cannot be used for authentication.

        Raises:
            ApiKeyDisabledError: If the key is disabled.
            ApiKeyExpiredError: If the key is expired.
        """
        ...


D = TypeVar("D", bound=ApiKeyEntity)
"""Domain entity type variable bound to any ApiKeyEntity subclass."""
