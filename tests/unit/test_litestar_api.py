"""Unit tests for the Litestar integration module.

Tests verify API routes work correctly using InMemory repository.
Structure mirrors test_api.py to keep parity between FastAPI and Litestar.
"""

from datetime import timedelta

import pytest
from litestar import Litestar, get
from litestar.di import Provide
from litestar.testing import TestClient

from fastapi_api_key.litestar_api import create_api_key_guard, create_api_keys_router
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
def app(service: ApiKeyService) -> Litestar:
    async def provide_svc() -> ApiKeyService:
        return service

    router = create_api_keys_router(provide_svc=provide_svc)
    return Litestar(route_handlers=[router])


@pytest.fixture
def client(app: Litestar) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class TestCreateApiKey:
    def test_create_with_name(self, client: TestClient) -> None:
        response = client.post(
            "/api-keys/", content='{"name": "test-key"}', headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 201
        data = response.json()
        assert "api_key" in data
        assert data["entity"]["name"] == "test-key"
        assert data["entity"]["is_active"] is True

    def test_create_with_all_fields(self, client: TestClient) -> None:
        payload = '{"name":"test-key","description":"desc","is_active":false,"scopes":["read","write"]}'
        response = client.post("/api-keys/", content=payload, headers={"Content-Type": "application/json"})
        assert response.status_code == 201
        data = response.json()
        assert data["entity"]["description"] == "desc"
        assert data["entity"]["is_active"] is False
        assert data["entity"]["scopes"] == ["read", "write"]

    def test_create_returns_key_id(self, client: TestClient) -> None:
        response = client.post("/api-keys/", content='{"name":"k"}', headers={"Content-Type": "application/json"})
        assert response.status_code == 201
        data = response.json()
        assert len(data["entity"]["key_id"]) == 16

    def test_create_with_expires_at(self, client: TestClient) -> None:
        expires = (datetime_factory() + timedelta(days=30)).isoformat()
        payload = f'{{"name":"expiring","expires_at":"{expires}"}}'
        response = client.post("/api-keys/", content=payload, headers={"Content-Type": "application/json"})
        assert response.status_code == 201
        assert response.json()["entity"]["expires_at"] is not None


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class TestListApiKeys:
    def test_list_empty(self, client: TestClient) -> None:
        response = client.get("/api-keys/")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_returns_keys(self, client: TestClient) -> None:
        client.post("/api-keys/", content='{"name":"k1"}', headers={"Content-Type": "application/json"})
        client.post("/api-keys/", content='{"name":"k2"}', headers={"Content-Type": "application/json"})
        response = client.get("/api-keys/")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_with_pagination(self, client: TestClient) -> None:
        for i in range(5):
            client.post("/api-keys/", content=f'{{"name":"k{i}"}}', headers={"Content-Type": "application/json"})
        response = client.get("/api-keys/?limit=2&offset=1")
        assert response.status_code == 200
        assert len(response.json()) == 2


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


class TestGetApiKey:
    def test_get_existing_key(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api-keys/", content='{"name":"test-key"}', headers={"Content-Type": "application/json"}
        )
        key_id = create_resp.json()["entity"]["id"]
        response = client.get(f"/api-keys/{key_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "test-key"

    def test_get_not_found(self, client: TestClient) -> None:
        response = client.get("/api-keys/non-existent-id")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class TestUpdateApiKey:
    def test_update_name(self, client: TestClient) -> None:
        create_resp = client.post("/api-keys/", content='{"name":"old"}', headers={"Content-Type": "application/json"})
        key_id = create_resp.json()["entity"]["id"]
        response = client.patch(
            f"/api-keys/{key_id}", content='{"name":"new"}', headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "new"

    def test_update_clear_expires(self, client: TestClient) -> None:
        expires = (datetime_factory() + timedelta(days=30)).isoformat()
        create_resp = client.post(
            "/api-keys/",
            content=f'{{"name":"k","expires_at":"{expires}"}}',
            headers={"Content-Type": "application/json"},
        )
        key_id = create_resp.json()["entity"]["id"]
        response = client.patch(
            f"/api-keys/{key_id}",
            content='{"clear_expires":true}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json()["expires_at"] is None

    def test_update_not_found(self, client: TestClient) -> None:
        response = client.patch(
            "/api-keys/no-such-id",
            content='{"name":"x"}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 404

    def test_update_scopes(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api-keys/",
            content='{"name":"k","scopes":["read"]}',
            headers={"Content-Type": "application/json"},
        )
        key_id = create_resp.json()["entity"]["id"]
        response = client.patch(
            f"/api-keys/{key_id}",
            content='{"scopes":["read","write","admin"]}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json()["scopes"] == ["read", "write", "admin"]


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDeleteApiKey:
    def test_delete_existing_key(self, client: TestClient) -> None:
        create_resp = client.post("/api-keys/", content='{"name":"k"}', headers={"Content-Type": "application/json"})
        key_id = create_resp.json()["entity"]["id"]
        assert client.delete(f"/api-keys/{key_id}").status_code == 204
        assert client.get(f"/api-keys/{key_id}").status_code == 404

    def test_delete_not_found(self, client: TestClient) -> None:
        assert client.delete("/api-keys/no-such-id").status_code == 404


# ---------------------------------------------------------------------------
# Activate / Deactivate
# ---------------------------------------------------------------------------


class TestActivateDeactivate:
    def test_activate_inactive_key(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api-keys/",
            content='{"name":"k","is_active":false}',
            headers={"Content-Type": "application/json"},
        )
        key_id = create_resp.json()["entity"]["id"]
        response = client.post(f"/api-keys/{key_id}/activate")
        assert response.status_code == 200
        assert response.json()["is_active"] is True

    def test_activate_already_active(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api-keys/",
            content='{"name":"k","is_active":true}',
            headers={"Content-Type": "application/json"},
        )
        key_id = create_resp.json()["entity"]["id"]
        response = client.post(f"/api-keys/{key_id}/activate")
        assert response.status_code == 200
        assert response.json()["is_active"] is True

    def test_deactivate_active_key(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api-keys/",
            content='{"name":"k","is_active":true}',
            headers={"Content-Type": "application/json"},
        )
        key_id = create_resp.json()["entity"]["id"]
        response = client.post(f"/api-keys/{key_id}/deactivate")
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_deactivate_already_inactive(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api-keys/",
            content='{"name":"k","is_active":false}',
            headers={"Content-Type": "application/json"},
        )
        key_id = create_resp.json()["entity"]["id"]
        response = client.post(f"/api-keys/{key_id}/deactivate")
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_activate_not_found(self, client: TestClient) -> None:
        assert client.post("/api-keys/no-such-id/activate").status_code == 404

    def test_deactivate_not_found(self, client: TestClient) -> None:
        assert client.post("/api-keys/no-such-id/deactivate").status_code == 404


# ---------------------------------------------------------------------------
# Search / Count
# ---------------------------------------------------------------------------


class TestSearchApiKeys:
    def test_search_empty_filter(self, client: TestClient) -> None:
        client.post("/api-keys/", content='{"name":"k1"}', headers={"Content-Type": "application/json"})
        client.post("/api-keys/", content='{"name":"k2"}', headers={"Content-Type": "application/json"})
        response = client.post("/api-keys/search", content="{}", headers={"Content-Type": "application/json"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_search_by_active_status(self, client: TestClient) -> None:
        client.post(
            "/api-keys/", content='{"name":"active","is_active":true}', headers={"Content-Type": "application/json"}
        )
        client.post(
            "/api-keys/", content='{"name":"inactive","is_active":false}', headers={"Content-Type": "application/json"}
        )
        response = client.post(
            "/api-keys/search", content='{"is_active":true}', headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "active"

    def test_search_by_name_contains(self, client: TestClient) -> None:
        client.post("/api-keys/", content='{"name":"production-key"}', headers={"Content-Type": "application/json"})
        client.post("/api-keys/", content='{"name":"staging-key"}', headers={"Content-Type": "application/json"})
        response = client.post(
            "/api-keys/search", content='{"name_contains":"prod"}', headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1


class TestCountApiKeys:
    def test_count_all(self, client: TestClient) -> None:
        for i in range(3):
            client.post("/api-keys/", content=f'{{"name":"k{i}"}}', headers={"Content-Type": "application/json"})
        response = client.post("/api-keys/count", content="{}", headers={"Content-Type": "application/json"})
        assert response.status_code == 200
        assert response.json()["total"] == 3

    def test_count_with_filter(self, client: TestClient) -> None:
        client.post(
            "/api-keys/", content='{"name":"a1","is_active":true}', headers={"Content-Type": "application/json"}
        )
        client.post(
            "/api-keys/", content='{"name":"a2","is_active":true}', headers={"Content-Type": "application/json"}
        )
        client.post(
            "/api-keys/", content='{"name":"i","is_active":false}', headers={"Content-Type": "application/json"}
        )
        response = client.post(
            "/api-keys/count", content='{"is_active":true}', headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        assert response.json()["total"] == 2

    def test_count_empty(self, client: TestClient) -> None:
        response = client.post("/api-keys/count", content="{}", headers={"Content-Type": "application/json"})
        assert response.status_code == 200
        assert response.json()["total"] == 0


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


class TestVerifyApiKey:
    def test_verify_valid_key(self, client: TestClient) -> None:
        create_resp = client.post("/api-keys/", content='{"name":"k"}', headers={"Content-Type": "application/json"})
        api_key = create_resp.json()["api_key"]
        response = client.post(
            "/api-keys/verify",
            content=f'{{"api_key":"{api_key}"}}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "k"

    def test_verify_invalid_key(self, client: TestClient) -> None:
        response = client.post(
            "/api-keys/verify",
            content='{"api_key":"ak-invalid-invalidkey"}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 401

    def test_verify_inactive_key(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api-keys/",
            content='{"name":"k","is_active":false}',
            headers={"Content-Type": "application/json"},
        )
        api_key = create_resp.json()["api_key"]
        response = client.post(
            "/api-keys/verify",
            content=f'{{"api_key":"{api_key}"}}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 403

    def test_verify_with_matching_scopes(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api-keys/",
            content='{"name":"k","scopes":["read","write"]}',
            headers={"Content-Type": "application/json"},
        )
        api_key = create_resp.json()["api_key"]
        response = client.post(
            "/api-keys/verify",
            content=f'{{"api_key":"{api_key}","required_scopes":["read"]}}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200

    def test_verify_with_missing_scopes(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api-keys/",
            content='{"name":"k","scopes":["read"]}',
            headers={"Content-Type": "application/json"},
        )
        api_key = create_resp.json()["api_key"]
        response = client.post(
            "/api-keys/verify",
            content=f'{{"api_key":"{api_key}","required_scopes":["admin"]}}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


class TestApiKeyGuard:
    @pytest.mark.asyncio
    async def test_guard_valid_key(self, service: ApiKeyService) -> None:
        async def provide_svc() -> ApiKeyService:
            return service

        guard = create_api_key_guard(provide_svc=provide_svc)

        @get("/protected", guards=[guard])
        async def protected() -> dict:
            return {"ok": True}

        app = Litestar(
            route_handlers=[protected],
            dependencies={"svc": Provide(provide_svc)},
        )

        entity, api_key = await service.create(name="k")

        with TestClient(app) as c:
            response = c.get("/protected", headers={"Authorization": f"Bearer {api_key}"})
        assert response.status_code == 200

    def test_guard_missing_key(self, service: ApiKeyService) -> None:
        async def provide_svc() -> ApiKeyService:
            return service

        guard = create_api_key_guard(provide_svc=provide_svc)

        @get("/protected", guards=[guard])
        async def protected() -> dict:
            return {"ok": True}

        with TestClient(Litestar(route_handlers=[protected])) as c:
            response = c.get("/protected")
        assert response.status_code == 401

    def test_guard_invalid_key(self, service: ApiKeyService) -> None:
        async def provide_svc() -> ApiKeyService:
            return service

        guard = create_api_key_guard(provide_svc=provide_svc)

        @get("/protected", guards=[guard])
        async def protected() -> dict:
            return {"ok": True}

        with TestClient(Litestar(route_handlers=[protected])) as c:
            response = c.get("/protected", headers={"Authorization": "Bearer ak-invalid-badkey"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_guard_inactive_key(self, service: ApiKeyService) -> None:
        async def provide_svc() -> ApiKeyService:
            return service

        guard = create_api_key_guard(provide_svc=provide_svc)

        @get("/protected", guards=[guard])
        async def protected() -> dict:
            return {"ok": True}

        app = Litestar(route_handlers=[protected])
        entity, api_key = await service.create(name="k", is_active=False)

        with TestClient(app) as c:
            response = c.get("/protected", headers={"Authorization": f"Bearer {api_key}"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_guard_expired_key(self, service: ApiKeyService) -> None:
        async def provide_svc() -> ApiKeyService:
            return service

        guard = create_api_key_guard(provide_svc=provide_svc)

        @get("/protected", guards=[guard])
        async def protected() -> dict:
            return {"ok": True}

        app = Litestar(route_handlers=[protected])
        entity, api_key = await service.create(name="k")
        entity.expires_at = datetime_factory() - timedelta(days=1)
        await service.update(entity)

        with TestClient(app) as c:
            response = c.get("/protected", headers={"Authorization": f"Bearer {api_key}"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_guard_missing_scopes(self, service: ApiKeyService) -> None:
        async def provide_svc() -> ApiKeyService:
            return service

        guard = create_api_key_guard(provide_svc=provide_svc, required_scopes=["admin"])

        @get("/protected", guards=[guard])
        async def protected() -> dict:
            return {"ok": True}

        app = Litestar(route_handlers=[protected])
        entity, api_key = await service.create(name="k", scopes=["read"])

        with TestClient(app) as c:
            response = c.get("/protected", headers={"Authorization": f"Bearer {api_key}"})
        assert response.status_code == 403
