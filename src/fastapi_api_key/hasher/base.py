import warnings
from abc import ABC, abstractmethod
from typing import Protocol, Optional

import base64
import os

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

    def __init__(self, pepper: Optional[str] = None) -> None:
        pepper = pepper or DEFAULT_PEPPER
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


def _generate_salt() -> str:
    """Generate a mock salt string encoded in base64.

    Returns:
        str: A random base64-encoded salt string.
    """
    return base64.b64encode(os.urandom(6)).decode("utf-8")


class MockApiKeyHasher(BaseApiKeyHasher):
    """Mock API key hasher for testing purposes.

    This implementation does not perform any real hashing. It only simulates
    the behavior of a hasher by concatenating the API key, a random salt, and
    a pepper. It should only be used for testing or development purposes.

    Attributes:
        _pepper (str): Secret string added to the API key before mock hashing.
    """

    _pepper: str

    def __init__(self, pepper: Optional[str] = None) -> None:
        """Initialize the fake hasher with an optional pepper.

        Args:
            pepper (Optional[str]): Optional secret pepper. If not provided,
                a default insecure pepper is used (with a warning).
        """
        super().__init__(pepper=pepper)

    def _apply_pepper(self, api_key: str) -> str:
        """Concatenate the API key with the pepper.

        Args:
            api_key (str): The API key to process.

        Returns:
            str: The API key with the pepper appended.
        """
        return f"{api_key}{self._pepper}"

    def hash(self, api_key: str) -> str:
        """Generate a mock hash of the API key.

        This function simulates hashing by concatenating a random salt,
        the API key, and the pepper. No cryptographic operation is performed.

        Args:
            api_key (str): The plain API key to "hash".

        Returns:
            str: A string formatted as "<salt>$<api_key_with_pepper>".
        """
        salt = _generate_salt()
        return f"{salt}${self._apply_pepper(api_key)}"

    def verify(self, stored_hash: str, supplied_key: str) -> bool:
        """Verify if the supplied API key matches the stored mock hash.

        The method extracts the salt and the stored value, then rebuilds
        the expected mock hash format and compares it directly.

        Args:
            stored_hash (str): The stored mock hash string in "<salt>$<value>" format.
            supplied_key (str): The API key to verify.

        Returns:
            bool: True if the key matches the stored mock hash, False otherwise.
        """
        try:
            salt, stored_value = stored_hash.split("$", 1)
        except ValueError:
            return False

        expected_value = self._apply_pepper(supplied_key)
        return stored_value == expected_value
