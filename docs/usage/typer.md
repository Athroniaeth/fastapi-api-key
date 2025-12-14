# Typer

Mount CLI commands that expose your key store over the command line. The CLI wires the service, repository, and hashers
together using Typer dependency injection.

## Features

- One call to `create_api_keys_cli` registers create, list, get, update, delete and verify commands.
- Depends on an async session factory (see `async_sessionmaker`).
- Shares a single `ApiKeyHasher` instance across requests.

## Example

This is the canonical example from `examples/example_cli.py`.

!!! warning "Always set a pepper"
    The default pepper is a placeholder. Set `SECRET_PEPPER` (or pass it explicitly to the hashers) in every environment.

```python
--8<-- "examples/example_cli.py"
```

### Commands exposed

| Command            | Description                       |
|--------------------|-----------------------------------|
| `create`           | Create a new API key              |
| `list`             | List all API keys                 |
| `get <id>`         | Get details of a specific API key |
| `delete <id>`      | Delete an API key                 |
| `verify <api_key>` | Verify an API key                 |
| `update <id>`      | Update an existing API key        |
| `activate <id>`    | Activate an API key               |
| `deactivate <id>`  | Deactivate an API key             |
| `search`           | Search API keys with filters      |
| `count`            | Count API keys                    |
