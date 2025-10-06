import warnings
from abc import ABC, abstractmethod
from typing import Protocol

DEFAULT_PEPPER = "super-secret-pepper"


class ApiKeyHasher(Protocol):
    """Protocol for API key hashing and verification."""

    _pepper: str

    def hash(self, api_key: str) -> str:
        """Hash an API key into a storable string representation."""
        ...

    def verify(self, stored_hash: str, supplied_key: str) -> bool:
        """Verify the supplied API key against the stored hash."""
        ...


class BaseApiKeyHasher(ApiKeyHasher, ABC):
    """Base class for API key hashing and verification.

    Notes:
        Implementations should use a pepper for added security. Ensure that
        pepper is kept secret and not hard-coded in production code.

    Attributes:
        _pepper (str): A secret string added to the API key before hashing.
    """

    _pepper: str

    def __init__(self, pepper: str = DEFAULT_PEPPER) -> None:
        if pepper == DEFAULT_PEPPER:
            warnings.warn(
                "Using default pepper is insecure. Please provide a strong pepper.",
                UserWarning,
            )
        self._pepper = pepper

    @abstractmethod
    def hash(self, api_key: str) -> str:
        """Hash an API key into a storable string representation."""
        ...

    @abstractmethod
    def verify(self, stored_hash: str, supplied_key: str) -> bool:
        """Verify the supplied API key against the stored hash."""
        ...
