"""Unit tests for AbstractApiKeyRepository implementations.

Tests the InMemoryApiKeyRepository as a reference implementation.
SQLAlchemy repository uses same interface, tested via integration tests.
"""

from datetime import timedelta

import pytest

from fastapi_api_key.repositories.base import ApiKeyFilter, SortableColumn
from fastapi_api_key.repositories.in_memory import InMemoryApiKeyRepository
from fastapi_api_key.utils import datetime_factory, key_id_factory
from tests.conftest import make_api_key  # pyrefly: ignore[missing-import]


class TestRepositoryCRUD:
    """Tests for basic CRUD operations."""

    @pytest.fixture
    def repo(self) -> InMemoryApiKeyRepository:
        """Fresh repository for each test."""
        return InMemoryApiKeyRepository()

    @pytest.mark.asyncio
    async def test_create_and_get_by_id(self, repo: InMemoryApiKeyRepository):
        """create() persists entity, get_by_id() retrieves it."""
        entity = make_api_key()

        created = await repo.create(entity)

        assert created.id_ == entity.id_
        retrieved = await repo.get_by_id(created.id_)
        assert retrieved is not None
        assert retrieved.id_ == entity.id_

    @pytest.mark.asyncio
    async def test_get_by_key_id(self, repo: InMemoryApiKeyRepository):
        """get_by_key_id() retrieves by key_id."""
        entity = make_api_key()
        await repo.create(entity)

        retrieved = await repo.get_by_key_id(entity.key_id)

        assert retrieved is not None
        assert retrieved.key_id == entity.key_id

    @pytest.mark.asyncio
    async def test_update(self, repo: InMemoryApiKeyRepository):
        """update() modifies existing entity."""
        entity = make_api_key()
        await repo.create(entity)

        entity.name = "updated-name"
        entity.is_active = False
        updated = await repo.update(entity)

        assert updated is not None
        assert updated.name == "updated-name"
        assert updated.is_active is False

    @pytest.mark.asyncio
    async def test_delete_by_id(self, repo: InMemoryApiKeyRepository):
        """delete_by_id() removes entity."""
        entity = make_api_key()
        await repo.create(entity)

        deleted = await repo.delete_by_id(entity.id_)
        assert deleted is not None
        assert deleted.id_ == entity.id_

        # Should not exist anymore
        retrieved = await repo.get_by_id(entity.id_)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_list_with_pagination(self, repo: InMemoryApiKeyRepository):
        """list() returns entities with pagination."""
        for _ in range(5):
            await repo.create(make_api_key())

        # Get first 3
        result = await repo.list(limit=3, offset=0)
        assert len(result) == 3

        # Get with offset
        result = await repo.list(limit=3, offset=3)
        assert len(result) == 2


