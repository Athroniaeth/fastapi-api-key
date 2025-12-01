"""Unit tests for API key hashers.

Tests each hasher implementation:
- MockApiKeyHasher (for tests)
- Argon2ApiKeyHasher
- BcryptApiKeyHasher

All hashers must satisfy the ApiKeyHasher protocol:
- hash() produces a non-empty string
- verify() returns True for correct key
- verify() returns False for wrong key
- Different hashes for same input (salting)
- Different pepper causes verification failure
"""

import pytest

from fastapi_api_key.hasher.base import ApiKeyHasher, MockApiKeyHasher, DEFAULT_PEPPER
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.hasher.bcrypt import BcryptApiKeyHasher




@pytest.fixture(params=["mock", "argon2", "bcrypt"])
def hasher(request: pytest.FixtureRequest) -> ApiKeyHasher:
    """Parameterized fixture providing all hasher implementations."""
    pepper = "test-pepper-12345"

    if request.param == "mock":
        return MockApiKeyHasher(pepper=pepper)
    elif request.param == "argon2":
        return Argon2ApiKeyHasher(pepper=pepper)
    else:
        return BcryptApiKeyHasher(pepper=pepper, rounds=4)  # Fast for tests




class TestHasherProtocol:
    """Tests that all hashers satisfy the ApiKeyHasher protocol."""

    def test_hash_returns_non_empty_string(self, hasher: ApiKeyHasher):
        """hash() returns a non-empty string."""
        result = hasher.hash("my-api-key")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_does_not_contain_raw_key(self, hasher: ApiKeyHasher):
        """hash() output should not contain the raw key (except mock hasher)."""
        raw_key = "my-secret-api-key-123"
        hashed = hasher.hash(raw_key)

        # MockApiKeyHasher includes key+pepper for testing purposes, skip this check
        if isinstance(hasher, MockApiKeyHasher):
            pytest.skip("MockApiKeyHasher intentionally includes key for testing")

        assert raw_key not in hashed

    def test_verify_correct_key(self, hasher: ApiKeyHasher):
        """verify() returns True for correct key."""
        api_key = "correct-api-key"
        hashed = hasher.hash(api_key)

        assert hasher.verify(hashed, api_key) is True

    def test_verify_wrong_key(self, hasher: ApiKeyHasher):
        """verify() returns False for wrong key."""
        hashed = hasher.hash("correct-key")

        assert hasher.verify(hashed, "wrong-key") is False

    def test_salting_produces_different_hashes(self, hasher: ApiKeyHasher):
        """Same key produces different hashes (salting)."""
        api_key = "my-api-key"

        hash1 = hasher.hash(api_key)
        hash2 = hasher.hash(api_key)

        assert hash1 != hash2

    def test_both_hashes_verify(self, hasher: ApiKeyHasher):
        """Both different hashes verify against same key."""
        api_key = "my-api-key"

        hash1 = hasher.hash(api_key)
        hash2 = hasher.hash(api_key)

        assert hasher.verify(hash1, api_key) is True
        assert hasher.verify(hash2, api_key) is True




class TestPepper:
    """Tests for pepper behavior."""

    def test_different_pepper_fails_verification(self):
        """Hash with one pepper cannot verify with different pepper."""
        hasher1 = MockApiKeyHasher(pepper="pepper-one")
        hasher2 = MockApiKeyHasher(pepper="pepper-two")

        api_key = "my-api-key"
        hashed = hasher1.hash(api_key)

        assert hasher1.verify(hashed, api_key) is True
        assert hasher2.verify(hashed, api_key) is False

    def test_default_pepper_warning(self):
        """Using default pepper raises a warning."""
        with pytest.warns(UserWarning, match="insecure"):
            MockApiKeyHasher(pepper=DEFAULT_PEPPER)




class TestBcryptSpecific:
    """Tests specific to BcryptApiKeyHasher."""

    def test_rounds_too_low(self):
        """Rounds below 4 raises ValueError."""
        with pytest.raises(ValueError, match="between 4 and 31"):
            BcryptApiKeyHasher(pepper="test", rounds=3)

    def test_rounds_too_high(self):
        """Rounds above 31 raises ValueError."""
        with pytest.raises(ValueError, match="between 4 and 31"):
            BcryptApiKeyHasher(pepper="test", rounds=32)

    def test_valid_rounds_accepted(self):
        """Valid rounds (4-31) are accepted."""
        hasher = BcryptApiKeyHasher(pepper="test", rounds=4)
        assert hasher._rounds == 4

        hasher = BcryptApiKeyHasher(pepper="test", rounds=31)
        assert hasher._rounds == 31

    def test_long_key_truncation(self):
        """Keys longer than 72 bytes are truncated consistently."""
        hasher = BcryptApiKeyHasher(pepper="test", rounds=4)

        # Create a key longer than 72 bytes
        long_key = "a" * 100
        hashed = hasher.hash(long_key)

        # Should still verify correctly (both hash and verify truncate)
        assert hasher.verify(hashed, long_key) is True



class TestMockHasherSpecific:
    """Tests specific to MockApiKeyHasher."""

    def test_invalid_hash_format(self):
        """verify() returns False for invalid hash format."""
        hasher = MockApiKeyHasher(pepper="test")

        # Missing $ separator
        assert hasher.verify("invalid-hash", "key") is False
