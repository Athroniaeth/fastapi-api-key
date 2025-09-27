import warnings
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, runtime_checkable, Protocol, TypeVar

from argon2 import PasswordHasher, exceptions

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
        self.is_active = False

    def enable(self) -> None:
        self.is_active = True

    def touch(self) -> None:
        self.last_used_at = datetime_factory()

    def ensure_can_authenticate(self) -> None:
        if not self.is_active:
            raise ApiKeyDisabledError("API key is disabled.")

        if self.expires_at and self.expires_at < datetime_factory():
            raise ApiKeyExpiredError("API key is expired.")


class ApiKeyHasher(Protocol):
    """Protocol for API key hashing and verification.

    Notes:
        Implementations should use a pepper for added security. Ensure that
        pepper is kept secret and not hard-coded in production code.

    Attributes:
        pepper (str): A secret string added to the API key before hashing.
    """

    pepper: str

    def hash(self, api_key: str) -> str:
        """Hash an API key into a storable string representation."""
        ...

    def verify(self, stored_hash: str, supplied_key: str) -> bool:
        """Verify the supplied API key against the stored hash."""
        ...


class Argon2ApiKeyHasher(ApiKeyHasher):
    """Argon2-based API key hasher and verifier with pepper."""

    pepper: str
    _ph: PasswordHasher

    def __init__(
        self,
        pepper: str = "super-secret-pepper",
        password_hasher: Optional[PasswordHasher] = None,
    ) -> None:
        if pepper == "super-secret-pepper":
            warnings.warn(
                "Using default pepper is insecure. Please provide a strong pepper.",
                UserWarning,
            )

        # Parameters by default are secure and recommended by Argon2 authors.
        # See https://argon2-cffi.readthedocs.io/en/stable/api.html
        self._ph = password_hasher or PasswordHasher()
        self._pepper = pepper

    def _apply_pepper(self, api_key: str) -> str:
        return f"{api_key}{self._pepper}"

    def hash(self, api_key: str) -> str:
        return self._ph.hash(self._apply_pepper(api_key))

    def verify(self, stored_hash: str, supplied_key: str) -> bool:
        try:
            return self._ph.verify(
                stored_hash,
                self._apply_pepper(supplied_key),
            )
        except (exceptions.VerifyMismatchError, exceptions.VerificationError):
            return False
