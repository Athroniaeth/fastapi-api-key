"""Django integration for keyshield.

Sub-modules
-----------
- ``models``      – Django ORM model (``ApiKeyModel``).
- ``repository``  – ``DjangoApiKeyRepository`` implementing
                    :class:`~keyshield.repositories.base.AbstractApiKeyRepository`.
- ``views``       – Class-based async views with full CRUD management.
- ``urls``        – ``create_api_keys_urlpatterns`` URL pattern factory.
- ``decorators``  – ``require_api_key`` async view decorator.
"""

default_app_config = "keyshield.django.apps.FastApiApiKeyDjangoConfig"
