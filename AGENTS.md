# AGENTS.md

This file guides automated coding agents working in this repository.
Follow existing patterns and run the same tooling as humans.

## Project overview

- Language: Python 3.9+
- Package: `fastapi_api_key` (src layout)
- Async-first services and repositories
- Optional extras for FastAPI, SQLAlchemy, Argon2, bcrypt, aiocache

## Tooling and environment

- Dependency manager: `uv`
- Build backend: `hatchling`
- Format/lint: Ruff
- Type checks: Ty and Pyrefly
- Security lint: Bandit
- Tests: pytest + pytest-cov + pytest-asyncio

## Build, lint, and test commands

### Install (dev)

- `uv sync --extra all --group dev`
- `source .venv/bin/activate` (or Windows `.venv\Scripts\Activate.ps1`)

### Lint and format

- `make lint`
  - Runs: `ruff format`, `ruff check --fix`, `ty check`, `pyrefly check`, `bandit`
- Direct commands:
  - `uv run ruff format .`
  - `uv run ruff check --fix .`
  - `uv run ty check .`
  - `uv run pyrefly check .`
  - `uv run bandit -c pyproject.toml -r src examples -q`

### Tests

- Full test suite: `uv run pytest`
- Single test file: `uv run pytest tests/unit/test_service.py`
- Single test by node id:
  - `uv run pytest tests/unit/test_service.py::test_create_api_key`
- Single test by keyword:
  - `uv run pytest -k "create_api_key"`
- Run a test class: `uv run pytest tests/unit/test_service.py::TestApiKeyService`

### Coverage output

Pytest defaults include coverage reports (XML/HTML/terminal) via `pyproject.toml`.
Artifacts: `coverage.xml`, `htmlcov/`, `junit.xml`.

## Code style and conventions

### Formatting

- Ruff handles formatting; follow it instead of manual styling.
- Line length: 120 characters.
- Indentation: 4 spaces.
- Quotes: double quotes.

### Imports

- Standard library imports first, then third-party, then local.
- Prefer explicit imports over wildcard.
- Keep module-level imports; avoid local imports unless required to break cycles.
- In optional dependency modules, guard imports with `try/except ModuleNotFoundError`.

### Typing

- Use Python 3.9+ type hints everywhere.
- Prefer `Optional[T]` and `list[T]`/`dict[K, V]` style.
- Return concrete types (`ApiKey`, `list[ApiKey]`, etc.) not `Any`.
- Use `Annotated` for FastAPI params when needed.

### Naming

- Classes: `CamelCase` (e.g., `ApiKeyService`).
- Functions/vars: `snake_case`.
- Constants: `UPPER_SNAKE_CASE`.
- Private helpers: prefix `_` (e.g., `_verify_entity`).
- API key fields follow existing names (`key_id`, `key_secret`, `key_hash`).

### Dataclasses and models

- Use `@dataclass` for small data carriers (e.g., parsed key results).
- Use Pydantic models for API request/response schemas.

### Error handling

- Domain exceptions live in `fastapi_api_key.domain.errors`.
- Raise domain errors in services and repositories, translate to HTTP exceptions in API layer.
- Preserve original errors with `raise ... from exc`.
- Use specific exceptions (`KeyNotFound`, `InvalidKey`, `ConfigurationError`) rather than `ValueError` unless appropriate.
- Validate inputs early; prefer guard clauses.

### Async and I/O

- Services and repositories are async; keep APIs async throughout.
- Use `await` for repo calls and when composing service logic.
- Avoid blocking I/O in async paths.

### Security-sensitive behavior

- Never log or return plaintext API keys after creation.
- Enforce API key parsing/validation via `ParsedApiKey` and `_get_parts` patterns.
- Use timing jitter on auth failures (`verify_key` behavior).
- Treat secret pepper as external configuration; do not hardcode.

### API layer

- Use FastAPI dependency injection with `Depends`.
- Map domain errors to `HTTPException` with correct status codes.
- API responses use Pydantic models; keep output schemas stable.

### Tests

- Tests live in `tests/` with unit and integration subpackages.
- Prefer clear arrange/act/assert structure.
- Use fixtures from `tests/conftest.py` where available.

## Repository layout

- `src/fastapi_api_key/` core library
- `tests/` unit/integration tests
- `examples/` example applications (used in docs)

## Repo-specific notes

- `make lint` is the canonical lint entrypoint.
- The project warns when the default pepper is used; tests expect that behavior.
- Examples are used in docs; keep them runnable.

## Cursor and Copilot rules

- No `.cursor/rules/`, `.cursorrules`, or `.github/copilot-instructions.md` found in this repo.

## When editing

- Preserve public API behavior and exception types.
- Keep docstrings consistent with existing style.
- Match current error messages when possible (tests may assert them).
- Avoid introducing extra dependencies without updating optional extras.
