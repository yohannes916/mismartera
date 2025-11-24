"""Pytest configuration and fixtures for DataManager tests."""
import pytest
import asyncio
from datetime import datetime, date, time
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models.database import Base
from app.config import settings


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def test_db_session():
    """Create a test database session.
    
    Uses in-memory SQLite database for fast, isolated tests.
    """
    # Create in-memory SQLite database
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session factory
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    # Provide session
    async with async_session() as session:
        yield session
    
    # Cleanup
    await engine.dispose()


@pytest.fixture
def system_manager():
    """Create a SystemManager instance for tests.
    
    Returns a fresh SystemManager instance in STOPPED state.
    Tests can call system_mgr.set_mode("live" or "backtest") as needed.
    """
    from app.managers.system_manager import SystemManager, reset_system_manager
    
    # Reset singleton to get fresh instance
    reset_system_manager()
    
    # Create new instance
    sys_mgr = SystemManager()
    
    yield sys_mgr
    
    # Cleanup - reset singleton after test
    reset_system_manager()


@pytest.fixture
def sample_date():
    """Provide a consistent sample date for tests."""
    return date(2025, 11, 20)


@pytest.fixture
def market_open_time():
    """Provide market open time (9:30 AM ET)."""
    return time(9, 30)


@pytest.fixture
def market_close_time():
    """Provide market close time (4:00 PM ET)."""
    return time(16, 0)
