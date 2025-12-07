"""CLI module for managing API keys via Typer.

Provides commands for CRUD operations on API keys using the service layer.
Uses Rich for beautiful terminal output.
"""

from asyncio import run
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import wraps
from typing import Any, AsyncIterator, Callable, List, Optional

from fastapi_api_key._types import ServiceFactory
from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.domain.errors import ApiKeyError
from fastapi_api_key.repositories.base import ApiKeyFilter, SortableColumn
from fastapi_api_key.services.base import AbstractApiKeyService
from fastapi_api_key.utils import datetime_factory

try:
    import typer
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Typer is required. Install with: pip install fastapi-api-key[cli]") from exc

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Rich is required. Install with: pip install fastapi-api-key[cli]") from exc

# Domain errors that should result in exit code 1
DomainErrors = (ApiKeyError,)

console = Console()


class AsyncTyper(typer.Typer):
    """Typer subclass with native async command support."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.event_handlers: defaultdict[str, list[Callable]] = defaultdict(list)

    def async_command(self, *args: Any, **kwargs: Any) -> Callable:
        """Decorator for async commands."""

        def decorator(async_func: Callable) -> Callable:
            @wraps(async_func)
            def sync_func(*_args: Any, **_kwargs: Any) -> Any:
                self.run_event_handlers("startup")
                try:
                    return run(async_func(*_args, **_kwargs))
                finally:
                    self.run_event_handlers("shutdown")

            self.command(*args, **kwargs)(sync_func)
            return async_func

        return decorator

    def run_event_handlers(self, event_type: str) -> None:
        """Run registered event handlers for the given event type."""
        for event in self.event_handlers[event_type]:  # pragma: no cover
            event()


@asynccontextmanager
async def handle_errors(
    service_factory: ServiceFactory,
) -> AsyncIterator[AbstractApiKeyService]:
    """Async context manager for service access with error handling.

    Yields the service and catches domain errors, converting them to CLI exits.
    """
    try:
        async with service_factory() as service:
            yield service
    except DomainErrors as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc


def create_api_keys_cli(
    service_factory: ServiceFactory,
    app: Optional[AsyncTyper] = None,
) -> AsyncTyper:
    """Build a Typer CLI bound to an ApiKeyService.

    Args:
        service_factory: Async context manager factory returning the service.
        app: Optional pre-configured AsyncTyper instance to extend.

    Returns:
        A configured AsyncTyper application with API key management commands.
    """
    cli = app or AsyncTyper(
        help="Manage API keys.",
        no_args_is_help=True,
        pretty_exceptions_enable=False,
    )

    @cli.async_command("create")
    async def create_key(
        ctx: typer.Context,
        name: Optional[str] = typer.Option(None, "--name", "-n", help="Human-readable name."),
        description: Optional[str] = typer.Option(None, "--description", "-d", help="Description."),
        inactive: bool = typer.Option(False, "--inactive/--active", help="Create as inactive."),
        expires_at: Optional[str] = typer.Option(None, "--expires-at", help="ISO datetime expiration."),
        scopes: Optional[str] = typer.Option(None, "--scopes", "-s", help="Comma-separated scopes."),
    ) -> None:
        """Create a new API key."""
        if name is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(0)

        async with handle_errors(service_factory) as service:
            parsed_expires = parse_datetime(expires_at) if expires_at else None
            parsed_scopes = parse_scopes(scopes)

            entity, api_key = await service.create(
                name=name,
                description=description,
                is_active=not inactive,
                expires_at=parsed_expires,
                scopes=parsed_scopes,
            )

            console.print("[green]API key created successfully.[/green]\n")
            print_entity_detail(entity)
            console.print("\n[yellow]Plain secret (store securely, shown only once):[/yellow]")
            console.print(f"[bold cyan]{api_key}[/bold cyan]")

    @cli.async_command("list")
    async def list_keys(
        limit: int = typer.Option(20, "--limit", "-l", min=1, help="Max keys to show."),
        offset: int = typer.Option(0, "--offset", "-o", min=0, help="Skip first N keys."),
    ) -> None:
        """List API keys with pagination."""
        async with handle_errors(service_factory) as service:
            items = await service.list(limit=limit, offset=offset)
            if not items:
                console.print("[yellow]No API keys found.[/yellow]")
                return
            print_keys_table(items, f"API Keys ({len(items)} shown)")

    @cli.async_command("get")
    async def get_key(
        ctx: typer.Context,
        id_: Optional[str] = typer.Argument(None, help="ID of the key."),
    ) -> None:
        """Get an API key by ID."""
        if id_ is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(0)

        async with handle_errors(service_factory) as service:
            entity = await service.get_by_id(id_)
            print_entity_detail(entity)

    @cli.async_command("delete")
    async def delete_key(
        ctx: typer.Context,
        id_: Optional[str] = typer.Argument(None, help="ID of the key to delete."),
    ) -> None:
        """Delete an API key."""
        if id_ is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(0)

        async with handle_errors(service_factory) as service:
            await service.delete_by_id(id_)
            console.print(f"[green]Deleted API key '{id_}'.[/green]")

    @cli.async_command("verify")
    async def verify_key(
        ctx: typer.Context,
        api_key: Optional[str] = typer.Argument(None, help="Full API key string."),
    ) -> None:
        """Verify an API key."""
        if api_key is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(0)

        async with handle_errors(service_factory) as service:
            entity = await service.verify_key(api_key)
            console.print("[green]API key is valid.[/green]\n")
            print_entity_detail(entity)

    @cli.async_command("update")
    async def update_key(
        ctx: typer.Context,
        id_: Optional[str] = typer.Argument(None, help="ID of the key to update."),
        name: Optional[str] = typer.Option(None, "--name", "-n", help="New name."),
        description: Optional[str] = typer.Option(None, "--description", "-d", help="New description."),
        expires_at: Optional[str] = typer.Option(None, "--expires-at", help="New expiration (ISO datetime)."),
        clear_expires: bool = typer.Option(False, "--clear-expires", help="Remove expiration."),
        scopes: Optional[str] = typer.Option(None, "--scopes", "-s", help="New scopes (comma-separated)."),
        active: Optional[bool] = typer.Option(None, "--active/--inactive", help="Activate or deactivate."),
    ) -> None:
        """Update an API key's metadata."""
        if id_ is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(0)

        async with handle_errors(service_factory) as service:
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
                entity.scopes = parse_scopes(scopes) or []
            if active is not None:
                entity.is_active = active

            updated = await service.update(entity)
            console.print("[green]API key updated.[/green]\n")
            print_entity_detail(updated)

    @cli.async_command("activate")
    async def activate_key(
        ctx: typer.Context,
        id_: Optional[str] = typer.Argument(None, help="ID of the key to activate."),
    ) -> None:
        """Activate an API key."""
        if id_ is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(0)

        async with handle_errors(service_factory) as service:
            entity = await service.get_by_id(id_)
            entity.enable()
            await service.update(entity)
            console.print(f"[green]API key '{id_}' activated.[/green]")

    @cli.async_command("deactivate")
    async def deactivate_key(
        ctx: typer.Context,
        id_: Optional[str] = typer.Argument(None, help="ID of the key to deactivate."),
    ) -> None:
        """Deactivate an API key."""
        if id_ is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(0)

        async with handle_errors(service_factory) as service:
            entity = await service.get_by_id(id_)
            entity.disable()
            await service.update(entity)
            console.print(f"[green]API key '{id_}' deactivated.[/green]")

    @cli.async_command("search")
    async def search_keys(
        limit: int = typer.Option(20, "--limit", "-l", min=1, help="Max keys to show."),
        offset: int = typer.Option(0, "--offset", "-o", min=0, help="Skip first N keys."),
        active: Optional[bool] = typer.Option(None, "--active/--inactive", help="Filter by status."),
        name: Optional[str] = typer.Option(None, "--name", "-n", help="Name contains."),
        name_exact: Optional[str] = typer.Option(None, "--name-exact", help="Exact name match."),
        scopes: Optional[str] = typer.Option(None, "--scopes", "-s", help="Must have ALL scopes."),
        scopes_any: Optional[str] = typer.Option(None, "--scopes-any", help="Must have at least ONE scope."),
        never_used: Optional[bool] = typer.Option(None, "--never-used/--used", help="Filter by usage."),
        expires_before: Optional[str] = typer.Option(None, "--expires-before", help="Expiring before (ISO datetime)."),
        expires_after: Optional[str] = typer.Option(None, "--expires-after", help="Expiring after (ISO datetime)."),
        created_before: Optional[str] = typer.Option(None, "--created-before", help="Created before (ISO datetime)."),
        created_after: Optional[str] = typer.Option(None, "--created-after", help="Created after (ISO datetime)."),
        last_used_before: Optional[str] = typer.Option(
            None, "--last-used-before", help="Last used before (ISO datetime)."
        ),
        last_used_after: Optional[str] = typer.Option(
            None, "--last-used-after", help="Last used after (ISO datetime)."
        ),
        order_by: SortableColumn = typer.Option(SortableColumn.CREATED_AT, "--order-by", help="Field to sort by."),
        descending: bool = typer.Option(True, "--desc/--asc", help="Sort descending or ascending."),
    ) -> None:
        """Search API keys with filters."""
        async with handle_errors(service_factory) as service:
            filter_ = ApiKeyFilter(
                is_active=active,
                name_contains=name,
                name_exact=name_exact,
                scopes_contain_all=parse_scopes(scopes),
                scopes_contain_any=parse_scopes(scopes_any),
                never_used=never_used,
                expires_before=parse_datetime(expires_before) if expires_before else None,
                expires_after=parse_datetime(expires_after) if expires_after else None,
                created_before=parse_datetime(created_before) if created_before else None,
                created_after=parse_datetime(created_after) if created_after else None,
                last_used_before=parse_datetime(last_used_before) if last_used_before else None,
                last_used_after=parse_datetime(last_used_after) if last_used_after else None,
                order_by=order_by,
                order_desc=descending,
                limit=limit,
                offset=offset,
            )
            items = await service.find(filter_)
            total = await service.count(filter_)

            if not items:
                console.print("[yellow]No API keys found.[/yellow]")
                return

            print_keys_table(items, f"Search Results ({len(items)} of {total})")

    @cli.async_command("count")
    async def count_keys(
        active: Optional[bool] = typer.Option(None, "--active/--inactive", help="Filter by status."),
        name: Optional[str] = typer.Option(None, "--name", "-n", help="Name contains."),
        never_used: Optional[bool] = typer.Option(None, "--never-used/--used", help="Filter by usage."),
    ) -> None:
        """Count API keys."""
        async with handle_errors(service_factory) as service:
            filter_ = ApiKeyFilter(
                is_active=active,
                name_contains=name,
                never_used=never_used,
            )
            total = await service.count(filter_)
            console.print(f"[blue]Total API keys: {total}[/blue]")

    return cli


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


