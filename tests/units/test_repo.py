import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.repositories.base import AbstractApiKeyRepository
from fastapi_api_key.repositories.sql import SqlAlchemyApiKeyRepository
from tests.conftest import make_api_key


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
    assert created.name == api_key.name
    assert created.description == api_key.description
    assert created.is_active == api_key.is_active
    assert created.expires_at == api_key.expires_at
    assert created.key_id == api_key.key_id
    assert created.key_hash == api_key.key_hash


@pytest.mark.asyncio
async def test_api_key_get_by_id(repository: AbstractApiKeyRepository) -> None:
    """Test retrieving an API key by ID."""
    api_key = make_api_key()
    created = await repository.create(entity=api_key)
    retrieved = await repository.get_by_id(id_=created.id_)

    assert retrieved is not None
    assert retrieved.id_ == created.id_
    assert retrieved.name == created.name
    assert retrieved.description == created.description
    assert retrieved.is_active == created.is_active
    assert retrieved.expires_at == created.expires_at
    assert retrieved.key_id == created.key_id
    assert retrieved.key_hash == created.key_hash


@pytest.mark.asyncio
async def test_api_key_get_by_prefix(repository: AbstractApiKeyRepository) -> None:
    """Test retrieving an API key by key_id."""
    api_key = make_api_key()
    created = await repository.create(entity=api_key)
    retrieved = await repository.get_by_key_id(key_id=created.key_id)

    assert retrieved is not None
    assert retrieved.id_ == created.id_
    assert retrieved.name == created.name
    assert retrieved.description == created.description
    assert retrieved.is_active == created.is_active
    assert retrieved.expires_at == created.expires_at
    assert retrieved.key_id == created.key_id
    assert retrieved.key_hash == created.key_hash


@pytest.mark.asyncio
async def test_api_key_update(repository: AbstractApiKeyRepository) -> None:
    """Test updating an existing API key."""
    api_key = make_api_key()
    created = await repository.create(entity=api_key)
    created.name = "updated-name"
    created.is_active = False
    updated = await repository.update(entity=created)

    assert updated is not None
    assert updated.id_ == created.id_
    assert updated.name == "updated-name"
    assert updated.is_active is False
    assert updated.description == created.description
    assert updated.expires_at == created.expires_at
    assert updated.key_id == created.key_id
    assert updated.key_hash == created.key_hash


@pytest.mark.asyncio
async def test_api_key_delete(repository: AbstractApiKeyRepository) -> None:
    """Test deleting an API key."""
    api_key = make_api_key()

    created = await repository.create(entity=api_key)
    assert created.id_ is not None

    result = await repository.delete_by_id(id_=created.id_)
    assert result is True

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
    assert deleted is False


@pytest.mark.asyncio
async def test_api_key_list_empty(repository: AbstractApiKeyRepository) -> None:
    """Test listing API keys when none exist."""
    listed = await repository.list(limit=10, offset=0)
    assert listed == []
