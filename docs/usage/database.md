# Database Configuration

This guide covers SQLAlchemy setup with aiosqlite for persistent API key storage.

## Installation

Install the SQLAlchemy extra:

```bash
pip install fastapi-api-key[sqlalchemy]
```

## Example

This is the canonical example from `examples/example_sql.py`:

!!! warning "Always set a pepper"
    The default pepper is a placeholder. Set `SECRET_PEPPER` (or pass it explicitly to the hashers) in every environment.

```python
--8<-- "examples/example_sql.py"
```
