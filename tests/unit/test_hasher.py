"""Unit tests for API key hashers.

Tests each hasher implementation with mocked backends:
- MockApiKeyHasher (for tests)
- Argon2ApiKeyHasher
- BcryptApiKeyHasher

Focus: Testing OUR code (pepper application, error handling, parameter validation),
NOT the underlying crypto libraries.
"""

from unittest.mock import MagicMock, patch

import pytest

from fastapi_api_key.hasher.base import MockApiKeyHasher, DEFAULT_PEPPER
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.hasher.bcrypt import BcryptApiKeyHasher


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
