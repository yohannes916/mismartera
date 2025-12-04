#!/usr/bin/env python3
"""Test script to verify 1d bar loading"""

from datetime import date, datetime, time
from app.managers.data_manager.parquet_storage import parquet_storage
from app.managers.data_manager.api import DataManager
from app.managers.system_manager.api import get_system_manager
from app.models.database import SessionLocal

# Initialize system manager
system_mgr = get_system_manager()
system_mgr.load_config("session_configs/example_session.json")

# Test 1: Check if 1d bars exist in parquet
print("=" * 60)
print("TEST 1: Checking 1d bars in Parquet storage")
print("=" * 60)

symbol = "RIVN"
start_date = date(2025, 6, 17)  # ~10 trading days before 2025-07-02
end_date = date(2025, 7, 1)      # Day before session

df = parquet_storage.read_bars(
    "1d",
    symbol,
    start_date=start_date,
    end_date=end_date
)

print(f"\n1d bars for {symbol} from {start_date} to {end_date}:")
print(f"  Rows loaded: {len(df)}")
if not df.empty:
    print(f"  First bar: {df.iloc[0]['timestamp']} - close=${df.iloc[0]['close']}")
    print(f"  Last bar: {df.iloc[-1]['timestamp']} - close=${df.iloc[-1]['close']}")
    print(f"\n  All dates:")
    for idx, row in df.iterrows():
        print(f"    {row['timestamp'].date()}: close=${row['close']:.2f}, vol={int(row['volume']):,}")
else:
    print("  ❌ No data found!")

# Test 2: Load via DataManager.get_bars()
print("\n" + "=" * 60)
print("TEST 2: Loading 1d bars via DataManager")
print("=" * 60)

data_mgr = system_mgr.get_data_manager()
start_dt = datetime.combine(start_date, time(0, 0))
end_dt = datetime.combine(end_date, time(23, 59, 59))

with SessionLocal() as session:
    bars = data_mgr.get_bars(
        session=session,
        symbol=symbol,
        start=start_dt,
        end=end_dt,
        interval="1d"
    )

print(f"\n1d bars loaded via DataManager:")
print(f"  Count: {len(bars)}")
if bars:
    print(f"  First: {bars[0].timestamp.date()} - ${bars[0].close}")
    print(f"  Last: {bars[-1].timestamp.date()} - ${bars[-1].close}")
else:
    print("  ❌ No bars returned!")

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
