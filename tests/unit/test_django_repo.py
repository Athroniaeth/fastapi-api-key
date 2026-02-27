"""Unit tests for DjangoApiKeyRepository.

Uses pytest-django with an in-memory SQLite database.
Django settings are configured via ``DJANGO_SETTINGS_MODULE`` in pyproject.toml.
"""

from datetime import timedelta

import pytest

from fastapi_api_key.django.repository import DjangoApiKeyRepository
from fastapi_api_key.repositories.base import ApiKeyFilter, SortableColumn
from fastapi_api_key.utils import datetime_factory
from tests.conftest import make_api_key  # pyrefly: ignore[missing-import]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo() -> DjangoApiKeyRepository:
    return DjangoApiKeyRepository()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestDjangoRepositoryCRUD:
    @pytest.mark.asyncio
    async def test_create_and_get_by_id(self, repo: DjangoApiKeyRepository) -> None:
        entity = make_api_key()
        created = await repo.create(entity)
        assert created.id_ == entity.id_

        retrieved = await repo.get_by_id(entity.id_)
        assert retrieved is not None
        assert retrieved.id_ == entity.id_
        assert retrieved.name == entity.name

    @pytest.mark.asyncio
    async def test_get_by_key_id(self, repo: DjangoApiKeyRepository) -> None:
        entity = make_api_key()
        await repo.create(entity)
        retrieved = await repo.get_by_key_id(entity.key_id)
        assert retrieved is not None
        assert retrieved.key_id == entity.key_id

    @pytest.mark.asyncio
    async def test_update(self, repo: DjangoApiKeyRepository) -> None:
        entity = make_api_key()
        await repo.create(entity)

        entity.name = "updated-name"
        entity.is_active = False
        updated = await repo.update(entity)

        assert updated is not None
        assert updated.name == "updated-name"
        assert updated.is_active is False

    @pytest.mark.asyncio
    async def test_delete_by_id(self, repo: DjangoApiKeyRepository) -> None:
        entity = make_api_key()
        await repo.create(entity)

        deleted = await repo.delete_by_id(entity.id_)
        assert deleted is not None

        retrieved = await repo.get_by_id(entity.id_)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_list(self, repo: DjangoApiKeyRepository) -> None:
        for _ in range(5):
            await repo.create(make_api_key())

        result = await repo.list(limit=3, offset=0)
        assert len(result) == 3

        result = await repo.list(limit=3, offset=3)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Not found
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestDjangoRepositoryNotFound:
    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repo: DjangoApiKeyRepository) -> None:
        assert await repo.get_by_id("non-existent") is None

    @pytest.mark.asyncio
    async def test_get_by_key_id_not_found(self, repo: DjangoApiKeyRepository) -> None:
        assert await repo.get_by_key_id("non-existent") is None

    @pytest.mark.asyncio
    async def test_update_not_found(self, repo: DjangoApiKeyRepository) -> None:
        entity = make_api_key()
        assert await repo.update(entity) is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, repo: DjangoApiKeyRepository) -> None:
        assert await repo.delete_by_id("non-existent") is None


