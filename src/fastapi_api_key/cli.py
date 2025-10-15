import asyncio
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from fastapi_api_key.domain.base import ApiKeyEntity
from fastapi_api_key.domain.errors import (
    InvalidKey,
    KeyExpired,
    KeyInactive,
    KeyNotFound,
    KeyNotProvided,
)
from fastapi_api_key.types import ServiceFactory

DomainErrors = (
    InvalidKey,
    KeyExpired,
    KeyInactive,
    KeyNotFound,
    KeyNotProvided,
)


def create_api_keys_cli(
    service_factory: ServiceFactory,
    app: Optional[Any] = None,
) -> Any:
    """Build a Typer CLI bound to an :class:`AbstractApiKeyService`.

    Args:
        service_factory: Async context manager factory returning the service to use for each command.
        app: Optional pre-configured Typer instance to extend. A new one is created if omitted.

    Returns:
        A configured Typer application exposing CRUD helpers for API keys.
    """

    typer = _import_typer()
    cli = app or typer.Typer(help="Manage API keys using fastapi-api-key services.", no_args_is_help=True)

    def run_async(coro: Awaitable[Any]) -> Any:
        try:
            return asyncio.run(coro)  # type: ignore[arg-type]
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    @cli.command("create")
    def create_key(  # type: ignore[misc]
        name: Optional[str] = typer.Option(None, "--name", "-n", help="Human readable identifier."),
        description: Optional[str] = typer.Option(None, "--description", "-d", help="Purpose of the API key."),
        inactive: bool = typer.Option(False, "--inactive/--active", help="Create the key disabled."),
        expires_at: Optional[str] = typer.Option(
            None,
            "--expires-at",
            help="ISO datetime (UTC if no timezone) for key expiration.",
        ),
        key_secret: Optional[str] = typer.Option(
            None,
            "--secret",
            help="Provide a custom secret; otherwise, one is generated.",
        ),
    ) -> None:
        """Create a new API key and display the plain secret once."""

        async def _create() -> None:
            async with service_factory() as service:
                payload: dict[str, Any] = {
                    "name": name,
                    "description": description,
                    "is_active": not inactive,
                }

                parsed_expires = _parse_datetime(expires_at) if expires_at else None
                if parsed_expires:
                    payload["expires_at"] = parsed_expires

                entity = service.domain_cls(  # type: ignore[call-arg]
                    **{key: value for key, value in payload.items() if value is not None}
                )

                created, api_key = await service.create(entity, key_secret=key_secret)

                typer.secho("API key created successfully.", fg=typer.colors.GREEN)
                typer.echo(_format_entity(created))
                typer.secho(
                    "Plain secret (store securely, it will not be shown again):",
                    fg=typer.colors.YELLOW,
                )
                typer.echo(api_key)

        _execute_with_handling(run_async, _create, typer)

    @cli.command("list")
    def list_keys(  # type: ignore[misc]
        limit: int = typer.Option(20, "--limit", "-l", min=1, help="Maximum number of keys to display."),
        offset: int = typer.Option(0, "--offset", "-o", min=0, help="Skip the first N keys."),
    ) -> None:
        """List API keys with pagination."""

        async def _list() -> None:
            async with service_factory() as service:
                items = await service.list(limit=limit, offset=offset)
                if not items:
                    typer.echo("No API keys found.")
                    return

                typer.secho(f"Found {len(items)} API key(s):", fg=typer.colors.BLUE)
                for entity in items:
                    typer.echo(_format_entity(entity))
                    typer.echo("-" * 40)

        _execute_with_handling(run_async, _list, typer)

    @cli.command("show")
    def show_key(  # type: ignore[misc]
        value: str = typer.Argument(..., help="Identifier value (id or key_id)."),
        by: str = typer.Option("id", "--by", case_sensitive=False, help="Lookup by 'id' or 'key_id'."),
    ) -> None:
        """Display details for a single API key."""

        lookup = by.lower()
        if lookup not in {"id", "key_id"}:
            typer.secho("The --by option must be 'id' or 'key_id'.", fg=typer.colors.RED)
            raise typer.Exit(1)

        async def _show() -> None:
            async with service_factory() as service:
                entity = await service.get_by_id(value) if lookup == "id" else await service.get_by_key_id(value)
                typer.echo(_format_entity(entity))

        _execute_with_handling(run_async, _show, typer)

    @cli.command("delete")
    def delete_key(  # type: ignore[misc]
        id_: str = typer.Argument(..., help="Identifier (id) of the key to delete."),
    ) -> None:
        """Delete an API key by its ID."""

        async def _delete() -> None:
            async with service_factory() as service:
                await service.delete_by_id(id_)
                typer.secho(f"Deleted API key '{id_}'.", fg=typer.colors.GREEN)

        _execute_with_handling(run_async, _delete, typer)

    @cli.command("verify")
    def verify_key(  # type: ignore[misc]
        api_key: str = typer.Argument(..., help="Full API key string."),
    ) -> None:
        """Verify a raw API key string."""

        async def _verify() -> None:
            async with service_factory() as service:
                typer.echo(f"Verifying API key '{api_key}'...")
                entity = await service.verify_key(api_key)
                typer.secho("API key verified.", fg=typer.colors.GREEN)
                typer.echo(_format_entity(entity))

        _execute_with_handling(run_async, _verify, typer)

    @cli.command("update")
    def update_key(  # type: ignore[misc]
        id_: str = typer.Argument(..., help="Identifier (id) of the key to update."),
        name: Optional[str] = typer.Option(None, "--name", "-n", help="New human readable name."),
        description: Optional[str] = typer.Option(
            None,
            "--description",
            "-d",
            help="Updated description.",
        ),
        expires_at: Optional[str] = typer.Option(
            None,
            "--expires-at",
            help="Replace expiration with an ISO datetime. Use with --clear-expires to remove.",
        ),
        clear_expires: bool = typer.Option(
            False,
            "--clear-expires",
            help="Remove the expiration timestamp.",
        ),
        activate: bool = typer.Option(
            False,
            "--activate",
            help="Enable the key after update.",
        ),
        deactivate: bool = typer.Option(
            False,
            "--deactivate",
            help="Disable the key after update.",
        ),
    ) -> None:
        """Update mutable fields of an API key."""

        if activate and deactivate:
            typer.secho("Cannot pass both --activate and --deactivate.", fg=typer.colors.RED)
            raise typer.Exit(1)

        async def _update() -> None:
            async with service_factory() as service:
                entity = await service.get_by_id(id_)

                if name is not None:
                    entity.name = name
                if description is not None:
                    entity.description = description
                if expires_at is not None:
                    entity.expires_at = _parse_datetime(expires_at)
                if clear_expires:
                    entity.expires_at = None
                if activate:
                    entity.enable()
                if deactivate:
                    entity.disable()

                updated = await service.update(entity)
                typer.secho("API key updated.", fg=typer.colors.GREEN)
                typer.echo(_format_entity(updated))

        _execute_with_handling(run_async, _update, typer)

    return cli


