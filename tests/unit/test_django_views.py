"""Unit tests for Django async views and require_api_key decorator.

Uses Django's ``RequestFactory`` to call views directly (no URL routing).
Django settings are configured via ``DJANGO_SETTINGS_MODULE`` in pyproject.toml.
"""

import json
from datetime import timedelta

import pytest
from django.http import JsonResponse
from django.test import RequestFactory

from keyshield.django.decorators import require_api_key
from keyshield.django.urls import create_api_keys_urlpatterns
from keyshield.django.views import (
    ApiKeyActivateView,
    ApiKeyCountView,
    ApiKeyDeactivateView,
    ApiKeyDetailView,
    ApiKeyListCreateView,
    ApiKeySearchView,
    ApiKeyVerifyView,
)
from keyshield.hasher.base import MockApiKeyHasher
from keyshield.repositories.in_memory import InMemoryApiKeyRepository
from keyshield.services.base import ApiKeyService
from keyshield.utils import datetime_factory


# ---------------------------------------------------------------------------
# Shared fixtures
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
def factory() -> RequestFactory:
    return RequestFactory()


def _json(data: dict) -> bytes:
    return json.dumps(data).encode()


def _make_view(view_class, svc_factory):
    """Return a bound async view callable."""
    return view_class.as_view(svc_factory=svc_factory)


# ---------------------------------------------------------------------------
# Create + List (ApiKeyListCreateView)
# ---------------------------------------------------------------------------


