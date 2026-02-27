import hashlib
import hmac
from typing import Optional

from fastapi_api_key.hasher.base import BaseApiKeyHasher


class HmacSha256ApiKeyHasher(BaseApiKeyHasher):
    """HMAC-SHA256-based API key hasher and verifier.

    Uses the pepper as the HMAC secret key and SHA-256 as the digest algorithm.
    Verification uses :func:`hmac.compare_digest` for constant-time comparison
    to prevent timing-based side-channel attacks.

    This hasher is appropriate for **high-entropy API keys** (128+ bits of
    randomness) in high-throughput environments where Argon2 or bcrypt would
    introduce unacceptable latency.  For secrets with lower or variable entropy,
    prefer :class:`~fastapi_api_key.hasher.argon2.Argon2ApiKeyHasher` instead,
    as its memory-hard design resists brute-force even on weak inputs.

    Security properties:

    - The pepper acts as an HMAC secret key; an attacker who obtains the
      stored hashes but not the pepper cannot mount a pre-computation attack.
    - :func:`hmac.compare_digest` ensures the comparison runs in constant time,
      preventing oracle attacks based on response latency.
    - No external dependencies — uses Python's :mod:`hmac` and
      :mod:`hashlib` standard library modules only.

    Example::

        hasher = HmacSha256ApiKeyHasher(pepper="strong-secret-pepper")
        key_hash = hasher.hash("my-api-key-secret")
        assert hasher.verify(key_hash, "my-api-key-secret") is True
        assert hasher.verify(key_hash, "wrong-secret") is False
    """

    def __init__(self, pepper: Optional[str] = None) -> None:
        super().__init__(pepper=pepper)

    def hash(self, key_secret: str) -> str:
        """Hash an API key secret using HMAC-SHA256.

        Args:
            key_secret: The plain API key secret to hash.

        Returns:
            A hex-encoded HMAC-SHA256 digest of ``key_secret`` keyed with
            the pepper.
        """
        return hmac.new(
            self._pepper.encode("utf-8"),
            key_secret.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify(self, key_hash: str, key_secret: str) -> bool:
        """Verify an API key secret against a stored HMAC-SHA256 hash.

        Uses :func:`hmac.compare_digest` for constant-time comparison.

        Args:
            key_hash: The stored hex-encoded HMAC-SHA256 hash.
            key_secret: The plain API key secret to verify.

        Returns:
            ``True`` if ``key_secret`` matches ``key_hash``, ``False`` otherwise.
        """
        expected = self.hash(key_secret)
        return hmac.compare_digest(expected, key_hash)
