#!/usr/bin/env python3
"""Fix timezone information in parquet files.

Problem: Timestamps are stored with UTC timezone (+00:00) but actually represent
market time (America/New_York). This script:
1. Reads all parquet files
2. Reinterprets timestamps as market time
3. Converts to true UTC
4. Writes back to parquet

Run this script to fix existing data files.
"""
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import pytz

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.logger import logger
from app.managers.data_manager.parquet_storage import ParquetStorage


def fix_parquet_file(file_path: Path, market_tz: pytz.timezone, dry_run: bool = False) -> tuple[int, bool]:
    """Fix timezone information in a single parquet file.
    
    Args:
        file_path: Path to parquet file
        market_tz: Market timezone (e.g., America/New_York)
        dry_run: If True, don't write changes
        
    Returns:
        (rows_processed, had_changes): Count of rows and whether changes were made
    """
    try:
        # Read parquet file
        df = pd.read_parquet(file_path)
        
        if 'timestamp' not in df.columns:
            logger.warning(f"No timestamp column in {file_path}, skipping")
            return 0, False
        
        row_count = len(df)
        
        # Check if timestamps are already correct
        # If they're timezone-naive or have +00:00, they need fixing
        sample_ts = df['timestamp'].iloc[0]
        
        if sample_ts.tzinfo is None:
            logger.info(f"{file_path.name}: Timestamps are naive, adding market timezone")
            # Naive timestamps - assume they're in market time
            df['timestamp'] = df['timestamp'].dt.tz_localize(market_tz)
            # Convert to UTC
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
            had_changes = True
            
        elif str(sample_ts.tzinfo) == 'UTC':
            logger.info(f"{file_path.name}: Timestamps marked as UTC, reinterpreting as market time")
            # Remove wrong UTC timezone
            df['timestamp'] = df['timestamp'].dt.tz_localize(None)
            # Interpret as market time
            df['timestamp'] = df['timestamp'].dt.tz_localize(market_tz)
            # Convert to true UTC
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
            had_changes = True
            
        else:
            logger.info(f"{file_path.name}: Timestamps already have timezone {sample_ts.tzinfo}, checking if correct")
            # Already has timezone, check if it's market timezone
            if str(sample_ts.tzinfo) != str(market_tz):
                logger.info(f"{file_path.name}: Converting from {sample_ts.tzinfo} to UTC")
                df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
                had_changes = True
            else:
                logger.info(f"{file_path.name}: Already in correct timezone, converting to UTC")
                df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
                had_changes = True
        
        if not dry_run and had_changes:
            # Backup original file
            backup_path = file_path.with_suffix('.parquet.backup')
            if not backup_path.exists():
                import shutil
                shutil.copy2(file_path, backup_path)
                logger.info(f"Created backup: {backup_path.name}")
            
            # Write fixed data
            df.to_parquet(
                file_path,
                compression='zstd',
                index=False,
                engine='pyarrow',
            )
            logger.success(f"✓ Fixed {row_count} rows in {file_path.name}")
        elif dry_run and had_changes:
            logger.info(f"[DRY RUN] Would fix {row_count} rows in {file_path.name}")
        else:
            logger.info(f"No changes needed for {file_path.name}")
        
        return row_count, had_changes
        
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 0, False


def fix_all_parquet_files(
    base_path: str = "data/parquet",
    exchange_group: str = "US_EQUITY",
    market_tz_name: str = "America/New_York",
    dry_run: bool = False
):
    """Fix timezone information in all parquet files.
    
    Args:
        base_path: Base directory for parquet files
        exchange_group: Exchange group (e.g., 'US_EQUITY')
        market_tz_name: Market timezone name
        dry_run: If True, don't write changes (just report what would be done)
    """
    base_path = Path(base_path)
    market_tz = pytz.timezone(market_tz_name)
    
    logger.info("=" * 80)
    logger.info("PARQUET TIMEZONE FIX SCRIPT")
    logger.info("=" * 80)
    logger.info(f"Base path: {base_path}")
    logger.info(f"Exchange group: {exchange_group}")
    logger.info(f"Market timezone: {market_tz_name}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 80)
    
    # Find all parquet files
    search_path = base_path / exchange_group
    if not search_path.exists():
        logger.error(f"Path does not exist: {search_path}")
        return
    
    parquet_files = sorted(search_path.rglob("*.parquet"))
    
    # Filter out backup files
    parquet_files = [f for f in parquet_files if not f.name.endswith('.backup')]
    
    if not parquet_files:
        logger.warning(f"No parquet files found in {search_path}")
        return
    
    logger.info(f"Found {len(parquet_files)} parquet files to process")
    logger.info("")
    
    # Process each file
    total_rows = 0
    files_changed = 0
    files_processed = 0
    
    for file_path in parquet_files:
        logger.info(f"Processing: {file_path.relative_to(base_path)}")
        rows, changed = fix_parquet_file(file_path, market_tz, dry_run)
        total_rows += rows
        files_processed += 1
        if changed:
            files_changed += 1
        logger.info("")
    
    # Summary
    logger.info("=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Files processed: {files_processed}")
    logger.info(f"Files changed: {files_changed}")
    logger.info(f"Total rows processed: {total_rows:,}")
    
    if dry_run:
        logger.info("")
        logger.info("This was a DRY RUN. No files were modified.")
        logger.info("Run with --apply to actually fix the files.")
    else:
        logger.info("")
        logger.success("✓ All files have been fixed!")
        logger.info("Backup files (.parquet.backup) have been created.")
        logger.info("You can delete them once you've verified the data is correct.")
    
    logger.info("=" * 80)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Fix timezone information in parquet files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (see what would be fixed)
  python fix_parquet_timezones.py --dry-run
  
  # Actually fix the files
  python fix_parquet_timezones.py --apply
  
  # Fix specific exchange group
  python fix_parquet_timezones.py --apply --exchange US_EQUITY
  
  # Use different market timezone
  python fix_parquet_timezones.py --apply --timezone America/Chicago
"""
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Actually apply the fixes (default is dry-run)'
    )
    
    parser.add_argument(
        '--base-path',
        default='data/parquet',
        help='Base path for parquet files (default: data/parquet)'
    )
    
    parser.add_argument(
        '--exchange',
        default='US_EQUITY',
        help='Exchange group (default: US_EQUITY)'
    )
    
    parser.add_argument(
        '--timezone',
        default='America/New_York',
        help='Market timezone (default: America/New_York)'
    )
    
    args = parser.parse_args()
    
    # Default is dry-run unless --apply is specified
    dry_run = not args.apply
    
    if dry_run and not args.dry_run:
        logger.warning("No --apply flag specified, running in DRY RUN mode")
        logger.warning("Use --apply to actually fix the files")
        logger.info("")
    
    fix_all_parquet_files(
        base_path=args.base_path,
        exchange_group=args.exchange,
        market_tz_name=args.timezone,
        dry_run=dry_run
    )


if __name__ == '__main__':
    main()
