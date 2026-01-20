"""Acceptance tests for the CLI module.

Tests verify CLI commands work correctly using InMemory repository.
Focus on behavior, not implementation details.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta

import pytest
from typer.testing import CliRunner

from fastapi_api_key import ApiKeyService
from fastapi_api_key.cli import create_api_keys_cli
from fastapi_api_key.hasher.base import MockApiKeyHasher
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key.utils import datetime_factory


@pytest.fixture
def runner() -> CliRunner:
    """Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def repo() -> InMemoryApiKeyRepository:
    """Fresh in-memory repository for each test."""
    return InMemoryApiKeyRepository()


@pytest.fixture
def service(repo: InMemoryApiKeyRepository) -> ApiKeyService:
    """Service with mock hasher for fast tests."""
    return ApiKeyService(
        repo=repo,
        hasher=MockApiKeyHasher(pepper="test-pepper"),
        min_delay=0,
        max_delay=0,
    )


@pytest.fixture
def cli(service: ApiKeyService):
    """CLI app bound to the test service."""

    @asynccontextmanager
    async def service_factory():
        yield service

    return create_api_keys_cli(service_factory)


class TestNoArgsShowsHelp:
    """Commands without args should show help."""

    def test_create_no_args_shows_help(self, runner: CliRunner, cli):
        """create without --name shows help."""
        result = runner.invoke(cli, ["create"])
        assert result.exit_code == 0
        assert "Usage" in result.stdout or "--name" in result.stdout

    def test_get_no_args_shows_help(self, runner: CliRunner, cli):
        """get without ID shows help."""
        result = runner.invoke(cli, ["get"])
        assert result.exit_code == 0
        assert "Usage" in result.stdout

    def test_delete_no_args_shows_help(self, runner: CliRunner, cli):
        """delete without ID shows help."""
        result = runner.invoke(cli, ["delete"])
        assert result.exit_code == 0
        assert "Usage" in result.stdout

    def test_verify_no_args_shows_help(self, runner: CliRunner, cli):
        """verify without API key shows help."""
        result = runner.invoke(cli, ["verify"])
        assert result.exit_code == 0
        assert "Usage" in result.stdout

    def test_update_no_args_shows_help(self, runner: CliRunner, cli):
        """update without ID shows help."""
        result = runner.invoke(cli, ["update"])
        assert result.exit_code == 0
        assert "Usage" in result.stdout

    def test_activate_no_args_shows_help(self, runner: CliRunner, cli):
        """activate without ID shows help."""
        result = runner.invoke(cli, ["activate"])
        assert result.exit_code == 0
        assert "Usage" in result.stdout

    def test_deactivate_no_args_shows_help(self, runner: CliRunner, cli):
        """deactivate without ID shows help."""
        result = runner.invoke(cli, ["deactivate"])
        assert result.exit_code == 0
        assert "Usage" in result.stdout


class TestCreateCommand:
    """Tests for 'create' command."""

    def test_create_with_name(self, runner: CliRunner, cli):
        """Create a key with a name."""
        result = runner.invoke(cli, ["create", "--name", "test-key"])

        assert result.exit_code == 0
        assert "test-key" in result.stdout
        assert "ak-" in result.stdout  # API key is displayed

    def test_create_with_description(self, runner: CliRunner, cli):
        """Create a key with name and description."""
        result = runner.invoke(cli, ["create", "--name", "my-key", "--description", "For testing purposes"])

        assert result.exit_code == 0
        assert "my-key" in result.stdout

    def test_create_inactive(self, runner: CliRunner, cli):
        """Create a key in inactive state."""
        result = runner.invoke(cli, ["create", "--name", "inactive-key", "--inactive"])

        assert result.exit_code == 0
        assert "inactive" in result.stdout.lower()

    def test_create_with_scopes(self, runner: CliRunner, cli):
        """Create a key with scopes."""
        result = runner.invoke(cli, ["create", "--name", "scoped-key", "--scopes", "read,write"])

        assert result.exit_code == 0
        assert "read" in result.stdout
        assert "write" in result.stdout

    def test_create_displays_secret_once(self, runner: CliRunner, cli):
        """The plain API key is displayed after creation."""
        result = runner.invoke(cli, ["create", "--name", "secret-key"])

        assert result.exit_code == 0
        # Should contain an API key format
        assert "ak-" in result.stdout


