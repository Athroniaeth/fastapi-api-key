"""Regression tests for public API stability.

Tests that ensure:
- Public API remains importable
- Optional dependencies raise helpful ImportError
- Security warnings work correctly
- Utility factories behave correctly
"""

import importlib
import sys
import re
import string
from datetime import datetime, timezone
from typing import Optional

import pytest

from fastapi_api_key.hasher.base import MockApiKeyHasher, DEFAULT_PEPPER
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.hasher.bcrypt import BcryptApiKeyHasher
from fastapi_api_key.utils import (
    uuid_factory,
    key_id_factory,
    key_secret_factory,
    datetime_factory,
)


class TestPublicApiImports:
    """Ensure public API remains importable."""

    @pytest.mark.parametrize(
        ["module_path", "attr"],
        [
            (None, "ApiKey"),
            (None, "ApiKeyService"),
            ("api", "create_api_keys_router"),
            ("api", "create_depends_api_key"),
            ("cli", "create_api_keys_cli"),
            ("repositories.sql", "ApiKeyModelMixin"),
            ("repositories.sql", "SqlAlchemyApiKeyRepository"),
            ("repositories.in_memory", "InMemoryApiKeyRepository"),
            ("services.cached", "CachedApiKeyService"),
            ("hasher", "MockApiKeyHasher"),
            ("hasher.bcrypt", "BcryptApiKeyHasher"),
            ("hasher.argon2", "Argon2ApiKeyHasher"),
        ],
    )
    def test_import_public_api(self, module_path: Optional[str], attr: str):
        """Public API attributes are importable."""
        module_name = "fastapi_api_key" if module_path is None else f"fastapi_api_key.{module_path}"
        module = importlib.import_module(module_name)
        assert hasattr(module, attr)


class TestOptionalDependencyErrors:
    """Ensure helpful errors when optional dependencies are missing."""

    @pytest.mark.parametrize(
        ["library", "module_path"],
        [
            ("sqlalchemy", "fastapi_api_key.repositories.sql"),
            ("bcrypt", "fastapi_api_key.hasher.bcrypt"),
            ("argon2", "fastapi_api_key.hasher.argon2"),
            ("aiocache", "fastapi_api_key.services.cached"),
        ],
    )
    def test_missing_dependency_raises_helpful_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        library: str,
        module_path: str,
    ):
        """Missing optional dependency raises ImportError with install hint."""
        monkeypatch.setitem(sys.modules, library, None)  # pyrefly: ignore[bad-argument-type]

        with pytest.raises(ImportError) as exc_info:
            module = importlib.import_module(module_path)
            importlib.reload(module)

        expected = f"requires '{library}'. Install it with: uv add fastapi_api_key[{library}]"
        assert expected in str(exc_info.value)


class TestSecurityWarnings:
    """Ensure security warnings work correctly."""

    @pytest.mark.parametrize(
        "hasher_class",
        [MockApiKeyHasher, Argon2ApiKeyHasher, BcryptApiKeyHasher],
    )
    def test_default_pepper_warning(self, hasher_class):
        """Using default pepper raises UserWarning."""
        with pytest.warns(UserWarning, match="insecure"):
            if hasher_class == BcryptApiKeyHasher:
                hasher_class(pepper=DEFAULT_PEPPER, rounds=4)
            else:
                hasher_class(pepper=DEFAULT_PEPPER)


class TestUtilityFactories:
    """Tests for utility factory functions."""

    def test_uuid_factory_format(self):
        """uuid_factory returns 32 lowercase hex chars."""
        result = uuid_factory()

        assert isinstance(result, str)
        assert re.fullmatch(r"[0-9a-f]{32}", result)

    def test_uuid_factory_unique(self):
        """uuid_factory returns unique values."""
        assert uuid_factory() != uuid_factory()

    def test_key_id_factory_format(self):
        """key_id_factory returns 16 hex chars."""
        result = key_id_factory()

        assert isinstance(result, str)
        assert len(result) == 16
        assert re.fullmatch(r"[0-9a-f]{16}", result)

    def test_key_id_factory_unique(self):
        """key_id_factory returns unique values."""
        assert key_id_factory() != key_id_factory()

    @pytest.mark.parametrize("length", [32, 48, 64])
    def test_key_secret_factory_format(self, length: int):
        """key_secret_factory returns alphanumeric string of specified length."""
        result = key_secret_factory(length)

        assert isinstance(result, str)
        assert len(result) == length

        valid_chars = string.ascii_letters + string.digits
        assert all(c in valid_chars for c in result)

    def test_key_secret_factory_unique(self):
        """key_secret_factory returns unique values."""
        assert key_secret_factory() != key_secret_factory()

    def test_datetime_factory_utc_aware(self):
        """datetime_factory returns UTC-aware datetime."""
        result = datetime_factory()

        assert isinstance(result, datetime)
        assert result.tzinfo == timezone.utc

    def test_datetime_factory_is_current(self):
        """datetime_factory returns current time."""
        result = datetime_factory()
        now = datetime.now(timezone.utc)

        delta = abs((now - result).total_seconds())
        assert delta < 2
