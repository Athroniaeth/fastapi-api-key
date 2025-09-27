import secrets
import string
import uuid
from datetime import datetime


def uuid_factory() -> str:
    """Helper function to create a UUID string."""
    return uuid.uuid4().hex


def prefix_factory() -> str:
    """Helper function to create unique prefix for API keys."""
    return uuid_factory()[:10]


def plain_key_factory(length: int = 64) -> str:
    """Helper function to create a secure random plain key."""
    alphabet = string.ascii_letters + string.digits  # 62 chars
    return "".join(secrets.choice(alphabet) for _ in range(length))


def datetime_factory() -> datetime:
    """Helper function to create a timezone-aware datetime object."""
    return datetime.now()  # timezone.utc)
