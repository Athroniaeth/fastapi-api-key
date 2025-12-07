"""Unit tests for SqlAlchemyApiKeyRepository.

Tests the SQLAlchemy repository implementation with an in-memory SQLite database.
"""

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from fastapi_api_key.repositories.base import ApiKeyFilter, SortableColumn
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository, Base
from fastapi_api_key.utils import datetime_factory
from tests.conftest import make_api_key  # pyrefly: ignore[missing-import]


@pytest_asyncio.fixture(scope="function")
async def sql_repo():
    """Create a fresh SQLAlchemy repository with in-memory database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        async with session.begin():
            yield SqlAlchemyApiKeyRepository(session)

    await engine.dispose()


class TestSqlRepositoryCRUD:
    """Tests for basic CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_and_get_by_id(self, sql_repo: SqlAlchemyApiKeyRepository):
        """create() and get_by_id() work correctly."""
        entity = make_api_key()
        created = await sql_repo.create(entity)

        assert created.id_ == entity.id_

        retrieved = await sql_repo.get_by_id(entity.id_)
        assert retrieved is not None
        assert retrieved.id_ == entity.id_
        assert retrieved.name == entity.name

    @pytest.mark.asyncio
    async def test_get_by_key_id(self, sql_repo: SqlAlchemyApiKeyRepository):
        """get_by_key_id() retrieves by key_id."""
        entity = make_api_key()
        await sql_repo.create(entity)

        retrieved = await sql_repo.get_by_key_id(entity.key_id)
        assert retrieved is not None
        assert retrieved.key_id == entity.key_id

    @pytest.mark.asyncio
    async def test_update(self, sql_repo: SqlAlchemyApiKeyRepository):
        """update() modifies existing entity."""
        entity = make_api_key()
        await sql_repo.create(entity)

        entity.name = "updated-name"
        entity.is_active = False
        updated = await sql_repo.update(entity)

        assert updated is not None
        assert updated.name == "updated-name"
        assert updated.is_active is False

    @pytest.mark.asyncio
    async def test_delete_by_id(self, sql_repo: SqlAlchemyApiKeyRepository):
        """delete_by_id() removes entity."""
        entity = make_api_key()
        await sql_repo.create(entity)

        deleted = await sql_repo.delete_by_id(entity.id_)
        assert deleted is not None

        retrieved = await sql_repo.get_by_id(entity.id_)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_list(self, sql_repo: SqlAlchemyApiKeyRepository):
        """list() returns entities with pagination."""
        for _ in range(5):
            await sql_repo.create(make_api_key())

        result = await sql_repo.list(limit=3, offset=0)
        assert len(result) == 3

        result = await sql_repo.list(limit=3, offset=3)
        assert len(result) == 2


class TestSqlRepositoryNotFound:
    """Tests for operations on non-existent entities."""

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, sql_repo: SqlAlchemyApiKeyRepository):
        """get_by_id() returns None for non-existent ID."""
        result = await sql_repo.get_by_id("non-existent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_key_id_not_found(self, sql_repo: SqlAlchemyApiKeyRepository):
        """get_by_key_id() returns None for non-existent key_id."""
        result = await sql_repo.get_by_key_id("non-existent")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_not_found(self, sql_repo: SqlAlchemyApiKeyRepository):
        """update() returns None for non-existent entity."""
        entity = make_api_key()
        result = await sql_repo.update(entity)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, sql_repo: SqlAlchemyApiKeyRepository):
        """delete_by_id() returns None for non-existent ID."""
        result = await sql_repo.delete_by_id("non-existent")
        assert result is None


