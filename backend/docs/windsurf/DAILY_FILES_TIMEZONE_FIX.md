# Daily Files: Timezone Handling & Data Migration

**Date**: December 7, 2025  
**Status**: ✅ **CRITICAL FIX APPLIED**

---

## Summary

Fixed critical timezone issue in daily file grouping and clarified data migration strategy for existing monthly parquet files.

---

## **1. Critical Timezone Fix** ⚠️

### **The Problem**

Original implementation grouped bars by **UTC day**, but trading days are defined by **exchange timezone** (Eastern Time for US stocks).

**Example of the bug**:
```
Trading Day: July 15, 2025 (Eastern Time)
Extended hours: 04:00 ET - 20:00 ET

UTC conversion (EDT = UTC-4):
- 04:00 ET → 08:00 UTC (July 15) ✓
- 09:30 ET → 13:30 UTC (July 15) ✓  
- 16:00 ET → 20:00 UTC (July 15) ✓
- 19:00 ET → 23:00 UTC (July 15) ✓
- 20:00 ET → 00:00 UTC (July 16) ❌ NEXT DAY!

Result (WRONG):
- bars/1s/AAPL/2025/07/15.parquet (most bars)
- bars/1s/AAPL/2025/07/16.parquet (evening bars 20:00-20:00 ET)

ONE trading day split across TWO files!
```

### **The Fix**

**Group by exchange timezone day, NOT UTC day**:

```python
# BEFORE (WRONG) ❌
df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
df['day'] = df['timestamp'].dt.day  # UTC day!

# AFTER (CORRECT) ✅
df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')  # Storage in UTC
df_local = df['timestamp'].dt.tz_convert(exchange_tz)   # But group by ET
df['day'] = df_local.dt.day                              # ET day!
```

**Result (CORRECT)**:
```
Trading Day: July 15, 2025 (Eastern Time)
All bars from 04:00-20:00 ET → bars/1s/AAPL/2025/07/15.parquet

Even though some UTC timestamps are on July 16, they're still July 15 ET.
```

---

## **2. Timezone Architecture**

### **Clear Separation of Concerns**

```
┌─────────────────────────────────────────────────────────┐
│ REST OF SYSTEM (Exchange Timezone ONLY)                │
│ - Session data: Eastern Time                            │
│ - Trading hours: Eastern Time                           │
│ - Bar timestamps: Eastern Time                          │
│ - No timezone conversion happens here                   │
└─────────────────────────────────────────────────────────┘
                           ↕
         ONLY DataManager/ParquetStorage do conversion
                           ↕
┌─────────────────────────────────────────────────────────┐
│ PARQUET STORAGE (UTC)                                   │
│ - Files store UTC timestamps                            │
│ - But grouped by exchange timezone day                  │
│ - On read: Convert UTC → Exchange Timezone             │
│ - On write: Convert Exchange Timezone → UTC            │
└─────────────────────────────────────────────────────────┘
```

### **Key Principles**

1. **Storage Layer (Parquet)**:
   - ✅ Store timestamps in UTC (universal standard)
   - ✅ Group files by exchange timezone day (trading day alignment)
   - ✅ Handle all timezone conversions

2. **Application Layer (Rest of System)**:
   - ✅ Work exclusively in exchange timezone (no conversion)
   - ✅ Receive data already converted from DataManager
   - ✅ Never deal with UTC or timezones directly

3. **Boundary (DataManager/ParquetStorage)**:
   - ✅ Convert UTC → Exchange Timezone on read
   - ✅ Convert Exchange Timezone → UTC on write
   - ✅ Ensure day boundaries respect exchange timezone

---

## **3. Write Operation Flow**

### **Step-by-Step**

```python
# 1. Bars come from system (Exchange Timezone)
bars = [
    {"timestamp": "2025-07-15 09:30:00-04:00", ...},  # 09:30 EDT
    {"timestamp": "2025-07-15 16:00:00-04:00", ...},  # 16:00 EDT
    {"timestamp": "2025-07-15 19:00:00-04:00", ...},  # 19:00 EDT (after hours)
]

# 2. ParquetStorage.write_bars() receives them
df = pd.DataFrame(bars)

# 3. Convert to UTC for storage
df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
# Results:
#   09:30 EDT → 13:30 UTC (July 15)
#   16:00 EDT → 20:00 UTC (July 15)
#   19:00 EDT → 23:00 UTC (July 15)

# 4. Extract date components in EXCHANGE TIMEZONE
exchange_tz = self._get_system_timezone()  # "America/New_York"
df_local = df['timestamp'].dt.tz_convert(exchange_tz)

df['year'] = df_local.dt.year   # 2025 (all same)
df['month'] = df_local.dt.month  # 7 (all same)
df['day'] = df_local.dt.day      # 15 (all same) ✓

# 5. Group by (year, month, day) - Exchange Timezone
grouped = df.groupby(['year', 'month', 'day'])

# 6. Write to file
# All bars go to: bars/1s/AAPL/2025/07/15.parquet
# File contains UTC timestamps but represents July 15 ET trading day
```

