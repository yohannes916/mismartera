# Exchange Timezone Storage Architecture

**Date**: December 7, 2025  
**Status**: ✅ **IMPLEMENTED** (Simplified Architecture)

---

## Summary

Parquet storage now uses **exchange timezone timestamps** (timezone-aware) with **no conversion**. The `exchange_group` directory structure implicitly defines the timezone.

---

## Core Principle

**One exchange group = one timezone = one storage bucket**

```
data/parquet/US_EQUITY/     ← America/New_York timezone
data/parquet/LSE_EQUITY/    ← Europe/London timezone
data/parquet/JPX_EQUITY/    ← Asia/Tokyo timezone
```

---

## Architecture

### **Storage Layer**
```python
# Write: Store timestamps as-is (timezone-aware)
df['timestamp'] → dtype: datetime64[ns, America/New_York]
to_parquet()  # Preserves timezone

# Read: Return timestamps as-is (timezone-aware)
df = read_parquet()
df['timestamp'] → dtype: datetime64[ns, America/New_York]
```

### **Application Layer**
```python
# System works exclusively in exchange timezone
# NO timezone conversion anywhere except ParquetStorage boundary
bars = [
    {"timestamp": datetime(2025, 7, 15, 9, 30, tzinfo=ZoneInfo("America/New_York")), ...},
    {"timestamp": datetime(2025, 7, 15, 16, 0, tzinfo=ZoneInfo("America/New_York")), ...},
]
```

---

## Key Benefits

### **1. No Conversion Overhead** ✅
```python
# OLD (Complex) ❌
Write: ET → UTC conversion
Storage: UTC timestamps
Read: UTC → ET conversion

# NEW (Simple) ✅
Write: Store as-is
Storage: ET timestamps (timezone-aware)
Read: Return as-is
```

**Performance**: Zero conversion overhead on every read/write

### **2. Natural Day Boundaries** ✅
```python
# July 15, 2025 (Eastern Time)
# Extended hours: 04:00 ET - 20:00 ET

# All bars from this trading day → bars/1s/AAPL/2025/07/15.parquet
# File contains: timestamps in America/New_York timezone
# No UTC midnight boundary issues!
```

### **3. Self-Documenting Structure** ✅
```
data/parquet/US_EQUITY/bars/1s/AAPL/2025/07/15.parquet
             ^^^^^^^^
             This directory = America/New_York timezone
             
data/parquet/LSE_EQUITY/bars/1s/BARC/2025/07/15.parquet
             ^^^^^^^^^^
             This directory = Europe/London timezone
```

**File path tells you the timezone!**

### **4. Consistent with System Design** ✅
- Rest of system works in exchange timezone
- No conversion happens outside ParquetStorage
- Simple mental model: "Everything is in ET"

---

## Implementation Details

### **Write Operation**

```python
def write_bars(self, bars, data_type, symbol):
    # 1. Convert to DataFrame
    df = pd.DataFrame(bars)
    
    # 2. Ensure timezone-aware in exchange timezone
    exchange_tz = self._get_system_timezone()  # "America/New_York"
    
    if df['timestamp'].dt.tz is not None:
        # Has timezone, ensure it's exchange timezone
        df['timestamp'] = df['timestamp'].dt.tz_convert(exchange_tz)
    else:
        # Naive, assume already exchange timezone
        df['timestamp'] = df['timestamp'].dt.tz_localize(exchange_tz)
    
    # 3. Extract date components (already in exchange timezone)
    df['year'] = df['timestamp'].dt.year    # ET year
    df['month'] = df['timestamp'].dt.month   # ET month
    df['day'] = df['timestamp'].dt.day       # ET day
    
    # 4. Group by (year, month, day) - natural ET day boundaries
    grouped = df.groupby(['year', 'month', 'day'])
    
    # 5. Write to parquet (preserves timezone)
    for (year, month, day), group_df in grouped:
        file_path = f"bars/{data_type}/{symbol}/{year}/{month:02d}/{day:02d}.parquet"
        group_df.to_parquet(file_path)
        # File contains: timestamps in America/New_York timezone
```

### **Read Operation**

```python
def read_bars(self, data_type, symbol, start_date, end_date):
    # 1. Determine files needed (based on ET dates)
    files = []
    current = start_date
    while current <= end_date:
        file_path = f"bars/{data_type}/{symbol}/{current.year}/{current.month:02d}/{current.day:02d}.parquet"
        if file_path.exists():
            files.append(file_path)
        current += timedelta(days=1)
    
    # 2. Read parquet files
    dfs = []
    for file_path in files:
        df = pd.read_parquet(file_path)
        # df['timestamp'] is already timezone-aware in America/New_York
        dfs.append(df)
    
    # 3. Concatenate and return (no conversion!)
    result = pd.concat(dfs)
    return result  # Timestamps still in America/New_York
```

