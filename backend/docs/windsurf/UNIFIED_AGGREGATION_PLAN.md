# Unified Data Aggregation System - Implementation Plan

## Objective
Create a unified, flexible aggregation system that:
- Supports ALL bar type conversions (seconds, minutes, days, weeks)
- Reads from Parquet, aggregates, writes back to Parquet
- Uses existing `BarAggregator` with automatic mode detection
- Provides clean CLI interface: `data aggregate <target> <source> <symbol> <start> <end>`
- Clean break: Delete old redundant code, no backward compatibility

---

## Current State Analysis

### ✅ What We Have (Keep & Use)

**1. BarAggregator (Unified Framework)**
- Location: `app/managers/data_manager/bar_aggregation/aggregator.py`
- Supports: tick→1s, 1s→1m, 1m→Nm, 1m→1d, 1d→1w
- Three modes:
  - `TIME_WINDOW`: ticks → 1s (round timestamps)
  - `FIXED_CHUNK`: 1s→1m, 1m→5m (N consecutive bars)
  - `CALENDAR`: 1m→1d, 1d→1w (trading calendar)
- Already parameterized and flexible
- **Status**: ✅ Keep as-is, use for everything

**2. ParquetStorage**
- Location: `app/managers/data_manager/parquet_storage.py`
- Methods: `read_bars()`, `write_bars()`, `get_symbols()`, `get_intervals()`
- Already handles exchange timezone conversion
- **Status**: ✅ Keep as-is, use for read/write

**3. Existing Usage**
- `aggregate_ticks_to_1s()` - Already uses BarAggregator
- **Status**: ✅ Good pattern to replicate

### ❌ What to Delete (Redundant)

**1. aggregate_quotes_by_second()**
- Location: `parquet_storage.py` lines 196-238
- Special quote logic (tightest spread), NOT bar aggregation
- **Decision**: Keep for now (different purpose - quote filtering, not bar OHLCV)

---

## Architecture Design

### Component 1: Mode Detection Utility

**New File**: `app/managers/data_manager/bar_aggregation/mode_detector.py`

```python
def detect_aggregation_mode(source_interval: str, target_interval: str) -> AggregationMode:
    """Auto-detect which aggregation mode to use.
    
    Rules:
    - tick → any = TIME_WINDOW
    - X → daily/weekly = CALENDAR
    - X → X_multiple = FIXED_CHUNK (1s→1m, 1m→5m, 5m→15m)
    
    Returns:
        AggregationMode enum
    
    Raises:
        ValueError: If conversion is invalid
    """
```