class TestSqlRepositoryFind:
    """Tests for find() method."""

    @pytest.mark.asyncio
    async def test_find_empty_filter(self, sql_repo: SqlAlchemyApiKeyRepository):
        """find() with empty filter returns all."""
        for _ in range(3):
            await sql_repo.create(make_api_key())

        result = await sql_repo.find(ApiKeyFilter())
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_find_by_is_active(self, sql_repo: SqlAlchemyApiKeyRepository):
        """find() filters by is_active."""
        await sql_repo.create(make_api_key(is_active=True))
        await sql_repo.create(make_api_key(is_active=False))

        result = await sql_repo.find(ApiKeyFilter(is_active=True))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_expires_before(self, sql_repo: SqlAlchemyApiKeyRepository):
        """find() filters by expires_before."""
        now = datetime_factory()

        key1 = make_api_key()
        key1.expires_at = now + timedelta(days=5)
        await sql_repo.create(key1)

        key2 = make_api_key()
        key2.expires_at = now + timedelta(days=30)
        await sql_repo.create(key2)

        result = await sql_repo.find(ApiKeyFilter(expires_before=now + timedelta(days=10)))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_expires_after(self, sql_repo: SqlAlchemyApiKeyRepository):
        """find() filters by expires_after."""
        now = datetime_factory()

        key1 = make_api_key()
        key1.expires_at = now + timedelta(days=5)
        await sql_repo.create(key1)

        key2 = make_api_key()
        key2.expires_at = now + timedelta(days=30)
        await sql_repo.create(key2)

        result = await sql_repo.find(ApiKeyFilter(expires_after=now + timedelta(days=10)))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_created_before(self, sql_repo: SqlAlchemyApiKeyRepository):
        """find() filters by created_before."""
        now = datetime_factory()

        key1 = make_api_key()
        key1.created_at = now - timedelta(days=10)
        await sql_repo.create(key1)

        key2 = make_api_key()
        key2.created_at = now - timedelta(days=1)
        await sql_repo.create(key2)

        result = await sql_repo.find(ApiKeyFilter(created_before=now - timedelta(days=5)))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_created_after(self, sql_repo: SqlAlchemyApiKeyRepository):
        """find() filters by created_after."""
        now = datetime_factory()

        key1 = make_api_key()
        key1.created_at = now - timedelta(days=10)
        await sql_repo.create(key1)

        key2 = make_api_key()
        key2.created_at = now - timedelta(days=1)
        await sql_repo.create(key2)

        result = await sql_repo.find(ApiKeyFilter(created_after=now - timedelta(days=5)))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_last_used_before(self, sql_repo: SqlAlchemyApiKeyRepository):
        """find() filters by last_used_before."""
        now = datetime_factory()

        key1 = make_api_key()
        key1.last_used_at = now - timedelta(days=10)
        await sql_repo.create(key1)

        key2 = make_api_key()
        key2.last_used_at = now - timedelta(days=1)
        await sql_repo.create(key2)

        result = await sql_repo.find(ApiKeyFilter(last_used_before=now - timedelta(days=5)))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_last_used_after(self, sql_repo: SqlAlchemyApiKeyRepository):
        """find() filters by last_used_after."""
        now = datetime_factory()

        key1 = make_api_key()
        key1.last_used_at = now - timedelta(days=10)
        await sql_repo.create(key1)

        key2 = make_api_key()
        key2.last_used_at = now - timedelta(days=1)
        await sql_repo.create(key2)

        result = await sql_repo.find(ApiKeyFilter(last_used_after=now - timedelta(days=5)))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_never_used(self, sql_repo: SqlAlchemyApiKeyRepository):
        """find() filters by never_used."""
        key_used = make_api_key()
        key_used.last_used_at = datetime_factory()
        await sql_repo.create(key_used)

        key_never = make_api_key()
        key_never.last_used_at = None
        await sql_repo.create(key_never)

        # Find never used
        result = await sql_repo.find(ApiKeyFilter(never_used=True))
        assert len(result) == 1
        assert result[0].last_used_at is None

        # Find used
        result = await sql_repo.find(ApiKeyFilter(never_used=False))
        assert len(result) == 1
        assert result[0].last_used_at is not None

    @pytest.mark.asyncio
    async def test_find_by_name_contains(self, sql_repo: SqlAlchemyApiKeyRepository):
        """find() filters by name_contains (case-insensitive)."""
        key1 = make_api_key()
        key1.name = "Production API Key"
        await sql_repo.create(key1)

        key2 = make_api_key()
        key2.name = "Development Key"
        await sql_repo.create(key2)

        result = await sql_repo.find(ApiKeyFilter(name_contains="api"))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_name_exact(self, sql_repo: SqlAlchemyApiKeyRepository):
        """find() filters by name_exact."""
        key1 = make_api_key()
        key1.name = "my-key"
        await sql_repo.create(key1)

        key2 = make_api_key()
        key2.name = "my-key-2"
        await sql_repo.create(key2)

        result = await sql_repo.find(ApiKeyFilter(name_exact="my-key"))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_by_scopes_contain_all(self, sql_repo: SqlAlchemyApiKeyRepository):
        """find() filters by scopes_contain_all."""
        await sql_repo.create(make_api_key(scopes=["read", "write", "admin"]))
        await sql_repo.create(make_api_key(scopes=["read", "write"]))
        await sql_repo.create(make_api_key(scopes=["read"]))

        result = await sql_repo.find(ApiKeyFilter(scopes_contain_all=["read", "write"]))
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_find_by_scopes_contain_any(self, sql_repo: SqlAlchemyApiKeyRepository):
        """find() filters by scopes_contain_any."""
        await sql_repo.create(make_api_key(scopes=["admin"]))
        await sql_repo.create(make_api_key(scopes=["read"]))
        await sql_repo.create(make_api_key(scopes=["other"]))

        result = await sql_repo.find(ApiKeyFilter(scopes_contain_any=["admin", "read"]))
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_find_order_ascending(self, sql_repo: SqlAlchemyApiKeyRepository):
        """find() orders ascending when specified."""
        for _ in range(3):
            await sql_repo.create(make_api_key())

        result = await sql_repo.find(ApiKeyFilter(order_by=SortableColumn.CREATED_AT, order_desc=False))
        assert len(result) == 3
        assert result[0].created_at <= result[1].created_at


