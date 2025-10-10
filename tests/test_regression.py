import importlib
import sys
from typing import Optional, Type

import pytest
from fastapi_api_key.hasher.base import ApiKeyHasher


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
