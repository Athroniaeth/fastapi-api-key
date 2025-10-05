import secrets
import string
import uuid
from datetime import datetime, timezone


def uuid_factory() -> str:
    """Helper function to create a UUID string."""
    return uuid.uuid4().hex


def key_id_factory() -> str:
    """Helper function to create unique key_id for API keys."""
    return uuid_factory()[:16]


def key_secret_factory(length: int = 64) -> str:
    """Helper function to create a secure random plain key."""
    alphabet = string.ascii_letters + string.digits  # 62 chars
    return "".join(secrets.choice(alphabet) for _ in range(length))


def datetime_factory() -> datetime:
    """Helper function to create a timezone-aware datetime object."""
    return datetime.now(timezone.utc)
