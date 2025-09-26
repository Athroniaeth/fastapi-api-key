import secrets
import uuid
from datetime import datetime


def uuid_factory() -> str:
    """Helper function to create a UUID string."""
    return uuid.uuid4().hex


def prefix_factory() -> str:
    """Helper function to create a 16-character prefix."""
    return uuid_factory()


def plain_key_factory(length: int = 32) -> str:
    """Helper function to create a secure random plain key."""
    if length < 16:
        raise ValueError("Length must be at least 16 bytes for sufficient security.")
    return secrets.token_urlsafe(32)  # 32 bytes = 64 hex characters


def datetime_factory() -> datetime:
    """Helper function to create a timezone-aware datetime object."""
    return datetime.now()
