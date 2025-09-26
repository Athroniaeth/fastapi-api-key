import secrets
import uuid
from datetime import datetime


def uuid_factory() -> str:
    """Helper function to create a UUID string."""
    return uuid.uuid4().hex


def prefix_factory() -> str:
    """Helper function to create a 16-character prefix."""
    return uuid_factory()


def hash_factory() -> str:
    """Helper function to create a 64-character hash."""
    return secrets.token_hex(32)  # 32 bytes = 64 hex characters


def datetime_factory() -> datetime:
    """Helper function to create a timezone-aware datetime object."""
    return datetime.now()
