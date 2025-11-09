# Dotenv

If you don't need to have complex system (add, remove, update API keys) management, you can use environment variables to store your API keys.

You can generate API keys using the `fak` (Fastapi Api Key) CLI
```bash
fak generate
```

```bash
Set in your .env : "API_KEY_DEV: ak-e71947d5509e48e9-Dryc0fsQRaTv9Gl7mTScMFARDE6FgwZPUnm38MlX1OSJZCYCkKi4jsoTXxEtGGNC"
```

## Example

This is the canonical example from `examples/example_inmemory_env.py`:

!!! warning "Always set a pepper"
    The default pepper is a placeholder. Set `API_KEY_PEPPER` (or pass it explicitly to the hashers) in every environment.

```python
--8<-- "examples/example_inmemory_env.py"
```

