"""Unit tests for the API router module.

Tests verify API routes work correctly using InMemory repository.
Focus on behavior, not implementation details.
"""

import warnings
from contextlib import asynccontextmanager
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.security import APIKeyHeader, HTTPBearer
from fastapi.testclient import TestClient

from fastapi_api_key import ApiKeyService
from fastapi_api_key.api import create_api_keys_router, create_depends_api_key
from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.domain.errors import KeyNotFound, KeyNotProvided
from fastapi_api_key.hasher.base import MockApiKeyHasher
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key.services.base import AbstractApiKeyService
from fastapi_api_key.utils import datetime_factory


@pytest.fixture
def repo() -> InMemoryApiKeyRepository:
    """Fresh in-memory repository for each test."""
    return InMemoryApiKeyRepository()


@pytest.fixture
def service(repo: InMemoryApiKeyRepository) -> ApiKeyService:
    """Service with mock hasher for fast tests."""
    return ApiKeyService(
        repo=repo,
        hasher=MockApiKeyHasher(pepper="test-pepper"),
        min_delay=0,
        max_delay=0,
    )


@pytest.fixture
def app(service: ApiKeyService) -> FastAPI:
    """FastAPI app with API keys router."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(lifespan=lifespan)

    async def get_service():
        return service

    router = create_api_keys_router(depends_svc_api_keys=get_service)
    app.include_router(router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Test client for the FastAPI app."""
    return TestClient(app)