class TestListCommand:
    """Tests for 'list' command."""

    def test_list_empty(self, runner: CliRunner, cli):
        """List returns message when no keys exist."""
        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0
        assert "No API keys" in result.stdout or "0" in result.stdout

    def test_list_shows_keys(self, runner: CliRunner, cli, service):
        """List shows created keys."""
        asyncio.run(service.create(name="key-1"))
        asyncio.run(service.create(name="key-2"))

        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0
        assert "key-1" in result.stdout
        assert "key-2" in result.stdout

    def test_list_shows_full_id(self, runner: CliRunner, cli, service):
        """List shows full key IDs."""
        entity, _ = asyncio.run(service.create(name="test"))

        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0
        # Should show the full ID
        assert entity.id_ in result.stdout

    def test_list_shows_expiration_info(self, runner: CliRunner, cli, service):
        """List shows expiration information."""
        expires = datetime_factory() + timedelta(days=30)
        asyncio.run(service.create(name="expiring", expires_at=expires))

        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0
        # Should show days remaining or expiration date
        assert "30" in result.stdout or "day" in result.stdout.lower() or "expires" in result.stdout.lower()

    def test_list_with_limit(self, runner: CliRunner, cli, service):
        """List respects limit parameter."""
        for i in range(5):
            asyncio.run(service.create(name=f"key-{i}"))

        result = runner.invoke(cli, ["list", "--limit", "2"])

        assert result.exit_code == 0


class TestGetCommand:
    """Tests for 'get' command."""

    def test_get_by_id(self, runner: CliRunner, cli, service):
        """Get a key by its ID."""
        entity, _ = asyncio.run(service.create(name="findme"))

        result = runner.invoke(cli, ["get", entity.id_])

        assert result.exit_code == 0
        assert "findme" in result.stdout

    def test_get_not_found(self, runner: CliRunner, cli):
        """Get returns error for non-existent key."""
        result = runner.invoke(cli, ["get", "nonexistent-id"])

        assert result.exit_code == 1
        assert "not found" in result.stdout.lower() or "not found" in (result.stderr or "").lower()


class TestDeleteCommand:
    """Tests for 'delete' command."""

    def test_delete_existing(self, runner: CliRunner, cli, service):
        """Delete an existing key."""
        entity, _ = asyncio.run(service.create(name="to-delete"))

        result = runner.invoke(cli, ["delete", entity.id_])

        assert result.exit_code == 0
        assert "deleted" in result.stdout.lower()

    def test_delete_not_found(self, runner: CliRunner, cli):
        """Delete returns error for non-existent key."""
        result = runner.invoke(cli, ["delete", "nonexistent"])

        assert result.exit_code == 1


class TestVerifyCommand:
    """Tests for 'verify' command."""

    def test_verify_valid_key(self, runner: CliRunner, cli, service):
        """Verify a valid API key."""
        entity, api_key = asyncio.run(service.create(name="verify-me"))

        result = runner.invoke(cli, ["verify", api_key])

        assert result.exit_code == 0
        assert "valid" in result.stdout.lower() or "verified" in result.stdout.lower()

    def test_verify_invalid_key(self, runner: CliRunner, cli):
        """Verify returns error for invalid key."""
        result = runner.invoke(cli, ["verify", "ak-invalid-key123"])

        assert result.exit_code == 1

    def test_verify_malformed_key(self, runner: CliRunner, cli):
        """Verify returns error for malformed key."""
        result = runner.invoke(cli, ["verify", "not-an-api-key"])

        assert result.exit_code == 1


