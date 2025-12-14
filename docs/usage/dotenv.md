# Dotenv

If you don't need to have complex system (add, remove, update API keys) management, you can use environment variables to store your API keys.

You can generate API keys using the CLI `create` command or programmatically, then store them in your `.env` file:

```bash
API_KEY_DEV=ak-dcde9fa8eec44aa2-n8JK2HPXoosH6UXPL5h2YeO3OdW55WESb97CKc7mbVUzFpWFQYLuDD7Xs8fbco5d
```

## Example

This is the canonical example from `examples/example_inmemory_env.py`:

!!! warning "Always set a pepper"
    The default pepper is a placeholder. Set `SECRET_PEPPER` (or pass it explicitly to the hashers) in every environment.

```python
--8<-- "examples/example_inmemory_env.py"
```