# ---------------------------------------------------------------------------
# Find
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestDjangoRepositoryFind:
    @pytest.mark.asyncio
    async def test_find_empty_filter(self, repo: DjangoApiKeyRepository) -> None:
        for _ in range(3):
            await repo.create(make_api_key())
        result = await repo.find(ApiKeyFilter())
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_find_by_is_active(self, repo: DjangoApiKeyRepository) -> None:
        await repo.create(make_api_key(is_active=True))
        await repo.create(make_api_key(is_active=False))
        result = await repo.find(ApiKeyFilter(is_active=True))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_expires_before(self, repo: DjangoApiKeyRepository) -> None:
        now = datetime_factory()
        k1 = make_api_key()
        k1.expires_at = now + timedelta(days=5)
        await repo.create(k1)

        k2 = make_api_key()
        k2.expires_at = now + timedelta(days=30)
        await repo.create(k2)

        result = await repo.find(ApiKeyFilter(expires_before=now + timedelta(days=10)))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_expires_after(self, repo: DjangoApiKeyRepository) -> None:
        now = datetime_factory()
        k1 = make_api_key()
        k1.expires_at = now + timedelta(days=5)
        await repo.create(k1)

        k2 = make_api_key()
        k2.expires_at = now + timedelta(days=30)
        await repo.create(k2)

        result = await repo.find(ApiKeyFilter(expires_after=now + timedelta(days=10)))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_created_before(self, repo: DjangoApiKeyRepository) -> None:
        now = datetime_factory()
        k1 = make_api_key()
        k1.created_at = now - timedelta(days=10)
        await repo.create(k1)

        k2 = make_api_key()
        k2.created_at = now - timedelta(days=1)
        await repo.create(k2)

        result = await repo.find(ApiKeyFilter(created_before=now - timedelta(days=5)))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_created_after(self, repo: DjangoApiKeyRepository) -> None:
        now = datetime_factory()
        k1 = make_api_key()
        k1.created_at = now - timedelta(days=10)
        await repo.create(k1)

        k2 = make_api_key()
        k2.created_at = now - timedelta(days=1)
        await repo.create(k2)

        result = await repo.find(ApiKeyFilter(created_after=now - timedelta(days=5)))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_last_used_before(self, repo: DjangoApiKeyRepository) -> None:
        now = datetime_factory()
        k1 = make_api_key()
        k1.last_used_at = now - timedelta(days=10)
        await repo.create(k1)

        k2 = make_api_key()
        k2.last_used_at = now - timedelta(days=1)
        await repo.create(k2)

        result = await repo.find(ApiKeyFilter(last_used_before=now - timedelta(days=5)))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_last_used_after(self, repo: DjangoApiKeyRepository) -> None:
        now = datetime_factory()
        k1 = make_api_key()
        k1.last_used_at = now - timedelta(days=10)
        await repo.create(k1)

        k2 = make_api_key()
        k2.last_used_at = now - timedelta(days=1)
        await repo.create(k2)

        result = await repo.find(ApiKeyFilter(last_used_after=now - timedelta(days=5)))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_never_used(self, repo: DjangoApiKeyRepository) -> None:
        k_used = make_api_key()
        k_used.last_used_at = datetime_factory()
        await repo.create(k_used)

        k_never = make_api_key()
        k_never.last_used_at = None
        await repo.create(k_never)

        result = await repo.find(ApiKeyFilter(never_used=True))
        assert len(result) == 1
        assert result[0].last_used_at is None

        result = await repo.find(ApiKeyFilter(never_used=False))
        assert len(result) == 1
        assert result[0].last_used_at is not None

    @pytest.mark.asyncio
    async def test_find_by_name_contains(self, repo: DjangoApiKeyRepository) -> None:
        k1 = make_api_key()
        k1.name = "Production API Key"
        await repo.create(k1)

        k2 = make_api_key()
        k2.name = "Development Key"
        await repo.create(k2)

        result = await repo.find(ApiKeyFilter(name_contains="api"))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_name_exact(self, repo: DjangoApiKeyRepository) -> None:
        k1 = make_api_key()
        k1.name = "my-key"
        await repo.create(k1)

        k2 = make_api_key()
        k2.name = "my-key-2"
        await repo.create(k2)

        result = await repo.find(ApiKeyFilter(name_exact="my-key"))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_scopes_contain_all(self, repo: DjangoApiKeyRepository) -> None:
        await repo.create(make_api_key(scopes=["read", "write", "admin"]))
        await repo.create(make_api_key(scopes=["read", "write"]))
        await repo.create(make_api_key(scopes=["read"]))

        result = await repo.find(ApiKeyFilter(scopes_contain_all=["read", "write"]))
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_find_by_scopes_contain_any(self, repo: DjangoApiKeyRepository) -> None:
        await repo.create(make_api_key(scopes=["admin"]))
        await repo.create(make_api_key(scopes=["read"]))
        await repo.create(make_api_key(scopes=["other"]))

        result = await repo.find(ApiKeyFilter(scopes_contain_any=["admin", "read"]))
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_find_order_ascending(self, repo: DjangoApiKeyRepository) -> None:
        for _ in range(3):
            await repo.create(make_api_key())

        result = await repo.find(ApiKeyFilter(order_by=SortableColumn.CREATED_AT, order_desc=False))
        assert len(result) == 3
        assert result[0].created_at <= result[1].created_at


# ---------------------------------------------------------------------------
# Count
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestDjangoRepositoryCount:
    @pytest.mark.asyncio
    async def test_count_all(self, repo: DjangoApiKeyRepository) -> None:
        for _ in range(5):
            await repo.create(make_api_key())
        assert await repo.count() == 5

    @pytest.mark.asyncio
    async def test_count_with_filter(self, repo: DjangoApiKeyRepository) -> None:
        await repo.create(make_api_key(is_active=True))
        await repo.create(make_api_key(is_active=True))
        await repo.create(make_api_key(is_active=False))
        assert await repo.count(ApiKeyFilter(is_active=True)) == 2

    @pytest.mark.asyncio
    async def test_count_with_scope_filter(self, repo: DjangoApiKeyRepository) -> None:
        await repo.create(make_api_key(scopes=["admin"]))
        await repo.create(make_api_key(scopes=["read"]))
        await repo.create(make_api_key(scopes=["admin", "read"]))
        assert await repo.count(ApiKeyFilter(scopes_contain_all=["admin"])) == 2

    @pytest.mark.asyncio
    async def test_count_with_name_filter(self, repo: DjangoApiKeyRepository) -> None:
        k1 = make_api_key()
        k1.name = "Production API"
        await repo.create(k1)

        k2 = make_api_key()
        k2.name = "Development"
        await repo.create(k2)

        assert await repo.count(ApiKeyFilter(name_contains="api")) == 1
        assert await repo.count(ApiKeyFilter(name_exact="Development")) == 1


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestDjangoRepositoryConversion:
    @pytest.mark.asyncio
    async def test_to_domain_preserves_all_fields(self, repo: DjangoApiKeyRepository) -> None:
        entity = make_api_key()
        entity.description = "Test description"
        entity.scopes = ["read", "write", "admin"]

        await repo.create(entity)
        retrieved = await repo.get_by_id(entity.id_)

        assert retrieved is not None
        assert retrieved.id_ == entity.id_
        assert retrieved.name == entity.name
        assert retrieved.description == entity.description
        assert retrieved.is_active == entity.is_active
        assert retrieved.key_id == entity.key_id
        assert retrieved.key_hash == entity.key_hash
        assert retrieved.scopes == entity.scopes