def format_status(is_active: bool) -> str:
    """Format active status with color."""
    return "[green]Active[/green]" if is_active else "[red]Inactive[/red]"


def format_expires(expires_at: Optional[datetime]) -> str:
    """Format expiration with days remaining."""
    if expires_at is None:
        return "[dim]Never[/dim]"

    now = datetime_factory()
    delta = expires_at - now

    if delta.total_seconds() < 0:
        return "[red]Expired[/red]"

    days = delta.days

    if days == 0:
        hours = int(delta.total_seconds() // 3600)
        return f"[yellow]{hours}h[/yellow]"
    if days <= 7:
        return f"[yellow]{days}d[/yellow]"
    if days <= 30:
        return f"[blue]{days}d[/blue]"

    return f"[green]{days}d[/green]"


def format_datetime(dt: Optional[datetime]) -> str:
    """Format datetime for display."""
    if dt is None:
        return "[dim]-[/dim]"
    return dt.strftime("%Y-%m-%d %H:%M")


def print_keys_table(entities: List[ApiKey], title: str) -> None:
    """Print a table of API keys."""
    table = Table(title=title, show_header=True, header_style="bold")

    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="white", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Expires", justify="center")
    table.add_column("Scopes", style="dim", no_wrap=True)

    for entity in entities:
        table.add_row(
            entity.id_,
            entity.name or "[dim]-[/dim]",
            format_status(entity.is_active),
            format_expires(entity.expires_at),
            ", ".join(entity.scopes) if entity.scopes else "[dim]-[/dim]",
        )

    console.print(table)


def print_entity_detail(entity: ApiKey) -> None:
    """Print detailed view of an API key."""
    lines = [
        f"[bold]ID:[/bold]          {entity.id_}",
        f"[bold]Key ID:[/bold]      {entity.key_id}",
        f"[bold]Name:[/bold]        {entity.name or '[dim]-[/dim]'}",
        f"[bold]Description:[/bold] {entity.description or '[dim]-[/dim]'}",
        f"[bold]Status:[/bold]      {format_status(entity.is_active)}",
        f"[bold]Scopes:[/bold]      {', '.join(entity.scopes) if entity.scopes else '[dim]-[/dim]'}",
        f"[bold]Created:[/bold]     {format_datetime(entity.created_at)}",
        f"[bold]Last Used:[/bold]   {format_datetime(entity.last_used_at)}",
        f"[bold]Expires:[/bold]     {format_expires(entity.expires_at)}",
    ]

    panel = Panel("\n".join(lines), title="API Key Details", border_style="blue")
    console.print(panel)
