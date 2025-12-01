# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`fastapi-api-key` is a library for issuing, persisting, and verifying API keys in FastAPI applications. It provides pluggable hashing strategies (Argon2, bcrypt), backend-agnostic persistence (SQLAlchemy, in-memory), optional caching (aiocache), and connectors for FastAPI and Typer CLI.

## Development Commands

```bash
# Install all dependencies (runtime + dev)
uv sync --extra all --group dev

# Format and lint (runs ruff format, ruff check, ty, bandit)
uv run lint

# Run tests with coverage
uv run pytest

# Run a single test file
uv run pytest tests/units/test_service.py

# Run a specific test
uv run pytest tests/units/test_service.py::test_function_name -v

# Preview documentation
uv run mkdocs serve

# Build documentation
uv run mkdocs build

# CLI tool (requires cli extra)
uv run fak --help
```

## Architecture

### Core Components

- **`ApiKeyService`** (`src/fastapi_api_key/services/base.py`): Main service orchestrating key creation, verification, and lifecycle. Handles timing attack mitigation via random response delays (rrd parameter).

- **`AbstractApiKeyRepository`** (`src/fastapi_api_key/repositories/base.py`): Repository contract. Implementations:
  - `InMemoryApiKeyRepository` - for testing
  - `SqlAlchemyApiKeyRepository` - production use with SQLAlchemy

- **`ApiKeyHasher`** (`src/fastapi_api_key/hasher/base.py`): Protocol for hashing. Implementations in `hasher/argon2.py` and `hasher/bcrypt.py`. Uses pepper (secret) + salt pattern.

- **`ApiKey`** (`src/fastapi_api_key/domain/entities.py`): Domain entity representing an API key with fields: id_, key_id, key_hash, name, description, is_active, scopes, expires_at, last_used_at.

### API Key Format

`{global_prefix}-{key_id}-{key_secret}` (e.g., `ak-7a74caa323a5410d-mAfP3l6y...`)

- `key_id`: 16-char UUID fragment (public, stored in DB for lookup)
- `key_secret`: 48-char base64 string (hashed before storage, never returned after creation)

### Connectors

- **FastAPI Router** (`src/fastapi_api_key/api.py`): `create_api_keys_router()` provides CRUD endpoints. `create_depends_api_key()` creates a FastAPI dependency for protecting routes.

- **Typer CLI** (`src/fastapi_api_key/cli.py`): `create_api_keys_cli()` for command-line key management.

### Caching Layer

`CachedApiKeyService` (`src/fastapi_api_key/services/cached.py`) wraps the base service with aiocache support.

## Key Design Decisions

- Secrets are hashed with salt + pepper; plaintext only returned once at creation
- Repository pattern enables swapping storage backends
- Service raises domain errors (`KeyNotFound`, `KeyInactive`, `KeyExpired`, `InvalidKey`, `InvalidScopes`) from `domain/errors.py`
- RFC 9110/7235 compliance: 401 for missing/invalid keys, 403 for inactive/expired
- Supports `Authorization: Bearer`, `X-API-Key` header, and `api_key` query param

## Testing

Tests are in `tests/` with coverage configured in `pyproject.toml`. The library emits warnings when using the default pepper - tests rely on this behavior.

## Branching

Feature branches should be created from `development` branch. PRs target `development`.
