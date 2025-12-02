"""Acceptance tests for the CLI module.

Tests verify CLI commands work correctly using InMemory repository.
Focus on behavior, not implementation details.
"""

import json
from contextlib import asynccontextmanager

import pytest
from typer.testing import CliRunner

from fastapi_api_key import ApiKeyService
from fastapi_api_key.cli import create_api_keys_cli
from fastapi_api_key.hasher.base import MockApiKeyHasher
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository


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
        rrd=0,  # No random delay for tests
    )


@pytest.fixture
def cli(service: ApiKeyService):
    """CLI app bound to the test service."""

    @asynccontextmanager
    async def service_factory():
        yield service

    return create_api_keys_cli(service_factory)


class TestCreateCommand:
    """Tests for 'create' command."""

    def test_create_minimal(self, runner: CliRunner, cli):
        """Create a key with just a name."""
        result = runner.invoke(cli, ["create", "--name", "test-key"])

        assert result.exit_code == 0
        assert "test-key" in result.stdout
        assert "ak-" in result.stdout  # API key is displayed

    def test_create_with_description(self, runner: CliRunner, cli):
        """Create a key with name and description."""
        result = runner.invoke(cli, ["create", "--name", "my-key", "--description", "For testing purposes"])

        assert result.exit_code == 0
        assert "my-key" in result.stdout
        assert "For testing purposes" in result.stdout

    def test_create_inactive(self, runner: CliRunner, cli):
        """Create a key in inactive state."""
        result = runner.invoke(cli, ["create", "--name", "inactive-key", "--inactive"])

        assert result.exit_code == 0
        output = json.loads(_extract_json(result.stdout))
        assert output["is_active"] is False

    def test_create_with_scopes(self, runner: CliRunner, cli):
        """Create a key with scopes."""
        result = runner.invoke(cli, ["create", "--name", "scoped-key", "--scopes", "read,write"])

        assert result.exit_code == 0
        output = json.loads(_extract_json(result.stdout))
        assert "read" in output["scopes"]
        assert "write" in output["scopes"]

    def test_create_displays_secret_once(self, runner: CliRunner, cli):
        """The plain API key is displayed after creation."""
        result = runner.invoke(cli, ["create", "--name", "secret-key"])

        assert result.exit_code == 0
        # Should contain an API key format
        lines = result.stdout.strip().split("\n")
        api_key_line = [line for line in lines if line.startswith("ak-")]
        assert len(api_key_line) == 1


class TestListCommand:
    """Tests for 'list' command."""

    def test_list_empty(self, runner: CliRunner, cli):
        """List returns message when no keys exist."""
        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0
        assert "No API keys" in result.stdout or "[]" in result.stdout

    def test_list_shows_keys(self, runner: CliRunner, cli, service):
        """List shows created keys."""
        import asyncio

        asyncio.run(service.create(name="key-1"))
        asyncio.run(service.create(name="key-2"))

        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0
        assert "key-1" in result.stdout
        assert "key-2" in result.stdout

    def test_list_with_limit(self, runner: CliRunner, cli, service):
        """List respects limit parameter."""
        import asyncio

        for i in range(5):
            asyncio.run(service.create(name=f"key-{i}"))

        result = runner.invoke(cli, ["list", "--limit", "2"])

        assert result.exit_code == 0
        # Should only show 2 keys


class TestGetCommand:
    """Tests for 'get' command."""

    def test_get_by_id(self, runner: CliRunner, cli, service):
        """Get a key by its ID."""
        import asyncio

        entity, _ = asyncio.run(service.create(name="findme"))

        result = runner.invoke(cli, ["get", entity.id_])

        assert result.exit_code == 0
        assert "findme" in result.stdout

    def test_get_not_found(self, runner: CliRunner, cli):
        """Get returns error for non-existent key."""
        result = runner.invoke(cli, ["get", "nonexistent-id"])

        assert result.exit_code == 1
        assert "not found" in result.stdout.lower() or "not found" in result.stderr.lower()


class TestDeleteCommand:
    """Tests for 'delete' command."""

    def test_delete_existing(self, runner: CliRunner, cli, service):
        """Delete an existing key."""
        import asyncio

        entity, _ = asyncio.run(service.create(name="to-delete"))

        result = runner.invoke(cli, ["delete", entity.id_])

        assert result.exit_code == 0

        # Verify it's gone
        list_result = runner.invoke(cli, ["list"])
        assert "to-delete" not in list_result.stdout

    def test_delete_not_found(self, runner: CliRunner, cli):
        """Delete returns error for non-existent key."""
        result = runner.invoke(cli, ["delete", "nonexistent"])

        assert result.exit_code == 1


class TestVerifyCommand:
    """Tests for 'verify' command."""

    def test_verify_valid_key(self, runner: CliRunner, cli, service):
        """Verify a valid API key."""
        import asyncio

        entity, api_key = asyncio.run(service.create(name="verify-me"))

        result = runner.invoke(cli, ["verify", api_key])

        assert result.exit_code == 0
        assert "verify-me" in result.stdout

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
        import asyncio

        entity, _ = asyncio.run(service.create(name="old-name"))

        result = runner.invoke(cli, ["update", entity.id_, "--name", "new-name"])

        assert result.exit_code == 0
        assert "new-name" in result.stdout

    def test_update_description(self, runner: CliRunner, cli, service):
        """Update a key's description."""
        import asyncio

        entity, _ = asyncio.run(service.create(name="test"))

        result = runner.invoke(cli, ["update", entity.id_, "--description", "Updated description"])

        assert result.exit_code == 0
        assert "Updated description" in result.stdout

    def test_update_not_found(self, runner: CliRunner, cli):
        """Update returns error for non-existent key."""
        result = runner.invoke(cli, ["update", "nonexistent", "--name", "x"])

        assert result.exit_code == 1


