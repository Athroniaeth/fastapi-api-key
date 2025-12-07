"""Unit tests for ApiKey entity.

Tests the domain entity behavior in isolation:
- Field types and defaults
- Methods (disable, enable, touch)
- Validation (ensure_can_authenticate, ensure_valid_scopes)
- Key secret handling
"""

from datetime import datetime, timedelta, timezone

import pytest

from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.domain.errors import KeyExpired, KeyInactive, InvalidScopes, KeyHashNotSet, KeySecretNotSet
from fastapi_api_key.utils import datetime_factory


class TestApiKeyStructure:
    """Tests for ApiKey field types and defaults."""

    def test_default_fields(self):
        """ApiKey has correct default values."""
        key = ApiKey()

        assert isinstance(key.id_, str)
        assert key.name is None
        assert key.description is None
        assert key.is_active
        assert key.expires_at is None
        assert isinstance(key.created_at, datetime)
        assert key.last_used_at is None
        assert isinstance(key.key_id, str)
        assert key._key_hash is None
        assert key.scopes == []

    def test_created_at_is_utc(self):
        """created_at should be timezone-aware (UTC)."""
        key = ApiKey()
        assert key.created_at.tzinfo is not None

    def test_naive_datetime_normalized_to_utc(self):
        """Naive datetimes are converted to UTC."""
        naive_dt = datetime(2024, 1, 1, 12, 0, 0)
        key = ApiKey(expires_at=naive_dt)

        assert key.expires_at is not None
        assert key.expires_at.tzinfo == timezone.utc

    def test_aware_datetime_preserved(self):
        """Aware datetimes are preserved."""
        aware_dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        key = ApiKey(expires_at=aware_dt)

        assert key.expires_at == aware_dt


class TestApiKeyReprSecurity:
    """Tests that repr() and str() don't leak sensitive information."""

    @pytest.mark.parametrize("str_method", [repr, str])
    def test_does_not_contain_key_hash(self, str_method):
        """String representation should not contain the actual key_hash value."""
        secret_hash = "argon2id$v=19$m=65536,t=3,p=4$secret_salt$secret_hash_value"
        key = ApiKey(key_hash=secret_hash)

        result = str_method(key)

        assert secret_hash not in result
        assert "secret_hash_value" not in result

    @pytest.mark.parametrize("str_method", [repr, str])
    def test_does_not_contain_key_secret(self, str_method):
        """String representation should not contain the key_secret value."""
        secret = "super-secret-api-key-value-12345"
        key = ApiKey(key_secret=secret)

        result = str_method(key)

        assert secret not in result

    @pytest.mark.parametrize("str_method", [repr, str])
    def test_does_not_contain_key_secret_first(self, str_method):
        """String representation should not contain the key_secret_first value."""
        key = ApiKey(key_secret_first="abcd")

        result = str_method(key)

        assert "abcd" not in result

    @pytest.mark.parametrize("str_method", [repr, str])
    def test_does_not_contain_key_secret_last(self, str_method):
        """String representation should not contain the key_secret_last value."""
        key = ApiKey(key_secret_last="wxyz")

        result = str_method(key)

        assert "wxyz" not in result

    @pytest.mark.parametrize("str_method", [repr, str])
    def test_contains_masked_key_hash_indicator(self, str_method):
        """String representation should indicate key_hash is set but masked."""
        key = ApiKey(key_hash="some-hash")

        result = str_method(key)

        assert "key_hash=" in result
        assert "*" in result or "..." in result  # Some masking indicator

    @pytest.mark.parametrize("str_method", [repr, str])
    def test_shows_none_when_key_hash_not_set(self, str_method):
        """String representation should show None when key_hash is not set."""
        key = ApiKey()

        result = str_method(key)

        assert "key_hash=None" in result


class TestApiKeyStateMethods:
    """Tests for enable, disable, touch methods."""

    def test_disable(self):
        """disable() sets is_active to False."""
        key = ApiKey()
        assert key.is_active

        key.disable()
        assert key.is_active is False  # pyrefly: ignore[unnecessary-comparison]

    def test_enable(self):
        """enable() sets is_active to True."""
        key = ApiKey(is_active=False)
        assert key.is_active is False  # pyrefly: ignore[unnecessary-comparison]

        key.enable()
        assert key.is_active

    def test_touch_updates_last_used_at(self):
        """touch() updates last_used_at to current time."""
        key = ApiKey()
        assert key.last_used_at is None

        key.touch()

        assert key.last_used_at is not None
        delta = (datetime_factory() - key.last_used_at).total_seconds()
        assert delta < 2  # Within 2 seconds


