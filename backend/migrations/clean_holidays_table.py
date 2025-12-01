#!/usr/bin/env python3
"""
Clean all holidays from trading_holidays table

This removes ALL holidays so you can reimport correctly with exchange groups.

Usage:
    python3 migrations/clean_holidays_table.py
"""
import sys
import sqlite3
from pathlib import Path


def clean_holidays():
    """Delete all holidays from table"""
    
    print("="*70)
    print("CLEANING HOLIDAYS TABLE")
    print("="*70)
    print("⚠️  This will DELETE ALL holidays from the database!")
    print("")
    
    # Find database
    backend_dir = Path(__file__).parent.parent
    db_path = backend_dir / "data" / "trading_app.db"
    
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return False
    
    print(f"Database: {db_path}")
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Count existing
        cursor.execute("SELECT COUNT(*) FROM trading_holidays")
        count = cursor.fetchone()[0]
        print(f"Found {count} holidays to delete")
        
        if count == 0:
            print("Table is already empty")
            conn.close()
            return True
        
        # Delete all
        print("Deleting all holidays...")
        cursor.execute("DELETE FROM trading_holidays")
        conn.commit()
        conn.close()
        
        print("")
        print("✅ All holidays deleted!")
        print("")
        print("Next steps:")
        print("  1. ./start_cli.sh")
        print("  2. time holidays import data/holidays/2025_Holiday_Schedule.csv")
        print("  3. time holidays 2025  (verify)")
        print("")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = clean_holidays()
    sys.exit(0 if success else 1)
