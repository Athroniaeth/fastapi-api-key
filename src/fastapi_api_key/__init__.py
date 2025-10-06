import importlib.metadata

from fastapi_api_key.cli import create_api_keys_cli
from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.domain.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.domain.hasher.bcrypt import BcryptApiKeyHasher
from fastapi_api_key.repositories.sql import ApiKeyModelMixin
from fastapi_api_key.services.base import ApiKeyService

__all__ = [
    "ApiKey",
    "ApiKeyService",
    "ApiKeyModelMixin",
    "Argon2ApiKeyHasher",
    "BcryptApiKeyHasher",
    "create_api_keys_cli",
]

__version__ = importlib.metadata.version("fastapi_api_key")
