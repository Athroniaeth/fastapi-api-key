from contextlib import AbstractAsyncContextManager
from typing import Union, Callable, Awaitable

from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.services.base import AbstractApiKeyService


AsyncSessionMaker = async_sessionmaker[AsyncSession]
"""Type alias for an "async_sessionmaker" instance of SQLAlchemy."""

SecurityHTTPBearer = Union[Callable[[HTTPAuthorizationCredentials], Awaitable[ApiKey]]]
"""Type alias for a security dependency callable using HTTP Bearer scheme."""

SecurityAPIKeyHeader = Union[Callable[[str], Awaitable[ApiKey]]]
"""Type alias for a security dependency callable using API Key Header scheme."""

ServiceFactory = Callable[[], AbstractAsyncContextManager[AbstractApiKeyService]]
"""Callable returning an async context manager that yields an API key service instance."""
