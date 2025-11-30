# Parquet Storage Architecture Design

## File Organization

```
data/parquet/
├── bars/
│   ├── 1s/
│   │   ├── AAPL.2024-01.parquet    # January 1s bars
│   │   ├── AAPL.2024-02.parquet    # February 1s bars
│   │   └── AAPL.2024-12.parquet
│   ├── 1m/
│   │   ├── AAPL.2024-01.parquet
│   │   └── RIVN.2024-01.parquet
│   └── 1d/
│       └── AAPL.2024.parquet       # Full year for daily (smaller)
└── quotes/
    ├── AAPL.2024-01.parquet        # Aggregated: 1 per second
    └── AAPL.2024-02.parquet
```

## File Naming Convention

```
Format: {SYMBOL}.{YEAR}-{MONTH}.parquet
Examples:
  - AAPL.2024-01.parquet    # January 2024
  - AAPL.2024-12.parquet    # December 2024
  - TSLA.2023-06.parquet    # June 2023
  
For daily bars (yearly):
  - AAPL.2024.parquet       # Full year
```

## Schema Definitions

### 1s Bars (from Ticks/Trades)
```python
{
    'symbol': str,          # e.g., 'AAPL'
    'timestamp': datetime,  # UTC timezone
    'open': float,
    'high': float,
    'low': float,
    'close': float,
    'volume': int,
    'trade_count': int      # Number of trades in this second
}
```

### 1m Bars
```python
{
    'symbol': str,
    'timestamp': datetime,  # UTC timezone
    'open': float,
    'high': float,
    'low': float,
    'close': float,
    'volume': int,
    'vwap': float          # Optional
}
```

### 1d Bars
```python
{
    'symbol': str,
    'timestamp': datetime,  # UTC timezone (date at 00:00)
    'open': float,
    'high': float,
    'low': float,
    'close': float,
    'volume': int
}
```

### Quotes (Aggregated 1 per second)
```python
{
    'symbol': str,
    'timestamp': datetime,  # UTC timezone
    'bid_price': float,
    'bid_size': int,
    'ask_price': float,
    'ask_size': int,
    'spread': float,        # ask - bid (for filtering)
    'exchange': str         # Optional
}
```

## Data Processing Pipeline

### Download Ticks → 1s Bars
```python
# Alpaca returns ticks with microsecond timestamps
ticks = [
    {'timestamp': '2024-01-15T14:30:00.123456Z', 'price': 150.25, 'size': 100},
    {'timestamp': '2024-01-15T14:30:00.234567Z', 'price': 150.26, 'size': 50},
    {'timestamp': '2024-01-15T14:30:00.876543Z', 'price': 150.24, 'size': 75},
    {'timestamp': '2024-01-15T14:30:01.123456Z', 'price': 150.27, 'size': 200},
    ...
]

# Aggregate to 1s bars
bars_1s = aggregate_ticks_to_1s(ticks)
# Result:
[
    {
        'timestamp': '2024-01-15T14:30:00Z',  # Rounded to second
        'open': 150.25,    # First tick
        'high': 150.26,    # Max price
        'low': 150.24,     # Min price
        'close': 150.24,   # Last tick
        'volume': 225,     # Sum of sizes
        'trade_count': 3   # Number of ticks
    },
    {
        'timestamp': '2024-01-15T14:30:01Z',
        'open': 150.27,
        'high': 150.27,
        'low': 150.27,
        'close': 150.27,
        'volume': 200,
        'trade_count': 1
    },
    ...
]
```

### Download Quotes → 1 Quote per Second
```python
# Alpaca returns quotes with microsecond timestamps
quotes = [
    {'timestamp': '14:30:00.123', 'bid': 150.25, 'ask': 150.27, 'bid_size': 100, 'ask_size': 200},
    {'timestamp': '14:30:00.456', 'bid': 150.26, 'ask': 150.28, 'bid_size': 150, 'ask_size': 100},
    {'timestamp': '14:30:00.789', 'bid': 150.25, 'ask': 150.26, 'bid_size': 200, 'ask_size': 150},
    {'timestamp': '14:30:01.123', 'bid': 150.27, 'ask': 150.29, 'bid_size': 100, 'ask_size': 200},
    ...
]

# Keep 1 per second (tightest spread)
quotes_aggregated = aggregate_quotes_by_second(quotes)
# Result:
[
    {
        'timestamp': '2024-01-15T14:30:00Z',
        'bid_price': 150.25,
        'ask_price': 150.26,
        'bid_size': 200,
        'ask_size': 150,
        'spread': 0.01,     # Tightest spread: 150.26 - 150.25
        'exchange': 'V'
    },
    {
        'timestamp': '2024-01-15T14:30:01Z',
        'bid_price': 150.27,
        'ask_price': 150.29,
        'bid_size': 100,
        'ask_size': 200,
        'spread': 0.02,
        'exchange': 'V'
    },
    ...
]
```

## Timezone Handling

### Storage: Always UTC
```python
# All timestamps stored in Parquet are UTC
timestamp: pd.Timestamp('2024-01-15 14:30:00+00:00')  # UTC
```

