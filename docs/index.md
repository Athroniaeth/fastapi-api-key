# Fastapi Api Key

`fastapi-api-key` provides reusable building blocks to issue, persist, and verify API keys in FastAPI applications. It
ships with a domain model, hashing helpers, repository contracts, and an optional FastAPI router for CRUD management of
keys.

## Features

- **Security-first**: secrets are hashed with a salt and a pepper, and never logged or returned after creation
- **Ready-to-use**: just create your repository (storage) and use service
- **Prod-ready**: services and repositories are async, and battle-tested

- **Agnostic hasher**: you can use any async-compatible hashing strategy (default: Argon2)
- **Agnostic backend**: you can use any async-compatible database (default: SQLAlchemy)
- **Factory**: create a Typer, FastAPI router wired to api key systems (only SQLAlchemy for now)

## Installation

This projet does not publish to PyPI. Use a tool like [uv](https://docs.astral.sh/uv/) to manage dependencies.

```bash
uv add fastapi-api-key
uv pip install fastapi-api-key
```

## Development installation

Clone the repository and install the project with the extras that fit your stack. Examples below use `uv`:

```bash
uv sync --extra all  # fastapi + sqlalchemy + argon2 + bcrypt
uv pip install -e ".[all]"
```

For lighter setups you can choose individual extras:

| Installation mode           | Command                       | Description                                                                      |
|-----------------------------|-------------------------------|----------------------------------------------------------------------------------|
| **Base installation**       | `fastapi-api-key`             | Installs the core package without any optional dependencies.                     |
| **With bcrypt support**     | `fastapi-api-key[bcrypt]`     | Adds support for password hashing using **bcrypt** (`bcrypt>=5.0.0`).            |
| **With Argon2 support**     | `fastapi-api-key[argon2]`     | Adds support for password hashing using **Argon2** (`argon2-cffi>=25.1.0`).      |
| **With SQLAlchemy support** | `fastapi-api-key[sqlalchemy]` | Adds database integration via **SQLAlchemy** (`sqlalchemy>=2.0.43`).             |
| **Core setup**              | `fastapi-api-key[core]`       | Installs the **core dependencies** (SQLAlchemy + Argon2 + bcrypt).               |
| **FastAPI only**            | `fastapi-api-key[fastapi]`    | Installs **FastAPI** as an optional dependency (`fastapi>=0.118.0`).             |
| **Full installation**       | `fastapi-api-key[all]`        | Installs **all optional dependencies**: FastAPI, SQLAlchemy, Argon2, and bcrypt. |

```bash
uv add fastapi-api-key[sqlalchemy]
uv pip install fastapi-api-key[sqlalchemy]
uv sync --extra sqlalchemy
uv pip install -e ".[sqlalchemy]"
```

Development dependencies (pytest, ruff, etc.) are available under the `dev` group:

```bash
uv sync --extra dev
uv pip install -e ".[dev]"
```

## What to read next

1. Head to the [Quickstart](quickstart.md) to wire the service in a REPL or script.
2. Browse the [Usage](usage/custom/) section to reuse the example applications that ship with the project.