class TestSqlRepositoryCount:
    """Tests for count() method."""

    @pytest.mark.asyncio
    async def test_count_all(self, sql_repo: SqlAlchemyApiKeyRepository):
        """count() returns total count."""
        for _ in range(5):
            await sql_repo.create(make_api_key())

        assert await sql_repo.count() == 5

    @pytest.mark.asyncio
    async def test_count_with_filter(self, sql_repo: SqlAlchemyApiKeyRepository):
        """count() respects filter."""
        await sql_repo.create(make_api_key(is_active=True))
        await sql_repo.create(make_api_key(is_active=True))
        await sql_repo.create(make_api_key(is_active=False))

        assert await sql_repo.count(ApiKeyFilter(is_active=True)) == 2

    @pytest.mark.asyncio
    async def test_count_with_scope_filter(self, sql_repo: SqlAlchemyApiKeyRepository):
        """count() with scope filter uses find() fallback."""
        await sql_repo.create(make_api_key(scopes=["admin"]))
        await sql_repo.create(make_api_key(scopes=["read"]))
        await sql_repo.create(make_api_key(scopes=["admin", "read"]))

        assert await sql_repo.count(ApiKeyFilter(scopes_contain_all=["admin"])) == 2

    @pytest.mark.asyncio
    async def test_count_with_expires_filter(self, sql_repo: SqlAlchemyApiKeyRepository):
        """count() with expires_before/after filter."""
        now = datetime_factory()

        key1 = make_api_key()
        key1.expires_at = now + timedelta(days=5)
        await sql_repo.create(key1)

        key2 = make_api_key()
        key2.expires_at = now + timedelta(days=30)
        await sql_repo.create(key2)

        assert await sql_repo.count(ApiKeyFilter(expires_before=now + timedelta(days=10))) == 1
        assert await sql_repo.count(ApiKeyFilter(expires_after=now + timedelta(days=10))) == 1

    @pytest.mark.asyncio
    async def test_count_with_created_filter(self, sql_repo: SqlAlchemyApiKeyRepository):
        """count() with created_before/after filter."""
        now = datetime_factory()

        key1 = make_api_key()
        key1.created_at = now - timedelta(days=10)
        await sql_repo.create(key1)

        key2 = make_api_key()
        key2.created_at = now - timedelta(days=1)
        await sql_repo.create(key2)

        assert await sql_repo.count(ApiKeyFilter(created_before=now - timedelta(days=5))) == 1
        assert await sql_repo.count(ApiKeyFilter(created_after=now - timedelta(days=5))) == 1

    @pytest.mark.asyncio
    async def test_count_with_last_used_filter(self, sql_repo: SqlAlchemyApiKeyRepository):
        """count() with last_used_before/after filter."""
        now = datetime_factory()

        key1 = make_api_key()
        key1.last_used_at = now - timedelta(days=10)
        await sql_repo.create(key1)

        key2 = make_api_key()
        key2.last_used_at = now - timedelta(days=1)
        await sql_repo.create(key2)

        assert await sql_repo.count(ApiKeyFilter(last_used_before=now - timedelta(days=5))) == 1
        assert await sql_repo.count(ApiKeyFilter(last_used_after=now - timedelta(days=5))) == 1

    @pytest.mark.asyncio
    async def test_count_with_never_used_filter(self, sql_repo: SqlAlchemyApiKeyRepository):
        """count() with never_used filter."""
        key_used = make_api_key()
        key_used.last_used_at = datetime_factory()
        await sql_repo.create(key_used)

        key_never = make_api_key()
        key_never.last_used_at = None
        await sql_repo.create(key_never)

        assert await sql_repo.count(ApiKeyFilter(never_used=True)) == 1
        assert await sql_repo.count(ApiKeyFilter(never_used=False)) == 1

    @pytest.mark.asyncio
    async def test_count_with_name_filter(self, sql_repo: SqlAlchemyApiKeyRepository):
        """count() with name_contains/exact filter."""
        key1 = make_api_key()
        key1.name = "Production API"
        await sql_repo.create(key1)

        key2 = make_api_key()
        key2.name = "Development"
        await sql_repo.create(key2)

        assert await sql_repo.count(ApiKeyFilter(name_contains="api")) == 1
        assert await sql_repo.count(ApiKeyFilter(name_exact="Development")) == 1


