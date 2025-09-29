class ApiKeyError(Exception):
    """Base class for all API key related errors."""

    ...


class KeyNotFound(ApiKeyError):
    """Raised when no API key with the requested ID exists."""

    ...


class KeyNotProvided(ApiKeyError):
    """Raised when an API key is required but not provided."""

    ...


class KeyInactive(ApiKeyError):
    """Raised when an API key exists but is marked as inactive."""

    ...


class KeyExpired(ApiKeyError):
    """Raised when an API key exists but is expired."""

    ...


class InvalidKey(ApiKeyError):
    """Raised when an API key is invalid (key key_id matches but hash does not)."""

    ...