class TestCreateApiKey:
    """Tests for POST / endpoint."""

    def test_create_with_name(self, client: TestClient):
        """Create a key with just a name."""
        response = client.post("/api-keys/", json={"name": "test-key"})
        assert response.status_code == 201
        data = response.json()
        assert "api_key" in data
        assert data["entity"]["name"] == "test-key"
        assert data["entity"]["is_active"] is True

    def test_create_with_all_fields(self, client: TestClient):
        """Create a key with all fields."""
        response = client.post(
            "/api-keys/",
            json={
                "name": "test-key",
                "description": "Test description",
                "is_active": False,
                "scopes": ["read", "write"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["entity"]["name"] == "test-key"
        assert data["entity"]["description"] == "Test description"
        assert data["entity"]["is_active"] is False
        assert data["entity"]["scopes"] == ["read", "write"]

    def test_create_with_expires_at(self, client: TestClient):
        """Create a key with expiration date."""
        expires = (datetime_factory() + timedelta(days=30)).isoformat()
        response = client.post(
            "/api-keys/",
            json={"name": "expiring-key", "expires_at": expires},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["entity"]["expires_at"] is not None

    def test_create_returns_key_id(self, client: TestClient):
        """Create returns key_id in response."""
        response = client.post("/api-keys/", json={"name": "test-key"})
        assert response.status_code == 201
        data = response.json()
        assert "key_id" in data["entity"]
        assert len(data["entity"]["key_id"]) == 16


class TestListApiKeys:
    """Tests for GET / endpoint."""

    def test_list_empty(self, client: TestClient):
        """List returns empty array when no keys."""
        response = client.get("/api-keys/")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_returns_keys(self, client: TestClient):
        """List returns created keys."""
        client.post("/api-keys/", json={"name": "key-1"})
        client.post("/api-keys/", json={"name": "key-2"})

        response = client.get("/api-keys/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_with_pagination(self, client: TestClient):
        """List respects limit and offset."""
        for i in range(5):
            client.post("/api-keys/", json={"name": f"key-{i}"})

        response = client.get("/api-keys/", params={"limit": 2, "offset": 1})
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


class TestGetApiKey:
    """Tests for GET /{id} endpoint."""

    def test_get_existing_key(self, client: TestClient):
        """Get returns key details."""
        create_response = client.post("/api-keys/", json={"name": "test-key"})
        key_id = create_response.json()["entity"]["id"]

        response = client.get(f"/api-keys/{key_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test-key"
        assert "key_id" in data
        assert "expires_at" in data

    def test_get_not_found(self, client: TestClient):
        """Get returns 404 for non-existent key."""
        response = client.get("/api-keys/non-existent-id")
        assert response.status_code == 404


class TestUpdateApiKey:
    """Tests for PATCH /{id} endpoint."""

    def test_update_name(self, client: TestClient):
        """Update key name."""
        create_response = client.post("/api-keys/", json={"name": "old-name"})
        key_id = create_response.json()["entity"]["id"]

        response = client.patch(f"/api-keys/{key_id}", json={"name": "new-name"})
        assert response.status_code == 200
        assert response.json()["name"] == "new-name"

    def test_update_expires_at(self, client: TestClient):
        """Update expiration date."""
        create_response = client.post("/api-keys/", json={"name": "test-key"})
        key_id = create_response.json()["entity"]["id"]

        expires = (datetime_factory() + timedelta(days=30)).isoformat()
        response = client.patch(f"/api-keys/{key_id}", json={"expires_at": expires})
        assert response.status_code == 200
        assert response.json()["expires_at"] is not None

    def test_update_clear_expires(self, client: TestClient):
        """Clear expiration date."""
        expires = (datetime_factory() + timedelta(days=30)).isoformat()
        create_response = client.post("/api-keys/", json={"name": "test-key", "expires_at": expires})
        key_id = create_response.json()["entity"]["id"]

        response = client.patch(f"/api-keys/{key_id}", json={"clear_expires": True})
        assert response.status_code == 200
        assert response.json()["expires_at"] is None

    def test_update_not_found(self, client: TestClient):
        """Update returns 404 for non-existent key."""
        response = client.patch("/api-keys/non-existent-id", json={"name": "new-name"})
        assert response.status_code == 404

    def test_update_description(self, client: TestClient):
        """Update key description."""
        create_response = client.post("/api-keys/", json={"name": "test-key"})
        key_id = create_response.json()["entity"]["id"]

        response = client.patch(f"/api-keys/{key_id}", json={"description": "New description"})
        assert response.status_code == 200
        assert response.json()["description"] == "New description"

    def test_update_is_active(self, client: TestClient):
        """Update key active status."""
        create_response = client.post("/api-keys/", json={"name": "test-key", "is_active": True})
        key_id = create_response.json()["entity"]["id"]

        response = client.patch(f"/api-keys/{key_id}", json={"is_active": False})
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_update_scopes(self, client: TestClient):
        """Update key scopes."""
        create_response = client.post("/api-keys/", json={"name": "test-key", "scopes": ["read"]})
        key_id = create_response.json()["entity"]["id"]

        response = client.patch(f"/api-keys/{key_id}", json={"scopes": ["read", "write", "admin"]})
        assert response.status_code == 200
        assert response.json()["scopes"] == ["read", "write", "admin"]


class TestDeleteApiKey:
    """Tests for DELETE /{id} endpoint."""

    def test_delete_existing_key(self, client: TestClient):
        """Delete removes the key."""
        create_response = client.post("/api-keys/", json={"name": "test-key"})
        key_id = create_response.json()["entity"]["id"]

        response = client.delete(f"/api-keys/{key_id}")
        assert response.status_code == 204

        get_response = client.get(f"/api-keys/{key_id}")
        assert get_response.status_code == 404

    def test_delete_not_found(self, client: TestClient):
        """Delete returns 404 for non-existent key."""
        response = client.delete("/api-keys/non-existent-id")
        assert response.status_code == 404


class TestActivateDeactivate:
    """Tests for POST /{id}/activate and /{id}/deactivate endpoints."""

    def test_activate_inactive_key(self, client: TestClient):
        """Activate an inactive key."""
        create_response = client.post("/api-keys/", json={"name": "test-key", "is_active": False})
        key_id = create_response.json()["entity"]["id"]

        response = client.post(f"/api-keys/{key_id}/activate")
        assert response.status_code == 200
        assert response.json()["is_active"] is True

    def test_activate_already_active(self, client: TestClient):
        """Activate already active key returns success."""
        create_response = client.post("/api-keys/", json={"name": "test-key", "is_active": True})
        key_id = create_response.json()["entity"]["id"]

        response = client.post(f"/api-keys/{key_id}/activate")
        assert response.status_code == 200
        assert response.json()["is_active"] is True

    def test_deactivate_active_key(self, client: TestClient):
        """Deactivate an active key."""
        create_response = client.post("/api-keys/", json={"name": "test-key", "is_active": True})
        key_id = create_response.json()["entity"]["id"]

        response = client.post(f"/api-keys/{key_id}/deactivate")
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_deactivate_already_inactive(self, client: TestClient):
        """Deactivate already inactive key returns success."""
        create_response = client.post("/api-keys/", json={"name": "test-key", "is_active": False})
        key_id = create_response.json()["entity"]["id"]

        response = client.post(f"/api-keys/{key_id}/deactivate")
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_activate_not_found(self, client: TestClient):
        """Activate returns 404 for non-existent key."""
        response = client.post("/api-keys/non-existent-id/activate")
        assert response.status_code == 404

    def test_deactivate_not_found(self, client: TestClient):
        """Deactivate returns 404 for non-existent key."""
        response = client.post("/api-keys/non-existent-id/deactivate")
        assert response.status_code == 404


class TestSearchApiKeys:
    """Tests for POST /search endpoint."""

    def test_search_empty_filter(self, client: TestClient):
        """Search with empty filter returns all keys."""
        client.post("/api-keys/", json={"name": "key-1"})
        client.post("/api-keys/", json={"name": "key-2"})

        response = client.post("/api-keys/search", json={})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2

    def test_search_by_active_status(self, client: TestClient):
        """Search filters by active status."""
        client.post("/api-keys/", json={"name": "active-key", "is_active": True})
        client.post("/api-keys/", json={"name": "inactive-key", "is_active": False})

        response = client.post("/api-keys/search", json={"is_active": True})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "active-key"

    def test_search_by_name_contains(self, client: TestClient):
        """Search filters by name substring."""
        client.post("/api-keys/", json={"name": "production-key"})
        client.post("/api-keys/", json={"name": "staging-key"})

        response = client.post("/api-keys/search", json={"name_contains": "prod"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "production-key"


class TestVerifyApiKey:
    """Tests for POST /verify endpoint."""

    def test_verify_valid_key(self, client: TestClient):
        """Verify returns key details for valid key."""
        create_response = client.post("/api-keys/", json={"name": "test-key"})
        api_key = create_response.json()["api_key"]

        response = client.post("/api-keys/verify", json={"api_key": api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test-key"
        assert "key_id" in data

    def test_verify_invalid_key(self, client: TestClient):
        """Verify returns 401 for invalid key."""
        response = client.post("/api-keys/verify", json={"api_key": "ak-invalid-invalidkey"})
        assert response.status_code == 401
        assert response.json()["detail"] == "API key invalid"

    def test_verify_inactive_key(self, client: TestClient):
        """Verify returns 403 for inactive key."""
        create_response = client.post("/api-keys/", json={"name": "test-key", "is_active": False})
        api_key = create_response.json()["api_key"]

        response = client.post("/api-keys/verify", json={"api_key": api_key})
        assert response.status_code == 403
        assert response.json()["detail"] == "API key inactive"

    def test_verify_expired_key(self, client: TestClient):
        """Verify returns 403 for expired key."""
        # Create key first (can't create with past expiration)
        create_response = client.post("/api-keys/", json={"name": "test-key"})
        api_key = create_response.json()["api_key"]
        key_id = create_response.json()["entity"]["id"]

        # Update expiration to be in the past
        expires = (datetime_factory() - timedelta(days=1)).isoformat()
        client.patch(f"/api-keys/{key_id}", json={"expires_at": expires})

        response = client.post("/api-keys/verify", json={"api_key": api_key})
        assert response.status_code == 403
        assert response.json()["detail"] == "API key expired"

    def test_verify_with_matching_scopes(self, client: TestClient):
        """Verify succeeds when key has required scopes."""
        create_response = client.post("/api-keys/", json={"name": "test-key", "scopes": ["read", "write"]})
        api_key = create_response.json()["api_key"]

        response = client.post(
            "/api-keys/verify",
            json={"api_key": api_key, "required_scopes": ["read"]},
        )
        assert response.status_code == 200

    def test_verify_with_missing_scopes(self, client: TestClient):
        """Verify returns 403 when key is missing required scopes."""
        create_response = client.post("/api-keys/", json={"name": "test-key", "scopes": ["read"]})
        api_key = create_response.json()["api_key"]

        response = client.post(
            "/api-keys/verify",
            json={"api_key": api_key, "required_scopes": ["admin"]},
        )
        assert response.status_code == 403
        assert "missing required scopes" in response.json()["detail"]


class TestCountApiKeys:
    """Tests for POST /count endpoint."""

    def test_count_all(self, client: TestClient):
        """Count returns total number of keys."""
        client.post("/api-keys/", json={"name": "key-1"})
        client.post("/api-keys/", json={"name": "key-2"})
        client.post("/api-keys/", json={"name": "key-3"})

        response = client.post("/api-keys/count", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3

    def test_count_with_filter(self, client: TestClient):
        """Count respects filter criteria."""
        client.post("/api-keys/", json={"name": "active-1", "is_active": True})
        client.post("/api-keys/", json={"name": "active-2", "is_active": True})
        client.post("/api-keys/", json={"name": "inactive", "is_active": False})

        response = client.post("/api-keys/count", json={"is_active": True})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    def test_count_empty(self, client: TestClient):
        """Count returns 0 when no keys exist."""
        response = client.post("/api-keys/count", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0


class TestApiKeyOutFields:
    """Tests for ApiKeyOut response model fields."""

    def test_response_includes_key_id(self, client: TestClient):
        """Response includes key_id field."""
        create_response = client.post("/api-keys/", json={"name": "test-key"})
        key_id = create_response.json()["entity"]["id"]

        response = client.get(f"/api-keys/{key_id}")
        assert response.status_code == 200
        data = response.json()
        assert "key_id" in data
        assert len(data["key_id"]) == 16

    def test_response_includes_expires_at(self, client: TestClient):
        """Response includes expires_at field."""
        expires = (datetime_factory() + timedelta(days=30)).isoformat()
        create_response = client.post("/api-keys/", json={"name": "test-key", "expires_at": expires})
        key_id = create_response.json()["entity"]["id"]

        response = client.get(f"/api-keys/{key_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["expires_at"] is not None

    def test_response_expires_at_null_when_not_set(self, client: TestClient):
        """Response expires_at is null when not set."""
        create_response = client.post("/api-keys/", json={"name": "test-key"})
        key_id = create_response.json()["entity"]["id"]

        response = client.get(f"/api-keys/{key_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["expires_at"] is None


class TestCreateDependsApiKey:
    """Tests for create_depends_api_key function."""

    def test_default_http_bearer(self, service: ApiKeyService):
        """Default security scheme is HTTPBearer."""

        async def get_service():
            return service

        dependency = create_depends_api_key(depends_svc_api_keys=get_service)
        assert callable(dependency)

    @pytest.mark.asyncio
    async def test_http_bearer_valid_key(self, service: AbstractApiKeyService):
        """HTTPBearer accepts valid API key."""

        async def get_service():
            return service

        app = FastAPI()
        dependency = create_depends_api_key(depends_svc_api_keys=get_service)

        @app.get("/protected")
        async def protected_route(key: ApiKey = Depends(dependency)):
            return {"key_id": key.key_id}

        entity, api_key = await service.create(name="test-key")

        client = TestClient(app)
        response = client.get("/protected", headers={"Authorization": f"Bearer {api_key}"})
        assert response.status_code == 200
        assert response.json()["key_id"] == entity.key_id

    def test_http_bearer_missing_key(self, service: ApiKeyService):
        """HTTPBearer returns 401 for missing key."""

        async def get_service():
            return service

        app = FastAPI()
        dependency = create_depends_api_key(depends_svc_api_keys=get_service)

        @app.get("/protected")
        async def protected_route(key: ApiKey = Depends(dependency)):
            return {"key_id": key.key_id}

        client = TestClient(app)
        response = client.get("/protected")
        assert response.status_code == 401
        assert response.json()["detail"] == "API key missing"

    def test_http_bearer_invalid_key(self, service: ApiKeyService):
        """HTTPBearer returns 401 for invalid key."""

        async def get_service():
            return service

        app = FastAPI()
        dependency = create_depends_api_key(depends_svc_api_keys=get_service)

        @app.get("/protected")
        async def protected_route(key: ApiKey = Depends(dependency)):
            return {"key_id": key.key_id}

        client = TestClient(app)
        response = client.get("/protected", headers={"Authorization": "Bearer ak-invalid-invalidkey"})
        assert response.status_code == 401
        assert response.json()["detail"] == "API key invalid"

    @pytest.mark.asyncio
    async def test_http_bearer_inactive_key(self, service: ApiKeyService):
        """HTTPBearer returns 403 for inactive key."""

        async def get_service():
            return service

        app = FastAPI()
        dependency = create_depends_api_key(depends_svc_api_keys=get_service)

        @app.get("/protected")
        async def protected_route(key: ApiKey = Depends(dependency)):
            return {"key_id": key.key_id}

        async def create_key():
            return await service.create(name="test-key", is_active=False)

        entity, api_key = await create_key()

        client = TestClient(app)
        response = client.get("/protected", headers={"Authorization": f"Bearer {api_key}"})
        assert response.status_code == 403
        assert response.json()["detail"] == "API key inactive"

    @pytest.mark.asyncio
    async def test_http_bearer_expired_key(self, service: ApiKeyService):
        """HTTPBearer returns 403 for expired key."""

        async def get_service():
            return service

        app = FastAPI()
        dependency = create_depends_api_key(depends_svc_api_keys=get_service)

        @app.get("/protected")
        async def protected_route(key: ApiKey = Depends(dependency)):
            return {"key_id": key.key_id}

        async def create_and_expire_key():
            entity, api_key = await service.create(name="test-key")
            entity.expires_at = datetime_factory() - timedelta(days=1)
            await service.update(entity)
            return entity, api_key

        entity, api_key = await create_and_expire_key()

        client = TestClient(app)
        response = client.get("/protected", headers={"Authorization": f"Bearer {api_key}"})
        assert response.status_code == 403
        assert response.json()["detail"] == "API key expired"

    @pytest.mark.asyncio
    async def test_http_bearer_missing_scopes(self, service: ApiKeyService):
        """HTTPBearer returns 403 for missing scopes."""

        async def get_service():
            return service

        app = FastAPI()
        dependency = create_depends_api_key(depends_svc_api_keys=get_service, required_scopes=["admin"])

        @app.get("/protected")
        async def protected_route(key: ApiKey = Depends(dependency)):
            return {"key_id": key.key_id}

        async def create_key():
            return await service.create(name="test-key", scopes=["read"])

        entity, api_key = await create_key()

        client = TestClient(app)
        response = client.get("/protected", headers={"Authorization": f"Bearer {api_key}"})
        assert response.status_code == 403
        assert "missing required scopes" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_api_key_header_valid_key(self, service: ApiKeyService):
        """APIKeyHeader accepts valid API key."""

        async def get_service():
            return service

        app = FastAPI()
        security = APIKeyHeader(name="X-API-Key", auto_error=False)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            dependency = create_depends_api_key(depends_svc_api_keys=get_service, security=security)
            assert len(w) == 1
            assert "RFC 6750" in str(w[0].message)

        @app.get("/protected")
        async def protected_route(key: ApiKey = Depends(dependency)):
            return {"key_id": key.key_id}

        async def create_key():
            return await service.create(name="test-key")

        entity, api_key = await create_key()

        client = TestClient(app)
        response = client.get("/protected", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        assert response.json()["key_id"] == entity.key_id

    @pytest.mark.asyncio
    async def test_api_key_header_missing_key(self, service: ApiKeyService):
        """APIKeyHeader returns 401 for missing key."""

        async def get_service():
            return service

        app = FastAPI()
        security = APIKeyHeader(name="X-API-Key", auto_error=False)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dependency = create_depends_api_key(depends_svc_api_keys=get_service, security=security)

        @app.get("/protected")
        async def protected_route(key: ApiKey = Depends(dependency)):
            return {"key_id": key.key_id}

        client = TestClient(app)
        response = client.get("/protected")
        assert response.status_code == 401
        assert response.json()["detail"] == "API key missing"

    @pytest.mark.asyncio
    async def test_api_key_header_invalid_key(self, service: ApiKeyService):
        """APIKeyHeader returns 401 for invalid key."""

        async def get_service():
            return service

        app = FastAPI()
        security = APIKeyHeader(name="X-API-Key", auto_error=False)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dependency = create_depends_api_key(depends_svc_api_keys=get_service, security=security)

        @app.get("/protected")
        async def protected_route(key: ApiKey = Depends(dependency)):
            return {"key_id": key.key_id}

        client = TestClient(app)
        response = client.get("/protected", headers={"X-API-Key": "ak-invalid-invalidkey"})
        assert response.status_code == 401
        assert response.json()["detail"] == "API key invalid"

    @pytest.mark.asyncio
    async def test_api_key_header_inactive_key(self, service: ApiKeyService):
        """APIKeyHeader returns 403 for inactive key."""

        async def get_service():
            return service

        app = FastAPI()
        security = APIKeyHeader(name="X-API-Key", auto_error=False)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dependency = create_depends_api_key(depends_svc_api_keys=get_service, security=security)

        @app.get("/protected")
        async def protected_route(key: ApiKey = Depends(dependency)):
            return {"key_id": key.key_id}

        async def create_key():
            return await service.create(name="test-key", is_active=False)

        entity, api_key = await create_key()

        client = TestClient(app)
        response = client.get("/protected", headers={"X-API-Key": api_key})
        assert response.status_code == 403
        assert response.json()["detail"] == "API key inactive"

    @pytest.mark.asyncio
    async def test_api_key_header_expired_key(self, service: ApiKeyService):
        """APIKeyHeader returns 403 for expired key."""

        async def get_service():
            return service

        app = FastAPI()
        security = APIKeyHeader(name="X-API-Key", auto_error=False)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dependency = create_depends_api_key(depends_svc_api_keys=get_service, security=security)

        @app.get("/protected")
        async def protected_route(key: ApiKey = Depends(dependency)):
            return {"key_id": key.key_id}

        async def create_and_expire_key():
            entity, api_key = await service.create(name="test-key")
            entity.expires_at = datetime_factory() - timedelta(days=1)
            await service.update(entity)
            return entity, api_key

        entity, api_key = await create_and_expire_key()

        client = TestClient(app)
        response = client.get("/protected", headers={"X-API-Key": api_key})
        assert response.status_code == 403
        assert response.json()["detail"] == "API key expired"

    @pytest.mark.asyncio
    async def test_api_key_header_missing_scopes(self, service: ApiKeyService):
        """APIKeyHeader returns 403 for missing scopes."""

        async def get_service():
            return service

        app = FastAPI()
        security = APIKeyHeader(name="X-API-Key", auto_error=False)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dependency = create_depends_api_key(
                depends_svc_api_keys=get_service, security=security, required_scopes=["admin"]
            )

        @app.get("/protected")
        async def protected_route(key: ApiKey = Depends(dependency)):
            return {"key_id": key.key_id}

        async def create_key():
            return await service.create(name="test-key", scopes=["read"])

        entity, api_key = await create_key()

        client = TestClient(app)
        response = client.get("/protected", headers={"X-API-Key": api_key})
        assert response.status_code == 403
        assert "missing required scopes" in response.json()["detail"]

    def test_auto_error_true_raises_value_error(self, service: ApiKeyService):
        """auto_error=True raises ValueError."""

        async def get_service():
            return service

        security = HTTPBearer(auto_error=True)

        with pytest.raises(ValueError, match="auto_error=False"):
            create_depends_api_key(depends_svc_api_keys=get_service, security=security)

    def test_invalid_security_type_raises_value_error(self, service: ApiKeyService):
        """Invalid security type raises ValueError."""

        async def get_service():
            return service

        # Create a mock security object that is neither HTTPBearer nor APIKeyHeader
        class InvalidSecurity:
            auto_error = False

        with pytest.raises(ValueError, match="HTTPBearer or APIKeyHeader"):
            create_depends_api_key(depends_svc_api_keys=get_service, security=InvalidSecurity())  # type: ignore[arg-type]


class TestHandleVerifyKeyEdgeCases:
    """Tests for edge cases in _handle_verify_key."""

    def test_key_not_provided_via_service(self):
        """KeyNotProvided from service returns 401."""
        mock_service = AsyncMock()
        mock_service.verify_key.side_effect = KeyNotProvided("No API key provided")

        async def get_service():
            return mock_service

        app = FastAPI()
        dependency = create_depends_api_key(depends_svc_api_keys=get_service)

        @app.get("/protected")
        async def protected_route(key: ApiKey = Depends(dependency)):
            return {"key_id": key.key_id}

        client = TestClient(app)
        # Provide a bearer token so we pass the "if not api_key" check in the dependency
        response = client.get("/protected", headers={"Authorization": "Bearer some-token"})
        assert response.status_code == 401
        assert response.json()["detail"] == "API key missing"


class TestUpdateRaceCondition:
    """Tests for race conditions in update endpoint."""

    def test_update_key_deleted_between_get_and_update(self):
        """Update returns 404 if key deleted between get and update."""
        mock_service = AsyncMock()

        # get_by_id succeeds first time
        mock_entity = ApiKey(id_="test-id", name="test-key", key_hash="hash")
        mock_service.get_by_id.return_value = mock_entity

        # update raises KeyNotFound (simulating deletion between get and update)
        mock_service.update.side_effect = KeyNotFound("Key not found")

        async def get_service():
            return mock_service

        app = FastAPI()
        router = create_api_keys_router(depends_svc_api_keys=get_service)
        app.include_router(router)

        client = TestClient(app)
        response = client.patch("/api-keys/test-id", json={"name": "new-name"})
        assert response.status_code == 404
        assert response.json()["detail"] == "API key not found"
