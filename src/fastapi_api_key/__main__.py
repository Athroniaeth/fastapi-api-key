from typing import Optional

import typer
from typer import Typer

from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.services.base import DEFAULT_SEPARATOR, DEFAULT_GLOBAL_PREFIX
from fastapi_api_key.utils import key_id_factory, key_secret_factory

app = Typer(no_args_is_help=True, help="FastAPI API Keys CLI")


@app.callback(invoke_without_command=True)
def _main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show the FastAPI API Keys package version and exit.",
        is_eager=True,
    ),
):
    """FastAPI API Keys CLI"""
    from fastapi_api_key import __version__

    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
def generate(
    global_prefix: str = DEFAULT_GLOBAL_PREFIX,
    key_id: Optional[str] = None,
    key_secret: Optional[str] = None,
    separator: str = DEFAULT_SEPARATOR,
) -> str:
    """Generate a new API key for set in dotenv file."""
    key_id = key_id or key_id or key_id_factory()
    key_secret = key_secret or key_secret or key_secret_factory()

    api_key = ApiKey.full_key_secret(
        global_prefix=global_prefix,
        key_id=key_id,
        key_secret=key_secret,
        separator=separator,
    )
    typer.echo(f'Set in your .env : "API_KEY_DEV: {api_key}"')
    return api_key


def main():
    app()


if __name__ == "__main__":
    app()
