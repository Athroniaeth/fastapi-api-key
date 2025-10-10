try:
    import argon2  # noqa: F401
except ModuleNotFoundError as e:
    raise ImportError("SQLAlchemy backend requires 'argon2'. Install it with: uv add fastapi_api_key[argon2]") from e

from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from fastapi_api_key.hasher.base import BaseApiKeyHasher


class Argon2ApiKeyHasher(BaseApiKeyHasher):
    """Argon2-based API key hasher and verifier with pepper."""

    _pepper: str
    _ph: PasswordHasher

    def __init__(
        self,
        pepper: Optional[str] = None,
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