**Logic**:
1. Parse intervals using `parse_interval()`
2. Validate source < target (can't aggregate down)
3. Check target type:
   - Daily/Weekly → `CALENDAR`
   - Ticks → `TIME_WINDOW`
   - Same unit (s→s, m→m) → `FIXED_CHUNK`
4. Validate compatibility (no 1d→1m, no 1m→1s, etc.)

### Component 2: DataManager Aggregation API

**New Method in**: `app/managers/data_manager/api.py`

```python
def aggregate_and_store(
    self,
    session: Session,
    target_interval: str,
    source_interval: str,
    symbol: str,
    start_date: str,
    end_date: str
) -> Dict:
    """Aggregate existing Parquet data to new interval.
    
    Unified aggregation pipeline:
    1. Validate intervals and mode
    2. Read source bars from Parquet
    3. Create BarAggregator with auto-detected mode
    4. Aggregate bars
    5. Write to Parquet (target interval)
    6. Return stats
    
    Args:
        session: DB session
        target_interval: Target interval (e.g., "5m", "1d", "1w")
        source_interval: Source interval (e.g., "1s", "1m", "5m")
        symbol: Stock symbol
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
    
    Returns:
        {
            "success": bool,
            "source_interval": str,
            "target_interval": str,
            "mode": str,
            "source_bars": int,
            "aggregated_bars": int,
            "files_written": int,
            "date_range": str
        }
    
    Supported Aggregations:
        Seconds: 1s → 1m, 5m, 15m, 30m, 60m, etc.
        Minutes: 1m → 5m, 15m, 30m, 60m, 1d
                 5m → 15m, 30m, 60m, 1d
                 15m → 30m, 60m, 1d
        Days:    1d → 1w
    
    Examples:
        # 1-second to 1-minute
        aggregate_and_store(session, "1m", "1s", "AAPL", "2025-07-01", "2025-07-31")
        
        # 1-minute to 5-minute
        aggregate_and_store(session, "5m", "1m", "AAPL", "2025-07-01", "2025-07-31")
        
        # 1-minute to daily
        aggregate_and_store(session, "1d", "1m", "AAPL", "2025-07-01", "2025-07-31")
        
        # Daily to weekly
        aggregate_and_store(session, "1w", "1d", "AAPL", "2025-01-01", "2025-12-31")
    """
```

**Implementation Steps**:
1. Parse and validate dates
2. Validate intervals exist in Parquet
3. Read source bars using `parquet_storage.read_bars()`
4. Auto-detect mode using `detect_aggregation_mode()`
5. Get TimeManager from SystemManager (required for CALENDAR mode)
6. Create `BarAggregator(source_interval, target_interval, time_mgr, mode)`
7. Call `aggregator.aggregate(bars, require_complete=True, check_continuity=True)`
8. Write aggregated bars using `parquet_storage.write_bars()`
9. Return comprehensive stats

### Component 3: CLI Command

**Add to**: `app/cli/data_commands.py`

```python
@app.command("aggregate")
def aggregate_data(
    target: str = typer.Argument(..., help="Target interval (5m, 1d, 1w)"),
    source: str = typer.Argument(..., help="Source interval (1s, 1m, 5m, 1d)"),
    symbol: str = typer.Argument(..., help="Stock symbol"),
    start_date: str = typer.Argument(..., help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Argument(..., help="End date (YYYY-MM-DD)"),
) -> None:
    """Aggregate existing Parquet data to new interval.
    
    Examples:
        data aggregate 1m 1s AAPL 2025-07-01 2025-07-31
        data aggregate 5m 1m AAPL 2025-07-01 2025-07-31
        data aggregate 1d 1m AAPL 2025-07-01 2025-07-31
        data aggregate 1w 1d AAPL 2025-01-01 2025-12-31
    """
    aggregate_command(target, source, symbol, start_date, end_date)
```

**Interactive CLI Handler**: `app/cli/interactive.py`
```python
elif subcmd == 'aggregate' and len(args) >= 6:
    target = args[1]
    source = args[2]
    symbol = args[3].upper()
    start_date = args[4]
    end_date = args[5]
    from app.cli.data_commands import aggregate_command
    aggregate_command(target, source, symbol, start_date, end_date)
```

**Command Registry**: `app/cli/command_registry.py`
```python
DataCommandMeta(
    name="aggregate",
    usage="data aggregate <target> <source> <symbol> <start> <end>",
    description="Aggregate existing Parquet data to new interval (e.g., 1m→5m, 1d→1w)",
    examples=[
        "data aggregate 5m 1m AAPL 2025-07-01 2025-07-31",
        "data aggregate 1d 1m AAPL 2025-07-01 2025-07-31",
        "data aggregate 1w 1d AAPL 2025-01-01 2025-12-31"
    ],
    suggests_symbols_at=3,
)
```

---

## Supported Aggregation Matrix

| Source | Target | Mode | Example Use Case |
|--------|--------|------|------------------|
| 1s | 1m, 5m, 15m, 30m, 60m | FIXED_CHUNK | High-freq to standard timeframes |
| 1m | 5m, 15m, 30m, 60m | FIXED_CHUNK | Standard intraday conversions |
| 5m | 15m, 30m, 60m | FIXED_CHUNK | Coarser intraday timeframes |
| 1s, 1m, 5m, 15m | 1d | CALENDAR | Intraday to daily |
| 1d | 1w | CALENDAR | Daily to weekly |

**Not Supported** (by design):
- ❌ 1d → 1m (can't create finer resolution)
- ❌ 1m → 1s (can't create finer resolution)
- ❌ Hourly (1h, 2h) - use 60m, 120m instead

---

## Implementation Order

### Phase 1: Core Infrastructure ✅
- [x] Analyze existing BarAggregator (already done)
- [x] Design API signature
- [ ] Create `mode_detector.py`
- [ ] Add unit tests for mode detection

### Phase 2: DataManager API
- [ ] Implement `aggregate_and_store()` in `api.py`
- [ ] Add comprehensive error handling
- [ ] Add logging at each step
- [ ] Test with sample data

### Phase 3: CLI Integration
- [ ] Add `aggregate_command()` to `data_commands.py`
- [ ] Add Typer command definition
- [ ] Add interactive CLI handler
- [ ] Update command registry
- [ ] Update help system

### Phase 4: Cleanup 🧹
- [ ] Review for redundant code (none identified yet)
- [ ] Keep `aggregate_quotes_by_second()` (different purpose)
- [ ] Delete any wrapper functions if found
- [ ] Update documentation

### Phase 5: Testing
- [ ] Test 1s → 1m aggregation
- [ ] Test 1m → 5m, 15m aggregations
- [ ] Test 1m → 1d aggregation
- [ ] Test 1d → 1w aggregation
- [ ] Test error cases (invalid intervals, missing data)

---

## Error Handling

**Validation Errors**:
- Invalid interval format → User-friendly message with examples
- Source > Target → "Cannot create finer resolution"
- Incompatible intervals → "Cannot aggregate 1d → 5m"
- Missing source data → "No {source} bars found for {symbol}"

**Mode Detection Errors**:
- Hourly intervals → "Use 60m instead of 1h"
- Unsupported conversion → List valid targets for given source

**Execution Errors**:
- Incomplete bars → Log warning, continue with complete ones
- Gaps in data → Log gaps, aggregate what's continuous
- Write failure → Rollback, preserve original data

---

## Benefits

1. **Unified**: Single API for all aggregations
2. **Flexible**: Auto-detects mode, handles all intervals
3. **Consistent**: Uses same BarAggregator as real-time system
4. **Safe**: Validates before aggregating, preserves source data
5. **Clean**: CLI interface matches existing patterns
6. **Complete**: Handles seconds → minutes → days → weeks
7. **Smart**: TimeManager integration for calendar aggregations

---

## Example Workflows

### Weekly Chart Data
```bash
# Import daily bars from API
data import-api 1d AAPL 2025-01-01 2025-12-31

# Aggregate to weekly
data aggregate 1w 1d AAPL 2025-01-01 2025-12-31
```

### 5-Minute Backtest Data
```bash
# Import 1-minute bars
data import-api 1m AAPL 2025-07-01 2025-07-31

# Aggregate to 5-minute
data aggregate 5m 1m AAPL 2025-07-01 2025-07-31
```

### High-Frequency Analysis
```bash
# Import 1-second bars (if available)
data import-api 1s AAPL 2025-07-01 2025-07-01

# Create 1-minute bars
data aggregate 1m 1s AAPL 2025-07-01 2025-07-01

# Create 5-minute bars
data aggregate 5m 1m AAPL 2025-07-01 2025-07-01
```

---

## Files to Modify

### New Files
1. `app/managers/data_manager/bar_aggregation/mode_detector.py` - Mode detection logic
2. `docs/windsurf/UNIFIED_AGGREGATION_PLAN.md` - This plan document

### Modified Files
1. `app/managers/data_manager/api.py` - Add `aggregate_and_store()` method
2. `app/cli/data_commands.py` - Add `aggregate_command()` and Typer command
3. `app/cli/interactive.py` - Add CLI handler for 'data aggregate'
4. `app/cli/command_registry.py` - Add command metadata

### No Deletions
- All existing code is kept (nothing redundant identified)
- `aggregate_quotes_by_second()` serves different purpose (quote filtering)
- `aggregate_ticks_to_1s()` is used internally, keep as convenience wrapper

---

## Success Criteria

- ✅ Single unified API for all bar aggregations
- ✅ Auto-detects aggregation mode (TIME_WINDOW, FIXED_CHUNK, CALENDAR)
- ✅ CLI command matches existing pattern: `data aggregate <target> <source> <symbol> <start> <end>`
- ✅ Supports: 1s→1m, 1m→5m, 1m→1d, 1d→1w, and all valid combinations
- ✅ Comprehensive error handling and validation
- ✅ Preserves exchange timezone (already in parquet_storage)
- ✅ Uses TimeManager for calendar operations
- ✅ Clean, tested, documented

---

## Timeline Estimate

- **Phase 1** (Mode Detector): 1 hour
- **Phase 2** (DataManager API): 2 hours
- **Phase 3** (CLI Integration): 1 hour
- **Phase 4** (Cleanup): 30 minutes
- **Phase 5** (Testing): 1 hour

**Total**: ~5.5 hours

---

## Next Steps

Ready to proceed? I'll:
1. Create `mode_detector.py` with automatic mode detection
2. Implement `DataManager.aggregate_and_store()` 
3. Add CLI command and integration
4. Test all aggregation paths
5. Update documentation

Shall I start with Phase 1? 🚀
