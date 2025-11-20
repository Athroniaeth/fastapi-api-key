# Repository Guidelines

## Project Structure & Module Organization
- Core implementation lives in `src/fastapi_api_key/` with feature-specific subpackages (repositories, hashers, FastAPI router).
- Tests mirror the layout in `tests/`, keeping fixtures and helpers beside the code under test.
- Live examples sit in `examples/`; MkDocs sources live in `docs/` with runnable snippets.
- Generated artifacts like `dist/`, `htmlcov/`, and `site/` are disposable and should not be edited manually.

## Build, Test, and Development Commands
- `uv sync --extra all --group dev` once, then `source .venv/bin/activate` to enter the environment.
- `uv run lint` runs formatting, linting, typing, and security checks (Ruff format/check, Ty, Bandit); treat warnings as failures.
- `uv run pytest` executes unit tests and doctests with coverage outputs in `coverage.xml` and `htmlcov/`.
- `uv run mkdocs serve` for live docs preview; `uv run mkdocs build` to validate the static site.
- `uv run fak --help` exercises the packaged Typer CLI for quick sanity checks.

## Coding Style & Naming Conventions
- Python 3.9+ with 4-space indentation and full type hints; prefer existing dataclasses and Pydantic models.
- Public APIs use descriptive nouns (`ApiKeyService`, `SqlAlchemyApiKeyRepository`); private helpers start with `_`.
- Configuration lives in `pyproject.toml`; avoid per-file overrides unless essential.

## Testing Guidelines
- Pytest collects from `src/` and `tests/`, including doctests; branch coverage is enforced.
- Name tests `test_<topic>.py` and functions `test_<behavior>()`; place tests next to the code they cover.
- For persistence and hashing paths, include async success and failure cases; add integration tests under `tests/integration/` for routers or CLI changes.
- Run `uv run pytest` locally before pushing; update coverage artifacts as needed.

## Commit & Pull Request Guidelines
- Use Conventional Commits via `cz commit` (e.g., `feat(router): add bulk revoke endpoint`) and squash fixups locally.
- Target PRs to `development`, reference related issues, and call out API/CLI/storage contract changes.
- Provide evidence of `uv run lint`, `uv run pytest`, and `uv run mkdocs build` (for doc updates); include screenshots or sample outputs when relevant.

## Security & Configuration Tips
- Set `API_KEY_PEPPER` in production; default pepper is only for local usage and should log a warning.
- Never log raw API keys; store secrets with your chosen backend (SQLAlchemy, Redis, etc.).
- Update `docs/security.md` and `SECURITY.md` if you fix or discover vulnerabilities to inform downstream consumers promptly.
