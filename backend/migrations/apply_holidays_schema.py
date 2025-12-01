#!/usr/bin/env python3
"""
Apply new holidays schema - CLEAN BREAK

Drops old trading_holidays table and creates new one with exchange_group.
Old data is lost - reimport from CSV after running this.

Usage:
    python3 migrations/apply_holidays_schema.py
"""
import sys
import sqlite3
from pathlib import Path


def apply_migration():
    """Drop old table and create new one with exchange_group"""
    
    print("="*70)
    print("APPLYING HOLIDAYS SCHEMA MIGRATION")
    print("="*70)
    print("⚠️  This will DELETE all existing holiday data!")
    print("You will need to reimport from CSV after this.")
    print("")
    
    # Find database
    backend_dir = Path(__file__).parent.parent
    db_path = backend_dir / "data" / "trading_app.db"
    
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return False
    
    print(f"Database: {db_path}")
    
    # Read SQL file
    sql_file = Path(__file__).parent / "drop_and_recreate_holidays_table.sql"
    if not sql_file.exists():
        print(f"❌ SQL file not found: {sql_file}")
        return False
    
    sql_script = sql_file.read_text()
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Execute as multiple statements (filter out comments and empty lines)
        statements = []
        for line in sql_script.split('\n'):
            line = line.strip()
            if line and not line.startswith('--'):
                statements.append(line)
        
        # Join and split by semicolon
        full_sql = ' '.join(statements)
        for statement in full_sql.split(';'):
            statement = statement.strip()
            if statement:
                print(f"Executing: {statement[:80]}...")
                cursor.execute(statement)
        
        conn.commit()
        conn.close()
        
        print("")
        print("✅ Migration complete!")
        print("")
        print("Next steps:")
        print("  1. ./start_cli.sh")
        print("  2. time holidays import data/holidays/2025_Holiday_Schedule.csv")
        print("  3. time holidays 2025  (verify import)")
        print("")
        
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        print("Database may be in inconsistent state!")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = apply_migration()
    sys.exit(0 if success else 1)
