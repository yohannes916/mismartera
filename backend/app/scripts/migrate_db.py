"""
Database Migration Script
Adds new columns to existing tables or recreates them if needed
"""
import asyncio
from sqlalchemy import text
from app.models.database import engine, Base
from app.models import schemas  # Import to register all models
from app.logger import logger


async def check_table_exists(table_name: str) -> bool:
    """Check if a table exists"""
    async with engine.begin() as conn:
        result = await conn.execute(
            text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        )
        return result.fetchone() is not None


async def check_column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    async with engine.begin() as conn:
        result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result.fetchall()]
        return column_name in columns


async def add_column_if_missing(table_name: str, column_name: str, column_type: str, default_value: str = "NULL"):
    """Add a column to a table if it doesn't exist"""
    async with engine.begin() as conn:
        exists = await check_column_exists(table_name, column_name)
        if not exists:
            logger.info(f"Adding column {column_name} to {table_name}")
            await conn.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type} DEFAULT {default_value}")
            )
            logger.success(f"✓ Added column {column_name} to {table_name}")
        else:
            logger.info(f"Column {column_name} already exists in {table_name}")


async def migrate_market_data_table():
    """Migrate market_data table to add new columns"""
    logger.info("Checking market_data table...")
    
    table_exists = await check_table_exists("market_data")
    
    if not table_exists:
        logger.info("market_data table doesn't exist, will be created")
        return
    
    # Add source column
    await add_column_if_missing(
        "market_data",
        "source",
        "VARCHAR(50)",
        "'csv'"
    )
    
    # Add imported_at column
    await add_column_if_missing(
        "market_data",
        "imported_at",
        "DATETIME",
        "CURRENT_TIMESTAMP"
    )
    
    logger.success("✓ market_data table migration complete")


async def recreate_all_tables():
    """Drop and recreate all tables (use with caution - data loss!)"""
    logger.warning("⚠ This will DROP ALL TABLES and recreate them!")
    logger.warning("⚠ ALL DATA WILL BE LOST!")
    
    async with engine.begin() as conn:
        # Drop all tables
        await conn.run_sync(Base.metadata.drop_all)
        logger.info("✓ Dropped all tables")
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        logger.success("✓ Created all tables with new schema")


async def run_migration(recreate: bool = False):
    """
    Run database migration
    
    Args:
        recreate: If True, drop and recreate all tables (DATA LOSS!)
    """
    logger.info("Starting database migration...")
    
    try:
        if recreate:
            await recreate_all_tables()
        else:
            # Run specific migrations
            await migrate_market_data_table()
            
            logger.success("✓ Database migration complete!")
            logger.info("All tables are up to date")
    
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    import sys
    
    # Check for --recreate flag
    recreate = "--recreate" in sys.argv
    
    if recreate:
        print("\n⚠️  WARNING: You are about to DROP ALL TABLES and recreate them!")
        print("⚠️  This will DELETE ALL DATA in the database!")
        response = input("\nType 'YES' to confirm: ")
        if response != "YES":
            print("Aborted.")
            sys.exit(0)
    
    # Run migration
    asyncio.run(run_migration(recreate=recreate))
