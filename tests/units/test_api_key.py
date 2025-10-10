from datetime import datetime, timedelta
from typing import Type, Union

import pytest

from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.hasher.base import ApiKeyHasher
from fastapi_api_key.domain.errors import KeyInactive, KeyExpired

from fastapi_api_key.utils import datetime_factory
from tests.conftest import MockPasswordHasher

# Python <3.10 compatibility
NoneType = type(None)


@pytest.mark.parametrize(
    [
        "field_name",
        "expected_type",
    ],
    [
        ("id_", str),
        ("is_active", bool),
        ("name", (str, NoneType)),
        ("description", (str, NoneType)),
        ("created_at", datetime),
        ("expires_at", (datetime, NoneType)),
        ("last_used_at", (datetime, NoneType)),
        ("key_id", str),
        ("key_hash", (str, NoneType)),
    ],
)
def test_apikey_entity_structure(
    field_name: str,
    expected_type: Union[type, tuple[type, ...]],
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
        (False, None, KeyInactive),
        # Key active and not expired → OK
        (True, datetime_factory() + timedelta(days=1), None),
        # Key active but expired → error
        (True, datetime_factory() - timedelta(days=1), KeyExpired),
    ],
)
def test_ensure_can_authenticate(
    is_active: bool,
    expires_at: Union[datetime, None],
    should_raise: Union[Type[Exception], None],
):
    """Test the ensure_can_authenticate method of ApiKey."""
    api_key = ApiKey(is_active=is_active, expires_at=expires_at)

    if should_raise is not None:
        with pytest.raises(should_raise):
            api_key.ensure_can_authenticate()
    else:
        api_key.ensure_can_authenticate()


@pytest.mark.parametrize(
    "hasher",
    [
        Argon2ApiKeyHasher(
            pepper="unit-test-pepper",
            password_hasher=MockPasswordHasher(fixed_salt=False),
        ),
    ],
)
def test_hasher_contract(hasher: ApiKeyHasher):
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
        password_hasher=MockPasswordHasher(fixed_salt=False),
    )
    assert not no_pepper.verify(stored_hash, raw_key)
