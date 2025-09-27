import hashlib
import os
from datetime import datetime, timedelta
from types import NoneType
from typing import Type

import pytest
from argon2.exceptions import VerifyMismatchError

from fastapi_api_key.domain.entities import ApiKey, ApiKeyHasher, Argon2ApiKeyHasher
from fastapi_api_key.domain.errors import ApiKeyDisabledError, ApiKeyExpiredError
from argon2 import PasswordHasher

from fastapi_api_key.utils import datetime_factory


@pytest.mark.parametrize(
    [
        "field_name",
        "expected_type",
    ],
    [
        ("id_", str),
        ("name", (str, NoneType)),
        ("description", (str, NoneType)),
        ("is_active", bool),
        ("expires_at", (datetime, NoneType)),
        ("created_at", datetime),
        ("last_used_at", (datetime, NoneType)),
        ("key_prefix", str),
        ("key_hash", str),
    ],
)
def test_apikey_entity_structure(
    field_name: str,
    expected_type: type | tuple[type, ...],
):
    instance = ApiKey()
    assert hasattr(instance, field_name), f"Missing field '{field_name}'"

    value = getattr(instance, field_name)
    assert isinstance(value, expected_type), f"Field '{field_name}' has wrong type"


@pytest.mark.parametrize(
    "method_name",
    [
        "disable",
        "enable",
        "touch",
        "ensure_can_authenticate",
    ],
)
def test_apikey_have_methods(method_name: str):
    """Test that ApiKey has the expected methods."""
    instance = ApiKey()
    for method_name in ["disable", "enable", "touch", "ensure_can_authenticate"]:
        assert hasattr(instance, method_name), f"Missing method '{method_name}'"
        method = getattr(instance, method_name)
        assert callable(method), f"'{method_name}' is not callable"


def test_disable_and_enable():
    """Test the disable and enable methods of ApiKey."""
    api_key = ApiKey()

    api_key.disable()
    assert api_key.is_active is False

    api_key.enable()
    assert api_key.is_active is True


def test_touch_updates_last_used_at():
    """Test that touch method updates last_used_at to current time."""
    api_key = ApiKey()
    assert api_key.last_used_at is None

    # Check that it's "recent"
    api_key.touch()
    assert isinstance(api_key.last_used_at, datetime)
    difference = (datetime_factory() - api_key.last_used_at).total_seconds()
    assert difference < 2, "last_used_at was not updated to a recent time"


@pytest.mark.parametrize(
    [
        "is_active",
        "expires_at",
        "should_raise",
    ],
    [
        # Key active and no expiration → OK
        (True, None, None),
        # Key not active but no expiration → error
        (False, None, ApiKeyDisabledError),
        # Key active but expired → error
        (True, datetime_factory() - timedelta(days=1), ApiKeyExpiredError),
        # Key active and not expired → OK
        (True, datetime_factory() + timedelta(days=1), None),
    ],
)
def test_ensure_can_authenticate(
    is_active: bool,
    expires_at: datetime | None,
    should_raise: Type[Exception] | None,
):
    """Test the ensure_can_authenticate method of ApiKey."""
    api_key = ApiKey(is_active=is_active, expires_at=expires_at)

    if should_raise is not None:
        with pytest.raises(should_raise):
            api_key.ensure_can_authenticate()
    else:
        api_key.ensure_can_authenticate()


class MockPasswordHasher(PasswordHasher):
    """Mock implementation of Argon2 PasswordHasher with fake salting.

    This mock is designed for unit testing. It simulates hashing with a random
    salt and verification against the stored hash. The raw password is never
    stored in plain form inside the hash.
    """

    def __init__(self):
        super().__init__()

    def hash(self, password: str | bytes, *, salt: bytes | None = None) -> str:
        _salt = os.urandom(8).hex()
        if isinstance(password, bytes):
            password_bytes = password
        else:
            password_bytes = password.encode()
        digest = hashlib.sha256(password_bytes + _salt.encode()).hexdigest()
        return f"hashed-{digest}:{_salt}"

    def verify(self, hash: str, password: str | bytes) -> bool:
        try:
            digest, salt = hash.replace("hashed-", "").split(":")
        except ValueError:
            raise VerifyMismatchError("Malformed hash format")

        if isinstance(password, bytes):
            password_bytes = password
        else:
            password_bytes = password.encode()

        expected = hashlib.sha256(password_bytes + salt.encode()).hexdigest()
        if digest == expected:
            return True
        raise VerifyMismatchError("Mock mismatch")


@pytest.mark.parametrize(
    "hasher",
    [
        Argon2ApiKeyHasher(
            pepper="unit-test-pepper",
            password_hasher=MockPasswordHasher(),
        ),
    ],
)
def test_api_key_hasher_contract(hasher: ApiKeyHasher):
    raw_key = "test-api-key-123"
    stored_hash = hasher.hash(raw_key)

    # Raw key don't must be in the hash
    assert raw_key not in stored_hash

    # Stored hash must be a non-empty string
    assert isinstance(stored_hash, str)
    assert len(stored_hash) > 0

    # Stored hash must be verifiable
    assert hasher.verify(stored_hash, raw_key)
    assert not hasher.verify(stored_hash, "wrong-key")

    # Hashing must implement salting (different hash for same input)
    stored_hash_2 = hasher.hash(raw_key)
    assert stored_hash != stored_hash_2

    # Verification must fail if pepper is different
    no_pepper = Argon2ApiKeyHasher(
        pepper="different-unit-test-pepper",
        password_hasher=MockPasswordHasher(),
    )
    assert not no_pepper.verify(stored_hash, raw_key)
