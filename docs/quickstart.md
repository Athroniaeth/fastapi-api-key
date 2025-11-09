# Quickstart

This quickstart guide helps you set up the package and create your first API key. It assumes you have Python 3.9+ installed.

## 1. Install dependencies

### Basic installation
This project is not published to PyPI. Use a tool like [uv](https://docs.astral.sh/uv/) to manage dependencies.

```bash
uv add fastapi-api-key
uv pip install fastapi-api-key
```

### Development installation

Clone or fork the repository and install the project with the extras that fit your stack. Examples below use `uv`:

```bash
uv sync --extra all  # fastapi + sqlalchemy + argon2 + bcrypt
uv pip install -e ".[all]"
```

### Optional dependencies

For lighter setups you can choose individual extras:

| Installation mode              | Command                       | Description                                                                 |
|--------------------------------|-------------------------------|-----------------------------------------------------------------------------|
| **Base installation**          | `fastapi-api-key`             | Installs the core package without any optional dependencies.                |
| **With Bcrypt support**        | `fastapi-api-key[bcrypt]`     | Adds support for password hashing using **bcrypt**                          |
| **With Argon2 support**        | `fastapi-api-key[argon2]`     | Adds support for password hashing using **Argon2**                          |
| **With SQLAlchemy support**    | `fastapi-api-key[sqlalchemy]` | Adds database integration via **SQLAlchemy**                                |
| **With Cache Service support** | `fastapi-api-key[aiocache]`   | Adds database integration via **Aiocache**                                  |
| **Core setup**                 | `fastapi-api-key[core]`       | Installs the **core dependencies** (SQLAlchemy + Argon2 + bcrypt + aiocache |
| **FastAPI only**               | `fastapi-api-key[fastapi]`    | Installs **FastAPI** as an optional dependency                              |
| **Full installation**          | `fastapi-api-key[all]`        | Installs **all optional dependencies**                                      |

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

## 2. Create api key

Create a script and run the following code. This mirrors `examples/example_inmemory.py`.

```python
--8<-- "examples/example_inmemory.py"
```

## 3. Persist api key

Swap the repository for the SQL implementation and connect it to an async engine. This mirrors `examples/example_sql.py`.

```python
--8<-- "examples/example_sql.py"
```

Next, explore the detailed usage guides which embed the full example scripts from the repository.
