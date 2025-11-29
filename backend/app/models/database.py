"""
Database configuration and session management
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings
from app.logger import logger
from pathlib import Path

# Create database directory if it doesn't exist
# Convert async URL to sync URL (remove +aiosqlite)
db_url = settings.DATABASE_URL.replace("sqlite+aiosqlite://", "sqlite://")
db_path = Path(db_url.replace("sqlite:///", ""))
db_path.parent.mkdir(parents=True, exist_ok=True)

# Create synchronous engine
# Thread-safe by default - each thread gets its own connection from pool
# No event loop issues, no asyncio complexity
engine = create_engine(
    db_url,
    echo=False,  # Disable SQL query logging for cleaner output
    pool_pre_ping=True,  # Verify connections before using
    connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
)

# Create synchronous session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# Base class for models
Base = declarative_base()


def get_db() -> Session:
    """
    Dependency for getting database session
    
    Yields:
        Session: Database session
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        session.close()


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized")


def close_db():
    """Close database connections"""
    engine.dispose()
    logger.info("Database connections closed")
