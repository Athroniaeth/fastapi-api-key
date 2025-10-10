import pytest
from fastapi_api_key.hasher.base import ApiKeyHasher
from fastapi_api_key.hasher.bcrypt import BcryptApiKeyHasher


def test_hash_and_verify_success(hasher: ApiKeyHasher) -> None:
    """Test that a hashed API key can be successfully verified.

    Args:
        hasher (ApiKeyHasher): Fixture for the hasher implementation.
    """
    api_key = "my-secret-api-key"
    hashed = hasher.hash(api_key)
    assert hasher.verify(hashed, api_key) is True, "The API key should verify successfully."


def test_verify_fail_with_wrong_key(hasher: ApiKeyHasher) -> None:
    """Test that verification fails with an incorrect API key.

    Args:
        hasher (ApiKeyHasher): Fixture for the hasher implementation.
    """
    api_key = "correct-key"
    wrong_key = "wrong-key"
    hashed = hasher.hash(api_key)
    assert hasher.verify(hashed, wrong_key) is False


def test_hasher_not_deterministic(hasher: ApiKeyHasher) -> None:
    """Test that hashing the same API key multiple times produces different hashes.

    Args:
        hasher (ApiKeyHasher): Fixture for the hasher implementation.
    """
    api_key = "my-secret-api-key"
    hash1 = hasher.hash(api_key)
    hash2 = hasher.hash(api_key)
    assert hash1 != hash2, "Hashes should differ due to salting."


def test_hasher_bcrypt_rounds_limit() -> None:
    """Test that BcryptApiKeyHasher raises ValueError for invalid rounds."""
    with pytest.raises(ValueError):
        BcryptApiKeyHasher(rounds=3)  # Too low

    with pytest.raises(ValueError):
        BcryptApiKeyHasher(rounds=32)  # Too high
