# Parquet Test Investigation - December 9, 2025

## Issue Summary
All 7 Stream Requirements with Parquet tests are failing because test data is written to wrong file paths.

## Root Cause: **BUG IN TEST HELPER**

### The Problem

The backdoor write function `write_test_bars_parquet()` creates files at **incorrect paths** that don't match what `ParquetStorage` expects to read.

### Path Mismatch

**Test writes to (WRONG):**
```
/tmp/.../US_EQUITY/bars/1m/AAPL/2025/07.parquet
                                    ^^^^^^^^^ Month-level file
```

**ParquetStorage expects (CORRECT):**
```
/tmp/.../US_EQUITY/bars/1m/AAPL/2025/07/02.parquet
                                    ^^^^^^^ Day-level file (DAILY granularity)
```

### Why This Happens

#### 1. Storage Strategy
From `/app/managers/data_manager/interval_storage.py`:
- 1m intervals use `FileGranularity.DAILY`
- DAILY granularity means: **one file per day**
- Path structure: `bars/<interval>/<SYMBOL>/<YEAR>/<MONTH>/<DAY>.parquet`

#### 2. Test Helper (Incorrect)
From `/tests/e2e/test_stream_requirements_with_parquet.py` lines 120-124:
```python
# Intraday: YYYY/MM.parquet (WRONG!)
file_path = (
    base_path / exchange_group / "bars" / interval / symbol /
    f"{start_dt.year}" / f"{start_dt.month:02d}.parquet"
)
```

This creates **monthly files** instead of **daily files**.

#### 3. Read Logic (Correct)
From `/app/managers/data_manager/parquet_storage.py` line 764:
```python
file_path = self.get_file_path(data_type, symbol, year, month, day)
```

It correctly looks for: `bars/1m/AAPL/2025/07/02.parquet`

### The Flow

1. Test writes 390 bars → `AAPL/2025/07.parquet` ✅ (file created)
2. Test reads via data_checker → looks for `AAPL/2025/07/02.parquet` ❌ (file not found)
3. Returns 0 bars → Test fails

---

## Detailed Analysis

### Test Structure

All 7 failing tests follow this pattern:
1. **Setup**: Write bars using `write_test_bars_parquet()` (backdoor)
2. **Execute**: Create data_checker, query data
3. **Assert**: Expect N bars, get 0 bars

### Affected Tests

1. `TestParquetDataChecker::test_create_data_checker` - Expects 390, gets 0
2. `TestParquetDataChecker::test_multiple_symbols` - Expects 390, gets 0
3. `TestCoordinatorWithParquet::test_validation_success_with_data` - Expects valid, gets invalid
4. `TestCoordinatorWithParquet::test_validation_with_sparse_data` - Expects valid, gets invalid
5. `TestDifferentIntervals::test_1s_interval_requirement` - Expects valid, gets invalid
6. `TestRealWorldScenarios::test_multi_day_backtest` - Expects valid, gets invalid
7. `TestRealWorldScenarios::test_partial_date_range_passes` - Expects valid, gets invalid

All fail because written data can't be found/read.

### Why Test Passed Before

This test likely worked when:
1. File structure was different (monthly files for intraday)
2. Storage strategy had different granularity rules
3. Or test was never run / always skipped

The current `IntervalStorageStrategy` uses **daily files for sub-daily intervals** (1s, 1m, etc.) which is correct for:
- Performance (smaller files)
- Scalability (easier to manage)
- Query efficiency (less data to scan)

---

## Classification

✅ **BUG IN TEST** - Not a real bug in production code

### Evidence

1. **ParquetStorage is correct**
   - Uses proper granularity (DAILY for 1m)
   - Path construction matches storage strategy
   - Read logic is consistent

2. **Storage strategy is correct**
   - DAILY granularity for sub-daily intervals (1s, 1m)
   - YEARLY granularity for daily+ intervals (1d, 1w)
   - Documented in `interval_storage.py`

3. **Test helper is incorrect**
   - Hardcodes monthly files for intraday data
   - Doesn't use storage strategy API
   - Comment says "Intraday: YYYY/MM.parquet" which is wrong

---

## Fix Required

### Fix Test Helper Function

**File**: `/tests/e2e/test_stream_requirements_with_parquet.py`

**Lines**: 87-166 (`write_test_bars_parquet` function)

**Change**: Update path construction to match actual storage strategy

**Current (WRONG)**:
```python
def write_test_bars_parquet(...):
    # Create bar directory structure
    if interval == "1d":
        # Daily: YYYY.parquet
        file_path = (
            base_path / exchange_group / "bars" / interval / symbol /
            f"{start_dt.year}.parquet"
        )
    else:
        # Intraday: YYYY/MM.parquet (WRONG!)
        file_path = (
            base_path / exchange_group / "bars" / interval / symbol /
            f"{start_dt.year}" / f"{start_dt.month:02d}.parquet"
        )
```

**Fixed (CORRECT)**:
```python
def write_test_bars_parquet(...):
    # Use IntervalStorageStrategy to get correct path
    from app.managers.data_manager.interval_storage import IntervalStorageStrategy
    
    storage_strategy = IntervalStorageStrategy(base_path, exchange_group)
    
    # Get correct file path based on storage granularity
    year = start_dt.year
    month = start_dt.month
    day = start_dt.day
    
    file_path = storage_strategy.get_file_path(interval, symbol, year, month, day)
```

**Alternative (Manual but correct)**:
```python
def write_test_bars_parquet(...):
    # Create bar directory structure matching actual storage
    if interval in ["1d", "1w"]:
        # Daily+: YYYY.parquet (yearly files)
        file_path = (
            base_path / exchange_group / "bars" / interval / symbol /
            f"{start_dt.year}.parquet"
        )
    else:
        # Intraday: YYYY/MM/DD.parquet (daily files)
        file_path = (
            base_path / exchange_group / "bars" / interval / symbol /
            f"{start_dt.year}" / f"{start_dt.month:02d}" / f"{start_dt.day:02d}.parquet"
        )
```

---

## Impact Assessment

### Production Code
✅ **No impact** - Production code is correct

### Tests
❌ **7 tests broken** - All parquet-related E2E tests fail

### Data Integrity
✅ **Not affected** - Real data uses correct paths

---

## Recommendation

**Priority**: Medium (tests broken but not blocking development)

**Action**: Fix test helper to use correct file structure

**Steps**:
1. Update `write_test_bars_parquet()` to create daily files for sub-daily intervals
2. Option A: Use `IntervalStorageStrategy.get_file_path()` (preferred - uses real API)
3. Option B: Manually construct correct paths (simpler but less maintainable)
4. Run all 7 tests to verify fix
5. Consider adding a test that validates helper creates correct paths

---

## Additional Notes

### Why Use IntervalStorageStrategy?

Using the real storage strategy API in tests:
1. **Consistency**: Tests use same logic as production
2. **Maintainability**: If storage strategy changes, tests auto-adapt
3. **Correctness**: Can't get path wrong if using real API
4. **Documentation**: Code shows how to properly use storage strategy

### Test Philosophy

This reveals a testing anti-pattern:
- **Bad**: Hardcode file structures in test helpers
- **Good**: Use production APIs to create test data

The backdoor approach is fine (directly writing parquet files), but it should use production APIs to determine paths.

---

## Summary

**Root Cause**: Test helper creates files at wrong paths (monthly instead of daily)

**Classification**: Bug in test, not in production code

**Fix**: Update `write_test_bars_parquet()` to use correct daily file structure

**Confidence**: 100% - Verified by path comparison and code inspection

**Status**: Ready to fix - clear solution identified
