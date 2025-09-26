from datetime import datetime, timedelta, timezone
from types import NoneType
from typing import Type

import pytest

from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.domain.errors import ApiKeyDisabledError, ApiKeyExpiredError


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
    difference = (datetime.now(timezone.utc) - api_key.last_used_at).total_seconds()
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
        (True, datetime.now(timezone.utc) - timedelta(days=1), ApiKeyExpiredError),
        # Key active and not expired → OK
        (True, datetime.now(timezone.utc) + timedelta(days=1), None),
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