class TestEnsureCanAuthenticate:
    """Tests for ensure_can_authenticate method."""

    def test_active_key_no_expiration(self):
        """Active key without expiration passes."""
        key = ApiKey(is_active=True, expires_at=None)
        key.ensure_can_authenticate()  # Should not raise

    def test_inactive_key_raises(self):
        """Inactive key raises KeyInactive."""
        key = ApiKey(is_active=False)

        with pytest.raises(KeyInactive):
            key.ensure_can_authenticate()

    def test_expired_key_raises(self):
        """Expired key raises KeyExpired."""
        key = ApiKey(expires_at=datetime_factory() - timedelta(days=1))

        with pytest.raises(KeyExpired):
            key.ensure_can_authenticate()

    def test_active_key_not_expired(self):
        """Active key with future expiration passes."""
        key = ApiKey(expires_at=datetime_factory() + timedelta(days=1))
        key.ensure_can_authenticate()  # Should not raise


class TestEnsureValidScopes:
    """Tests for ensure_valid_scopes method."""

    def test_empty_required_scopes(self):
        """Empty required scopes always passes."""
        key = ApiKey(scopes=[])
        key.ensure_valid_scopes([])  # Should not raise

    def test_has_all_required_scopes(self):
        """Key with all required scopes passes."""
        key = ApiKey(scopes=["read", "write", "admin"])
        key.ensure_valid_scopes(["read", "write"])  # Should not raise

    def test_missing_scope_raises(self):
        """Missing required scope raises InvalidScopes."""
        key = ApiKey(scopes=["read"])

        with pytest.raises(InvalidScopes) as exc_info:
            key.ensure_valid_scopes(["read", "write"])

        assert "write" in str(exc_info.value)

    def test_missing_multiple_scopes(self):
        """Multiple missing scopes are listed in error."""
        key = ApiKey(scopes=[])

        with pytest.raises(InvalidScopes) as exc_info:
            key.ensure_valid_scopes(["read", "write"])

        error_msg = str(exc_info.value)
        assert "read" in error_msg
        assert "write" in error_msg


class TestKeyHash:
    """Tests for key_hash property."""

    def test_key_hash_returns_value_when_set(self):
        """key_hash returns the hash when set."""
        key = ApiKey(key_hash="hashed-value")
        assert key.key_hash == "hashed-value"

    def test_key_hash_raises_when_not_set(self):
        """key_hash raises KeyHashNotSet when not set."""
        key = ApiKey()

        with pytest.raises(KeyHashNotSet, match="Key hash is not set"):
            _ = key.key_hash


class TestKeySecret:
    """Tests for key_secret property and related methods."""

    def test_key_secret_cleared_after_access(self):
        """key_secret is cleared after first access."""
        key = ApiKey(key_secret="secret123")

        first_access = key.key_secret
        assert first_access == "secret123"

        second_access = key.key_secret
        assert second_access is None

    def test_key_secret_first_from_secret(self):
        """key_secret_first returns first 4 chars of secret."""
        key = ApiKey(key_secret="abcd1234efgh")
        assert key.key_secret_first == "abcd"

    def test_key_secret_last_from_secret(self):
        """key_secret_last returns last 4 chars of secret."""
        key = ApiKey(key_secret="abcd1234efgh")
        assert key.key_secret_last == "efgh"

    def test_key_secret_first_from_stored(self):
        """key_secret_first uses stored value if available."""
        key = ApiKey(key_secret_first="XXXX")
        assert key.key_secret_first == "XXXX"

    def test_key_secret_last_from_stored(self):
        """key_secret_last uses stored value if available."""
        key = ApiKey(key_secret_last="YYYY")
        assert key.key_secret_last == "YYYY"

    def test_key_secret_first_raises_when_unavailable(self):
        """key_secret_first raises if no secret available."""
        key = ApiKey()

        with pytest.raises(KeySecretNotSet, match="Key secret is not set"):
            _ = key.key_secret_first

    def test_key_secret_last_raises_when_unavailable(self):
        """key_secret_last raises if no secret available."""
        key = ApiKey()

        with pytest.raises(KeySecretNotSet, match="Key secret is not set"):
            _ = key.key_secret_last


class TestFullKeySecret:
    """Tests for full_key_secret static method."""

    def test_full_key_format(self):
        """full_key_secret constructs correct format."""
        result = ApiKey.get_api_key(
            global_prefix="ak",
            key_id="abc123",
            key_secret="secretXYZ",
            separator="-",
        )
        assert result == "ak-abc123-secretXYZ"

    def test_custom_separator(self):
        """full_key_secret works with custom separator."""
        result = ApiKey.get_api_key(
            global_prefix="key",
            key_id="id",
            key_secret="secret",
            separator="_",
        )
        assert result == "key_id_secret"
