"""CLI module for managing API keys via Typer.

Provides commands for CRUD operations on API keys using the service layer.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, List, Optional

from fastapi_api_key._types import ServiceFactory
from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.domain.errors import (
    ApiKeyError,
    InvalidKey,
    KeyExpired,
    KeyInactive,
    KeyNotFound,
    KeyNotProvided,
)
from fastapi_api_key.repositories.base import ApiKeyFilter

# Domain errors that should result in exit code 1
DomainErrors = (
    InvalidKey,
    KeyExpired,
    KeyInactive,
    KeyNotFound,
    KeyNotProvided,
    ApiKeyError,
)


def create_api_keys_cli(
    service_factory: ServiceFactory,
    app: Optional[Any] = None,
) -> Any:
    """Build a Typer CLI bound to an ApiKeyService.

    Args:
        service_factory: Async context manager factory returning the service.
        app: Optional pre-configured Typer instance to extend.

    Returns:
        A configured Typer application with API key management commands.
    """
    typer = _import_typer()
    cli = app or typer.Typer(
        help="Manage API keys.",
        no_args_is_help=True,
        pretty_exceptions_enable=False,
    )

    # --- Helpers ---

    def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
        """Run an async coroutine synchronously."""
        try:
            return asyncio.run(coro)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    def handle_errors(func: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        """Execute async function with domain error handling."""
        try:
            run_async(func())
        except DomainErrors as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc

    def output_entity(entity: ApiKey, message: Optional[str] = None) -> None:
        """Output an entity as JSON with optional message."""
        if message:
            typer.secho(message, fg=typer.colors.GREEN)
        typer.echo(format_entity(entity))

    def output_entities(entities: List[ApiKey], message: Optional[str] = None) -> None:
        """Output multiple entities as JSON array."""
        if message:
            typer.secho(message, fg=typer.colors.BLUE)
        typer.echo(json.dumps([serialize_entity(e) for e in entities], indent=2))

    # --- Commands ---

    @cli.command("create")
    def create_key(
        name: Optional[str] = typer.Option(None, "--name", "-n", help="Human-readable name."),
        description: Optional[str] = typer.Option(None, "--description", "-d", help="Description."),
        inactive: bool = typer.Option(False, "--inactive/--active", help="Create as inactive."),
        expires_at: Optional[str] = typer.Option(None, "--expires-at", help="ISO datetime expiration."),
        scopes: Optional[str] = typer.Option(None, "--scopes", "-s", help="Comma-separated scopes."),
    ) -> None:
        """Create a new API key."""

        async def _run() -> None:
            async with service_factory() as service:
                parsed_expires = parse_datetime(expires_at) if expires_at else None
                parsed_scopes = parse_scopes(scopes)

                entity, api_key = await service.create(
                    name=name,
                    description=description,
                    is_active=not inactive,
                    expires_at=parsed_expires,
                    scopes=parsed_scopes,
                )

                output_entity(entity, "API key created successfully.")
                typer.secho(
                    "Plain secret (store securely, shown only once):",
                    fg=typer.colors.YELLOW,
                )
                typer.echo(api_key)

        handle_errors(_run)

    @cli.command("list")
    def list_keys(
        limit: int = typer.Option(20, "--limit", "-l", min=1, help="Max keys to show."),
        offset: int = typer.Option(0, "--offset", "-o", min=0, help="Skip first N keys."),
    ) -> None:
        """List API keys with pagination."""

        async def _run() -> None:
            async with service_factory() as service:
                items = await service.list(limit=limit, offset=offset)
                if not items:
                    typer.echo("No API keys found.")
                    return
                output_entities(items, f"Found {len(items)} API key(s):")

        handle_errors(_run)

    @cli.command("get")
    def get_key(
        id_: str = typer.Argument(..., help="ID of the key."),
    ) -> None:
        """Get an API key by ID."""

        async def _run() -> None:
            async with service_factory() as service:
                entity = await service.get_by_id(id_)
                output_entity(entity)

        handle_errors(_run)

    @cli.command("delete")
    def delete_key(
        id_: str = typer.Argument(..., help="ID of the key to delete."),
    ) -> None:
        """Delete an API key."""

        async def _run() -> None:
            async with service_factory() as service:
                await service.delete_by_id(id_)
                typer.secho(f"Deleted API key '{id_}'.", fg=typer.colors.GREEN)

        handle_errors(_run)

    @cli.command("verify")
    def verify_key(
        api_key: str = typer.Argument(..., help="Full API key string."),
    ) -> None:
        """Verify an API key."""

        async def _run() -> None:
            async with service_factory() as service:
                entity = await service.verify_key(api_key)
                typer.secho("API key verified.", fg=typer.colors.GREEN)
                output_entity(entity)

        handle_errors(_run)

    @cli.command("update")
    def update_key(
        id_: str = typer.Argument(..., help="ID of the key to update."),
        name: Optional[str] = typer.Option(None, "--name", "-n", help="New name."),
        description: Optional[str] = typer.Option(None, "--description", "-d", help="New description."),
        expires_at: Optional[str] = typer.Option(None, "--expires-at", help="New expiration (ISO datetime)."),
        clear_expires: bool = typer.Option(False, "--clear-expires", help="Remove expiration."),
        scopes: Optional[str] = typer.Option(None, "--scopes", "-s", help="New scopes (comma-separated)."),
    ) -> None:
        """Update an API key's metadata."""

        async def _run() -> None:
            async with service_factory() as service:
                entity = await service.get_by_id(id_)

                if name is not None:
                    entity.name = name
                if description is not None:
                    entity.description = description
                if expires_at is not None:
                    entity.expires_at = parse_datetime(expires_at)
                if clear_expires:
                    entity.expires_at = None
                if scopes is not None:
                    entity.scopes = parse_scopes(scopes)

                updated = await service.update(entity)
                output_entity(updated, "API key updated.")

        handle_errors(_run)

    @cli.command("activate")
    def activate_key(
        id_: str = typer.Argument(..., help="ID of the key to activate."),
    ) -> None:
        """Activate an API key."""

        async def _run() -> None:
            async with service_factory() as service:
                entity = await service.get_by_id(id_)
                entity.enable()
                updated = await service.update(entity)
                output_entity(updated, "API key activated.")

        handle_errors(_run)

    @cli.command("deactivate")
    def deactivate_key(
        id_: str = typer.Argument(..., help="ID of the key to deactivate."),
    ) -> None:
        """Deactivate an API key."""

        async def _run() -> None:
            async with service_factory() as service:
                entity = await service.get_by_id(id_)
                entity.disable()
                updated = await service.update(entity)
                output_entity(updated, "API key deactivated.")

        handle_errors(_run)

    @cli.command("revoke")
    def revoke_key(
        id_: str = typer.Argument(..., help="ID of the key to revoke."),
    ) -> None:
        """Revoke (deactivate) an API key."""

        async def _run() -> None:
            async with service_factory() as service:
                entity = await service.get_by_id(id_)
                entity.disable()
                updated = await service.update(entity)
                output_entity(updated, "API key revoked.")

        handle_errors(_run)

    @cli.command("search")
    def search_keys(
        limit: int = typer.Option(20, "--limit", "-l", min=1, help="Max keys to show."),
        offset: int = typer.Option(0, "--offset", "-o", min=0, help="Skip first N keys."),
        active: Optional[bool] = typer.Option(None, "--active/--inactive", help="Filter by status."),
        name: Optional[str] = typer.Option(None, "--name", "-n", help="Name contains."),
        scopes: Optional[str] = typer.Option(None, "--scopes", "-s", help="Must have ALL scopes."),
        never_used: Optional[bool] = typer.Option(None, "--never-used/--used", help="Filter by usage."),
    ) -> None:
        """Search API keys with filters."""

        async def _run() -> None:
            async with service_factory() as service:
                filter_ = ApiKeyFilter(
                    is_active=active,
                    name_contains=name,
                    scopes_contain_all=parse_scopes(scopes),
                    never_used=never_used,
                    limit=limit,
                    offset=offset,
                )
                items = await service.find(filter_)
                total = await service.count(filter_)

                if not items:
                    typer.echo("No API keys found.")
                    return

                output_entities(items, f"Found {len(items)} of {total} matching key(s):")

        handle_errors(_run)

    @cli.command("count")
    def count_keys(
        active: Optional[bool] = typer.Option(None, "--active/--inactive", help="Filter by status."),
        name: Optional[str] = typer.Option(None, "--name", "-n", help="Name contains."),
        never_used: Optional[bool] = typer.Option(None, "--never-used/--used", help="Filter by usage."),
    ) -> None:
        """Count API keys."""

        async def _run() -> None:
            async with service_factory() as service:
                filter_ = ApiKeyFilter(
                    is_active=active,
                    name_contains=name,
                    never_used=never_used,
                )
                total = await service.count(filter_)
                typer.secho(f"Total: {total}", fg=typer.colors.BLUE)

        handle_errors(_run)

    return cli


