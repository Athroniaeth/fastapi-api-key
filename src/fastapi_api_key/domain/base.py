from datetime import datetime
from typing import Optional, runtime_checkable, Protocol, List


@runtime_checkable
class ApiKeyEntity(Protocol):
    """Protocol defining the contract for an API key entity.

    This protocol defines only the required attributes and method signatures.
    For the default implementation, see :class:`ApiKey` in ``entities.py``.

    Attributes:
        id_ (str): Unique identifier for the API key.
        name (Optional[str]): Optional name for the API key.
        description (Optional[str]): Optional description for the API key.
        is_active (bool): Indicates if the API key is active.
        expires_at (Optional[datetime]): Optional expiration datetime for the API key.
        created_at (datetime): Datetime when the API key was created.
        last_used_at (Optional[datetime]): Optional datetime when the API key was last used.
        scopes (List[str]): List of scopes/permissions associated with the API key.
        key_id (str): Public identifier part of the API key.
        key_hash (str): Hashed secret part of the API key. This is set by the service
            during creation and is required for authentication.
    """

    # Required attributes
    id_: str
    name: Optional[str]
    description: Optional[str]
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime
    last_used_at: Optional[datetime]
    scopes: List[str]
    key_id: str
    _key_hash: Optional[str]

    # Required properties
    @property
    def key_hash(self) -> str:
        """The hashed part of the API key used for verification.

        Raises:
            KeyHashNotSet: If the key hash is not set.
        """
        ...

    @property
    def key_secret(self) -> Optional[str]:
        """The secret part of the API key, only available at creation time.

        Warning:
            Implementations should clear the secret after first access for security.
        """
        ...

    @property
    def key_secret_first(self) -> str:
        """First characters of the secret for display purposes."""
        ...

    @property
    def key_secret_last(self) -> str:
        """Last characters of the secret for display purposes."""
        ...

    # Required methods
    @staticmethod
    def get_api_key(
        global_prefix: str,
        key_id: str,
        key_secret: str,
        separator: str,
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
            KeyInactive: If the key is disabled.
            KeyExpired: If the key is expired.
        """
        ...

    def ensure_valid_scopes(self, required_scopes: List[str]) -> None:
        """Raise domain error if this key does not have the required scopes.

        Raises:
            InvalidScopes: If the key does not have the required scopes.
        """
        ...

    def ensure_valid(self, scopes: List[str]) -> None:
        """Ensure the API key is valid for authentication and scopes.

        This is a convenience method that combines both `ensure_can_authenticate`
        and `ensure_valid_scopes`.

        Arguments:
            scopes (List[str]): List of required scopes to check against the key's scopes.
        Raises:
            KeyInactive: If the key is disabled.
            KeyExpired: If the key is expired.
            InvalidScopes: If the key does not have the required scopes.
        """
        ...
