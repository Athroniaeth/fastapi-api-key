"""Django application configuration for fastapi-api-key.

Add ``"fastapi_api_key.django"`` to ``INSTALLED_APPS`` in your Django settings
to make the :class:`~fastapi_api_key.django.models.ApiKeyModel` available for
migrations.
"""

try:
    from django.apps import AppConfig
except ModuleNotFoundError as e:  # pragma: no cover
    raise ImportError("Django integration requires 'django'. Install it with: uv add fastapi_api_key[django]") from e


class FastApiApiKeyDjangoConfig(AppConfig):
    """App config that registers the Django ORM model under the label
    ``fastapi_api_key_django``."""

    name = "fastapi_api_key.django"
    label = "fastapi_api_key_django"
    verbose_name = "FastAPI API Key"
    default_auto_field = "django.db.models.BigAutoField"
