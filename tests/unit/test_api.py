"""Unit tests for the API router module.

Tests verify API routes work correctly using InMemory repository.
Focus on behavior, not implementation details.
"""

from contextlib import asynccontextmanager
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_api_key import ApiKeyService
from fastapi_api_key.api import create_api_keys_router
from fastapi_api_key.hasher.base import MockApiKeyHasher
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
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
        rrd=0,  # No random delay for tests
    )


@pytest.fixture
def app(service: ApiKeyService) -> FastAPI:
    """FastAPI app with API keys router."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(lifespan=lifespan)

    async def get_service():
        yield service

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
