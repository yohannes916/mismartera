"""
Migration: Add Exchange Support to Trading Holidays
Migrates from single-market to multi-exchange holiday schema
"""
import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path

from app.models.database import AsyncSessionLocal
from app.logger import logger


async def migrate_holidays():
    """Migrate trading_holidays table to include exchange column"""
    
    db_path = Path("data/trading_app.db")
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        return False
    
    logger.info("Starting holiday migration to multi-exchange schema...")
    
    # Use synchronous sqlite3 for schema migration
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # 1. Check current schema
        cursor.execute("PRAGMA table_info(trading_holidays)")
        columns = {row[1] for row in cursor.fetchall()}
        
        if 'exchange' in columns:
            logger.info("Migration already complete - exchange column exists")
            return True
        
        # 2. Backup old data
        logger.info("Backing up existing holiday data...")
        cursor.execute("SELECT * FROM trading_holidays")
        old_holidays = cursor.fetchall()
        logger.info(f"Found {len(old_holidays)} existing holidays")
        
        # 3. Create new table with exchange column
        logger.info("Creating new table schema with exchange support...")
        cursor.execute("""
            CREATE TABLE trading_holidays_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                exchange VARCHAR(50) NOT NULL DEFAULT 'NYSE',
                holiday_name VARCHAR(200) NOT NULL,
                notes VARCHAR(500),
                is_closed BOOLEAN DEFAULT 1,
                early_close_time TIME,
                created_at DATE DEFAULT CURRENT_DATE,
                UNIQUE(date, exchange)
            )
        """)
        
        cursor.execute("CREATE INDEX idx_holidays_date_exchange ON trading_holidays_new(date, exchange)")
        cursor.execute("CREATE INDEX idx_holidays_exchange ON trading_holidays_new(exchange)")
        
        # 4. Migrate old data (assign all to NYSE by default)
        logger.info("Migrating old holidays to new schema...")
        if old_holidays:
            # Old schema: id, date, holiday_name, notes, is_closed, early_close_time, created_at
            for row in old_holidays:
                cursor.execute("""
                    INSERT INTO trading_holidays_new 
                    (id, date, exchange, holiday_name, notes, is_closed, early_close_time, created_at)
                    VALUES (?, ?, 'NYSE', ?, ?, ?, ?, ?)
                """, row)
            logger.info(f"Migrated {len(old_holidays)} holidays to new schema")
        
        # 5. Drop old table and rename new one
        logger.info("Replacing old table with new schema...")
        cursor.execute("DROP TABLE trading_holidays")
        cursor.execute("ALTER TABLE trading_holidays_new RENAME TO trading_holidays")
        
        conn.commit()
        logger.info("✓ Migration completed successfully!")
        
        # 6. Verify migration
        cursor.execute("SELECT COUNT(*) FROM trading_holidays WHERE exchange = 'NYSE'")
        count = cursor.fetchone()[0]
        logger.info(f"✓ Verified: {count} holidays now in multi-exchange schema")
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


async def main():
    """Run migration"""
    print("\n" + "="*70)
    print("HOLIDAY SCHEMA MIGRATION: Single-Market → Multi-Exchange")
    print("="*70)
    print("\nThis will:")
    print("  1. Backup existing holiday data")
    print("  2. Create new schema with exchange column")
    print("  3. Migrate all holidays (assigned to NYSE)")
    print("  4. Drop old table and use new schema")
    print("\n" + "="*70 + "\n")
    
    response = input("Continue with migration? (yes/no): ")
    if response.lower() != 'yes':
        print("Migration cancelled")
        return
    
    success = await migrate_holidays()
    
    if success:
        print("\n✓ Migration completed successfully!")
        print("\nNext steps:")
        print("  1. Import holidays for other exchanges using: time import-holidays <file>")
        print("  2. Update code to use exchange-aware holiday queries")
    else:
        print("\n✗ Migration failed - check logs for details")


if __name__ == "__main__":
    asyncio.run(main())
