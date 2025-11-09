# Scopes

This libray integrates the concept of scopes to provide fine-grained access control for API keys. Scopes are strings that define the permissions associated with an API key. When creating or updating an API key, you can specify the scopes that the key should have.
If you define 2 scopes "read" and "write" to an route, an API key must have both scopes to access that route.

## Example

### Simple

This is the canonical example from `examples/example_scopes.py`:

!!! warning "Always set a pepper"
    The default pepper is a placeholder. Set `API_KEY_PEPPER` (or pass it explicitly to the hashers) in every environment.

```python
--8<-- "examples/example_scopes.py"

```

### FastAPI

You can create security Depends with required scopes like this:

```python
--8<-- "examples/example_fastapi_scopes.py"

```