"""Quart integration for keyshield.

Provides:
- ``create_api_keys_blueprint`` – Quart :class:`~quart.Blueprint` with full
  CRUD management endpoints (same REST contract as the FastAPI/Litestar
  counterparts).
- ``require_api_key`` – async decorator that verifies the
  ``Authorization: Bearer <api-key>`` header and stores the verified entity
  in ``quart.g.api_key``.

Example::

    from quart import Quart
    from keyshield.quart_api import create_api_keys_blueprint, require_api_key
    from keyshield.services.base import ApiKeyService
    from keyshield.repositories.in_memory import InMemoryApiKeyRepository
    from keyshield.hasher.argon2 import Argon2ApiKeyHasher

    _svc = ApiKeyService(
        repo=InMemoryApiKeyRepository(),
        hasher=Argon2ApiKeyHasher(pepper="your-secret-pepper"),
    )

    async def get_service():
        return _svc

    app = Quart(__name__)
    app.register_blueprint(create_api_keys_blueprint(svc_factory=get_service))

    @app.get("/protected")
    @require_api_key(svc_factory=get_service)
    async def protected():
        from quart import g
        return {"key_id": g.api_key.key_id}
"""

try:
    import quart  # noqa: F401
except ModuleNotFoundError as e:  # pragma: no cover
    raise ImportError("Quart integration requires 'quart'. Install it with: uv add keyshield[quart]") from e

from functools import wraps
from typing import Any, Awaitable, Callable, List, Optional

from pydantic import ValidationError
from quart import Blueprint, abort, g, jsonify, request