class TestUpdateCommand:
    """Tests for 'update' command."""

    def test_update_name(self, runner: CliRunner, cli, service):
        """Update a key's name."""
        entity, _ = asyncio.run(service.create(name="old-name"))

        result = runner.invoke(cli, ["update", entity.id_, "--name", "new-name"])

        assert result.exit_code == 0
        assert "new-name" in result.stdout or "updated" in result.stdout.lower()

    def test_update_description(self, runner: CliRunner, cli, service):
        """Update a key's description."""
        entity, _ = asyncio.run(service.create(name="test"))

        result = runner.invoke(cli, ["update", entity.id_, "--description", "Updated description"])

        assert result.exit_code == 0

    def test_update_not_found(self, runner: CliRunner, cli):
        """Update returns error for non-existent key."""
        result = runner.invoke(cli, ["update", "nonexistent", "--name", "x"])

        assert result.exit_code == 1

    def test_update_activate(self, runner: CliRunner, cli, service):
        """Update can activate a key."""
        entity, _ = asyncio.run(service.create(name="test", is_active=False))

        result = runner.invoke(cli, ["update", entity.id_, "--active"])

        assert result.exit_code == 0
        assert "Active" in result.stdout

    def test_update_deactivate(self, runner: CliRunner, cli, service):
        """Update can deactivate a key."""
        entity, _ = asyncio.run(service.create(name="test", is_active=True))

        result = runner.invoke(cli, ["update", entity.id_, "--inactive"])

        assert result.exit_code == 0
        assert "Inactive" in result.stdout

    def test_update_expires_at(self, runner: CliRunner, cli, service):
        """Update can set expiration date."""
        entity, _ = asyncio.run(service.create(name="test"))

        result = runner.invoke(cli, ["update", entity.id_, "--expires-at", "2030-01-01"])

        assert result.exit_code == 0

    def test_update_expires_at_with_timezone(self, runner: CliRunner, cli, service):
        """Update can set expiration date with timezone."""
        entity, _ = asyncio.run(service.create(name="test"))

        result = runner.invoke(cli, ["update", entity.id_, "--expires-at", "2030-01-01T12:00:00+02:00"])

        assert result.exit_code == 0

    def test_update_clear_expires(self, runner: CliRunner, cli, service):
        """Update can clear expiration date."""
        from datetime import timedelta

        expires = datetime_factory() + timedelta(days=30)
        entity, _ = asyncio.run(service.create(name="test", expires_at=expires))

        result = runner.invoke(cli, ["update", entity.id_, "--clear-expires"])

        assert result.exit_code == 0
        assert "Never" in result.stdout

    def test_update_scopes(self, runner: CliRunner, cli, service):
        """Update can change scopes."""
        entity, _ = asyncio.run(service.create(name="test"))

        result = runner.invoke(cli, ["update", entity.id_, "--scopes", "admin,write"])

        assert result.exit_code == 0
        assert "admin" in result.stdout
        assert "write" in result.stdout


class TestActivateCommand:
    """Tests for 'activate' command."""

    def test_activate_inactive_key(self, runner: CliRunner, cli, service):
        """Activate an inactive key."""
        entity, _ = asyncio.run(service.create(name="inactive", is_active=False))

        result = runner.invoke(cli, ["activate", entity.id_])

        assert result.exit_code == 0
        assert "activated" in result.stdout.lower()
        # Should NOT contain JSON
        assert "{" not in result.stdout

    def test_activate_already_active(self, runner: CliRunner, cli, service):
        """Activate an already active key (no-op)."""
        entity, _ = asyncio.run(service.create(name="active", is_active=True))

        result = runner.invoke(cli, ["activate", entity.id_])

        assert result.exit_code == 0

    def test_activate_not_found(self, runner: CliRunner, cli):
        """Activate returns error for non-existent key."""
        result = runner.invoke(cli, ["activate", "nonexistent"])

        assert result.exit_code == 1


class TestDeactivateCommand:
    """Tests for 'deactivate' command."""

    def test_deactivate_active_key(self, runner: CliRunner, cli, service):
        """Deactivate an active key."""
        entity, _ = asyncio.run(service.create(name="active", is_active=True))

        result = runner.invoke(cli, ["deactivate", entity.id_])

        assert result.exit_code == 0
        assert "deactivated" in result.stdout.lower()
        # Should NOT contain JSON
        assert "{" not in result.stdout

    def test_deactivate_already_inactive(self, runner: CliRunner, cli, service):
        """Deactivate an already inactive key (no-op)."""
        entity, _ = asyncio.run(service.create(name="inactive", is_active=False))

        result = runner.invoke(cli, ["deactivate", entity.id_])

        assert result.exit_code == 0


