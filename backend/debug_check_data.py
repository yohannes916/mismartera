#!/usr/bin/env python3
"""
Debug script to check data availability and gaps for specific symbols and date.
Step 1 of debugging session_data issues.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo
from app.managers.data_manager.parquet_storage import parquet_storage


def check_data_availability():
    """Check data for AAPL and RIVN on 2025-07-02"""
    
    # Target date
    target_date = datetime(2025, 7, 2, tzinfo=ZoneInfo("America/New_York"))
    market_open = datetime.combine(target_date.date(), time(9, 30), tzinfo=ZoneInfo("America/New_York"))
    market_close = datetime.combine(target_date.date(), time(16, 0), tzinfo=ZoneInfo("America/New_York"))
    
    symbols = ["AAPL", "RIVN"]
    
    print("=" * 80)
    print(f"CHECKING DATA AVAILABILITY FOR {target_date.date()}")
    print("=" * 80)
    
    for symbol in symbols:
        print(f"\n{'='*80}")
        print(f"SYMBOL: {symbol}")
        print(f"{'='*80}")
        
        try:
            # Read all 1m bars for the symbol
            df = parquet_storage.read_bars('1m', symbol)
            
            if df.empty:
                print(f"❌ NO DATA FOUND for {symbol}")
                continue
            
            # Filter to target date
            # Timestamps are already timezone-aware in parquet (UTC), convert to ET
            df['timestamp'] = df['timestamp'].dt.tz_convert('America/New_York')
            day_df = df[(df['timestamp'] >= market_open) & (df['timestamp'] < market_close)]
            
            total_bars = len(day_df)
            print(f"Total 1m bars: {total_bars}")
            print(f"Expected bars: 390 (full trading day 09:30-16:00)")
            
            if total_bars == 0:
                print(f"❌ NO DATA for {target_date.date()}")
                continue
            
            # Get first and last bar timestamps
            first_bar = day_df['timestamp'].min()
            last_bar = day_df['timestamp'].max()
            
            print(f"First bar: {first_bar.strftime('%H:%M:%S')}")
            print(f"Last bar:  {last_bar.strftime('%H:%M:%S')}")
            
            # Check for gaps
            timestamps = day_df['timestamp'].sort_values().tolist()
            gaps = []
            for i in range(len(timestamps) - 1):
                current = timestamps[i]
                next_ts = timestamps[i + 1]
                diff_seconds = (next_ts - current).total_seconds()
                
                # Should be 60 seconds for consecutive 1m bars
                if diff_seconds > 60:
                    missing_minutes = int(diff_seconds / 60) - 1
                    gaps.append({
                        'after': current.strftime('%H:%M:%S'),
                        'before': next_ts.strftime('%H:%M:%S'),
                        'missing_bars': missing_minutes
                    })
            
            if gaps:
                print(f"\n❌ FOUND {len(gaps)} GAP(S):")
                for gap in gaps[:10]:  # Show first 10 gaps
                    print(f"   Gap after {gap['after']} → {gap['before']} "
                          f"(missing {gap['missing_bars']} bars)")
                if len(gaps) > 10:
                    print(f"   ... and {len(gaps) - 10} more gaps")
            else:
                print("\n✅ NO GAPS - Data is continuous")
            
            # Check specific timestamps mentioned in the issue
            if symbol == "AAPL":
                # Check for 09:38 bar (reported missing between 09:37 and 09:39)
                ts_0938 = datetime(2025, 7, 2, 9, 38, tzinfo=ZoneInfo("America/New_York"))
                has_0938 = any(day_df['timestamp'] == ts_0938)
                print(f"\n09:38 bar exists: {'✅ YES' if has_0938 else '❌ NO (MISSING)'}")
            
            if symbol == "RIVN":
                # Check for bars between 09:37 and 09:58
                ts_start = datetime(2025, 7, 2, 9, 37, tzinfo=ZoneInfo("America/New_York"))
                ts_end = datetime(2025, 7, 2, 9, 58, tzinfo=ZoneInfo("America/New_York"))
                bars_in_range = day_df[(day_df['timestamp'] >= ts_start) & (day_df['timestamp'] <= ts_end)]
                bars_0937_0958 = len(bars_in_range)
                print(f"\nBars between 09:37-09:58: {bars_0937_0958} (expected: 22)")
                if bars_0937_0958 < 22:
                    print(f"   ❌ MISSING {22 - bars_0937_0958} bars in this range")
        
        except FileNotFoundError:
            print(f"❌ NO PARQUET DATA FOUND for {symbol}")
        except Exception as e:
            print(f"❌ ERROR reading {symbol}: {e}")
    
    print("\n" + "="*80)
    print("DATABASE CHECK COMPLETE")
    print("="*80)


if __name__ == "__main__":
    check_data_availability()
