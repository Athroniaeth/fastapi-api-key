"""Unit tests for the Quart integration module.

Tests verify API routes work correctly using InMemory repository.
Structure mirrors test_api.py to keep parity between all framework integrations.
"""

from datetime import timedelta

import pytest
from quart import Quart, g

from fastapi_api_key.quart_api import create_api_keys_blueprint, require_api_key
from fastapi_api_key.hasher.base import MockApiKeyHasher
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key.services.base import ApiKeyService
from fastapi_api_key.utils import datetime_factory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo() -> InMemoryApiKeyRepository:
    return InMemoryApiKeyRepository()


@pytest.fixture
def service(repo: InMemoryApiKeyRepository) -> ApiKeyService:
    return ApiKeyService(
        repo=repo,
        hasher=MockApiKeyHasher(pepper="test-pepper"),
        min_delay=0,
        max_delay=0,
    )


@pytest.fixture
def app(service: ApiKeyService) -> Quart:
    async def get_service() -> ApiKeyService:
        return service

    application = Quart(__name__)
    application.register_blueprint(create_api_keys_blueprint(svc_factory=get_service))
    return application


@pytest.fixture
def client(app: Quart):
    return app.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

JSON_CT = {"Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class TestCreateApiKey:
    @pytest.mark.asyncio
    async def test_create_with_name(self, client) -> None:
        response = await client.post("/api-keys/", json={"name": "test-key"})
        assert response.status_code == 201
        data = await response.get_json()
        assert "api_key" in data
        assert data["entity"]["name"] == "test-key"
        assert data["entity"]["is_active"] is True

    @pytest.mark.asyncio
    async def test_create_with_all_fields(self, client) -> None:
        response = await client.post(
            "/api-keys/",
            json={"name": "key", "description": "desc", "is_active": False, "scopes": ["read", "write"]},
        )
        assert response.status_code == 201
        data = await response.get_json()
        assert data["entity"]["description"] == "desc"
        assert data["entity"]["is_active"] is False
        assert data["entity"]["scopes"] == ["read", "write"]

    @pytest.mark.asyncio
    async def test_create_returns_key_id(self, client) -> None:
        response = await client.post("/api-keys/", json={"name": "k"})
        assert response.status_code == 201
        data = await response.get_json()
        assert len(data["entity"]["key_id"]) == 16

    @pytest.mark.asyncio
    async def test_create_with_expires_at(self, client) -> None:
        expires = (datetime_factory() + timedelta(days=30)).isoformat()
        response = await client.post("/api-keys/", json={"name": "k", "expires_at": expires})
        assert response.status_code == 201
        data = await response.get_json()
        assert data["entity"]["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_create_without_body_returns_400(self, client) -> None:
        response = await client.post("/api-keys/", data="not-json", headers=JSON_CT)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_invalid_body_returns_422(self, client) -> None:
        # name is required – missing → ValidationError → 422
        response = await client.post("/api-keys/", json={})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class TestListApiKeys:
    @pytest.mark.asyncio
    async def test_list_empty(self, client) -> None:
        response = await client.get("/api-keys/")
        assert response.status_code == 200
        assert await response.get_json() == []

    @pytest.mark.asyncio
    async def test_list_returns_keys(self, client) -> None:
        await client.post("/api-keys/", json={"name": "k1"})
        await client.post("/api-keys/", json={"name": "k2"})
        response = await client.get("/api-keys/")
        assert response.status_code == 200
        assert len(await response.get_json()) == 2

    @pytest.mark.asyncio
    async def test_list_with_pagination(self, client) -> None:
        for i in range(5):
            await client.post("/api-keys/", json={"name": f"k{i}"})
        response = await client.get("/api-keys/?limit=2&offset=1")
        assert response.status_code == 200
        assert len(await response.get_json()) == 2


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


class TestGetApiKey:
    @pytest.mark.asyncio
    async def test_get_existing_key(self, client) -> None:
        create_resp = await client.post("/api-keys/", json={"name": "test-key"})
        key_id = (await create_resp.get_json())["entity"]["id"]
        response = await client.get(f"/api-keys/{key_id}")
        assert response.status_code == 200
        assert (await response.get_json())["name"] == "test-key"

    @pytest.mark.asyncio
    async def test_get_not_found(self, client) -> None:
        response = await client.get("/api-keys/non-existent-id")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class TestUpdateApiKey:
    @pytest.mark.asyncio
    async def test_update_name(self, client) -> None:
        create_resp = await client.post("/api-keys/", json={"name": "old"})
        key_id = (await create_resp.get_json())["entity"]["id"]
        response = await client.patch(f"/api-keys/{key_id}", json={"name": "new"})
        assert response.status_code == 200
        assert (await response.get_json())["name"] == "new"

    @pytest.mark.asyncio
    async def test_update_clear_expires(self, client) -> None:
        expires = (datetime_factory() + timedelta(days=30)).isoformat()
        create_resp = await client.post("/api-keys/", json={"name": "k", "expires_at": expires})
        key_id = (await create_resp.get_json())["entity"]["id"]
        response = await client.patch(f"/api-keys/{key_id}", json={"clear_expires": True})
        assert response.status_code == 200
        assert (await response.get_json())["expires_at"] is None

    @pytest.mark.asyncio
    async def test_update_not_found(self, client) -> None:
        response = await client.patch("/api-keys/no-such-id", json={"name": "x"})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_scopes(self, client) -> None:
        create_resp = await client.post("/api-keys/", json={"name": "k", "scopes": ["read"]})
        key_id = (await create_resp.get_json())["entity"]["id"]
        response = await client.patch(f"/api-keys/{key_id}", json={"scopes": ["read", "write", "admin"]})
        assert response.status_code == 200
        assert (await response.get_json())["scopes"] == ["read", "write", "admin"]

    @pytest.mark.asyncio
    async def test_update_is_active(self, client) -> None:
        create_resp = await client.post("/api-keys/", json={"name": "k", "is_active": True})
        key_id = (await create_resp.get_json())["entity"]["id"]
        response = await client.patch(f"/api-keys/{key_id}", json={"is_active": False})
        assert response.status_code == 200
        assert (await response.get_json())["is_active"] is False


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDeleteApiKey:
    @pytest.mark.asyncio
    async def test_delete_existing_key(self, client) -> None:
        create_resp = await client.post("/api-keys/", json={"name": "k"})
        key_id = (await create_resp.get_json())["entity"]["id"]
        assert (await client.delete(f"/api-keys/{key_id}")).status_code == 204
        assert (await client.get(f"/api-keys/{key_id}")).status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client) -> None:
        assert (await client.delete("/api-keys/no-such-id")).status_code == 404


# ---------------------------------------------------------------------------
# Activate / Deactivate
# ---------------------------------------------------------------------------


class TestActivateDeactivate:
    @pytest.mark.asyncio
    async def test_activate_inactive_key(self, client) -> None:
        create_resp = await client.post("/api-keys/", json={"name": "k", "is_active": False})
        key_id = (await create_resp.get_json())["entity"]["id"]
        response = await client.post(f"/api-keys/{key_id}/activate")
        assert response.status_code == 200
        assert (await response.get_json())["is_active"] is True

    @pytest.mark.asyncio
    async def test_activate_already_active(self, client) -> None:
        create_resp = await client.post("/api-keys/", json={"name": "k", "is_active": True})
        key_id = (await create_resp.get_json())["entity"]["id"]
        response = await client.post(f"/api-keys/{key_id}/activate")
        assert response.status_code == 200
        assert (await response.get_json())["is_active"] is True

    @pytest.mark.asyncio
    async def test_deactivate_active_key(self, client) -> None:
        create_resp = await client.post("/api-keys/", json={"name": "k", "is_active": True})
        key_id = (await create_resp.get_json())["entity"]["id"]
        response = await client.post(f"/api-keys/{key_id}/deactivate")
        assert response.status_code == 200
        assert (await response.get_json())["is_active"] is False

    @pytest.mark.asyncio
    async def test_deactivate_already_inactive(self, client) -> None:
        create_resp = await client.post("/api-keys/", json={"name": "k", "is_active": False})
        key_id = (await create_resp.get_json())["entity"]["id"]
        response = await client.post(f"/api-keys/{key_id}/deactivate")
        assert response.status_code == 200
        assert (await response.get_json())["is_active"] is False

    @pytest.mark.asyncio
    async def test_activate_not_found(self, client) -> None:
        assert (await client.post("/api-keys/no-such-id/activate")).status_code == 404

    @pytest.mark.asyncio
    async def test_deactivate_not_found(self, client) -> None:
        assert (await client.post("/api-keys/no-such-id/deactivate")).status_code == 404


# ---------------------------------------------------------------------------
# Search / Count
# ---------------------------------------------------------------------------


class TestSearchApiKeys:
    @pytest.mark.asyncio
    async def test_search_empty_filter(self, client) -> None:
        await client.post("/api-keys/", json={"name": "k1"})
        await client.post("/api-keys/", json={"name": "k2"})
        response = await client.post("/api-keys/search", json={})
        assert response.status_code == 200
        data = await response.get_json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_search_by_active_status(self, client) -> None:
        await client.post("/api-keys/", json={"name": "active", "is_active": True})
        await client.post("/api-keys/", json={"name": "inactive", "is_active": False})
        response = await client.post("/api-keys/search", json={"is_active": True})
        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "active"

    @pytest.mark.asyncio
    async def test_search_by_name_contains(self, client) -> None:
        await client.post("/api-keys/", json={"name": "production-key"})
        await client.post("/api-keys/", json={"name": "staging-key"})
        response = await client.post("/api-keys/search", json={"name_contains": "prod"})
        assert response.status_code == 200
        assert len((await response.get_json())["items"]) == 1


class TestCountApiKeys:
    @pytest.mark.asyncio
    async def test_count_all(self, client) -> None:
        for i in range(3):
            await client.post("/api-keys/", json={"name": f"k{i}"})
        response = await client.post("/api-keys/count", json={})
        assert response.status_code == 200
        assert (await response.get_json())["total"] == 3

    @pytest.mark.asyncio
    async def test_count_with_filter(self, client) -> None:
        await client.post("/api-keys/", json={"name": "a1", "is_active": True})
        await client.post("/api-keys/", json={"name": "a2", "is_active": True})
        await client.post("/api-keys/", json={"name": "i", "is_active": False})
        response = await client.post("/api-keys/count", json={"is_active": True})
        assert response.status_code == 200
        assert (await response.get_json())["total"] == 2

    @pytest.mark.asyncio
    async def test_count_empty(self, client) -> None:
        response = await client.post("/api-keys/count", json={})
        assert response.status_code == 200
        assert (await response.get_json())["total"] == 0


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


class TestVerifyApiKey:
    @pytest.mark.asyncio
    async def test_verify_valid_key(self, client) -> None:
        create_resp = await client.post("/api-keys/", json={"name": "k"})
        api_key = (await create_resp.get_json())["api_key"]
        response = await client.post("/api-keys/verify", json={"api_key": api_key})
        assert response.status_code == 200
        assert (await response.get_json())["name"] == "k"

    @pytest.mark.asyncio
    async def test_verify_invalid_key(self, client) -> None:
        response = await client.post("/api-keys/verify", json={"api_key": "ak-invalid-invalidkey"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_inactive_key(self, client) -> None:
        create_resp = await client.post("/api-keys/", json={"name": "k", "is_active": False})
        api_key = (await create_resp.get_json())["api_key"]
        response = await client.post("/api-keys/verify", json={"api_key": api_key})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_verify_with_matching_scopes(self, client) -> None:
        create_resp = await client.post("/api-keys/", json={"name": "k", "scopes": ["read", "write"]})
        api_key = (await create_resp.get_json())["api_key"]
        response = await client.post("/api-keys/verify", json={"api_key": api_key, "required_scopes": ["read"]})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_verify_with_missing_scopes(self, client) -> None:
        create_resp = await client.post("/api-keys/", json={"name": "k", "scopes": ["read"]})
        api_key = (await create_resp.get_json())["api_key"]
        response = await client.post("/api-keys/verify", json={"api_key": api_key, "required_scopes": ["admin"]})
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# require_api_key decorator
# ---------------------------------------------------------------------------


class TestRequireApiKey:
    @pytest.mark.asyncio
    async def test_valid_key_passes(self, service: ApiKeyService) -> None:
        async def get_service() -> ApiKeyService:
            return service

        app = Quart(__name__)

        @app.get("/protected")
        @require_api_key(svc_factory=get_service)
        async def protected():
            return {"key_id": g.api_key.key_id}

        entity, api_key = await service.create(name="k")
        async with app.test_client() as c:
            response = await c.get("/protected", headers={"Authorization": f"Bearer {api_key}"})
        assert response.status_code == 200
        data = await response.get_json()
        assert data["key_id"] == entity.key_id

    @pytest.mark.asyncio
    async def test_missing_key_returns_401(self, service: ApiKeyService) -> None:
        async def get_service() -> ApiKeyService:
            return service

        app = Quart(__name__)

        @app.get("/protected")
        @require_api_key(svc_factory=get_service)
        async def protected():
            return {"ok": True}

        async with app.test_client() as c:
            response = await c.get("/protected")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_key_returns_401(self, service: ApiKeyService) -> None:
        async def get_service() -> ApiKeyService:
            return service

        app = Quart(__name__)

        @app.get("/protected")
        @require_api_key(svc_factory=get_service)
        async def protected():
            return {"ok": True}

        async with app.test_client() as c:
            response = await c.get("/protected", headers={"Authorization": "Bearer ak-invalid-badkey"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_key_returns_403(self, service: ApiKeyService) -> None:
        async def get_service() -> ApiKeyService:
            return service

        app = Quart(__name__)

        @app.get("/protected")
        @require_api_key(svc_factory=get_service)
        async def protected():
            return {"ok": True}

        entity, api_key = await service.create(name="k", is_active=False)
        async with app.test_client() as c:
            response = await c.get("/protected", headers={"Authorization": f"Bearer {api_key}"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_expired_key_returns_403(self, service: ApiKeyService) -> None:
        async def get_service() -> ApiKeyService:
            return service

        app = Quart(__name__)

        @app.get("/protected")
        @require_api_key(svc_factory=get_service)
        async def protected():
            return {"ok": True}

        entity, api_key = await service.create(name="k")
        entity.expires_at = datetime_factory() - timedelta(days=1)
        await service.update(entity)

        async with app.test_client() as c:
            response = await c.get("/protected", headers={"Authorization": f"Bearer {api_key}"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_scopes_returns_403(self, service: ApiKeyService) -> None:
        async def get_service() -> ApiKeyService:
            return service

        app = Quart(__name__)

        @app.get("/protected")
        @require_api_key(svc_factory=get_service, required_scopes=["admin"])
        async def protected():
            return {"ok": True}

        entity, api_key = await service.create(name="k", scopes=["read"])
        async with app.test_client() as c:
            response = await c.get("/protected", headers={"Authorization": f"Bearer {api_key}"})
        assert response.status_code == 403