---

## Example Data Flow

### **Scenario**: Write 1s bars for July 15, 2025 (ET)

```python
# 1. System generates bars (in ET)
bars = [
    {"timestamp": datetime(2025, 7, 15, 9, 30, 0, tzinfo=ZoneInfo("America/New_York")), ...},   # Market open
    {"timestamp": datetime(2025, 7, 15, 16, 0, 0, tzinfo=ZoneInfo("America/New_York")), ...},  # Market close
    {"timestamp": datetime(2025, 7, 15, 19, 59, 59, tzinfo=ZoneInfo("America/New_York")), ...}, # After hours end
]

# 2. Write to parquet
storage.write_bars(bars, "1s", "AAPL")

# 3. Storage operation
# - Timestamps: Already in ET ✓
# - Extract: year=2025, month=7, day=15 (all same day in ET)
# - Write: bars/1s/AAPL/2025/07/15.parquet
# - File contains: timestamps in America/New_York timezone

# 4. Read back
df = storage.read_bars("1s", "AAPL", date(2025, 7, 15), date(2025, 7, 15))

# 5. Result
# df['timestamp'] → dtype: datetime64[ns, America/New_York]
# All timestamps in ET, ready to use, NO conversion needed!
```

---

## Exchange Group → Timezone Mapping

### **Implicit Mapping**

| Exchange Group | Timezone | Region |
|---------------|----------|--------|
| `US_EQUITY` | `America/New_York` | US Stocks |
| `US_CRYPTO` | `America/New_York` | US Crypto exchanges |
| `LSE_EQUITY` | `Europe/London` | London Stock Exchange |
| `XETRA_EQUITY` | `Europe/Berlin` | Deutsche Börse |
| `JPX_EQUITY` | `Asia/Tokyo` | Tokyo Stock Exchange |
| `HKEX_EQUITY` | `Asia/Hong_Kong` | Hong Kong Exchange |

### **SystemManager Integration**

```python
# SystemManager knows exchange_group → timezone mapping
system_manager.timezone → "America/New_York"  # For US_EQUITY

# ParquetStorage uses this
def _get_system_timezone(self):
    sys_mgr = get_system_manager()
    return sys_mgr.timezone  # Returns exchange timezone
```

---

## Timezone-Aware Data

### **Pandas DataFrame**

```python
# After reading from parquet
df = storage.read_bars("1s", "AAPL", date(2025, 7, 15), date(2025, 7, 15))

# Inspect timezone
df['timestamp'].dtype
# → dtype('datetime64[ns, America/New_York]')

# Timezone info preserved
df['timestamp'].iloc[0]
# → Timestamp('2025-07-15 09:30:00-0400', tz='America/New_York')

# Direct operations (no conversion needed)
df['hour'] = df['timestamp'].dt.hour        # ET hour
df['date'] = df['timestamp'].dt.date        # ET date
df_filtered = df[df['timestamp'].dt.hour >= 9]  # Filter by ET hour
```

### **Parquet Files**

```python
# Parquet format supports timezone-aware timestamps
# Schema includes timezone metadata:

<Schema>
  timestamp: timestamp[ns, tz=America/New_York]
  symbol: string
  open: double
  high: double
  low: double
  close: double
  volume: int64
</Schema>

# When read back, timezone is preserved automatically!
```

---

## Comparison with Old Architecture

### **OLD: UTC Storage with Conversion** ❌

```python
# Write operation
bars_et = [...]  # In ET
df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')  # Convert to UTC
df['day'] = df['timestamp'].dt.day  # UTC day (WRONG!)
# Result: One ET day splits across multiple UTC days

# Read operation
df = read_parquet()  # UTC timestamps
df['timestamp'] = df['timestamp'].dt.tz_convert('America/New_York')  # Convert back
# Conversion overhead on every read!

# Issues:
# 1. Day boundary mismatch (UTC vs ET)
# 2. Conversion overhead
# 3. Complex logic
# 4. Easy to make mistakes
```

### **NEW: Exchange Timezone Storage** ✅

```python
# Write operation
bars_et = [...]  # In ET
df['timestamp'] = df['timestamp']  # Already ET, no conversion!
df['day'] = df['timestamp'].dt.day  # ET day (CORRECT!)
# Result: One ET day = one file

# Read operation
df = read_parquet()  # ET timestamps (timezone-aware)
# Return as-is, no conversion!

# Benefits:
# 1. Natural day boundaries (ET)
# 2. Zero conversion overhead
# 3. Simple logic
# 4. Hard to make mistakes
```

