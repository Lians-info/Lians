"""
Test fixtures: in-memory SQLite-equivalent via async SQLAlchemy.
We use an in-process PG via pytest-postgresql or a real local PG for integration tests.
For unit tests we mock the DB session with an in-memory approach.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from src.agentmem.db import Base
from src.agentmem.config import get_settings, Settings


# Override settings for tests
@pytest.fixture(autouse=True)
def test_settings(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def db():
    """SQLite in-memory async session for unit tests (no pgvector)."""
    from sqlalchemy import event as sa_event, text

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Drop PG-only indexes before table creation so SQLite doesn't choke
    from src.agentmem.models import Base as AppBase
    import sqlalchemy as sa
    pg_indexes = [
        idx for table in AppBase.metadata.tables.values()
        for idx in table.indexes
        if idx.dialect_kwargs.get("postgresql_using") is not None
    ]
    for idx in pg_indexes:
        idx.table.indexes.discard(idx)

    async with engine.begin() as conn:
        await conn.run_sync(AppBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()