### **Why This Works**

- **File path** based on exchange timezone day (July 15 ET)
- **File content** stores UTC timestamps (universal)
- **One trading day** = one file (session-aligned)

---

## **4. Read Operation Flow**

### **Step-by-Step**

```python
# 1. System requests data for July 15, 2025 (Exchange Timezone)
start = datetime(2025, 7, 15, 0, 0, tzinfo=ZoneInfo("America/New_York"))
end = datetime(2025, 7, 15, 23, 59, tzinfo=ZoneInfo("America/New_York"))

# 2. ParquetStorage.read_bars() determines files needed
# Iterates through days in exchange timezone
files = []
current = start.date()  # July 15, 2025
while current <= end.date():
    file_path = get_file_path("1s", "AAPL", 2025, 7, 15)
    files.append(file_path)
    # Found: bars/1s/AAPL/2025/07/15.parquet

# 3. Read parquet file
df = pd.read_parquet(file_path)
# Timestamps are UTC:
#   13:30 UTC (July 15)
#   20:00 UTC (July 15)
#   23:00 UTC (July 15)

# 4. Convert to exchange timezone
exchange_tz = self._get_system_timezone()
df['timestamp'] = df['timestamp'].dt.tz_convert(exchange_tz)
# Results:
#   13:30 UTC → 09:30 EDT
#   20:00 UTC → 16:00 EDT
#   23:00 UTC → 19:00 EDT

# 5. Return to system (Exchange Timezone)
# System receives bars with EDT timestamps
```

---

## **5. Data Migration Strategy**

### **Current State**

**Existing monthly files** (if any):
```
bars/1s/AAPL/2025/07.parquet  (UTC storage, monthly grouping)
bars/1m/AAPL/2025/07.parquet  (UTC storage, monthly grouping)
```

**New daily files**:
```
bars/1s/AAPL/2025/07/15.parquet  (UTC storage, daily grouping by ET day)
bars/1m/AAPL/2025/07/15.parquet  (UTC storage, daily grouping by ET day)
```

### **Impact**

- ❌ **Existing monthly files will NOT be read** (clean break)
- ❌ **Historical data effectively dropped** unless migrated
- ✅ **New data writes to daily files** with correct timezone handling

### **Migration Script** (Optional)

If you want to preserve existing monthly data:

```python
#!/usr/bin/env python3
"""Migrate monthly parquet files to daily files with correct timezone handling."""

import pandas as pd
from pathlib import Path
from zoneinfo import ZoneInfo

def migrate_monthly_to_daily(
    monthly_file: Path,
    interval: str,
    symbol: str,
    exchange_tz: str = "America/New_York"
):
    """Migrate one monthly file to daily files.
    
    Args:
        monthly_file: Path to old monthly file
        interval: Interval string (e.g., "1s", "1m")
        symbol: Stock symbol
        exchange_tz: Exchange timezone
    """
    print(f"Migrating {monthly_file}...")
    
    # Read old monthly file (UTC timestamps)
    df = pd.read_parquet(monthly_file)
    
    if df.empty:
        print(f"  Empty file, skipping")
        return
    
    # Ensure UTC timezone
    if df['timestamp'].dt.tz is None:
        df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
    else:
        df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
    
    # Group by EXCHANGE TIMEZONE day
    df_local = df['timestamp'].dt.tz_convert(exchange_tz)
    df['year'] = df_local.dt.year
    df['month'] = df_local.dt.month
    df['day'] = df_local.dt.day
    
    grouped = df.groupby(['year', 'month', 'day'])
    
    print(f"  Found {len(grouped)} trading days")
    
    # Write each day to new daily file
    for (year, month, day), group_df in grouped:
        # Construct new path
        output_dir = Path(f"data/parquet/US_EQUITY/bars/{interval}/{symbol}/{year}/{month:02d}")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{day:02d}.parquet"
        
        # Drop helper columns
        group_df = group_df.drop(columns=['year', 'month', 'day'])
        
        # Write to daily file
        group_df.to_parquet(output_file, compression='zstd', index=False)
        
        print(f"  Wrote {len(group_df)} bars to {output_file}")
    
    print(f"  Migration complete!")


# Example usage
if __name__ == "__main__":
    # Migrate all monthly files for a symbol
    symbol = "AAPL"
    intervals = ["1s", "1m", "5m", "15m"]
    
    for interval in intervals:
        monthly_dir = Path(f"data/parquet/US_EQUITY/bars/{interval}/{symbol}")
        
        if not monthly_dir.exists():
            continue
        
        for monthly_file in monthly_dir.glob("*.parquet"):
            # Skip if it's already a directory structure (yearly files)
            if monthly_file.is_file():
                migrate_monthly_to_daily(monthly_file, interval, symbol)
```

