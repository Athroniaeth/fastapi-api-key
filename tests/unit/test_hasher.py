"""Unit tests for API key hashers.

Tests each hasher implementation with mocked backends:
- MockApiKeyHasher (for tests)
- Argon2ApiKeyHasher
- BcryptApiKeyHasher
- HmacSha256ApiKeyHasher

Focus: Testing OUR code (pepper application, error handling, parameter validation),
NOT the underlying crypto libraries.
"""

from unittest.mock import MagicMock, patch

import pytest

from fastapi_api_key.hasher.base import MockApiKeyHasher, DEFAULT_PEPPER
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.hasher.bcrypt import BcryptApiKeyHasher
from fastapi_api_key.hasher.hmac_sha256 import HmacSha256ApiKeyHasher


class TestMockHasher:
    """Tests for MockApiKeyHasher."""

    def test_hash_applies_pepper(self):
        """hash() applies pepper to the key."""
        hasher = MockApiKeyHasher(pepper="my-pepper")
        result = hasher.hash("api-key")

        # Format: <salt>$<key><pepper>
        assert "$api-keymy-pepper" in result

    def test_hash_includes_salt(self):
        """hash() includes a random salt."""
        hasher = MockApiKeyHasher(pepper="pepper")

        hash1 = hasher.hash("key")
        hash2 = hasher.hash("key")

        # Different salts produce different hashes
        assert hash1 != hash2

    def test_verify_correct_key(self):
        """verify() returns True for correct key."""
        hasher = MockApiKeyHasher(pepper="pepper")
        hashed = hasher.hash("my-key")

        assert hasher.verify(hashed, "my-key") is True

    def test_verify_wrong_key(self):
        """verify() returns False for wrong key."""
        hasher = MockApiKeyHasher(pepper="pepper")
        hashed = hasher.hash("correct-key")

        assert hasher.verify(hashed, "wrong-key") is False

    def test_verify_invalid_format(self):
        """verify() returns False for invalid hash format."""
        hasher = MockApiKeyHasher(pepper="pepper")

        assert hasher.verify("no-dollar-sign", "key") is False

    def test_different_pepper_fails(self):
        """Hash with one pepper cannot verify with different pepper."""
        hasher1 = MockApiKeyHasher(pepper="pepper-one")
        hasher2 = MockApiKeyHasher(pepper="pepper-two")

        hashed = hasher1.hash("my-key")

        assert hasher1.verify(hashed, "my-key") is True
        assert hasher2.verify(hashed, "my-key") is False


class TestArgon2Hasher:
    """Tests for Argon2ApiKeyHasher with mocked PasswordHasher."""

    def test_hash_applies_pepper(self):
        """hash() passes peppered key to PasswordHasher."""
        mock_ph = MagicMock()
        mock_ph.hash.return_value = "hashed-value"

        hasher = Argon2ApiKeyHasher(pepper="my-pepper", password_hasher=mock_ph)
        result = hasher.hash("api-key")

        mock_ph.hash.assert_called_once_with("api-keymy-pepper")
        assert result == "hashed-value"

    def test_verify_applies_pepper(self):
        """verify() passes peppered key to PasswordHasher.verify."""
        mock_ph = MagicMock()
        mock_ph.verify.return_value = True

        hasher = Argon2ApiKeyHasher(pepper="my-pepper", password_hasher=mock_ph)
        result = hasher.verify("stored-hash", "api-key")

        mock_ph.verify.assert_called_once_with("stored-hash", "api-keymy-pepper")
        assert result is True

    def test_verify_returns_false_on_mismatch(self):
        """verify() returns False when PasswordHasher raises VerifyMismatchError."""
        from argon2.exceptions import VerifyMismatchError

        mock_ph = MagicMock()
        mock_ph.verify.side_effect = VerifyMismatchError()

        hasher = Argon2ApiKeyHasher(pepper="pepper", password_hasher=mock_ph)
        result = hasher.verify("hash", "wrong-key")

        assert result is False

    def test_verify_returns_false_on_verification_error(self):
        """verify() returns False when PasswordHasher raises VerificationError."""
        from argon2.exceptions import VerificationError

        mock_ph = MagicMock()
        mock_ph.verify.side_effect = VerificationError()

        hasher = Argon2ApiKeyHasher(pepper="pepper", password_hasher=mock_ph)
        result = hasher.verify("hash", "key")

        assert result is False

    def test_verify_returns_false_on_invalid_hash(self):
        """verify() returns False when PasswordHasher raises InvalidHashError."""
        from argon2.exceptions import InvalidHashError

        mock_ph = MagicMock()
        mock_ph.verify.side_effect = InvalidHashError()

        hasher = Argon2ApiKeyHasher(pepper="pepper", password_hasher=mock_ph)
        result = hasher.verify("invalid-hash", "key")

        assert result is False

    def test_uses_default_password_hasher_if_not_provided(self):
        """Constructor creates default PasswordHasher if not provided."""
        from argon2 import PasswordHasher

        hasher = Argon2ApiKeyHasher(pepper="pepper")

        assert isinstance(hasher._ph, PasswordHasher)


