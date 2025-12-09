import importlib.metadata

from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.services.base import ApiKeyService

__version__ = importlib.metadata.version("fastapi_api_key")
__all__ = [
    "ApiKey",
    "ApiKeyService",
    "__version__",
]
