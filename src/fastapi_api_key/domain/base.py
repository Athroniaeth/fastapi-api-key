from datetime import datetime
from typing import Optional, runtime_checkable, Protocol, TypeVar, List, Any


@runtime_checkable
class ApiKeyEntity(Protocol):
    """Protocol defining the contract for an API key entity.

    This protocol defines only the required attributes and method signatures.
    Implementations must provide all attributes and methods.

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

    Note:
        Entities should be created through ApiKeyService.create() which ensures
        all required fields (key_id, key_hash) are properly set. Direct instantiation
        is allowed for testing and advanced use cases.

    Example:
        To create a custom entity, implement all required attributes and methods::

            @dataclass
            class CustomApiKey:
                id_: str
                name: Optional[str] = None
                # ... all other required attributes ...

                @property
                def key_secret(self) -> Optional[str]:
                    # Custom implementation
                    ...

                def disable(self) -> None:
                    self.is_active = False

                # ... all other required methods ...
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
    key_hash: Optional[str]

    # Required properties
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
    def full_key_secret(
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


D = TypeVar("D", bound=ApiKeyEntity)
"""Domain entity type variable bound to any ApiKeyEntity subclass."""


class ApiKeyEntityFactory(Protocol[D]):
    """Protocol for API key entity factories.

    A factory is a callable that creates new API key entities. This allows
    developers to customize entity creation without subclassing the service.

    The factory receives all standard fields plus any extra kwargs passed
    to ``ApiKeyService.create()``.

    Example:
        Create a factory for multi-tenant API keys::

            @dataclass
            class TenantApiKey(ApiKey):
                tenant_id: str = ""
                rate_limit: int = 1000

            class TenantApiKeyFactory:
                def __init__(self, tenant_id: str, default_rate_limit: int = 1000):
                    self.tenant_id = tenant_id
                    self.default_rate_limit = default_rate_limit

                def __call__(
                    self,
                    key_id: str,
                    key_hash: str,
                    key_secret: str,
                    name: Optional[str] = None,
                    description: Optional[str] = None,
                    is_active: bool = True,
                    expires_at: Optional[datetime] = None,
                    scopes: Optional[List[str]] = None,
                    **kwargs,
                ) -> TenantApiKey:
                    return TenantApiKey(
                        key_id=key_id,
                        key_hash=key_hash,
                        _key_secret=key_secret,
                        name=name,
                        description=description,
                        is_active=is_active,
                        expires_at=expires_at,
                        scopes=scopes or [],
                        tenant_id=self.tenant_id,
                        rate_limit=kwargs.get("rate_limit", self.default_rate_limit),
                    )

            # Usage
            factory = TenantApiKeyFactory(tenant_id="tenant-123")
            service = ApiKeyService(repo=repo, entity_factory=factory)
            entity, key = await service.create(name="my-key", rate_limit=5000)
    """

    def __call__(
        self,
        key_id: str,
        key_hash: str,
        key_secret: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: bool = True,
        expires_at: Optional[datetime] = None,
        scopes: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> D:
        """Create a new API key entity.

        Args:
            key_id: Public identifier for the key.
            key_hash: Hashed secret (computed by the service).
            key_secret: Plain secret (will be cleared after first access).
            name: Human-friendly name.
            description: Description of the key's purpose.
            is_active: Whether the key is active.
            expires_at: Expiration datetime.
            scopes: List of scopes/permissions.
            **kwargs: Additional arguments for custom entity fields.

        Returns:
            A new API key entity instance.
        """
        ...
