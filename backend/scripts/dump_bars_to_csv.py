#!/usr/bin/env python3
"""
Dump raw bar data from database to CSV for inspection.
Includes timezone information to diagnose potential timezone issues.
"""
import sys
import csv
from datetime import date
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.managers.data_manager.parquet_storage import parquet_storage
import pandas as pd


def dump_bars_to_csv(symbol: str, interval: str, target_date: date, output_file: str):
    """
    Dump all bars for a symbol/interval/date to CSV with timezone info.
    
    Args:
        symbol: Stock symbol (e.g., "AAPL")
        interval: Bar interval (e.g., "1m")
        target_date: Date to query
        output_file: Output CSV path
    """
    print(f"Querying {symbol} {interval} bars for {target_date}...")
    
    # Read from parquet (raw data)
    df = pd.read_parquet(
        f'data/parquet/US_EQUITY/bars/{interval}/{symbol}/{target_date.year:04d}/{target_date.month:02d}.parquet'
    )
    
    # Filter to target date
    df['date'] = pd.to_datetime(df['timestamp']).dt.date
    df_day = df[df['date'] == target_date].copy()
    
    print(f"Found {len(df_day)} bars in database")
    
    # Add timezone info columns
    df_day['timestamp_str'] = df_day['timestamp'].astype(str)
    df_day['timestamp_utc'] = pd.to_datetime(df_day['timestamp']).dt.tz_convert('UTC')
    df_day['timestamp_et'] = pd.to_datetime(df_day['timestamp']).dt.tz_convert('America/New_York')
    df_day['hour_et'] = df_day['timestamp_et'].dt.hour
    df_day['minute_et'] = df_day['timestamp_et'].dt.minute
    df_day['time_et'] = df_day['timestamp_et'].dt.time
    
    # Check for duplicates
    duplicates = df_day[df_day.duplicated(subset=['timestamp'], keep=False)]
    if len(duplicates) > 0:
        print(f"⚠️  WARNING: Found {len(duplicates)} duplicate timestamps!")
        print("\nDuplicate timestamps:")
        for ts in duplicates['timestamp'].unique():
            count = len(df_day[df_day['timestamp'] == ts])
            print(f"  - {ts}: {count} bars")
    else:
        print("✅ No duplicate timestamps found")
    
    # Check for timezone inconsistencies
    unique_tzs = df_day['timestamp'].apply(lambda x: str(x.tzinfo)).unique()
    print(f"\nTimezone info in data: {unique_tzs}")
    
    # Sort by timestamp
    df_day = df_day.sort_values('timestamp')
    
    # Export to CSV
    output_columns = [
        'timestamp', 'timestamp_str', 'timestamp_utc', 'timestamp_et', 
        'time_et', 'hour_et', 'minute_et',
        'open', 'high', 'low', 'close', 'volume'
    ]
    df_day[output_columns].to_csv(output_file, index=False)
    
    print(f"\n✅ Exported {len(df_day)} bars to {output_file}")
    
    # Show time range summary
    if len(df_day) > 0:
        first_time = df_day.iloc[0]['time_et']
        last_time = df_day.iloc[-1]['time_et']
        print(f"\nTime range (ET): {first_time} - {last_time}")
        
        # Count bars by hour
        print("\nBars per hour (ET):")
        hour_counts = df_day.groupby('hour_et').size()
        for hour, count in hour_counts.items():
            hour_str = f"{hour:02d}:00"
            if 4 <= hour < 9:
                label = "pre-market"
            elif 9 <= hour < 16:
                label = "regular" if hour > 9 or (hour == 9 and df_day[df_day['hour_et'] == hour]['minute_et'].min() >= 30) else "pre-market"
            else:
                label = "after-market"
            print(f"  {hour_str}: {count} bars ({label})")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Dump bar data to CSV for inspection")
    parser.add_argument("symbol", help="Stock symbol (e.g., AAPL)")
    parser.add_argument("--interval", default="1m", help="Bar interval (default: 1m)")
    parser.add_argument("--date", help="Date (YYYY-MM-DD, default: 2025-07-02)")
    parser.add_argument("--output", help="Output CSV file (default: bars_dump_{symbol}_{date}.csv)")
    
    args = parser.parse_args()
    
    # Parse date
    if args.date:
        target_date = date.fromisoformat(args.date)
    else:
        target_date = date(2025, 7, 2)
    
    # Generate output filename
    if args.output:
        output_file = args.output
    else:
        output_file = f"bars_dump_{args.symbol}_{target_date}.csv"
    
    dump_bars_to_csv(args.symbol, args.interval, target_date, output_file)
