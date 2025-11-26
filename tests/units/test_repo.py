from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

import pytest
from sqlalchemy import String
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase


from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.repositories.base import AbstractApiKeyRepository, ApiKeyFilter
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository, ApiKeyModelMixin
from fastapi_api_key.utils import key_id_factory, datetime_factory
from tests.conftest import make_api_key


def assert_identical(a: ApiKey, b: ApiKey, same_name: bool = False, same_is_active: bool = False) -> None:
    """Assert that two ApiKey instances are identical."""
    assert a.id_ == b.id_, "IDs do not match"
    assert a.name == b.name or same_name, "Names do not match"
    assert a.description == b.description, "Descriptions do not match"
    assert a.is_active == b.is_active or same_is_active, "Active statuses do not match"
    assert a.expires_at == b.expires_at, "Expiration dates do not match"
    assert a.key_id == b.key_id, "Key IDs do not match"
    assert a.key_hash == b.key_hash, "Key hashes do not match"
    assert a.scopes == b.scopes, "Scopes do not match"


@pytest.mark.asyncio
async def test_ensure_table() -> None:
    """Test that the database table for API keys exists."""
    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as async_session:
        repo = SqlAlchemyApiKeyRepository(async_session=async_session)

        with pytest.raises(Exception):
            # Attempt to query the table before ensuring it exists
            await repo.create(entity=make_api_key())

        # Rollback transaction to clear any partial state
        await async_session.rollback()

        await repo.ensure_table()
        await repo.create(entity=make_api_key())  # Should not raise now


@pytest.mark.asyncio
async def test_api_key_create(repository: AbstractApiKeyRepository) -> None:
    """Test creating an API key."""
    api_key = make_api_key()
    assert api_key.id_ is not None  # Ensure ID is set before creation
    created = await repository.create(entity=api_key)

    assert created.id_ is not None
    assert_identical(created, api_key)


@pytest.mark.asyncio
async def test_api_key_get_by_id(repository: AbstractApiKeyRepository) -> None:
    """Test retrieving an API key by ID."""
    api_key = make_api_key()
    created = await repository.create(entity=api_key)
    retrieved = await repository.get_by_id(id_=created.id_)

    assert retrieved is not None
    assert_identical(created, api_key)


@pytest.mark.asyncio
async def test_api_key_get_by_prefix(repository: AbstractApiKeyRepository) -> None:
    """Test retrieving an API key by key_id."""
    api_key = make_api_key()
    created = await repository.create(entity=api_key)
    retrieved = await repository.get_by_key_id(key_id=created.key_id)

    assert retrieved is not None
    assert_identical(created, api_key)


@pytest.mark.asyncio
async def test_api_key_update(repository: AbstractApiKeyRepository) -> None:
    """Test updating an existing API key."""
    api_key = make_api_key()
    created = await repository.create(entity=api_key)
    created.name = "updated-name"
    created.is_active = False
    updated = await repository.update(entity=created)

    assert updated is not None
    assert_identical(
        created,
        api_key,
        same_name=True,
        same_is_active=True,
    )


@pytest.mark.asyncio
async def test_api_key_delete(repository: AbstractApiKeyRepository) -> None:
    """Test deleting an API key."""
    api_key = make_api_key()

    created = await repository.create(entity=api_key)
    assert created.id_ is not None

    result = await repository.delete_by_id(id_=created.id_)
    assert result == created

    deleted = await repository.get_by_id(id_=created.id_)
    assert deleted is None


@pytest.mark.asyncio
async def test_api_key_list(repository: AbstractApiKeyRepository) -> None:
    """Test listing API keys with pagination."""
    # Create multiple API keys
    keys = [make_api_key() for _ in range(5)]

    for key in keys:
        await repository.create(entity=key)

    listed = await repository.list(limit=3, offset=1)
    assert len(listed) == 3

    # Ensure the listed keys are part of the created keys
    created_ids = {key.id_ for key in keys}

    for key in listed:
        assert key.id_ in created_ids

    listed = await repository.list(limit=3, offset=1)
    assert all(isinstance(key, ApiKey) for key in listed)
    assert listed[0].created_at >= listed[1].created_at  # Ensure ordering by created_at desc
    assert listed[1].created_at >= listed[2].created_at