class TestApiKeyListCreateView:
    @pytest.mark.asyncio
    async def test_create_with_name(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view = _make_view(ApiKeyListCreateView, get_svc)
        request = factory.post("/", data=_json({"name": "test-key"}), content_type="application/json")
        response = await view(request)
        assert response.status_code == 201
        data = json.loads(response.content)
        assert data["entity"]["name"] == "test-key"
        assert "api_key" in data

    @pytest.mark.asyncio
    async def test_create_with_all_fields(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view = _make_view(ApiKeyListCreateView, get_svc)
        request = factory.post(
            "/",
            data=_json({"name": "k", "description": "desc", "is_active": False, "scopes": ["read"]}),
            content_type="application/json",
        )
        response = await view(request)
        assert response.status_code == 201
        data = json.loads(response.content)
        assert data["entity"]["description"] == "desc"
        assert data["entity"]["is_active"] is False

    @pytest.mark.asyncio
    async def test_create_invalid_body_returns_422(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view = _make_view(ApiKeyListCreateView, get_svc)
        request = factory.post("/", data=_json({}), content_type="application/json")
        response = await view(request)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_empty(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view = _make_view(ApiKeyListCreateView, get_svc)
        request = factory.get("/")
        response = await view(request)
        assert response.status_code == 200
        assert json.loads(response.content) == []

    @pytest.mark.asyncio
    async def test_list_returns_keys(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view = _make_view(ApiKeyListCreateView, get_svc)
        for i in range(3):
            req = factory.post("/", data=_json({"name": f"k{i}"}), content_type="application/json")
            await view(req)

        request = factory.get("/")
        response = await view(request)
        assert response.status_code == 200
        assert len(json.loads(response.content)) == 3

    @pytest.mark.asyncio
    async def test_list_with_pagination(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view = _make_view(ApiKeyListCreateView, get_svc)
        for i in range(5):
            req = factory.post("/", data=_json({"name": f"k{i}"}), content_type="application/json")
            await view(req)

        request = factory.get("/?limit=2&offset=1")
        response = await view(request)
        assert response.status_code == 200
        assert len(json.loads(response.content)) == 2


# ---------------------------------------------------------------------------
# Get + Update + Delete (ApiKeyDetailView)
# ---------------------------------------------------------------------------


class TestApiKeyDetailView:
    async def _create(self, factory, service):
        async def get_svc():
            return service

        view = _make_view(ApiKeyListCreateView, get_svc)
        req = factory.post("/", data=_json({"name": "test-key"}), content_type="application/json")
        resp = await view(req)
        return json.loads(resp.content)

    @pytest.mark.asyncio
    async def test_get_existing(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        created = await self._create(factory, service)
        key_id = created["entity"]["id"]

        view = _make_view(ApiKeyDetailView, get_svc)
        request = factory.get(f"/{key_id}/")
        response = await view(request, pk=key_id)
        assert response.status_code == 200
        assert json.loads(response.content)["name"] == "test-key"

    @pytest.mark.asyncio
    async def test_get_not_found(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view = _make_view(ApiKeyDetailView, get_svc)
        request = factory.get("/no-such-id/")
        response = await view(request, pk="no-such-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_name(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        created = await self._create(factory, service)
        key_id = created["entity"]["id"]

        view = _make_view(ApiKeyDetailView, get_svc)
        request = factory.patch(f"/{key_id}/", data=_json({"name": "new"}), content_type="application/json")
        response = await view(request, pk=key_id)
        assert response.status_code == 200
        assert json.loads(response.content)["name"] == "new"

    @pytest.mark.asyncio
    async def test_update_not_found(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view = _make_view(ApiKeyDetailView, get_svc)
        request = factory.patch("/no-such-id/", data=_json({"name": "x"}), content_type="application/json")
        response = await view(request, pk="no-such-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_clear_expires(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        expires = (datetime_factory() + timedelta(days=30)).isoformat()
        view_create = _make_view(ApiKeyListCreateView, get_svc)
        req = factory.post("/", data=_json({"name": "k", "expires_at": expires}), content_type="application/json")
        created = json.loads((await view_create(req)).content)
        key_id = created["entity"]["id"]

        view = _make_view(ApiKeyDetailView, get_svc)
        request = factory.patch(f"/{key_id}/", data=_json({"clear_expires": True}), content_type="application/json")
        response = await view(request, pk=key_id)
        assert response.status_code == 200
        assert json.loads(response.content)["expires_at"] is None

    @pytest.mark.asyncio
    async def test_delete_existing(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        created = await self._create(factory, service)
        key_id = created["entity"]["id"]

        view = _make_view(ApiKeyDetailView, get_svc)
        request = factory.delete(f"/{key_id}/")
        response = await view(request, pk=key_id)
        assert response.status_code == 204

        get_req = factory.get(f"/{key_id}/")
        get_resp = await view(get_req, pk=key_id)
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view = _make_view(ApiKeyDetailView, get_svc)
        request = factory.delete("/no-such-id/")
        response = await view(request, pk="no-such-id")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Activate / Deactivate
# ---------------------------------------------------------------------------


class TestActivateDeactivate:
    async def _create(self, factory, service, is_active=True):
        async def get_svc():
            return service

        view = _make_view(ApiKeyListCreateView, get_svc)
        req = factory.post("/", data=_json({"name": "k", "is_active": is_active}), content_type="application/json")
        resp = await view(req)
        return json.loads(resp.content)["entity"]["id"]

    @pytest.mark.asyncio
    async def test_activate(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        key_id = await self._create(factory, service, is_active=False)
        view = _make_view(ApiKeyActivateView, get_svc)
        response = await view(factory.post(f"/{key_id}/activate/"), pk=key_id)
        assert response.status_code == 200
        assert json.loads(response.content)["is_active"] is True

    @pytest.mark.asyncio
    async def test_deactivate(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        key_id = await self._create(factory, service, is_active=True)
        view = _make_view(ApiKeyDeactivateView, get_svc)
        response = await view(factory.post(f"/{key_id}/deactivate/"), pk=key_id)
        assert response.status_code == 200
        assert json.loads(response.content)["is_active"] is False

    @pytest.mark.asyncio
    async def test_activate_not_found(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view = _make_view(ApiKeyActivateView, get_svc)
        response = await view(factory.post("/no-such-id/activate/"), pk="no-such-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_deactivate_not_found(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view = _make_view(ApiKeyDeactivateView, get_svc)
        response = await view(factory.post("/no-such-id/deactivate/"), pk="no-such-id")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Search / Count
# ---------------------------------------------------------------------------


class TestSearchAndCount:
    @pytest.mark.asyncio
    async def test_search_empty_filter(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view_create = _make_view(ApiKeyListCreateView, get_svc)
        for i in range(2):
            await view_create(factory.post("/", data=_json({"name": f"k{i}"}), content_type="application/json"))

        view = _make_view(ApiKeySearchView, get_svc)
        response = await view(factory.post("/search/", data=b"{}", content_type="application/json"))
        assert response.status_code == 200
        assert json.loads(response.content)["total"] == 2

    @pytest.mark.asyncio
    async def test_count_all(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view_create = _make_view(ApiKeyListCreateView, get_svc)
        for i in range(3):
            await view_create(factory.post("/", data=_json({"name": f"k{i}"}), content_type="application/json"))

        view = _make_view(ApiKeyCountView, get_svc)
        response = await view(factory.post("/count/", data=b"{}", content_type="application/json"))
        assert response.status_code == 200
        assert json.loads(response.content)["total"] == 3

    @pytest.mark.asyncio
    async def test_count_with_filter(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view_create = _make_view(ApiKeyListCreateView, get_svc)
        await view_create(
            factory.post("/", data=_json({"name": "a1", "is_active": True}), content_type="application/json")
        )
        await view_create(
            factory.post("/", data=_json({"name": "a2", "is_active": True}), content_type="application/json")
        )
        await view_create(
            factory.post("/", data=_json({"name": "i", "is_active": False}), content_type="application/json")
        )

        view = _make_view(ApiKeyCountView, get_svc)
        response = await view(factory.post("/count/", data=_json({"is_active": True}), content_type="application/json"))
        assert response.status_code == 200
        assert json.loads(response.content)["total"] == 2


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


class TestVerifyApiKey:
    @pytest.mark.asyncio
    async def test_verify_valid(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view_create = _make_view(ApiKeyListCreateView, get_svc)
        resp = await view_create(factory.post("/", data=_json({"name": "k"}), content_type="application/json"))
        api_key = json.loads(resp.content)["api_key"]

        view = _make_view(ApiKeyVerifyView, get_svc)
        response = await view(
            factory.post("/verify/", data=_json({"api_key": api_key}), content_type="application/json")
        )
        assert response.status_code == 200
        assert json.loads(response.content)["name"] == "k"

    @pytest.mark.asyncio
    async def test_verify_invalid(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view = _make_view(ApiKeyVerifyView, get_svc)
        response = await view(
            factory.post("/verify/", data=_json({"api_key": "ak-invalid-badkey"}), content_type="application/json")
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_inactive(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view_create = _make_view(ApiKeyListCreateView, get_svc)
        resp = await view_create(
            factory.post("/", data=_json({"name": "k", "is_active": False}), content_type="application/json")
        )
        api_key = json.loads(resp.content)["api_key"]

        view = _make_view(ApiKeyVerifyView, get_svc)
        response = await view(
            factory.post("/verify/", data=_json({"api_key": api_key}), content_type="application/json")
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_verify_missing_scopes(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        view_create = _make_view(ApiKeyListCreateView, get_svc)
        resp = await view_create(
            factory.post("/", data=_json({"name": "k", "scopes": ["read"]}), content_type="application/json")
        )
        api_key = json.loads(resp.content)["api_key"]

        view = _make_view(ApiKeyVerifyView, get_svc)
        response = await view(
            factory.post(
                "/verify/",
                data=_json({"api_key": api_key, "required_scopes": ["admin"]}),
                content_type="application/json",
            )
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# URL patterns smoke test
# ---------------------------------------------------------------------------


class TestCreateApiKeysUrlpatterns:
    def test_returns_expected_count(self, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        patterns = create_api_keys_urlpatterns(svc_factory=get_svc)
        # list, search, count, verify, detail, activate, deactivate
        assert len(patterns) == 7


# ---------------------------------------------------------------------------
# require_api_key decorator
# ---------------------------------------------------------------------------


class TestRequireApiKey:
    @pytest.mark.asyncio
    async def test_valid_key_passes(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        @require_api_key(svc_factory=get_svc)
        async def my_view(request):
            return JsonResponse({"key_id": request.api_key.key_id})

        entity, api_key = await service.create(name="k")
        request = factory.get("/", HTTP_AUTHORIZATION=f"Bearer {api_key}")
        response = await my_view(request)
        assert response.status_code == 200
        assert json.loads(response.content)["key_id"] == entity.key_id

    @pytest.mark.asyncio
    async def test_missing_key_returns_401(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        @require_api_key(svc_factory=get_svc)
        async def my_view(request):
            return JsonResponse({"ok": True})

        request = factory.get("/")
        response = await my_view(request)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_key_returns_401(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        @require_api_key(svc_factory=get_svc)
        async def my_view(request):
            return JsonResponse({"ok": True})

        request = factory.get("/", HTTP_AUTHORIZATION="Bearer ak-invalid-badkey")
        response = await my_view(request)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_key_returns_403(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        @require_api_key(svc_factory=get_svc)
        async def my_view(request):
            return JsonResponse({"ok": True})

        entity, api_key = await service.create(name="k", is_active=False)
        request = factory.get("/", HTTP_AUTHORIZATION=f"Bearer {api_key}")
        response = await my_view(request)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_expired_key_returns_403(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        @require_api_key(svc_factory=get_svc)
        async def my_view(request):
            return JsonResponse({"ok": True})

        entity, api_key = await service.create(name="k")
        entity.expires_at = datetime_factory() - timedelta(days=1)
        await service.update(entity)

        request = factory.get("/", HTTP_AUTHORIZATION=f"Bearer {api_key}")
        response = await my_view(request)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_scopes_returns_403(self, factory: RequestFactory, service: ApiKeyService) -> None:
        async def get_svc():
            return service

        @require_api_key(svc_factory=get_svc, required_scopes=["admin"])
        async def my_view(request):
            return JsonResponse({"ok": True})

        entity, api_key = await service.create(name="k", scopes=["read"])
        request = factory.get("/", HTTP_AUTHORIZATION=f"Bearer {api_key}")
        response = await my_view(request)
        assert response.status_code == 403
