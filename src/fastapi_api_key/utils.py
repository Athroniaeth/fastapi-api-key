import uuid
from datetime import datetime, timezone


def uuid_factory() -> str:
    """Helper function to create a UUID string."""
    return uuid.uuid4().hex


def datetime_factory():
    """Helper function to create a timezone-aware datetime object."""
    return datetime.now(timezone.utc)
