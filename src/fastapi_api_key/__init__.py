import importlib.metadata

from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository
from fastapi_api_key.services.base import ApiKeyService

all = [
    "ApiKeyService",
    "InMemoryApiKeyRepository",
    "SqlAlchemyApiKeyRepository",
]

__version__ = importlib.metadata.version("fastapi_api_key")
