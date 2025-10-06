# Contributing

Thanks for helping improve `fastapi-api-key`! This guide walks you through the toolchain, branching model, and tooling conventions we follow.

## Prerequisites

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- Git and a GitHub account

## Workflow overview

1. **Fork** the repository to your own GitHub account.
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/<you>/fastapi-api-key.git
   cd fastapi-api-key
   ```
3. **Add the upstream remote** so you can sync later:
   ```bash
   git remote add upstream https://github.com/Athroniaeth/fastapi-api-key.git
   ```
4. **Create a feature branch** from the active integration branch (default: `development`):
   ```bash
   git checkout development
   git pull upstream development
   git checkout -b feat/<short-topic>
   ```

## Environment setup

```bash
# install runtime + dev dependencies
uv sync --extra all --group dev

# activate the virtual environment for your shell session
source .venv/bin/activate  # or .venv\Scripts\Activate.ps1 on Windows
```

## Development workflow

1. **Format & lint**
   ```bash
   uv run lint
   ```
   Runs `ruff format`, `ruff check --fix`, `ty`, and `bandit` in one pass.

2. **Run the tests**
   ```bash
   uv run pytest
   ```
   Pytest is configured with coverage (`pytest-cov`) and doctests in `pyproject.toml`.

3. **Preview the documentation** (when editing `docs/`)
   ```bash
   uv run mkdocs serve
   ```
   MkDocs Material hot-reloads pages as you edit.

4. **Commit with Commitizen**
   ```bash
   cz commit
   ```
   Follow the prompts to generate a Conventional Commit. To skip the interactive UI (e.g. CI), run:
   ```bash
   cz commit --name TYPE --message "type(scope): summary"
   ```

5. **Push your branch**
   ```bash
   git push origin feat/<short-topic>
   ```

6. **Open a pull request** targeting `Athroniaeth/fastapi-api-key:development`. Summarise the change, mention tests/docs runs, and link related issues if applicable.

## Pull request checklist

- [ ] `uv run lint`
- [ ] `uv run pytest`
- [ ] `uv run mkdocs build` *(when documentation changes)*
- [ ] Commits follow Commitizen/Conventional Commit format
- [ ] Added or updated tests when changing behaviour
- [ ] Synced with `upstream/development` if the branch diverged

## Keeping your fork up to date

```bash
git fetch upstream
git checkout development
git merge upstream/development
git push origin development
```
Then rebase your feature branch on the refreshed integration branch:
```bash
git checkout feat/<short-topic>
git rebase development
```

## Tips

- The library emits a warning when the default pepper is used; tests rely on this. Mind warning handling when touching hashers.
- Example apps live under `examples/` and are embedded directly into the documentation. Keep them runnable.
- New persistence layers should implement `AbstractApiKeyRepository` and receive corresponding docs/tests updates.

Happy hacking!
