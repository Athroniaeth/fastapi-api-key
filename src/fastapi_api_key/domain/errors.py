class ApiKeyError(Exception):
    """Base exception for API key domain errors."""


class ApiKeyExpiredError(ApiKeyError):
    """Raised when an API key is expired."""


class ApiKeyDisabledError(ApiKeyError):
    """Raised when an API key is disabled."""


class ApiKeyInvalidError(ApiKeyError):
    """Raised when an API key is invalid (e.g., hash mismatch)."""
