import importlib.metadata


from fastapi_api_key.services.base import ApiKeyService

__all__ = [
    "ApiKeyService",
]

__version__ = importlib.metadata.version("fastapi_api_key")
