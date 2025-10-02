import importlib
import sys
from typing import Optional, Type

import pytest
from fastapi_api_key.domain.hasher import (
    Argon2ApiKeyHasher,
)


def test_version():
    """Ensure the version attribute is present and correctly formatted."""
    module = importlib.import_module("fastapi_api_key")

    assert hasattr(module, "__version__")
    assert isinstance(module.__version__, str)
    assert module.__version__ == "0.1.0"  # Replace with the expected version


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
            None,
            "BcryptApiKeyHasher",
        ],
        [
            None,
            "Argon2ApiKeyHasher",
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
    ],
)
def test_import_lib_public_api(module_path: Optional[None], attr: str):
    """Ensure importing lib works and exposes the public API."""
    module_name = (
        "fastapi_api_key" if module_path is None else f"fastapi_api_key.{module_path}"
    )
    module = importlib.import_module(module_name)
    assert hasattr(module, attr)


def test_warning_default_pepper(hasher_class: Type[Argon2ApiKeyHasher]):
    """Ensure that ApiKeyHasher throw warning when default pepper isn't change."""
    with pytest.warns(
        UserWarning,
        match="Using default pepper is insecure. Please provide a strong pepper.",
    ):
        hasher_class()


def test_sqlalchemy_backend_import_error(monkeypatch):
    """Simulate absence of SQLAlchemy and check for ImportError."""
    monkeypatch.setitem(sys.modules, "sqlalchemy", None)

    with pytest.raises(ImportError) as exc_info:
        module = importlib.import_module("fastapi_api_key.repositories.sql")
        importlib.reload(module)

    expected = "SQLAlchemy backend requires 'sqlalchemy'. Install it with: uv add fastapi_api_key[sqlalchemy]"
    assert expected in f"{exc_info.value}"