@pytest.mark.asyncio
async def test_api_key_get_by_id_not_found(
    repository: AbstractApiKeyRepository,
) -> None:
    """Test retrieving a non-existent API key by ID."""
    retrieved = await repository.get_by_id(id_="non-existent-id")
    assert retrieved is None


@pytest.mark.asyncio
async def test_api_key_get_by_prefix_not_found(
    repository: AbstractApiKeyRepository,
) -> None:
    """Test retrieving a non-existent API key by key_id."""
    retrieved = await repository.get_by_key_id(key_id="non-existent-key_id")
    assert retrieved is None


@pytest.mark.asyncio
async def test_api_key_update_not_found(repository: AbstractApiKeyRepository) -> None:
    """Test updating a non-existent API key."""
    api_key = make_api_key()
    api_key.id_ = "non-existent-id"
    updated = await repository.update(entity=api_key)
    assert updated is None


@pytest.mark.asyncio
async def test_api_key_delete_not_found(repository: AbstractApiKeyRepository) -> None:
    """Test deleting a non-existent API key."""
    deleted = await repository.delete_by_id(id_="non-existent-id")
    assert deleted is None


@pytest.mark.asyncio
async def test_api_key_list_empty(repository: AbstractApiKeyRepository) -> None:
    """Test listing API keys when none exist."""
    listed = await repository.list(limit=10, offset=0)
    assert listed == []


@pytest.mark.asyncio
async def test_duplicate_key_id_creation_raises(repository: AbstractApiKeyRepository) -> None:
    """create(): should raise when trying to create two keys with same key_id."""
    key_id = key_id_factory()

    entity_1 = make_api_key(key_id=key_id)
    await repository.create(entity=entity_1)

    entity_2 = make_api_key(key_id=key_id)
    with pytest.raises(Exception):
        await repository.create(entity=entity_2)


# =============================================================================
# Tests for find() and count() methods
# =============================================================================


@pytest.mark.asyncio
async def test_find_empty_filter(repository: AbstractApiKeyRepository) -> None:
    """find(): should return all keys with empty filter."""
    keys = [make_api_key() for _ in range(3)]
    for key in keys:
        await repository.create(entity=key)

    result = await repository.find(ApiKeyFilter())
    assert len(result) == 3


@pytest.mark.asyncio
async def test_find_filter_is_active_true(repository: AbstractApiKeyRepository) -> None:
    """find(): should filter by is_active=True."""
    active_key = make_api_key()
    active_key.is_active = True
    await repository.create(entity=active_key)

    inactive_key = make_api_key()
    inactive_key.is_active = False
    await repository.create(entity=inactive_key)

    result = await repository.find(ApiKeyFilter(is_active=True))
    assert len(result) == 1
    assert result[0].id_ == active_key.id_


@pytest.mark.asyncio
async def test_find_filter_is_active_false(repository: AbstractApiKeyRepository) -> None:
    """find(): should filter by is_active=False."""
    active_key = make_api_key()
    active_key.is_active = True
    await repository.create(entity=active_key)

    inactive_key = make_api_key()
    inactive_key.is_active = False
    await repository.create(entity=inactive_key)

    result = await repository.find(ApiKeyFilter(is_active=False))
    assert len(result) == 1
    assert result[0].id_ == inactive_key.id_


@pytest.mark.asyncio
async def test_find_filter_expires_before(repository: AbstractApiKeyRepository) -> None:
    """find(): should filter by expires_before."""
    now = datetime_factory()

    key_expires_soon = make_api_key()
    key_expires_soon.expires_at = now + timedelta(days=5)
    await repository.create(entity=key_expires_soon)

    key_expires_later = make_api_key()
    key_expires_later.expires_at = now + timedelta(days=30)
    await repository.create(entity=key_expires_later)

    # Find keys expiring before 10 days from now
    result = await repository.find(ApiKeyFilter(expires_before=now + timedelta(days=10)))
    assert len(result) == 1
    assert result[0].id_ == key_expires_soon.id_