from keyshield.domain.errors import (
    InvalidKey,
    InvalidScopes,
    KeyExpired,
    KeyInactive,
    KeyNotFound,
    KeyNotProvided,
)
from keyshield.services.base import AbstractApiKeyService
from keyshield._schemas import (
    ApiKeyCountOut,
    ApiKeyCreateIn,
    ApiKeyCreatedOut,
    ApiKeySearchIn,
    ApiKeySearchOut,
    ApiKeyUpdateIn,
    ApiKeyVerifyIn,
    _to_out,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _parse_body(model_class: Any) -> Any:
    """Parse the request JSON body and validate it with the given Pydantic model.

    Raises:
        400: If the Content-Type is not JSON or the body is empty.
        422: If Pydantic validation fails.
    """
    data = await request.get_json(silent=True)
    if data is None:
        abort(400, description="JSON body required")
    try:
        return model_class(**data)
    except (ValidationError, TypeError) as exc:
        abort(422, description=str(exc))


async def _verify_key_or_abort(
    svc: AbstractApiKeyService,
    api_key_str: str,
    required_scopes: Optional[List[str]] = None,
) -> Any:
    """Run ``svc.verify_key`` and map domain errors to HTTP abort codes."""
    try:
        return await svc.verify_key(api_key_str, required_scopes=required_scopes)
    except KeyNotProvided:
        abort(401, description="API key missing")
    except (InvalidKey, KeyNotFound):
        abort(401, description="API key invalid")
    except KeyInactive:
        abort(403, description="API key inactive")
    except KeyExpired:
        abort(403, description="API key expired")
    except InvalidScopes:
        scopes_str = ", ".join([f"'{s}'" for s in (required_scopes or [])])
        abort(403, description=f"API key missing required scopes {scopes_str}")


# ---------------------------------------------------------------------------
# Blueprint factory
# ---------------------------------------------------------------------------


def create_api_keys_blueprint(
    svc_factory: Callable[..., Awaitable[AbstractApiKeyService]],
    url_prefix: str = "/api-keys",
    name: str = "api_keys",
) -> Blueprint:
    """Create a Quart ``Blueprint`` with full API key management endpoints.

    Args:
        svc_factory: Async callable that returns an
            :class:`~keyshield.services.base.AbstractApiKeyService`.
        url_prefix: URL prefix for all routes (default ``"/api-keys"``).
        name: Blueprint name (default ``"api_keys"``).

    Returns:
        A :class:`quart.Blueprint` ready to be registered on a Quart app.
    """
    bp = Blueprint(name, __name__, url_prefix=url_prefix)

    # ------------------------------------------------------------------
    # POST /  – Create
    # ------------------------------------------------------------------

    @bp.post("/")
    async def create_api_key() -> Any:
        """Create an API key and return the plaintext secret **once**."""
        payload: ApiKeyCreateIn = await _parse_body(ApiKeyCreateIn)
        svc = await svc_factory()
        entity, api_key_str = await svc.create(
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
            scopes=payload.scopes,
            expires_at=payload.expires_at,
        )
        out = ApiKeyCreatedOut(api_key=api_key_str, entity=_to_out(entity))
        return jsonify(out.model_dump(mode="json")), 201

    # ------------------------------------------------------------------
    # GET /  – List
    # ------------------------------------------------------------------

    @bp.get("/")
    async def list_api_keys() -> Any:
        """List API keys with offset/limit pagination."""
        try:
            offset = int(request.args.get("offset", 0))
            limit = int(request.args.get("limit", 50))
        except ValueError:
            abort(400, description="offset and limit must be integers")

        if offset < 0 or limit <= 0 or limit > 100:
            abort(400, description="offset >= 0 and 0 < limit <= 100")

        svc = await svc_factory()
        items = await svc.list(offset=offset, limit=limit)
        return jsonify([_to_out(e).model_dump(mode="json") for e in items])

    # ------------------------------------------------------------------
    # POST /search  – Search
    # ------------------------------------------------------------------

    @bp.post("/search")
    async def search_api_keys() -> Any:
        """Search API keys with advanced filtering criteria."""
        try:
            offset = int(request.args.get("offset", 0))
            limit = int(request.args.get("limit", 50))
        except ValueError:
            abort(400, description="offset and limit must be integers")

        payload: ApiKeySearchIn = await _parse_body(ApiKeySearchIn)
        svc = await svc_factory()
        filter_ = payload.to_filter(limit=limit, offset=offset)
        items = await svc.find(filter_)
        total = await svc.count(filter_)
        out = ApiKeySearchOut(
            items=[_to_out(e) for e in items],
            total=total,
            limit=limit,
            offset=offset,
        )
        return jsonify(out.model_dump(mode="json"))

    # ------------------------------------------------------------------
    # POST /count  – Count
    # ------------------------------------------------------------------

    @bp.post("/count")
    async def count_api_keys() -> Any:
        """Count API keys matching the given filter criteria."""
        payload: ApiKeySearchIn = await _parse_body(ApiKeySearchIn)
        svc = await svc_factory()
        filter_ = payload.to_filter(limit=0, offset=0)
        total = await svc.count(filter_)
        return jsonify(ApiKeyCountOut(total=total).model_dump(mode="json"))

    # ------------------------------------------------------------------
    # POST /verify  – Verify
    # ------------------------------------------------------------------

    @bp.post("/verify")
    async def verify_api_key() -> Any:
        """Verify an API key and return its details if valid."""
        payload: ApiKeyVerifyIn = await _parse_body(ApiKeyVerifyIn)
        svc = await svc_factory()
        entity = await _verify_key_or_abort(
            svc=svc,
            api_key_str=payload.api_key,
            required_scopes=payload.required_scopes,
        )
        return jsonify(_to_out(entity).model_dump(mode="json"))

    # ------------------------------------------------------------------
    # GET /<id>  – Get
    # ------------------------------------------------------------------

    @bp.get("/<api_key_id>")
    async def get_api_key(api_key_id: str) -> Any:
        """Retrieve an API key by its identifier."""
        svc = await svc_factory()
        try:
            entity = await svc.get_by_id(api_key_id)
        except KeyNotFound:
            abort(404, description="API key not found")
        return jsonify(_to_out(entity).model_dump(mode="json"))

    # ------------------------------------------------------------------
    # PATCH /<id>  – Update
    # ------------------------------------------------------------------

    @bp.patch("/<api_key_id>")
    async def update_api_key(api_key_id: str) -> Any:
        """Partially update an API key."""
        payload: ApiKeyUpdateIn = await _parse_body(ApiKeyUpdateIn)
        svc = await svc_factory()
        try:
            current = await svc.get_by_id(api_key_id)
        except KeyNotFound:
            abort(404, description="API key not found")

        if payload.name is not None:
            current.name = payload.name
        if payload.description is not None:
            current.description = payload.description
        if payload.is_active is not None:
            current.is_active = payload.is_active
        if payload.scopes is not None:
            current.scopes = payload.scopes
        if payload.clear_expires:
            current.expires_at = None
        elif payload.expires_at is not None:
            current.expires_at = payload.expires_at

        try:
            updated = await svc.update(current)
        except KeyNotFound:
            abort(404, description="API key not found")
        return jsonify(_to_out(updated).model_dump(mode="json"))

    # ------------------------------------------------------------------
    # DELETE /<id>  – Delete
    # ------------------------------------------------------------------

    @bp.delete("/<api_key_id>")
    async def delete_api_key(api_key_id: str) -> Any:
        """Delete an API key by ID."""
        svc = await svc_factory()
        try:
            await svc.delete_by_id(api_key_id)
        except KeyNotFound:
            abort(404, description="API key not found")
        return "", 204

    # ------------------------------------------------------------------
    # POST /<id>/activate  – Activate
    # ------------------------------------------------------------------

    @bp.post("/<api_key_id>/activate")
    async def activate_api_key(api_key_id: str) -> Any:
        """Activate an API key by ID."""
        svc = await svc_factory()
        try:
            entity = await svc.get_by_id(api_key_id)
        except KeyNotFound:
            abort(404, description="API key not found")

        if entity.is_active:
            return jsonify(_to_out(entity).model_dump(mode="json"))

        entity.is_active = True
        updated = await svc.update(entity)
        return jsonify(_to_out(updated).model_dump(mode="json"))

    # ------------------------------------------------------------------
    # POST /<id>/deactivate  – Deactivate
    # ------------------------------------------------------------------

    @bp.post("/<api_key_id>/deactivate")
    async def deactivate_api_key(api_key_id: str) -> Any:
        """Deactivate an API key by ID."""
        svc = await svc_factory()
        try:
            entity = await svc.get_by_id(api_key_id)
        except KeyNotFound:
            abort(404, description="API key not found")

        if not entity.is_active:
            return jsonify(_to_out(entity).model_dump(mode="json"))

        entity.is_active = False
        updated = await svc.update(entity)
        return jsonify(_to_out(updated).model_dump(mode="json"))

    return bp


# ---------------------------------------------------------------------------
# Auth decorator
# ---------------------------------------------------------------------------


def require_api_key(
    svc_factory: Callable[..., Awaitable[AbstractApiKeyService]],
    required_scopes: Optional[List[str]] = None,
) -> Callable:
    """Decorator that verifies the ``Authorization: Bearer`` header.

    On success, stores the verified :class:`~keyshield.domain.entities.ApiKey`
    entity in ``quart.g.api_key`` for downstream access.

    Args:
        svc_factory: Async callable returning an
            :class:`~keyshield.services.base.AbstractApiKeyService`.
        required_scopes: Optional list of scopes the key must possess.

    Example::

        @app.get("/protected")
        @require_api_key(svc_factory=get_service, required_scopes=["read"])
        async def protected():
            return {"key_id": g.api_key.key_id}
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            auth = request.headers.get("Authorization", "")
            if not auth.lower().startswith("bearer "):
                abort(401, description="API key missing")

            api_key_str = auth[7:]
            svc = await svc_factory()
            entity = await _verify_key_or_abort(
                svc=svc,
                api_key_str=api_key_str,
                required_scopes=required_scopes,
            )
            g.api_key = entity
            return await func(*args, **kwargs)

        return wrapper

    return decorator
