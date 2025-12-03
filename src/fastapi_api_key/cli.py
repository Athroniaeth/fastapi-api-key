"""CLI module for managing API keys via Typer.

Provides commands for CRUD operations on API keys using the service layer.
Uses Rich for beautiful terminal output.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, List, Optional

from fastapi_api_key._types import ServiceFactory
from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.domain.errors import ApiKeyError
from fastapi_api_key.repositories.base import ApiKeyFilter
from fastapi_api_key.utils import datetime_factory

# Domain errors that should result in exit code 1
DomainErrors = (ApiKeyError,)


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
    console = _import_console()

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
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(1) from exc

    # --- Commands ---

    @cli.command("create")
    def create_key(
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

                console.print("[green]API key created successfully.[/green]\n")
                print_entity_detail(console, entity)
                console.print("\n[yellow]Plain secret (store securely, shown only once):[/yellow]")
                console.print(f"[bold cyan]{api_key}[/bold cyan]")

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
                    console.print("[yellow]No API keys found.[/yellow]")
                    return
                print_keys_table(console, items, f"API Keys ({len(items)} shown)")

        handle_errors(_run)

    @cli.command("get")
    def get_key(
        ctx: typer.Context,
        id_: Optional[str] = typer.Argument(None, help="ID of the key."),
    ) -> None:
        """Get an API key by ID."""
        if id_ is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(0)

        async def _run() -> None:
            async with service_factory() as service:
                entity = await service.get_by_id(id_)
                print_entity_detail(console, entity)

        handle_errors(_run)

    @cli.command("delete")
    def delete_key(
        ctx: typer.Context,
        id_: Optional[str] = typer.Argument(None, help="ID of the key to delete."),
    ) -> None:
        """Delete an API key."""
        if id_ is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(0)

        async def _run() -> None:
            async with service_factory() as service:
                await service.delete_by_id(id_)
                console.print(f"[green]Deleted API key '{id_}'.[/green]")

        handle_errors(_run)

    @cli.command("verify")
    def verify_key(
        ctx: typer.Context,
        api_key: Optional[str] = typer.Argument(None, help="Full API key string."),
    ) -> None:
        """Verify an API key."""
        if api_key is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(0)

        async def _run() -> None:
            async with service_factory() as service:
                entity = await service.verify_key(api_key)
                console.print("[green]API key is valid.[/green]\n")
                print_entity_detail(console, entity)

        handle_errors(_run)

    @cli.command("update")
    def update_key(
        ctx: typer.Context,
        id_: Optional[str] = typer.Argument(None, help="ID of the key to update."),
        name: Optional[str] = typer.Option(None, "--name", "-n", help="New name."),
        description: Optional[str] = typer.Option(None, "--description", "-d", help="New description."),
        expires_at: Optional[str] = typer.Option(None, "--expires-at", help="New expiration (ISO datetime)."),
        clear_expires: bool = typer.Option(False, "--clear-expires", help="Remove expiration."),
        scopes: Optional[str] = typer.Option(None, "--scopes", "-s", help="New scopes (comma-separated)."),
    ) -> None:
        """Update an API key's metadata."""
        if id_ is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(0)

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
                    entity.scopes = parse_scopes(scopes) or []

                updated = await service.update(entity)
                console.print("[green]API key updated.[/green]\n")
                print_entity_detail(console, updated)

        handle_errors(_run)

    @cli.command("activate")
    def activate_key(
        ctx: typer.Context,
        id_: Optional[str] = typer.Argument(None, help="ID of the key to activate."),
    ) -> None:
        """Activate an API key."""
        if id_ is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(0)

        async def _run() -> None:
            async with service_factory() as service:
                entity = await service.get_by_id(id_)
                entity.enable()
                await service.update(entity)
                console.print(f"[green]API key '{id_}' activated.[/green]")

        handle_errors(_run)

    @cli.command("deactivate")
    def deactivate_key(
        ctx: typer.Context,
        id_: Optional[str] = typer.Argument(None, help="ID of the key to deactivate."),
    ) -> None:
        """Deactivate an API key."""
        if id_ is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(0)

        async def _run() -> None:
            async with service_factory() as service:
                entity = await service.get_by_id(id_)
                entity.disable()
                await service.update(entity)
                console.print(f"[green]API key '{id_}' deactivated.[/green]")

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
                    console.print("[yellow]No API keys found.[/yellow]")
                    return

                print_keys_table(console, items, f"Search Results ({len(items)} of {total})")

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
                console.print(f"[blue]Total API keys: {total}[/blue]")

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


def print_keys_table(console: Any, entities: List[ApiKey], title: str) -> None:
    """Print a table of API keys."""
    Table = _import_table()
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


def print_entity_detail(console: Any, entity: ApiKey) -> None:
    """Print detailed view of an API key."""
    Panel = _import_panel()

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


def _import_typer() -> Any:
    """Import typer with helpful error message."""
    try:
        import typer
    except ImportError as exc:
        raise RuntimeError("Typer is required. Install with: pip install fastapi-api-key[cli]") from exc
    return typer


def _import_console() -> Any:
    """Import Rich Console."""
    try:
        from rich.console import Console
    except ImportError as exc:
        raise RuntimeError("Rich is required. Install with: pip install fastapi-api-key[cli]") from exc
    return Console()


def _import_table() -> Any:
    """Import Rich Table."""
    from rich.table import Table

    return Table


def _import_panel() -> Any:
    """Import Rich Panel."""
    from rich.panel import Panel

    return Panel
