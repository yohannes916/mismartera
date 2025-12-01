#!/usr/bin/env python3
"""Drop legacy MarketData and QuoteData tables from database.

Market data is now stored exclusively in Parquet files.
This script removes the old SQL tables that are no longer used.

Run with: python scripts/drop_legacy_market_data_tables.py
"""

from sqlalchemy import text, inspect
from app.models.database import SessionLocal, engine
from app.logger import logger


def drop_legacy_tables():
    """Drop MarketData and QuoteData tables if they exist."""
    
    # Tables to drop
    legacy_tables = ['market_data', 'quotes']
    
    # Check which tables exist
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    tables_to_drop = [t for t in legacy_tables if t in existing_tables]
    
    if not tables_to_drop:
        logger.info("✓ No legacy market data tables found - database is clean")
        print("✓ No legacy tables to drop")
        return
    
    print(f"\nFound {len(tables_to_drop)} legacy table(s) to drop:")
    for table in tables_to_drop:
        print(f"  - {table}")
    
    # Confirm with user
    print("\n⚠️  WARNING: This will permanently delete these tables and all their data!")
    print("Market data should now be in Parquet files only.")
    response = input("\nProceed with dropping tables? (yes/no): ").strip().lower()
    
    if response != 'yes':
        print("Aborted - no changes made")
        return
    
    # Drop tables
    with SessionLocal() as session:
        for table in tables_to_drop:
            try:
                logger.info(f"Dropping table: {table}")
                session.execute(text(f"DROP TABLE IF EXISTS {table}"))
                session.commit()
                print(f"✓ Dropped table: {table}")
            except Exception as e:
                logger.error(f"Failed to drop table {table}: {e}")
                print(f"✗ Failed to drop {table}: {e}")
                session.rollback()
    
    print("\n✓ Cleanup complete!")
    print("\nMarket data storage:")
    print("  - SQL Database: User accounts, analysis, trading sessions")
    print("  - Parquet Files: ALL market data (bars, ticks, quotes)")


if __name__ == "__main__":
    print("=" * 60)
    print("Legacy Market Data Tables Cleanup")
    print("=" * 60)
    drop_legacy_tables()
