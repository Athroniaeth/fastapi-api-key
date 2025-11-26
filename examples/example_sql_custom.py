"""Example: Custom API Key with additional fields.

This example demonstrates how to extend the default ApiKey entity and model
with custom fields. Thanks to automatic introspection, you only need to:

1. Create a custom dataclass extending ApiKey
2. Create a custom SQLAlchemy model extending ApiKeyModelMixin
3. Pass them to the repository - no need to override to_model/to_domain!

The automatic mapping handles all common fields plus your custom ones.
"""

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase

from fastapi_api_key import ApiKeyService
from fastapi_api_key.domain.entities import ApiKey
from fastapi_api_key.hasher.argon2 import Argon2ApiKeyHasher
from fastapi_api_key.repositories.sql import (
    SqlAlchemyApiKeyRepository,
    ApiKeyModelMixin,
)


# 1. Define your custom SQLAlchemy Base
class Base(DeclarativeBase): ...


# 2. Create a custom domain entity with additional fields
@dataclass
class TenantApiKey(ApiKey):
    """API Key with tenant isolation support."""

    tenant_id: Optional[str] = field(default=None)
    notes: Optional[str] = field(default=None)


# 3. Create a custom SQLAlchemy model with matching columns
class TenantApiKeyModel(Base, ApiKeyModelMixin):
    """SQLAlchemy model with tenant support."""

    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,  # Index for efficient tenant queries
    )
    notes: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )


# 4. Create a factory function for your custom entity
def tenant_api_key_factory(
    key_id: str,
    key_hash: str,
    key_secret: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    is_active: bool = True,
    expires_at=None,
    scopes=None,
    tenant_id: Optional[str] = None,
    notes: Optional[str] = None,
    **kwargs,
) -> TenantApiKey:
    """Factory for creating TenantApiKey entities."""
    return TenantApiKey(
        key_id=key_id,
        key_hash=key_hash,
        _key_secret=key_secret,
        name=name,
        description=description,
        is_active=is_active,
        expires_at=expires_at,
        scopes=scopes or [],
        tenant_id=tenant_id,
        notes=notes,
    )


# Configuration
pepper = os.getenv("API_KEY_PEPPER")
hasher = Argon2ApiKeyHasher(pepper=pepper)

path = Path(__file__).parent / "db_custom.sqlite3"
database_url = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{path}")

async_engine = create_async_engine(database_url, future=True)
async_session_maker = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def main():
    # Create tables
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        # Create repository with custom model and domain classes
        # No need to override to_model/to_domain - automatic mapping handles it!
        repo = SqlAlchemyApiKeyRepository(
            async_session=session,
            model_cls=TenantApiKeyModel,
            domain_cls=TenantApiKey,
        )

        # Create service with custom factory
        service = ApiKeyService(
            repo=repo,
            hasher=hasher,
            entity_factory=tenant_api_key_factory,
        )

        # Create an API key with custom fields
        entity, secret = await service.create(
            name="tenant-key",
            description="API key for tenant operations",
            scopes=["read", "write"],
            tenant_id="tenant-123",
            notes="Created for demo purposes",
        )

        print(f"Created key for tenant: {entity.tenant_id}")
        print(f"Notes: {entity.notes}")
        print(f"Secret (store securely!): {secret}")

        await session.commit()

        # Verify the key works
        verified = await service.verify_key(secret)
        print(f"\nVerified! Tenant: {verified.tenant_id}")


if __name__ == "__main__":
    asyncio.run(main())