@pytest.mark.asyncio
async def test_find_filter_expires_after(repository: AbstractApiKeyRepository) -> None:
    """find(): should filter by expires_after."""
    now = datetime_factory()

    key_expires_soon = make_api_key()
    key_expires_soon.expires_at = now + timedelta(days=5)
    await repository.create(entity=key_expires_soon)

    key_expires_later = make_api_key()
    key_expires_later.expires_at = now + timedelta(days=30)
    await repository.create(entity=key_expires_later)

    # Find keys expiring after 10 days from now
    result = await repository.find(ApiKeyFilter(expires_after=now + timedelta(days=10)))
    assert len(result) == 1
    assert result[0].id_ == key_expires_later.id_


@pytest.mark.asyncio
async def test_find_filter_name_contains(repository: AbstractApiKeyRepository) -> None:
    """find(): should filter by name containing a substring (case-insensitive)."""
    key1 = make_api_key()
    key1.name = "Production API Key"
    await repository.create(entity=key1)

    key2 = make_api_key()
    key2.name = "Development Key"
    await repository.create(entity=key2)

    key3 = make_api_key()
    key3.name = "Test API"
    await repository.create(entity=key3)

    # Search for "api" (case-insensitive)
    result = await repository.find(ApiKeyFilter(name_contains="api"))
    assert len(result) == 2
    result_ids = {r.id_ for r in result}
    assert key1.id_ in result_ids
    assert key3.id_ in result_ids


@pytest.mark.asyncio
async def test_find_filter_name_exact(repository: AbstractApiKeyRepository) -> None:
    """find(): should filter by exact name match."""
    key1 = make_api_key()
    key1.name = "my-api-key"
    await repository.create(entity=key1)

    key2 = make_api_key()
    key2.name = "my-api-key-2"
    await repository.create(entity=key2)

    result = await repository.find(ApiKeyFilter(name_exact="my-api-key"))
    assert len(result) == 1
    assert result[0].id_ == key1.id_


@pytest.mark.asyncio
async def test_find_filter_scopes_contain_all(repository: AbstractApiKeyRepository) -> None:
    """find(): should filter by keys having all specified scopes."""
    key_admin = make_api_key()
    key_admin.scopes = ["read", "write", "admin"]
    await repository.create(entity=key_admin)

    key_user = make_api_key()
    key_user.scopes = ["read", "write"]
    await repository.create(entity=key_user)

    key_readonly = make_api_key()
    key_readonly.scopes = ["read"]
    await repository.create(entity=key_readonly)

    # Find keys with both "read" and "write" scopes
    result = await repository.find(ApiKeyFilter(scopes_contain_all=["read", "write"]))
    assert len(result) == 2
    result_ids = {r.id_ for r in result}
    assert key_admin.id_ in result_ids
    assert key_user.id_ in result_ids


@pytest.mark.asyncio
async def test_find_filter_scopes_contain_any(repository: AbstractApiKeyRepository) -> None:
    """find(): should filter by keys having at least one of the specified scopes."""
    key_admin = make_api_key()
    key_admin.scopes = ["admin"]
    await repository.create(entity=key_admin)

    key_user = make_api_key()
    key_user.scopes = ["read", "write"]
    await repository.create(entity=key_user)

    key_other = make_api_key()
    key_other.scopes = ["other"]
    await repository.create(entity=key_other)

    # Find keys with "admin" OR "write" scope
    result = await repository.find(ApiKeyFilter(scopes_contain_any=["admin", "write"]))
    assert len(result) == 2
    result_ids = {r.id_ for r in result}
    assert key_admin.id_ in result_ids
    assert key_user.id_ in result_ids


@pytest.mark.asyncio
async def test_find_filter_never_used(repository: AbstractApiKeyRepository) -> None:
    """find(): should filter by never_used (last_used_at is None)."""
    key_used = make_api_key()
    key_used.last_used_at = datetime_factory()
    await repository.create(entity=key_used)

    key_never_used = make_api_key()
    key_never_used.last_used_at = None
    await repository.create(entity=key_never_used)

    # Find keys never used
    result = await repository.find(ApiKeyFilter(never_used=True))
    assert len(result) == 1
    assert result[0].id_ == key_never_used.id_

    # Find keys that have been used
    result = await repository.find(ApiKeyFilter(never_used=False))
    assert len(result) == 1
    assert result[0].id_ == key_used.id_


