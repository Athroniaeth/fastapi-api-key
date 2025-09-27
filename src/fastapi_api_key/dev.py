import shutil  # nosec: B404
import subprocess  # nosec: B404


def _run_command(command: str) -> None:  # pragma: no cover
    """Run a command in the shell."""
    print(f"Running command: {command}")
    list_command = command.split()

    program = list_command[0]
    path_program = shutil.which(program)

    if path_program is None:
        raise RuntimeError(
            f"Program '{program}' not found in PATH. "
            f"Please use `uv sync --dev` to install development dependencies."
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
        "bandit -c pyproject.toml -r src -q",
    ]

    for command in list_commands:
        _run_command(command)
