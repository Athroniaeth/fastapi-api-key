from typing import Optional

try:
    import bcrypt
except ModuleNotFoundError as e:
    raise ImportError("Bcrypt backend requires 'bcrypt'. Install it with: uv add fastapi_api_key[bcrypt]") from e

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

    def hash(self, key_secret: str) -> str:
        salted_key = self._apply_pepper(key_secret).encode("utf-8")
        # Avoid exception : ValueError: password cannot be longer than 72 bytes, truncate manually if necessary (e.g. my_password[:72])
        hashed = bcrypt.hashpw(salted_key[:72], bcrypt.gensalt(self._rounds))
        return hashed.decode("utf-8")

    def verify(self, key_hash: str, key_secret: str) -> bool:
        # Ensure that verify truncates the supplied key to 72 bytes like hash()
        salted_key = self._apply_pepper(key_secret).encode("utf-8")[:72]
        return bcrypt.checkpw(salted_key, key_hash.encode("utf-8"))