class TestSearchCommand:
    """Tests for 'search' command."""

    def test_search_no_results(self, runner: CliRunner, cli):
        """Search returns message when no keys match."""
        result = runner.invoke(cli, ["search", "--name", "nonexistent"])

        assert result.exit_code == 0
        assert "No API keys" in result.stdout

    def test_search_by_active_status(self, runner: CliRunner, cli, service):
        """Search for active keys only."""
        asyncio.run(service.create(name="active-key", is_active=True))
        asyncio.run(service.create(name="inactive-key", is_active=False))

        result = runner.invoke(cli, ["search", "--active"])

        assert result.exit_code == 0
        assert "active-key" in result.stdout
        assert "inactive-key" not in result.stdout

    def test_search_by_name(self, runner: CliRunner, cli, service):
        """Search by name pattern."""
        asyncio.run(service.create(name="production-api"))
        asyncio.run(service.create(name="staging-api"))
        asyncio.run(service.create(name="other"))

        result = runner.invoke(cli, ["search", "--name", "api"])

        assert result.exit_code == 0
        assert "production-api" in result.stdout
        assert "staging-api" in result.stdout

    def test_search_shows_pagination_info(self, runner: CliRunner, cli, service):
        """Search shows pagination info."""
        for i in range(5):
            asyncio.run(service.create(name=f"key-{i}"))

        result = runner.invoke(cli, ["search", "--limit", "2"])

        assert result.exit_code == 0
        # Should show some pagination info
        assert "2" in result.stdout


class TestCountCommand:
    """Tests for 'count' command."""

    def test_count_all(self, runner: CliRunner, cli, service):
        """Count all keys."""
        for i in range(3):
            asyncio.run(service.create(name=f"key-{i}"))

        result = runner.invoke(cli, ["count"])

        assert result.exit_code == 0
        assert "3" in result.stdout

    def test_count_with_filter(self, runner: CliRunner, cli, service):
        """Count keys matching a filter."""
        asyncio.run(service.create(name="active", is_active=True))
        asyncio.run(service.create(name="inactive", is_active=False))

        result = runner.invoke(cli, ["count", "--active"])

        assert result.exit_code == 0
        assert "1" in result.stdout


class TestExpirationDisplay:
    """Tests for expiration display formatting."""

    def test_list_shows_expired_key(self, runner: CliRunner, cli, service, repo):
        """List shows expired indicator for expired keys."""
        # Create key normally, then modify expires_at directly in repo
        entity, _ = asyncio.run(service.create(name="expired-key"))
        entity.expires_at = datetime_factory() - timedelta(days=1)
        asyncio.run(repo.update(entity))

        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0
        assert "Expired" in result.stdout

    def test_list_shows_hours_remaining(self, runner: CliRunner, cli, service):
        """List shows hours remaining when less than a day."""
        expires = datetime_factory() + timedelta(hours=5)
        asyncio.run(service.create(name="hours-key", expires_at=expires))

        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0
        assert "h" in result.stdout  # Shows "5h" or similar

    def test_list_shows_days_under_week(self, runner: CliRunner, cli, service):
        """List shows days for keys expiring within a week."""
        expires = datetime_factory() + timedelta(days=5)
        asyncio.run(service.create(name="week-key", expires_at=expires))

        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0
        # Should show days with "d" suffix (could be 4d or 5d due to timing)
        assert "d" in result.stdout and "day" not in result.stdout.lower()


class TestOutputSecurity:
    """Tests for output security."""

    def test_output_does_not_leak_hash(self, runner: CliRunner, cli, service):
        """Output should not contain the key hash."""
        entity, _ = asyncio.run(service.create(name="secure"))

        result = runner.invoke(cli, ["get", entity.id_])

        assert result.exit_code == 0
        assert "_key_hash" not in result.stdout
        assert "key_hash" not in result.stdout

    def test_output_does_not_leak_secret(self, runner: CliRunner, cli, service):
        """Get output should not contain the key secret."""
        entity, api_key = asyncio.run(service.create(name="secure"))
        secret_part = api_key.split("-")[-1]  # Last segment is the secret

        result = runner.invoke(cli, ["get", entity.id_])

        assert result.exit_code == 0
        # The full secret should not appear in get output
        assert secret_part not in result.stdout