class TestRepositoryNotFound:
    """Tests for operations on non-existent entities."""

    @pytest.fixture
    def repo(self) -> InMemoryApiKeyRepository:
        return InMemoryApiKeyRepository()

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repo: InMemoryApiKeyRepository):
        """get_by_id() returns None for non-existent ID."""
        result = await repo.get_by_id("non-existent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_key_id_not_found(self, repo: InMemoryApiKeyRepository):
        """get_by_key_id() returns None for non-existent key_id."""
        result = await repo.get_by_key_id("non-existent-key_id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_key_id_not_found_with_existing_keys(self, repo: InMemoryApiKeyRepository):
        """get_by_key_id() returns None when key_id not found among existing keys."""
        # Add some keys first
        await repo.create(make_api_key())
        await repo.create(make_api_key())

        # Search for non-existent key_id
        result = await repo.get_by_key_id("non-existent-key_id")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_not_found(self, repo: InMemoryApiKeyRepository):
        """update() returns None for non-existent entity."""
        entity = make_api_key()
        entity.id_ = "non-existent-id"

        result = await repo.update(entity)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, repo: InMemoryApiKeyRepository):
        """delete_by_id() returns None for non-existent ID."""
        result = await repo.delete_by_id("non-existent-id")
        assert result is None


class TestRepositoryConstraints:
    """Tests for repository constraints."""

    @pytest.fixture
    def repo(self) -> InMemoryApiKeyRepository:
        return InMemoryApiKeyRepository()

    @pytest.mark.asyncio
    async def test_duplicate_key_id_raises(self, repo: InMemoryApiKeyRepository):
        """create() raises when key_id already exists."""
        key_id = key_id_factory()

        entity1 = make_api_key(key_id=key_id)
        await repo.create(entity1)

        entity2 = make_api_key(key_id=key_id)
        with pytest.raises(ValueError, match="key_id"):
            await repo.create(entity2)

    @pytest.mark.asyncio
    async def test_duplicate_id_raises(self, repo: InMemoryApiKeyRepository):
        """create() raises when id_ already exists."""
        entity1 = make_api_key()
        await repo.create(entity1)

        # Create entity with same id_ but different key_id
        entity2 = make_api_key()
        entity2.id_ = entity1.id_

        with pytest.raises(ValueError, match="id"):
            await repo.create(entity2)


class TestRepositoryFindAndCount:
    """Tests for find() and count() methods."""

    @pytest.fixture
    def repo(self) -> InMemoryApiKeyRepository:
        return InMemoryApiKeyRepository()

    @pytest.mark.asyncio
    async def test_find_empty_filter(self, repo: InMemoryApiKeyRepository):
        """find() with empty filter returns all."""
        for _ in range(3):
            await repo.create(make_api_key())

        result = await repo.find(ApiKeyFilter())
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_find_by_is_active(self, repo: InMemoryApiKeyRepository):
        """find() filters by is_active."""
        await repo.create(make_api_key(is_active=True))
        await repo.create(make_api_key(is_active=False))

        active = await repo.find(ApiKeyFilter(is_active=True))
        assert len(active) == 1

        inactive = await repo.find(ApiKeyFilter(is_active=False))
        assert len(inactive) == 1

    @pytest.mark.asyncio
    async def test_find_by_scopes_contain_all(self, repo: InMemoryApiKeyRepository):
        """find() filters by scopes_contain_all."""
        await repo.create(make_api_key(scopes=["read", "write", "admin"]))
        await repo.create(make_api_key(scopes=["read", "write"]))
        await repo.create(make_api_key(scopes=["read"]))

        # Keys with both read and write
        result = await repo.find(ApiKeyFilter(scopes_contain_all=["read", "write"]))
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_find_by_name_contains(self, repo: InMemoryApiKeyRepository):
        """find() filters by name_contains (case-insensitive)."""
        key1 = make_api_key()
        key1.name = "Production API Key"
        await repo.create(key1)

        key2 = make_api_key()
        key2.name = "Development Key"
        await repo.create(key2)

        result = await repo.find(ApiKeyFilter(name_contains="api"))
        assert len(result) == 1
        assert result[0].name == "Production API Key"

    @pytest.mark.asyncio
    async def test_find_by_expires_before(self, repo: InMemoryApiKeyRepository):
        """find() filters by expires_before."""
        now = datetime_factory()

        key_soon = make_api_key()
        key_soon.expires_at = now + timedelta(days=5)
        await repo.create(key_soon)

        key_later = make_api_key()
        key_later.expires_at = now + timedelta(days=30)
        await repo.create(key_later)

        result = await repo.find(ApiKeyFilter(expires_before=now + timedelta(days=10)))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_combined_filters(self, repo: InMemoryApiKeyRepository):
        """find() applies multiple filters (AND logic)."""
        now = datetime_factory()

        # Active, expiring soon, admin scope
        key1 = make_api_key(is_active=True, scopes=["admin"])
        key1.expires_at = now + timedelta(days=5)
        await repo.create(key1)

        # Active, expiring later, admin scope
        key2 = make_api_key(is_active=True, scopes=["admin"])
        key2.expires_at = now + timedelta(days=30)
        await repo.create(key2)

        # Inactive, expiring soon, admin scope
        key3 = make_api_key(is_active=False, scopes=["admin"])
        key3.expires_at = now + timedelta(days=5)
        await repo.create(key3)

        result = await repo.find(
            ApiKeyFilter(
                is_active=True,
                expires_before=now + timedelta(days=10),
                scopes_contain_all=["admin"],
            )
        )
        assert len(result) == 1
        assert result[0].id_ == key1.id_

    @pytest.mark.asyncio
    async def test_count_all(self, repo: InMemoryApiKeyRepository):
        """count() returns total count."""
        for _ in range(5):
            await repo.create(make_api_key())

        assert await repo.count() == 5

    @pytest.mark.asyncio
    async def test_count_with_filter(self, repo: InMemoryApiKeyRepository):
        """count() respects filter."""
        await repo.create(make_api_key(is_active=True))
        await repo.create(make_api_key(is_active=True))
        await repo.create(make_api_key(is_active=False))

        assert await repo.count(ApiKeyFilter(is_active=True)) == 2
        assert await repo.count(ApiKeyFilter(is_active=False)) == 1

    @pytest.mark.asyncio
    async def test_count_ignores_pagination(self, repo: InMemoryApiKeyRepository):
        """count() ignores limit and offset."""
        for _ in range(10):
            await repo.create(make_api_key())

        # Should return total, not limited
        assert await repo.count(ApiKeyFilter(limit=3, offset=5)) == 10

    @pytest.mark.asyncio
    async def test_find_by_created_before(self, repo: InMemoryApiKeyRepository):
        """find() filters by created_before."""
        now = datetime_factory()

        key1 = make_api_key()
        key1.created_at = now - timedelta(days=10)
        await repo.create(key1)

        key2 = make_api_key()
        key2.created_at = now - timedelta(days=1)
        await repo.create(key2)

        result = await repo.find(ApiKeyFilter(created_before=now - timedelta(days=5)))
        assert len(result) == 1
        assert result[0].id_ == key1.id_

    @pytest.mark.asyncio
    async def test_find_by_created_after(self, repo: InMemoryApiKeyRepository):
        """find() filters by created_after."""
        now = datetime_factory()

        key1 = make_api_key()
        key1.created_at = now - timedelta(days=10)
        await repo.create(key1)

        key2 = make_api_key()
        key2.created_at = now - timedelta(days=1)
        await repo.create(key2)

        result = await repo.find(ApiKeyFilter(created_after=now - timedelta(days=5)))
        assert len(result) == 1
        assert result[0].id_ == key2.id_

    @pytest.mark.asyncio
    async def test_find_by_last_used_before(self, repo: InMemoryApiKeyRepository):
        """find() filters by last_used_before."""
        now = datetime_factory()

        key1 = make_api_key()
        key1.last_used_at = now - timedelta(days=10)
        await repo.create(key1)

        key2 = make_api_key()
        key2.last_used_at = now - timedelta(days=1)
        await repo.create(key2)

        result = await repo.find(ApiKeyFilter(last_used_before=now - timedelta(days=5)))
        assert len(result) == 1
        assert result[0].id_ == key1.id_

    @pytest.mark.asyncio
    async def test_find_by_last_used_after(self, repo: InMemoryApiKeyRepository):
        """find() filters by last_used_after."""
        now = datetime_factory()

        key1 = make_api_key()
        key1.last_used_at = now - timedelta(days=10)
        await repo.create(key1)

        key2 = make_api_key()
        key2.last_used_at = now - timedelta(days=1)
        await repo.create(key2)

        result = await repo.find(ApiKeyFilter(last_used_after=now - timedelta(days=5)))
        assert len(result) == 1
        assert result[0].id_ == key2.id_

    @pytest.mark.asyncio
    async def test_find_by_never_used(self, repo: InMemoryApiKeyRepository):
        """find() filters by never_used."""
        key_used = make_api_key()
        key_used.last_used_at = datetime_factory()
        await repo.create(key_used)

        key_never_used = make_api_key()
        key_never_used.last_used_at = None
        await repo.create(key_never_used)

        # Find never used
        result = await repo.find(ApiKeyFilter(never_used=True))
        assert len(result) == 1
        assert result[0].id_ == key_never_used.id_

        # Find used
        result = await repo.find(ApiKeyFilter(never_used=False))
        assert len(result) == 1
        assert result[0].id_ == key_used.id_

    @pytest.mark.asyncio
    async def test_find_by_scopes_contain_any(self, repo: InMemoryApiKeyRepository):
        """find() filters by scopes_contain_any."""
        key_admin = make_api_key(scopes=["admin"])
        await repo.create(key_admin)

        key_user = make_api_key(scopes=["read", "write"])
        await repo.create(key_user)

        key_other = make_api_key(scopes=["other"])
        await repo.create(key_other)

        # Find keys with admin OR write
        result = await repo.find(ApiKeyFilter(scopes_contain_any=["admin", "write"]))
        assert len(result) == 2
        result_ids = {r.id_ for r in result}
        assert key_admin.id_ in result_ids
        assert key_user.id_ in result_ids

    @pytest.mark.asyncio
    async def test_find_by_name_exact(self, repo: InMemoryApiKeyRepository):
        """find() filters by name_exact."""
        key1 = make_api_key()
        key1.name = "my-api-key"
        await repo.create(key1)

        key2 = make_api_key()
        key2.name = "my-api-key-2"
        await repo.create(key2)

        result = await repo.find(ApiKeyFilter(name_exact="my-api-key"))
        assert len(result) == 1
        assert result[0].id_ == key1.id_

    @pytest.mark.asyncio
    async def test_find_expires_after(self, repo: InMemoryApiKeyRepository):
        """find() filters by expires_after."""
        now = datetime_factory()

        key_soon = make_api_key()
        key_soon.expires_at = now + timedelta(days=5)
        await repo.create(key_soon)

        key_later = make_api_key()
        key_later.expires_at = now + timedelta(days=30)
        await repo.create(key_later)

        result = await repo.find(ApiKeyFilter(expires_after=now + timedelta(days=10)))
        assert len(result) == 1
        assert result[0].id_ == key_later.id_

    @pytest.mark.asyncio
    async def test_find_order_ascending(self, repo: InMemoryApiKeyRepository):
        """find() orders by created_at ascending."""
        for _ in range(3):
            await repo.create(make_api_key())

        result = await repo.find(ApiKeyFilter(order_by=SortableColumn.CREATED_AT, order_desc=False))
        assert len(result) == 3
        assert result[0].created_at <= result[1].created_at
        assert result[1].created_at <= result[2].created_at