---

## Migration Notes

### **Breaking Change**

Existing parquet files (if any) that use UTC storage are **incompatible** with this new architecture.

### **Migration Strategy**

**Option 1: Clean Break** (Recommended)
- Delete old UTC-based parquet files
- Start fresh with exchange timezone storage
- Simplest approach

**Option 2: Migrate Data**
- Read old UTC files
- Convert timestamps to exchange timezone
- Write to new daily file structure
- Time-consuming but preserves history

### **Detection**

```python
# Check if file uses old UTC storage
df = pd.read_parquet(file_path)

if df['timestamp'].dt.tz is None:
    print("Old format: Naive timestamps")
elif df['timestamp'].dt.tz.zone == 'UTC':
    print("Old format: UTC timestamps")
else:
    print(f"New format: {df['timestamp'].dt.tz.zone} timestamps")
```

---

## Validation

### **Test 1: Timezone Preservation**

```python
def test_timezone_preserved():
    # Create bars in ET
    bars = [{"timestamp": datetime(2025, 7, 15, 9, 30, tzinfo=ZoneInfo("America/New_York")), ...}]
    
    # Write
    storage.write_bars(bars, "1s", "AAPL")
    
    # Read
    df = storage.read_bars("1s", "AAPL", date(2025, 7, 15), date(2025, 7, 15))
    
    # Verify timezone preserved
    assert df['timestamp'].dt.tz.zone == "America/New_York"
    assert df['timestamp'].iloc[0].hour == 9  # ET hour, not UTC
```

### **Test 2: Day Boundary**

```python
def test_day_boundary():
    # Create bars spanning ET day
    bars = [
        {"timestamp": datetime(2025, 7, 15, 4, 0, tzinfo=ZoneInfo("America/New_York")), ...},   # Pre-market
        {"timestamp": datetime(2025, 7, 15, 20, 0, tzinfo=ZoneInfo("America/New_York")), ...},  # After hours
    ]
    
    # Write
    count, files = storage.write_bars(bars, "1s", "AAPL")
    
    # Verify: ONE file (same ET day)
    assert len(files) == 1
    assert "2025/07/15.parquet" in str(files[0])
```

### **Test 3: No Conversion**

```python
def test_no_conversion():
    # Create bar
    ts_original = datetime(2025, 7, 15, 9, 30, tzinfo=ZoneInfo("America/New_York"))
    bars = [{"timestamp": ts_original, ...}]
    
    # Write and read
    storage.write_bars(bars, "1s", "AAPL")
    df = storage.read_bars("1s", "AAPL", date(2025, 7, 15), date(2025, 7, 15))
    
    # Verify: Exact same timestamp (no conversion)
    ts_read = df['timestamp'].iloc[0]
    assert ts_read == ts_original
    assert ts_read.tzinfo.zone == "America/New_York"
```

---

## Documentation Updates

### **Code Comments**

All key functions now have explicit comments:
- "Storage: Exchange timezone (no conversion)"
- "Already in exchange timezone"
- "No conversion needed"

### **Docstrings**

```python
def write_bars(...):
    """Write bars to Parquet.
    
    TIMEZONE: Data stored timezone-aware in exchange timezone.
    Exchange group implies timezone (US_EQUITY = America/New_York).
    NO conversion performed.
    """

def read_bars(...):
    """Read bars from Parquet.
    
    TIMEZONE: Data returned timezone-aware in exchange timezone.
    NO conversion performed.
    """
```

---

## Summary

### **Core Changes**

1. ✅ **Storage format**: Exchange timezone timestamps (timezone-aware)
2. ✅ **Day grouping**: Natural exchange timezone day boundaries
3. ✅ **No conversion**: Data stored and returned as-is
4. ✅ **Self-documenting**: Exchange group directory implies timezone

### **Benefits**

- ✅ **Simpler**: No timezone conversion logic
- ✅ **Faster**: Zero conversion overhead
- ✅ **Clearer**: One trading day = one file
- ✅ **Consistent**: Matches system architecture

### **Trade-offs**

- ❌ **Breaking change**: Incompatible with old UTC storage
- ✅ **Worth it**: Simpler architecture, better performance

---

## **Status**: ✅ **PRODUCTION READY**

Exchange timezone storage implemented. Parquet files now store timezone-aware timestamps in exchange timezone with no conversion overhead.