def _execute_with_handling(
    runner: Callable[[Awaitable[Any]], Any],
    async_fn: Callable[[], Awaitable[Any]],
    typer_mod: Any,
) -> None:
    try:
        runner(async_fn())
    except DomainErrors as exc:
        typer_mod.secho(str(exc), fg=typer_mod.colors.RED, err=True)
        raise typer_mod.Exit(1) from exc
    except Exception as exc:  # pragma: no cover - defensive fallback
        raise exc


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO datetime string into a UTC datetime.

    Examples:
        >>> _parse_datetime("2024-01-01")
        datetime.datetime(2024, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
        >>> _parse_datetime("2024-01-01T12:34:56+02:00")
        datetime.datetime(2024, 1, 1, 10, 34, 56, tzinfo=datetime.timezone.utc)
        >>> _parse_datetime("2024-01-01T12:34:56")
        datetime.datetime(2024, 1, 1, 12, 34, 56, tzinfo=datetime.timezone.utc)
    """
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _format_entity(entity: ApiKeyEntity) -> str:
    data = _serialize_entity(entity)
    return json.dumps(data, indent=2, sort_keys=True)


def _serialize_entity(entity: ApiKeyEntity) -> dict[str, Any]:
    if is_dataclass(entity):
        data = asdict(entity)
    else:
        data = dict(vars(entity))

    for key, value in list(data.items()):
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


def _import_typer() -> Any:
    try:
        import typer
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "Typer is required to build the CLI. Install it with 'pip install fastapi-api-key[cli]'"
        ) from exc
    return typer