class TestBcryptHasher:
    """Tests for BcryptApiKeyHasher with mocked bcrypt module."""

    @patch("fastapi_api_key.hasher.bcrypt.bcrypt")
    def test_hash_applies_pepper(self, mock_bcrypt):
        """hash() passes peppered key to bcrypt.hashpw."""
        mock_bcrypt.gensalt.return_value = b"$2b$04$salt"
        mock_bcrypt.hashpw.return_value = b"hashed-value"

        hasher = BcryptApiKeyHasher(pepper="my-pepper", rounds=4)
        result = hasher.hash("api-key")

        # Check pepper was applied
        call_args = mock_bcrypt.hashpw.call_args[0]
        assert call_args[0] == b"api-keymy-pepper"
        assert result == "hashed-value"

    @patch("fastapi_api_key.hasher.bcrypt.bcrypt")
    def test_hash_truncates_long_keys(self, mock_bcrypt):
        """hash() truncates keys longer than 72 bytes."""
        mock_bcrypt.gensalt.return_value = b"$2b$04$salt"
        mock_bcrypt.hashpw.return_value = b"hashed"

        hasher = BcryptApiKeyHasher(pepper="pepper", rounds=4)
        long_key = "a" * 100

        hasher.hash(long_key)

        call_args = mock_bcrypt.hashpw.call_args[0]
        assert len(call_args[0]) == 72

    @patch("fastapi_api_key.hasher.bcrypt.bcrypt")
    def test_verify_applies_pepper(self, mock_bcrypt):
        """verify() passes peppered key to bcrypt.checkpw."""
        mock_bcrypt.checkpw.return_value = True

        hasher = BcryptApiKeyHasher(pepper="my-pepper", rounds=4)
        result = hasher.verify("stored-hash", "api-key")

        call_args = mock_bcrypt.checkpw.call_args[0]
        assert call_args[0] == b"api-keymy-pepper"
        assert call_args[1] == b"stored-hash"
        assert result is True

    @patch("fastapi_api_key.hasher.bcrypt.bcrypt")
    def test_verify_truncates_long_keys(self, mock_bcrypt):
        """verify() truncates keys longer than 72 bytes."""
        mock_bcrypt.checkpw.return_value = True

        hasher = BcryptApiKeyHasher(pepper="pepper", rounds=4)
        long_key = "a" * 100

        hasher.verify("hash", long_key)

        call_args = mock_bcrypt.checkpw.call_args[0]
        assert len(call_args[0]) == 72

    def test_rounds_too_low_raises(self):
        """Rounds below 4 raises ValueError."""
        with pytest.raises(ValueError, match="between 4 and 31"):
            BcryptApiKeyHasher(pepper="pepper", rounds=3)

    def test_rounds_too_high_raises(self):
        """Rounds above 31 raises ValueError."""
        with pytest.raises(ValueError, match="between 4 and 31"):
            BcryptApiKeyHasher(pepper="pepper", rounds=32)

    def test_valid_rounds_boundary(self):
        """Valid rounds at boundaries are accepted."""
        hasher_min = BcryptApiKeyHasher(pepper="pepper", rounds=4)
        hasher_max = BcryptApiKeyHasher(pepper="pepper", rounds=31)

        assert hasher_min._rounds == 4
        assert hasher_max._rounds == 31


