import warnings
from abc import abstractmethod, ABC
from typing import Protocol, Optional

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

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


class BcryptApiKeyHasher(BaseApiKeyHasher):
    """Bcrypt-based API key hasher and verifier with pepper."""

    _pepper: str
    _rounds: int

    def __init__(
        self,
        pepper: str = DEFAULT_PEPPER,
        rounds: int = 12,
    ) -> None:
        if rounds < 4 or rounds > 31:
            raise ValueError("Bcrypt rounds must be between 4 and 31.")

        super().__init__(pepper=pepper)
        self._rounds = rounds

    def _apply_pepper(self, api_key: str) -> str:
        return f"{api_key}{self._pepper}"

    def hash(self, api_key: str) -> str:
        salted_key = self._apply_pepper(api_key).encode("utf-8")
        hashed = bcrypt.hashpw(salted_key[:72], bcrypt.gensalt(self._rounds))
        return hashed.decode("utf-8")

    def verify(self, stored_hash: str, supplied_key: str) -> bool:
        salted_key = self._apply_pepper(supplied_key).encode("utf-8")
        return bcrypt.checkpw(salted_key, stored_hash.encode("utf-8"))


class Argon2ApiKeyHasher(BaseApiKeyHasher):
    """Argon2-based API key hasher and verifier with pepper."""

    _pepper: str
    _ph: PasswordHasher

    def __init__(
        self,
        pepper: str = DEFAULT_PEPPER,
        password_hasher: Optional[PasswordHasher] = None,
    ) -> None:
        # Parameters by default are secure and recommended by Argon2 authors.
        # See https://argon2-cffi.readthedocs.io/en/stable/api.html
        self._ph = password_hasher or PasswordHasher()

        super().__init__(pepper=pepper)

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
        except (
            VerifyMismatchError,
            VerificationError,
            InvalidHashError,
        ):
            return False
