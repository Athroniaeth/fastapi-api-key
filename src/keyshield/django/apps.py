"""Django application configuration for keyshield.

Add ``"keyshield.django"`` to ``INSTALLED_APPS`` in your Django settings
to make the :class:`~keyshield.django.models.ApiKeyModel` available for
migrations.
"""

try:
    from django.apps import AppConfig
except ModuleNotFoundError as e:  # pragma: no cover
    raise ImportError("Django integration requires 'django'. Install it with: uv add keyshield[django]") from e


class FastApiApiKeyDjangoConfig(AppConfig):
    """App config that registers the Django ORM model under the label
    ``keyshield_django``."""

    name = "keyshield.django"
    label = "keyshield_django"
    verbose_name = "FastAPI API Key"
    default_auto_field = "django.db.models.BigAutoField"