class TestSqlRepositoryEnsureTable:
    """Tests for ensure_table() method."""

    @pytest.mark.asyncio
    async def test_ensure_table_creates_table(self):
        """ensure_table() creates table if not exists."""
        async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
        async_session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session_maker() as async_session:
            repo = SqlAlchemyApiKeyRepository(async_session)

            # Table doesn't exist yet, create should fail
            with pytest.raises(Exception):
                await repo.create(make_api_key())

            await async_session.rollback()

            # Now ensure table exists
            await repo.ensure_table(async_engine=async_engine)

            # Should work now
            entity = make_api_key()
            created = await repo.create(entity)
            assert created.id_ == entity.id_

        await async_engine.dispose()


class TestSqlRepositoryConversion:
    """Tests for model <-> domain conversion."""

    @pytest.mark.asyncio
    async def test_to_domain_preserves_all_fields(self, sql_repo: SqlAlchemyApiKeyRepository):
        """_to_domain preserves all entity fields."""
        entity = make_api_key()
        entity.description = "Test description"
        entity.scopes = ["read", "write", "admin"]

        await sql_repo.create(entity)
        retrieved = await sql_repo.get_by_id(entity.id_)

        assert retrieved is not None
        assert retrieved.id_ == entity.id_
        assert retrieved.name == entity.name
        assert retrieved.description == entity.description
        assert retrieved.is_active == entity.is_active
        assert retrieved.key_id == entity.key_id
        assert retrieved.key_hash == entity.key_hash
        assert retrieved.scopes == entity.scopes

    @pytest.mark.asyncio
    async def test_to_domain_returns_none_for_none(self, sql_repo: SqlAlchemyApiKeyRepository):
        """_to_domain returns None for None input."""
        result = SqlAlchemyApiKeyRepository._to_domain(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_update_uses_target_model(self, sql_repo: SqlAlchemyApiKeyRepository):
        """update() reuses existing model instance."""
        entity = make_api_key()
        await sql_repo.create(entity)

        entity.name = "updated"
        entity.description = "new description"
        entity.scopes = ["admin"]

        updated = await sql_repo.update(entity)

        assert updated is not None
        assert updated.name == "updated"
        assert updated.description == "new description"
        assert updated.scopes == ["admin"]
