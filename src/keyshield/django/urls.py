"""URL pattern factory for the Django integration.

Usage::

    from django.urls import path, include
    from keyshield.django.urls import create_api_keys_urlpatterns

    urlpatterns = [
        path("", include(create_api_keys_urlpatterns(svc_factory=get_service))),
    ]
"""

from typing import Any, Awaitable, Callable, List

try:
    from django.urls import path
except ModuleNotFoundError as e:  # pragma: no cover
    raise ImportError("Django integration requires 'django'. Install it with: uv add keyshield[django]") from e

from keyshield.services.base import AbstractApiKeyService
from keyshield.django.views import (
    ApiKeyActivateView,
    ApiKeyCountView,
    ApiKeyDeactivateView,
    ApiKeyDetailView,
    ApiKeyListCreateView,
    ApiKeySearchView,
    ApiKeyVerifyView,
)


def create_api_keys_urlpatterns(
    svc_factory: Callable[..., Awaitable[AbstractApiKeyService]],
) -> List[Any]:
    """Return a list of ``django.urls.path`` objects for API key management.

    Args:
        svc_factory: Async callable returning an
            :class:`~keyshield.services.base.AbstractApiKeyService`.

    Returns:
        List of URL patterns to include directly or via ``include()``.

    Example::

        urlpatterns = [
            path("api-keys/", include(create_api_keys_urlpatterns(svc_factory=get_service))),
        ]
    """
    kw = {"svc_factory": svc_factory}

    return [
        path("", ApiKeyListCreateView.as_view(**kw), name="api_key_list_create"),
        path("search/", ApiKeySearchView.as_view(**kw), name="api_key_search"),
        path("count/", ApiKeyCountView.as_view(**kw), name="api_key_count"),
        path("verify/", ApiKeyVerifyView.as_view(**kw), name="api_key_verify"),
        path("<str:pk>/", ApiKeyDetailView.as_view(**kw), name="api_key_detail"),
        path("<str:pk>/activate/", ApiKeyActivateView.as_view(**kw), name="api_key_activate"),
        path("<str:pk>/deactivate/", ApiKeyDeactivateView.as_view(**kw), name="api_key_deactivate"),
    ]