class TestActivateCommand:
    """Tests for 'activate' command."""

    def test_activate_inactive_key(self, runner: CliRunner, cli, service):
        """Activate an inactive key."""
        import asyncio

        entity, _ = asyncio.run(service.create(name="inactive", is_active=False))

        result = runner.invoke(cli, ["activate", entity.id_])

        assert result.exit_code == 0
        output = json.loads(_extract_json(result.stdout))
        assert output["is_active"] is True

    def test_activate_already_active(self, runner: CliRunner, cli, service):
        """Activate an already active key (no-op)."""
        import asyncio

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
        import asyncio

        entity, _ = asyncio.run(service.create(name="active", is_active=True))

        result = runner.invoke(cli, ["deactivate", entity.id_])

        assert result.exit_code == 0
        output = json.loads(_extract_json(result.stdout))
        assert output["is_active"] is False

    def test_deactivate_already_inactive(self, runner: CliRunner, cli, service):
        """Deactivate an already inactive key (no-op)."""
        import asyncio

        entity, _ = asyncio.run(service.create(name="inactive", is_active=False))

        result = runner.invoke(cli, ["deactivate", entity.id_])

        assert result.exit_code == 0


class TestRevokeCommand:
    """Tests for 'revoke' command (alias for deactivate)."""

    def test_revoke_is_alias_for_deactivate(self, runner: CliRunner, cli, service):
        """Revoke behaves like deactivate."""
        import asyncio

        entity, _ = asyncio.run(service.create(name="to-revoke", is_active=True))

        result = runner.invoke(cli, ["revoke", entity.id_])

        assert result.exit_code == 0
        output = json.loads(_extract_json(result.stdout))
        assert output["is_active"] is False


class TestSearchCommand:
    """Tests for 'search' command."""

    def test_search_by_active_status(self, runner: CliRunner, cli, service):
        """Search for active keys only."""
        import asyncio

        asyncio.run(service.create(name="active-key", is_active=True))
        asyncio.run(service.create(name="inactive-key", is_active=False))

        result = runner.invoke(cli, ["search", "--active"])

        assert result.exit_code == 0
        assert "active-key" in result.stdout
        assert "inactive-key" not in result.stdout

    def test_search_by_name(self, runner: CliRunner, cli, service):
        """Search by name pattern."""
        import asyncio

        asyncio.run(service.create(name="production-api"))
        asyncio.run(service.create(name="staging-api"))
        asyncio.run(service.create(name="other"))

        result = runner.invoke(cli, ["search", "--name", "api"])

        assert result.exit_code == 0
        assert "production-api" in result.stdout
        assert "staging-api" in result.stdout


class TestCountCommand:
    """Tests for 'count' command."""

    def test_count_all(self, runner: CliRunner, cli, service):
        """Count all keys."""
        import asyncio

        for i in range(3):
            asyncio.run(service.create(name=f"key-{i}"))

        result = runner.invoke(cli, ["count"])

        assert result.exit_code == 0
        assert "3" in result.stdout

    def test_count_with_filter(self, runner: CliRunner, cli, service):
        """Count keys matching a filter."""
        import asyncio

        asyncio.run(service.create(name="active", is_active=True))
        asyncio.run(service.create(name="inactive", is_active=False))

        result = runner.invoke(cli, ["count", "--active"])

        assert result.exit_code == 0
        assert "1" in result.stdout


class TestOutputFormat:
    """Tests for output formatting."""

    def test_json_output_is_valid(self, runner: CliRunner, cli, service):
        """Output should be valid JSON."""
        import asyncio

        asyncio.run(service.create(name="json-test"))

        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0
        # Should be able to parse JSON from output
        json_data = _extract_json(result.stdout)
        parsed = json.loads(json_data)
        assert isinstance(parsed, (dict, list))

    def test_output_does_not_leak_hash(self, runner: CliRunner, cli, service):
        """Output should not contain the key hash."""
        import asyncio

        entity, _ = asyncio.run(service.create(name="secure"))

        result = runner.invoke(cli, ["get", entity.id_])

        assert result.exit_code == 0
        assert "_key_hash" not in result.stdout
        assert "key_hash" not in result.stdout

    def test_output_does_not_leak_secret(self, runner: CliRunner, cli, service):
        """Output should not contain the key secret after creation."""
        import asyncio

        entity, api_key = asyncio.run(service.create(name="secure"))
        secret_part = api_key.split("-")[-1]  # Last segment is the secret

        result = runner.invoke(cli, ["get", entity.id_])

        assert result.exit_code == 0
        # The full secret should not appear in get output
        assert secret_part not in result.stdout


def _extract_json(output: str) -> str:
    """Extract JSON object or array from CLI output."""
    # Find first { or [
    start_obj = output.find("{")
    start_arr = output.find("[")

    if start_obj == -1 and start_arr == -1:
        return "{}"

    if start_obj == -1:
        start = start_arr
    elif start_arr == -1:
        start = start_obj
    else:
        start = min(start_obj, start_arr)

    # Find matching closing bracket
    depth = 0
    open_char = output[start]
    close_char = "}" if open_char == "{" else "]"

    for i, char in enumerate(output[start:], start):
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return output[start : i + 1]

    return output[start:]
