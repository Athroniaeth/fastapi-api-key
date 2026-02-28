"""Django ORM model for API keys.

This model mirrors the SQLAlchemy model in
:mod:`fastapi_api_key.repositories.sql` so both ORMs persist the same schema
(table name ``api_keys``).

Usage
-----
Add ``"fastapi_api_key.django"`` to ``INSTALLED_APPS`` in your Django settings,
then run migrations::

    python manage.py makemigrations fastapi_api_key_django
    python manage.py migrate
"""

try:
    import django  # noqa: F401
    from django.db import models
except ModuleNotFoundError as e:  # pragma: no cover
    raise ImportError("Django integration requires 'django'. Install it with: uv add fastapi_api_key[django]") from e


class ApiKeyModel(models.Model):
    """Django ORM model storing a single API key record.

    Attributes:
        id_: UUID-based primary key (stored as ``id`` in the database).
        name: Optional human-friendly display name.
        description: Optional free-text description.
        is_active: Whether the key is active.
        expires_at: Optional expiration timestamp (timezone-aware).
        created_at: Creation timestamp (timezone-aware).
        last_used_at: Last-used timestamp (timezone-aware, nullable).
        key_id: Short public identifier used for fast lookup (indexed, unique).
        key_hash: Hashed secret (never stored in plain text).
        key_secret_first: First 4 characters of the secret (hint for users).
        key_secret_last: Last 4 characters of the secret (hint for users).
        scopes: JSON list of permission scopes.
    """

    # Primary key stored as the "id" column in the DB.
    # Field is named "record_id" (not "id_") to avoid Django's delete_batch
    # building the ambiguous lookup string "id___in" via "%s__in" % attname.
    record_id = models.CharField(max_length=36, primary_key=True, db_column="id")

    name = models.CharField(max_length=128, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)

    # Fast-lookup index: the 16-char public identifier embedded in the key string
    key_id = models.CharField(max_length=16, unique=True, db_index=True)
    key_hash = models.CharField(max_length=255, unique=True)

    # Hint characters stored for display (first/last 4 chars of the secret)
    key_secret_first = models.CharField(max_length=4)
    key_secret_last = models.CharField(max_length=4)

    scopes = models.JSONField(default=list)

    class Meta:
        app_label = "fastapi_api_key_django"
        db_table = "api_keys"