# --- Utility Functions ---


def parse_datetime(value: str) -> datetime:
    """Parse ISO datetime string to UTC datetime."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_scopes(value: Optional[str]) -> Optional[List[str]]:
    """Parse comma-separated scopes string."""
    if not value:
        return None
    return [s.strip() for s in value.split(",") if s.strip()]


def serialize_entity(entity: ApiKey) -> dict[str, Any]:
    """Serialize ApiKey to dict for JSON output.

    Excludes sensitive fields like key_hash.
    """
    return {
        "id": entity.id_,
        "name": entity.name,
        "description": entity.description,
        "is_active": entity.is_active,
        "expires_at": entity.expires_at.isoformat() if entity.expires_at else None,
        "created_at": entity.created_at.isoformat() if entity.created_at else None,
        "last_used_at": entity.last_used_at.isoformat() if entity.last_used_at else None,
        "key_id": entity.key_id,
        "scopes": entity.scopes,
    }


def format_entity(entity: ApiKey) -> str:
    """Format ApiKey as JSON string."""
    return json.dumps(serialize_entity(entity), indent=2)


def _import_typer() -> Any:
    """Import typer with helpful error message."""
    try:
        import typer
    except ImportError as exc:
        raise RuntimeError("Typer is required. Install with: pip install fastapi-api-key[cli]") from exc
    return typer
