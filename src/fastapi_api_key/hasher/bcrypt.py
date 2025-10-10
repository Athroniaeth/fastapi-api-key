from typing import Optional

try:
    import bcrypt  # noqa: F401
except ModuleNotFoundError as e:
    raise ImportError("SQLAlchemy backend requires 'bcrypt'. Install it with: uv add fastapi_api_key[bcrypt]") from e
import bcrypt

from fastapi_api_key.hasher.base import BaseApiKeyHasher


class BcryptApiKeyHasher(BaseApiKeyHasher):
    """Bcrypt-based API key hasher and verifier with pepper."""

    _pepper: str
    _rounds: int

    def __init__(
        self,
        pepper: Optional[str] = None,
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