### Conversion Pipeline
```python
# 1. Alpaca returns UTC (with 'Z' suffix)
alpaca_time = "2024-01-15T14:30:00.123456Z"

# 2. Parse to UTC datetime
dt_utc = datetime.fromisoformat(alpaca_time.replace('Z', '+00:00'))

# 3. Store in Parquet as UTC
parquet.write(df)  # timestamp column is UTC

# 4. Query and convert to ET for display
df = parquet.read(file)
df['timestamp_et'] = df['timestamp'].dt.tz_convert('America/New_York')

# 5. Filter by market hours (in ET)
market_open = time(9, 30)
market_close = time(16, 0)
df = df[df['timestamp_et'].dt.time.between(market_open, market_close)]
```

### After-Hours Data
```python
# Keep ALL data (including pre-market and after-hours)
# Filter at query time if needed

# Example: Full day (pre-market + regular + after-hours)
04:00 ET (09:00 UTC) - Pre-market start
09:30 ET (14:30 UTC) - Regular market open
16:00 ET (21:00 UTC) - Regular market close
20:00 ET (01:00 UTC+1) - After-hours end

# Stored: All timestamps from 09:00 UTC to 01:00 UTC next day
# Query: Filter by time range as needed
```

## Query Patterns

### Load Full Month
```python
import pandas as pd

df = pd.read_parquet('data/parquet/bars/1m/AAPL.2024-01.parquet')
# Returns full month: ~9000 bars (23 trading days × ~390 bars/day)
```

### Load Date Range (Multiple Months)
```python
# Load Q1 2024
files = [
    'data/parquet/bars/1m/AAPL.2024-01.parquet',
    'data/parquet/bars/1m/AAPL.2024-02.parquet',
    'data/parquet/bars/1m/AAPL.2024-03.parquet',
]
df = pd.concat([pd.read_parquet(f) for f in files])
```

### Load Specific Date
```python
df = pd.read_parquet('data/parquet/bars/1m/AAPL.2024-01.parquet')
df = df[df['timestamp'].dt.date == date(2024, 1, 15)]
```

### Load with DuckDB (Fast SQL)
```python
import duckdb

# Query multiple months with SQL
result = duckdb.query("""
    SELECT * FROM 'data/parquet/bars/1m/AAPL.2024-*.parquet'
    WHERE timestamp >= '2024-01-15 14:30:00'
    AND timestamp <= '2024-03-15 21:00:00'
    ORDER BY timestamp
""").df()
```

## Performance Estimates

### File Sizes (Monthly)
```
1s bars:  ~2M bars/month  × 48 bytes = ~100 MB compressed
1m bars:  ~9K bars/month  × 48 bytes = ~500 KB compressed
1d bars:  ~250 bars/year  × 48 bytes = ~12 KB compressed
Quotes:   ~140K/month     × 56 bytes = ~8 MB compressed
```

### Read Performance
```
1s bars full month:  ~100 MB → Load in 0.5-1 sec
1m bars full month:  ~500 KB → Load in 0.05 sec
1d bars full year:   ~12 KB  → Load in 0.01 sec
Quotes full month:   ~8 MB   → Load in 0.2 sec
```

### Write Performance
```
1s bars:  2M bars → Write in 2-5 sec (vs 20+ min in database)
Quotes:   140K quotes → Write in 0.5-1 sec (vs 2+ min in database)
```

## Compression

```python
# Use ZSTD compression (best balance of speed and size)
df.to_parquet(
    path,
    compression='zstd',
    compression_level=3,  # 1-22, default 3 is good balance
    index=False
)
```

### Compression Comparison
```
None (uncompressed):  1.0x size,  fastest read/write
Snappy:               0.5x size,  very fast
ZSTD (level 3):       0.3x size,  fast (recommended)
ZSTD (level 19):      0.15x size, slow
GZIP:                 0.25x size, slow
```

## Migration Strategy

### Phase 1: New Imports to Parquet
```python
# All new data goes to Parquet
data import-api 1s AAPL 2024-11-01 2024-11-30
# → Writes to data/parquet/bars/1s/AAPL.2024-11.parquet

# Database remains for existing data
```

### Phase 2: Export Existing Database to Parquet
```python
# One-time export
data export-to-parquet --all
# Reads from database, writes to Parquet files

# OR export specific ranges
data export-to-parquet --symbol AAPL --year 2024
```

### Phase 3: Remove Database Dependency
```python
# Update session_data and backtest engine to read from Parquet
# Database becomes optional (only for real-time tracking)
```

## Advantages

✅ **100x faster writes** - No SQL overhead  
✅ **10x faster reads** - Columnar format, read only needed columns  
✅ **90% smaller** - ZSTD compression  
✅ **No database locks** - Concurrent reads without blocking  
✅ **Easy backup** - Just copy files  
✅ **Portable** - Works with Pandas, Polars, DuckDB, Spark  
✅ **Scalable** - Handle billions of rows easily  

## Disadvantages

❌ **No transactions** - Can't rollback partial writes  
❌ **No referential integrity** - File-based, not relational  
❌ **Updates expensive** - Must rewrite entire file  
❌ **File management** - Need to organize/cleanup old files  

## Best Practices

1. **One file per month** - Balance between too many files and files too large
2. **UTC timestamps** - Avoid DST issues
3. **ZSTD compression** - Best balance of speed and size
4. **Sorted by timestamp** - Faster queries with filters
5. **Include symbol in file** - Even though it's in filename (redundancy)
6. **Metadata in filename** - Easy to identify without opening
7. **Validate on write** - Ensure no duplicates, sorted, correct timezone

---

**Next Step:** Implement Parquet storage manager and update import functions
