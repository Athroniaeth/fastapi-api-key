# Quickstart

This quickstart guide helps you set up the package and create your first API key. It assumes you have Python 3.9+ installed.

## 1. Install dependencies

Install the package with all optional dependencies using your preferred method. Examples below use [uv](https://docs.astral.sh/uv/):

```bash
uv sync --extra all 
```

## 2. Create api key

Create a script and run the following code. This mirrors `examples/example_inmemory.py`.

```python
--8<-- "examples/example_inmemory.py"
```

## 3. Persist api key

Swap the repository for the SQL implementation and connect it to an async engine. This mirrors `examples/example_sql.py`.

```python
--8<-- "examples/example_sql.py"
```

Next, explore the detailed usage guides which embed the full example scripts from the repository.
