# Bulk Data Import Optimization

## Problem
Importing millions of records (e.g., 9.3M quotes) was extremely slow because:
1. **One-by-one insertion**: Each record was inserted individually
2. **Single transaction**: All 9M+ operations in one transaction
3. **No progress feedback**: Appeared stuck with no visibility
4. **Memory pressure**: Holding millions of records in memory

## Solutions Implemented

### 1. Batched Processing ✅
**File:** `/app/managers/data_manager/repositories/quote_repo.py`

- Split insertions into batches of 10,000 records
- Commit after each batch (932 batches for 9.3M quotes)
- Progress logging per batch
- Reduced memory pressure

**Benefits:**
- **Visibility**: See progress in real-time
- **Resume-ability**: If it fails, partial data is saved
- **Memory**: Process in chunks instead of all at once
- **Speed**: ~10-100x faster than single transaction

**Example Output:**
```log
Processing 9317913 quotes in 932 batches of 10000
[DB] Batch 1/932: Inserting quotes 0-10000 (10000 items)
[DB] ✓ Batch 1/932 complete (10000/9317913 total)
[DB] Batch 2/932: Inserting quotes 10000-20000 (10000 items)
[DB] ✓ Batch 2/932 complete (20000/9317913 total)
...
```

## Additional Optimizations to Consider

### 2. Skip Duplicates Check (Optional)
If you're importing fresh data with no duplicates:

```python
# In quote_repo.py, add skip_duplicates parameter
async def bulk_create_quotes(
    session: AsyncSession,
    quotes: List[dict],
    batch_size: int = 10000,
    skip_duplicates: bool = False,  # NEW
):
    if skip_duplicates:
        # Use simple INSERT instead of ON CONFLICT
        stmt = insert(QuoteData).values(batch)
    else:
        # Current upsert logic
        ...
```

**Speed gain:** ~3-5x faster (no duplicate checking)

### 3. Disable Indexes During Import (Advanced)

For very large imports, temporarily disable indexes:

```python
# Before import
session.execute("DROP INDEX IF EXISTS idx_quotes_symbol_timestamp")

# Import data (fast!)
bulk_create_quotes(session, quotes)

# After import
session.execute("CREATE INDEX idx_quotes_symbol_timestamp ON quotes(symbol, timestamp)")
```

**Speed gain:** ~5-10x faster for initial import  
**Downside:** Risky if interrupted

### 4. Parquet File Storage (Alternative Approach)

For historical data that's rarely updated, consider file-based storage:

```python
# Instead of database
import pyarrow.parquet as pq
import pandas as pd

# Save quotes to Parquet (compressed, columnar)
df = pd.DataFrame(quotes)
df.to_parquet(f'data/quotes/{symbol}_{start_date}_{end_date}.parquet', 
              compression='zstd',
              index=False)

# Read quotes when needed
df = pd.read_parquet(f'data/quotes/{symbol}_{start_date}_{end_date}.parquet')
quotes = df.to_dict('records')
```

**Benefits:**
- **Speed**: 100x faster writes, 10x faster reads
- **Size**: 80-90% smaller (compressed)
- **Query**: Use DuckDB or Polars for fast SQL queries
- **Cost**: Much cheaper storage

**Downside:**
- Not a relational database
- No ACID guarantees
- File management needed

### 5. PostgreSQL COPY Command (If Using PostgreSQL)

SQLite doesn't support this, but PostgreSQL has ultra-fast bulk loading:

```python
import io
import csv

# Create CSV in memory
output = io.StringIO()
writer = csv.writer(output)
for quote in quotes:
    writer.writerow([quote['symbol'], quote['timestamp'], ...])
output.seek(0)

# Ultra-fast COPY
session.execute(
    "COPY quotes (symbol, timestamp, bid_price, ...) FROM STDIN WITH CSV"
)
# Stream CSV data
...
```

**Speed gain:** ~50-100x faster than INSERT

### 6. Aggregate Quote Data

Do you really need every single quote? Consider alternatives:

**Option A: Sample quotes**
```python
# Keep only every 10th quote
quotes_sampled = quotes[::10]  # 930K instead of 9.3M
```

**Option B: Time-based aggregation**
```python
# Keep only best bid/ask per second
quotes_aggregated = aggregate_quotes_by_second(quotes)
```

**Option C: NBBO only**
```python
# Keep only National Best Bid/Offer changes
quotes_nbbo = filter_nbbo_changes(quotes)
```

**Reduction:** 90-99% fewer records, still useful for most backtesting

## Recommended Approach

### For Historical Data (Rare Updates)
**Use Parquet files:**
- Store raw data in compressed Parquet
- Load into database only for active backtest periods
- Keep last 30 days in database, rest in files

### For Active Data (Frequent Updates)
**Use batched database with optimization:**
- Batch size: 10,000-50,000 records
- Index optimization: Drop during import, recreate after
- Skip duplicates if possible
- Consider quote aggregation

## Performance Comparison

| Method | 9.3M Quotes | Notes |
|--------|-------------|-------|
| Original (one-by-one) | ~2-4 hours | Too slow |
| Batched (10K) | ~5-15 min | ✅ Implemented |
| Batched + no indexes | ~2-5 min | Risky |
| Parquet file | ~10-30 sec | ✅ Recommended for historical |
| PostgreSQL COPY | ~1-2 min | If switching from SQLite |

## Configuration

Add to `settings.py`:

```python
# Bulk import optimization
BULK_IMPORT_BATCH_SIZE: int = 10000  # Quotes per batch
BULK_IMPORT_SKIP_DUPLICATES: bool = False  # Faster if True
HISTORICAL_DATA_FORMAT: str = "database"  # or "parquet"
HISTORICAL_DATA_PATH: str = "data/historical"
```

## Usage

### Current (Database + Batching)
```bash
# Will now show progress every 10K records
data import-api quotes AAPL 2024-01-01 2024-12-31
```

**Output:**
```
[Alpaca] ✓ Final: Fetched 9317913 quotes from Alpaca for AAPL
[DB] Inserting 9317913 quotes into database for AAPL...
Processing 9317913 quotes in 932 batches of 10000
[DB] Batch 1/932: Inserting quotes 0-10000 (10000 items)
[DB] ✓ Batch 1/932 complete (10000/9317913 total)
[DB] Batch 2/932: Inserting quotes 10000-20000 (10000 items)
...
[DB] ✓ Successfully inserted 9317913 quotes for AAPL
```

### Future (Parquet-based)
```bash
# Much faster - saves to Parquet file
data import-api quotes AAPL 2024-01-01 2024-12-31 --format parquet

# Load into database only for specific date range (when needed)
data load-historical quotes AAPL 2024-11-01 2024-11-30
```

## Monitoring

Watch progress in real-time:
```bash
# In terminal 1
data import-api quotes AAPL 2024-01-01 2024-12-31

# In terminal 2 - watch progress
tail -f data/logs/app.log | grep "\[DB\] Batch"
```

## Next Steps

1. ✅ **Immediate**: Use batched approach (already implemented)
2. 🔄 **Short-term**: Add batch size configuration
3. 🔄 **Medium-term**: Implement Parquet storage for historical data
4. 🔄 **Long-term**: Hybrid approach (Parquet + database)

---

**Status:** Batching implemented ✅  
**Estimated improvement:** 10-100x faster than original
**Test command:** `data import-api quotes AAPL 2024-11-01 2024-11-30` (smaller range first)
