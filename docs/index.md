# fastapi-api-key

> Opinionated building blocks to issue, persist, and verify API keys for FastAPI services.

`fastapi-api-key` packages the pieces you need to generate keyed credentials, hash them securely, and expose management endpoints. It ships with:

- A domain entity that tracks activation, expiration, and usage timestamps.
- Async services that create, list, rotate, and verify secrets without ever storing the clear text.
- Repository contracts plus ready-to-use in-memory and SQLAlchemy implementations.
- A FastAPI router factory that mounts CRUD endpoints in a couple of lines.

## Why another API key library?

Modern APIs still rely on static keys for machine-to-machine traffic. This project focuses on:

- **Security defaults** – Argon2 hashing, pepper support, and separated `key_id` lookup.
- **Async-first design** – repositories and services are fully async/await friendly.
- **Extensibility** – customise the domain dataclass or the SQLAlchemy model in minutes.
- **FastAPI integration** – drop-in router exposes CRUD endpoints with request/response models.

Material for MkDocs powers this site, so everything is organised into quick starts, usage guides, and API references—just like the FastAPI and Pydantic docs you know.

## Installation

Choose the extras that match your stack. The examples on this site assume you are using `uv`, but `pip` or `rye` work as well.

```bash
uv sync --extra all --group dev
```

The `all` extra installs FastAPI, SQLAlchemy, Argon2, and BCrypt. For minimal deployments, pick the individual extras (`argon`, `bcrypt`, `sqlalchemy`).

!!! tip "Always set a pepper"
    The default pepper is a placeholder. Set `API_KEY_PEPPER` (or pass it explicitly to the hashers) in every environment.

## What to read next

1. Head to the [Quickstart](quickstart.md) to wire the service in a REPL or script.
2. Browse the [Usage](usage/inmemory.md) section to reuse the example applications that ship with the project.
3. Dive into the [Reference](reference/service.md) for service semantics and repository contracts.

Happy hacking!
