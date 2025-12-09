.PHONY: lint

lint:
	uv run ruff format .
	uv run ruff check --fix .
	uv run ty check .
	uv run pyrefly check .
	uv run bandit -c pyproject.toml -r src examples -q
