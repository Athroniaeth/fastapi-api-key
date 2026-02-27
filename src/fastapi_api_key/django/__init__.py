"""Django integration for fastapi-api-key.

Sub-modules
-----------
- ``models``      – Django ORM model (``ApiKeyModel``).
- ``repository``  – ``DjangoApiKeyRepository`` implementing
                    :class:`~fastapi_api_key.repositories.base.AbstractApiKeyRepository`.
- ``views``       – Class-based async views with full CRUD management.
- ``urls``        – ``create_api_keys_urlpatterns`` URL pattern factory.
- ``decorators``  – ``require_api_key`` async view decorator.
"""

default_app_config = "fastapi_api_key.django.apps.FastApiApiKeyDjangoConfig"
