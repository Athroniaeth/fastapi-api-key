import importlib

import pytest
from fastapi_api_key.domain.entities import Argon2ApiKeyHasher


def test_version():
    """Ensure the version attribute is present and correctly formatted."""
    module = importlib.import_module("fastapi_api_key")

    assert hasattr(module, "__version__")
    assert isinstance(module.__version__, str)
    assert module.__version__ == "0.1.0"  # Replace with the expected version


@pytest.mark.parametrize(
    "attr",
    [
        "ApiKeyService",
        "InMemoryApiKeyRepository",
        "SqlAlchemyApiKeyRepository",
    ],
)
def test_import_lib_public_api(attr: str):
    """Ensure importing lib works and exposes the public API."""
    module = importlib.import_module("fastapi_api_key")
    assert hasattr(module, attr)


def test_warning_default_pepper():
    """Ensure that ApiKeyHasher throw warning when default pepper isn't change."""
    with pytest.warns(
        UserWarning,
        match="Using default pepper is insecure. Please provide a strong pepper.",
    ):
        Argon2ApiKeyHasher()
