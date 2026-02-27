"""Minimal Django settings for the test suite.

Referenced via DJANGO_SETTINGS_MODULE in pyproject.toml [tool.pytest.ini_options].
"""

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    "fastapi_api_key.django",
]

USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