@pytest.mark.asyncio
async def test_find_pagination(repository: AbstractApiKeyRepository) -> None:
    """find(): should support pagination via limit and offset."""
    keys = [make_api_key() for _ in range(5)]
    for key in keys:
        await repository.create(entity=key)

    # Get first 2 items
    result = await repository.find(ApiKeyFilter(limit=2, offset=0))
    assert len(result) == 2

    # Get next 2 items
    result = await repository.find(ApiKeyFilter(limit=2, offset=2))
    assert len(result) == 2

    # Get remaining items
    result = await repository.find(ApiKeyFilter(limit=10, offset=4))
    assert len(result) == 1


@pytest.mark.asyncio
async def test_find_order_by_created_at_desc(repository: AbstractApiKeyRepository) -> None:
    """find(): should order by created_at descending by default."""
    keys = [make_api_key() for _ in range(3)]
    for key in keys:
        await repository.create(entity=key)

    result = await repository.find(ApiKeyFilter(order_by="created_at", order_desc=True))
    assert len(result) == 3
    assert result[0].created_at >= result[1].created_at
    assert result[1].created_at >= result[2].created_at


@pytest.mark.asyncio
async def test_find_order_by_created_at_asc(repository: AbstractApiKeyRepository) -> None:
    """find(): should order by created_at ascending when specified."""
    keys = [make_api_key() for _ in range(3)]
    for key in keys:
        await repository.create(entity=key)

    result = await repository.find(ApiKeyFilter(order_by="created_at", order_desc=False))
    assert len(result) == 3
    assert result[0].created_at <= result[1].created_at
    assert result[1].created_at <= result[2].created_at


@pytest.mark.asyncio
async def test_find_combined_filters(repository: AbstractApiKeyRepository) -> None:
    """find(): should apply multiple filters (AND logic)."""
    now = datetime_factory()

    # Active key expiring soon with admin scope
    key1 = make_api_key()
    key1.is_active = True
    key1.expires_at = now + timedelta(days=5)
    key1.scopes = ["admin"]
    await repository.create(entity=key1)

    # Active key expiring later with admin scope
    key2 = make_api_key()
    key2.is_active = True
    key2.expires_at = now + timedelta(days=30)
    key2.scopes = ["admin"]
    await repository.create(entity=key2)

    # Inactive key expiring soon with admin scope
    key3 = make_api_key()
    key3.is_active = False
    key3.expires_at = now + timedelta(days=5)
    key3.scopes = ["admin"]
    await repository.create(entity=key3)

    # Find active keys expiring before 10 days with admin scope
    result = await repository.find(
        ApiKeyFilter(
            is_active=True,
            expires_before=now + timedelta(days=10),
            scopes_contain_all=["admin"],
        )
    )
    assert len(result) == 1
    assert result[0].id_ == key1.id_


@pytest.mark.asyncio
async def test_find_empty_result(repository: AbstractApiKeyRepository) -> None:
    """find(): should return empty list when no keys match."""
    key = make_api_key()
    key.is_active = True
    await repository.create(entity=key)

    result = await repository.find(ApiKeyFilter(is_active=False))
    assert result == []


@pytest.mark.asyncio
async def test_count_all(repository: AbstractApiKeyRepository) -> None:
    """count(): should count all keys when no filter provided."""
    keys = [make_api_key() for _ in range(5)]
    for key in keys:
        await repository.create(entity=key)

    count = await repository.count()
    assert count == 5


@pytest.mark.asyncio
async def test_count_with_filter(repository: AbstractApiKeyRepository) -> None:
    """count(): should count keys matching the filter."""
    active_keys = [make_api_key() for _ in range(3)]
    for key in active_keys:
        key.is_active = True
        await repository.create(entity=key)

    inactive_keys = [make_api_key() for _ in range(2)]
    for key in inactive_keys:
        key.is_active = False
        await repository.create(entity=key)

    # Count active keys
    count = await repository.count(ApiKeyFilter(is_active=True))
    assert count == 3

    # Count inactive keys
    count = await repository.count(ApiKeyFilter(is_active=False))
    assert count == 2


