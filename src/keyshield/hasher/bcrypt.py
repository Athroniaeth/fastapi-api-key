import hashlib
import hmac
from typing import Optional

try:
    import bcrypt
except ModuleNotFoundError as e:
    raise ImportError("Bcrypt backend requires 'bcrypt'. Install it with: uv add keyshield[bcrypt]") from e

from keyshield.hasher.base import BaseApiKeyHasher


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

    def _apply_pepper(self, api_key: str) -> bytes:
        # HMAC-SHA256 with the pepper as key produces a fixed 32-byte digest,
        # well within bcrypt's 72-byte input limit. This avoids the silent
        # truncation that occurs when key_secret + pepper exceeds 72 bytes.
        return hmac.digest(self._pepper.encode("utf-8"), api_key.encode("utf-8"), hashlib.sha256)

    def hash(self, key_secret: str) -> str:
        hashed = bcrypt.hashpw(self._apply_pepper(key_secret), bcrypt.gensalt(self._rounds))
        return hashed.decode("utf-8")

    def verify(self, key_hash: str, key_secret: str) -> bool:
        return bcrypt.checkpw(self._apply_pepper(key_secret), key_hash.encode("utf-8"))
