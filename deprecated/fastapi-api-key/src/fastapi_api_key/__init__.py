import warnings

warnings.warn(
    "fastapi-api-key is deprecated and will receive no further updates. "
    "Please uninstall it and install keyshield instead: "
    "https://github.com/Athroniaeth/keyshield",
    DeprecationWarning,
    stacklevel=2,
)

from keyshield import (  # noqa: E402, F401
    ApiKey,
    ApiKeyService,
    __version__,
)

__all__ = [
    "ApiKey",
    "ApiKeyService",
    "__version__",
]