class TestHmacSha256Hasher:
    """Tests for HmacSha256ApiKeyHasher."""

    def test_hash_returns_hex_string(self):
        """hash() returns a 64-character hex string (SHA-256 output)."""
        hasher = HmacSha256ApiKeyHasher(pepper="test-pepper")
        result = hasher.hash("my-api-key")

        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_is_deterministic(self):
        """hash() produces the same output for the same input and pepper."""
        hasher = HmacSha256ApiKeyHasher(pepper="test-pepper")

        assert hasher.hash("my-key") == hasher.hash("my-key")

    def test_hash_differs_for_different_keys(self):
        """hash() produces different outputs for different inputs."""
        hasher = HmacSha256ApiKeyHasher(pepper="test-pepper")

        assert hasher.hash("key-one") != hasher.hash("key-two")

    def test_hash_differs_for_different_peppers(self):
        """Same key with different peppers produces different hashes."""
        hasher1 = HmacSha256ApiKeyHasher(pepper="pepper-one")
        hasher2 = HmacSha256ApiKeyHasher(pepper="pepper-two")

        assert hasher1.hash("my-key") != hasher2.hash("my-key")

    def test_verify_correct_key(self):
        """verify() returns True for correct key."""
        hasher = HmacSha256ApiKeyHasher(pepper="test-pepper")
        key_hash = hasher.hash("my-api-key")

        assert hasher.verify(key_hash, "my-api-key") is True

    def test_verify_wrong_key(self):
        """verify() returns False for wrong key."""
        hasher = HmacSha256ApiKeyHasher(pepper="test-pepper")
        key_hash = hasher.hash("correct-key")

        assert hasher.verify(key_hash, "wrong-key") is False

    def test_verify_wrong_pepper_fails(self):
        """Hash with one pepper cannot verify with different pepper."""
        hasher1 = HmacSha256ApiKeyHasher(pepper="pepper-one")
        hasher2 = HmacSha256ApiKeyHasher(pepper="pepper-two")

        key_hash = hasher1.hash("my-key")

        assert hasher1.verify(key_hash, "my-key") is True
        assert hasher2.verify(key_hash, "my-key") is False

    def test_verify_empty_hash_returns_false(self):
        """verify() returns False for an empty hash string."""
        hasher = HmacSha256ApiKeyHasher(pepper="test-pepper")

        assert hasher.verify("", "my-key") is False

    def test_uses_pepper_as_hmac_key(self):
        """hash() uses the pepper as the HMAC secret key, not appended to input."""
        import hashlib
        import hmac as hmac_mod

        pepper = "my-pepper"
        key_secret = "api-key"

        hasher = HmacSha256ApiKeyHasher(pepper=pepper)
        result = hasher.hash(key_secret)

        expected = hmac_mod.new(
            pepper.encode("utf-8"),
            key_secret.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        assert result == expected

    def test_exported_from_hasher_package(self):
        """HmacSha256ApiKeyHasher is accessible via the hasher package."""
        from fastapi_api_key.hasher import HmacSha256ApiKeyHasher as ImportedHasher

        assert ImportedHasher is HmacSha256ApiKeyHasher


class TestPepperWarning:
    """Tests for pepper warning behavior."""

    def test_default_pepper_emits_warning(self):
        """Using default pepper raises a warning."""
        with pytest.warns(UserWarning, match="insecure"):
            MockApiKeyHasher(pepper=DEFAULT_PEPPER)

    def test_custom_pepper_no_warning(self, recwarn):
        """Custom pepper does not raise warning."""
        MockApiKeyHasher(pepper="custom-secure-pepper")

        # No warnings should be emitted
        pepper_warnings = [w for w in recwarn if "insecure" in str(w.message)]
        assert len(pepper_warnings) == 0