### **Migration Checklist**

If migrating existing data:

1. ✅ **Backup existing monthly files** (just in case)
2. ✅ **Run migration script** for each symbol/interval
3. ✅ **Verify daily files** created correctly
4. ✅ **Spot check** a few days to ensure correct grouping
5. ✅ **Test read operations** to ensure data loads correctly
6. ✅ **Delete old monthly files** once verified

---

## **6. Verification**

### **Test Timezone Handling**

```python
def test_timezone_grouping():
    """Verify bars from one ET day go into one file."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    # Create bars spanning UTC midnight but same ET day
    bars = [
        {
            "symbol": "AAPL",
            "timestamp": datetime(2025, 7, 15, 13, 30, tzinfo=ZoneInfo("America/New_York")),  # 09:30 ET
            "open": 150.0, "high": 151.0, "low": 149.0, "close": 150.5, "volume": 1000
        },
        {
            "symbol": "AAPL",
            "timestamp": datetime(2025, 7, 15, 20, 0, tzinfo=ZoneInfo("America/New_York")),  # 16:00 ET
            "open": 150.5, "high": 152.0, "low": 150.0, "close": 151.5, "volume": 2000
        },
        {
            "symbol": "AAPL",
            "timestamp": datetime(2025, 7, 15, 23, 0, tzinfo=ZoneInfo("America/New_York")),  # 19:00 ET (after hours)
            "open": 151.5, "high": 152.0, "low": 151.0, "close": 151.8, "volume": 500
        },
    ]
    
    # Write bars
    storage = ParquetStorage()
    count, files = storage.write_bars(bars, "1s", "AAPL")
    
    # Verify: All bars in ONE file (same ET day)
    assert len(files) == 1
    assert "2025/07/15.parquet" in str(files[0])
    
    # Read back and verify
    df = storage.read_bars("1s", "AAPL",
                          datetime(2025, 7, 15, 0, 0, tzinfo=ZoneInfo("America/New_York")),
                          datetime(2025, 7, 15, 23, 59, tzinfo=ZoneInfo("America/New_York")))
    
    # All bars returned, in ET timezone
    assert len(df) == 3
    assert df['timestamp'].dt.tz.zone == "America/New_York"
    assert all(df['timestamp'].dt.date == datetime(2025, 7, 15).date())
    
    print("✅ Timezone handling verified!")
```

---

## **7. Summary**

### **What Changed**

1. ✅ **Fixed timezone grouping** - Group by exchange timezone day, not UTC day
2. ✅ **Clarified architecture** - Storage layer handles ALL timezone conversion
3. ✅ **Documented migration** - Optional script to convert monthly → daily

### **Key Principles**

1. **Storage**: UTC timestamps, exchange timezone day grouping
2. **Application**: Exchange timezone only, no conversion
3. **Boundary**: DataManager/ParquetStorage handle all conversion

### **Data Migration**

- Existing monthly files NOT automatically migrated
- Optional migration script provided
- Clean break - new data uses daily files

### **Files Modified**

1. **`parquet_storage.py`**:
   - Fixed grouping to use exchange timezone day
   - Added detailed comments explaining timezone handling

2. **Documentation**:
   - `DAILY_FILES_TIMEZONE_FIX.md` (this file)
   - `DAILY_FILE_STORAGE.md` (updated with timezone note)

---

## **Status**: ✅ **CRITICAL FIX APPLIED**

Timezone handling now correct. One trading day (exchange timezone) = one file, even though stored timestamps are UTC.
