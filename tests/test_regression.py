import importlib
import sys
from typing import Optional, Type

import pytest
from fastapi_api_key.hasher.base import ApiKeyHasher
import re
import string
from datetime import datetime, timezone


from fastapi_api_key.utils import (
    uuid_factory,
    key_id_factory,
    key_secret_factory,
    datetime_factory,
)


def test_version():
    """Ensure the version attribute is present and correctly formatted."""
    module = importlib.import_module("fastapi_api_key")

    assert hasattr(module, "__version__")
    assert isinstance(module.__version__, str)
    assert module.__version__ == "0.3.0"  # Replace with the expected version


@pytest.mark.parametrize(
    [
        "module_path",
        "attr",
    ],
    [
        [
            None,
            "ApiKey",
        ],
        [
            None,
            "ApiKeyService",
        ],
        [
            "api",
            "create_api_keys_router",
        ],
        [
            "api",
            "create_depends_api_key",
        ],
        [
            "cli",
            "create_api_keys_cli",
        ],
        [
            "repositories.sql",
            "ApiKeyModelMixin",
        ],
        [
            "repositories.sql",
            "SqlAlchemyApiKeyRepository",
        ],
        [
            "repositories.in_memory",
            "InMemoryApiKeyRepository",
        ],
        [
            "hasher",
            "MockApiKeyHasher",
        ],
        [
            "hasher.bcrypt",
            "BcryptApiKeyHasher",
        ],
        [
            "hasher.argon2",
            "Argon2ApiKeyHasher",
        ],
    ],
)
def test_import_lib_public_api(module_path: Optional[str], attr: str):
    """Ensure importing lib works and exposes the public API."""
    module_name = "fastapi_api_key" if module_path is None else f"fastapi_api_key.{module_path}"
    module = importlib.import_module(module_name)
    assert hasattr(module, attr)


def test_warning_default_pepper(hasher_class: Type[ApiKeyHasher]):
    """Ensure that ApiKeyHasher throw warning when default pepper isn't change."""
    with pytest.warns(
        UserWarning,
        match="Using default pepper is insecure. Please provide a strong pepper.",
    ):
        hasher_class()


@pytest.mark.parametrize(
    ["library", "module_path"],
    [
        ["sqlalchemy", "fastapi_api_key.repositories.sql"],
        ["bcrypt", "fastapi_api_key.hasher.bcrypt"],
        ["argon2", "fastapi_api_key.hasher.argon2"],
    ],
)
def test_sqlalchemy_backend_import_error(monkeypatch: pytest.MonkeyPatch, library: str, module_path: str):
    """Simulate absence of SQLAlchemy and check for ImportError."""
    monkeypatch.setitem(sys.modules, library, None)

    with pytest.raises(ImportError) as exc_info:
        module = importlib.import_module(module_path)
        importlib.reload(module)

    expected = f"backend requires '{library}'. Install it with: uv add fastapi_api_key[{library}]"
    assert expected in f"{exc_info.value}"


def test_uuid_factory_generates_valid_uuid():
    """Test that uuid_factory returns a valid UUID string."""
    result = uuid_factory()
    assert isinstance(result, str)
    assert re.fullmatch(r"[0-9a-f]{32}", result), "UUID should be 32 lowercase hex characters"

    # Regression: ensure different calls return unique values
    assert result != uuid_factory(), "UUIDs should be unique across calls"


def test_key_id_factory_returns_short_uuid_prefix():
    """Test that key_id_factory returns a 16-character substring of a UUID."""
    result = key_id_factory()
    assert isinstance(result, str)
    assert len(result) == 16, "key_id should be 16 characters long"
    assert re.fullmatch(r"[0-9a-f]{16}", result), "key_id should be hex"

    # Regression: ensure uniqueness across calls
    assert result != key_id_factory(), "key_id values should be unique"


@pytest.mark.parametrize("length", [32, 64, 128])
def test_key_secret_factory_generates_random_secure_string(length):
    """Test that key_secret_factory returns a secure random alphanumeric string.

    Args:
        length (int): Desired length of the generated secret.
    """
    result = key_secret_factory(length)

    assert isinstance(result, str)
    assert len(result) == length, "Returned key must match requested length"

    valid_chars = string.ascii_letters + string.digits
    assert all(c in valid_chars for c in result), "Key must contain only letters and digits"

    # Regression: ensure high entropy (different values)
    assert result != key_secret_factory(length), "Generated secrets should differ"


def test_datetime_factory_returns_timezone_aware_datetime():
    """Test that datetime_factory returns a timezone-aware datetime object."""
    result = datetime_factory()
    assert isinstance(result, datetime)
    assert result.tzinfo == timezone.utc, "Datetime must be UTC-aware"

    now = datetime.now(timezone.utc)
    delta = abs((now - result).total_seconds())
    assert delta < 2, "Datetime should be close to current UTC time"
