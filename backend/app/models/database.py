"""
Database configuration and session management
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings
from app.logger import logger
from pathlib import Path

# Create database directory if it doesn't exist
db_path = Path(settings.DATABASE_URL.replace("sqlite+aiosqlite:///", ""))
db_path.parent.mkdir(parents=True, exist_ok=True)

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Disable SQL query logging for cleaner output
    future=True,
    pool_pre_ping=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()


async def get_db() -> AsyncSession:
    """
    Dependency for getting async database session
    
    Yields:
        AsyncSession: Database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized")


async def close_db():
    """Close database connections"""
    await engine.dispose()
    logger.info("Database connections closed")
