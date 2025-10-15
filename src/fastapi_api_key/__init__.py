import importlib.metadata
import shutil  # nosec: B404
import subprocess  # nosec: B404

from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.services.service import ApiKeyService
from fastapi_api_key.api import create_api_keys_router, create_depends_api_key
from fastapi_api_key.cli import create_api_keys_cli

__all__ = [
    "ApiKey",
    "ApiKeyService",
    "create_api_keys_router",
    "create_depends_api_key",
    "create_api_keys_cli",
]

__version__ = importlib.metadata.version("fastapi_api_key")


def _run_command(command: str) -> None:  # pragma: no cover
    """Run a command in the shell."""
    print(f"Running command: {command}")
    list_command = command.split()

    program = list_command[0]
    path_program = shutil.which(program)

    if path_program is None:
        raise RuntimeError(
            f"Program '{program}' not found in PATH. Please use `uv sync --dev` to install development dependencies."
        )

    list_command[0] = path_program

    try:
        subprocess.run(list_command, check=True, shell=False)  # nosec: B603
    except subprocess.CalledProcessError as e:
        print(f"Command failed with error: {e}")


def test():  # pragma: no cover
    """Command UV to run tests for development."""
    list_commands = ["pytest --cov-report=html --cov-report=xml"]

    for command in list_commands:
        _run_command(command)


def lint():  # pragma: no cover
    """Command UV to run linters for development."""
    list_commands = [
        "ruff format .",
        "ruff check --fix .",
        "ty check .",
        "bandit -c pyproject.toml -r src examples -q",
    ]

    for command in list_commands:
        _run_command(command)
