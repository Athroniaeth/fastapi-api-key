# Dotenv

If you don't need to have complex system (add, remove, update API keys) management, you can use environment variables to store your API keys.

## Example

This is the canonical example from `examples/example_inmemory_env.py`:

!!! tip "Always set a pepper"
    The default pepper is a placeholder. Set `API_KEY_PEPPER` (or pass it explicitly to the hashers) in every environment.

```python
--8<-- "examples/example_inmemory_env.py"
```

