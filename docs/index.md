# FastAPI Api Key

![Python Version from PEP 621 TOML](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2FAthroniaeth%2Ffastapi-api-key%2Fmain%2Fpyproject.toml)
[![Tested with pytest](https://img.shields.io/badge/tests-pytest-informational.svg)](https://pytest.org/)
[![PyPI version](https://img.shields.io/pypi/v/fastapi-api-key.svg)](https://pypi.org/project/fastapi-api-key/)
[![Docs](https://img.shields.io/badge/docs-online-blue.svg)](https://athroniaeth.github.io/fastapi-api-key/)
[![codecov](https://codecov.io/gh/Athroniaeth/fastapi-api-key/graph/badge.svg)](https://codecov.io/gh/Athroniaeth/fastapi-api-key)
[![Security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://bandit.readthedocs.io/)
[![Deps: uv](https://img.shields.io/badge/deps-managed%20with%20uv-3E4DD8.svg)](https://docs.astral.sh/uv/)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-4B32C3.svg)](https://docs.astral.sh/ruff/)

`fastapi-api-key` provides reusable building blocks to issue, persist, and verify API keys in FastAPI applications. It
ships with a domain model, hashing helpers, repository contracts, and an optional FastAPI router for CRUD management of
keys.

## Links

- **Documentation:** [https://athroniaeth.github.io/fastapi-api-key/](https://athroniaeth.github.io/fastapi-api-key/)
- **PyPI package:** [https://pypi.org/project/fastapi-api-key/](https://pypi.org/project/fastapi-api-key/)

## Features

- **Security-first**: secrets are hashed with a salt and a pepper, and never logged or returned after creation
- **Prod-ready**: services and repositories are async, and battle-tested

- **Agnostic hasher**: you can use any async-compatible hashing strategy (default: Argon2)
- **Agnostic backend**: you can use any async-compatible database (default: SQLAlchemy)
- **Connector**: create a Typer, FastAPI router wired to api key systems


- **Envvar support**: easily configure peppers and other secrets via environment variables
- **Extensible**: customize models, repositories, hashers, and services to fit your needs
- **Scopes support**: assign scopes to API keys for fine-grained access control

## Standards compliance

This library try to follow best practices and relevant RFCs for API key management and authentication:

- **[RFC 9110/7235](https://www.rfc-editor.org/rfc/rfc9110.html)**: Router raise 401 for missing/invalid keys, 403 for
  valid but inactive/expired keys
- **[RFC 6750](https://datatracker.ietf.org/doc/html/rfc6750)**: Supports `Authorization: Bearer <api_key>` header for
  key transmission (also supports deprecated `X-API-Key` header and `api_key` query param)

## How API Keys Work

### API Key Format

This is a classic API key if you don't modify the service behavior:

**Structure:**

`{global_prefix}`-`{delimiter}`-`{identifier}`-`{delimiter}`-`{secret}`

**Example:**

`ak-7a74caa323a5410d-mAfP3l6yAxqFz0FV2LOhu2tPCqL66lQnj3Ubd08w9RyE4rV4skUcpiUVIfsKEbzw`

- "-" separators so that systems can easily split
- Prefix `ak` (for "Api Key"), to identify the key type (useful to indicate that it is an API key).
- 16 first characters are the identifier (UUIDv4 without dashes)
- 48 last characters are the secret (random URL-safe base64 string)

When verifying an API key, the service extracts the identifier, retrieves the corresponding record from the repository,
and compares the hashed secret. If found, it hashes the provided secret (with the same salt and pepper) and compares it
to the stored hash.
If they match, the key is valid.

### Schema validation

Here is a diagram showing what happens after you initialize your API key service with a global prefix and delimiter when you provide an API key to the `.verify_key()` method.

<img src="./schema.svg">

## Additional notes

- Python 3.9+ is required.
- The library issues warnings if you keep the default pepper; always configure a secret value outside source control.
- Never log peppers or plaintext API keys, change the pepper of prod will prevent you from reading API keys

## What to read next

1. Head to the [Quickstart](quickstart.md) to wire the service in a REPL or script.
2. Browse the [Usage](usage/custom/) section to reuse the example applications that ship with the project.