@pytest.mark.asyncio
async def test_count_empty(repository: AbstractApiKeyRepository) -> None:
    """count(): should return 0 when no keys exist."""
    count = await repository.count()
    assert count == 0


@pytest.mark.asyncio
async def test_count_ignores_pagination(repository: AbstractApiKeyRepository) -> None:
    """count(): should ignore limit and offset from filter."""
    keys = [make_api_key() for _ in range(10)]
    for key in keys:
        await repository.create(entity=key)

    # Count should return total, not limited count
    count = await repository.count(ApiKeyFilter(limit=3, offset=5))
    assert count == 10


# =============================================================================
# Tests for automatic mapping with custom fields
# =============================================================================


class CustomBase(DeclarativeBase): ...


@dataclass
class CustomApiKey(ApiKey):
    """Custom API key with additional fields for testing."""

    tenant_id: Optional[str] = field(default=None)
    custom_field: Optional[str] = field(default=None)


class CustomApiKeyModel(CustomBase, ApiKeyModelMixin):
    """Custom SQLAlchemy model with additional columns."""

    tenant_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    custom_field: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)


@pytest.mark.asyncio
async def test_auto_mapping_with_custom_fields() -> None:
    """to_model/to_domain: should automatically map custom fields."""
    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async with async_engine.begin() as conn:
        await conn.run_sync(CustomBase.metadata.create_all)

    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        repo = SqlAlchemyApiKeyRepository(
            async_session=session,
            model_cls=CustomApiKeyModel,
            domain_cls=CustomApiKey,
        )

        # Create entity with custom fields
        original = make_api_key()
        custom_entity = CustomApiKey(
            id_=original.id_,
            name=original.name,
            description=original.description,
            is_active=original.is_active,
            expires_at=original.expires_at,
            created_at=original.created_at,
            key_id=original.key_id,
            key_hash=original.key_hash,
            _key_secret=original._key_secret,
            scopes=original.scopes,
            tenant_id="tenant-abc",
            custom_field="custom-value",
        )

        # Create and retrieve
        created = await repo.create(custom_entity)

        assert isinstance(created, CustomApiKey)
        assert created.tenant_id == "tenant-abc"
        assert created.custom_field == "custom-value"

        # Verify retrieval
        retrieved = await repo.get_by_id(created.id_)
        assert isinstance(retrieved, CustomApiKey)
        assert retrieved.tenant_id == "tenant-abc"
        assert retrieved.custom_field == "custom-value"

        # Verify update
        retrieved.tenant_id = "tenant-xyz"
        retrieved.custom_field = "updated-value"
        updated = await repo.update(retrieved)

        assert updated.tenant_id == "tenant-xyz"
        assert updated.custom_field == "updated-value"

    await async_engine.dispose()


@pytest.mark.asyncio
async def test_auto_mapping_preserves_base_fields() -> None:
    """to_model/to_domain: custom fields should not break base field mapping."""
    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async with async_engine.begin() as conn:
        await conn.run_sync(CustomBase.metadata.create_all)

    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        repo = SqlAlchemyApiKeyRepository(
            async_session=session,
            model_cls=CustomApiKeyModel,
            domain_cls=CustomApiKey,
        )

        original = make_api_key()
        custom_entity = CustomApiKey(
            id_=original.id_,
            name="test-name",
            description="test-description",
            is_active=True,
            expires_at=original.expires_at,
            created_at=original.created_at,
            key_id=original.key_id,
            key_hash=original.key_hash,
            _key_secret=original._key_secret,
            scopes=["read", "write", "admin"],
            tenant_id="tenant-123",
            custom_field=None,
        )

        created = await repo.create(custom_entity)

        # Verify all base fields are preserved
        assert created.id_ == original.id_
        assert created.name == "test-name"
        assert created.description == "test-description"
        assert created.is_active is True
        assert created.key_id == original.key_id
        assert created.key_hash == original.key_hash
        assert created.scopes == ["read", "write", "admin"]

    await async_engine.dispose()
