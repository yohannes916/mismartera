# Session Data Validation

This directory contains tools for validating the correctness of the stream coordinator, session data, and backtest execution.

## Files

- **`session_validation_requirements.md`**: Comprehensive list of all behavioral requirements and invariants
- **`validate_session_dump.py`**: Python script to validate CSV dumps against requirements
- **`run_validation_test.sh`**: Helper script to run a test session and validate it

## Quick Start

### 1. Run Backtest with CSV Export

```bash
./start_cli.sh
system@mismartera: system start

# Immediately start data session (exports to validation/test_session.csv by default)
system@mismartera: data session

# Let it run for the entire backtest, then Ctrl+C or let it finish
```

### 2. Validate the CSV Dump

```bash
# Using CLI command (easiest - matches the data session defaults)
system@mismartera: data validate

# Or directly with Python script
cd validation
python validate_session_dump.py

# With custom files
data validate mytest.csv --config my_config.json
python validate_session_dump.py mytest.csv --config ../session_configs/my_config.json
```

**Defaults** (matched between `data session` and `data validate`):
- CSV file: `validation/test_session.csv` (always overwritten)
- Config file: `session_configs/example_session.json`

### 3. Review Results

The script will output:
- ✅ Total checks passed/failed
- 🚨 List of errors (violations of critical invariants)
- ⚠️  List of warnings (suspicious but non-fatal issues)

## Backtest Speed (Transparent to Validation)

**Important**: Backtest speed (60x, 1x, 0.5x, etc.) only affects how fast the replay happens in real-time. It is **completely transparent** to validation because:

- CSV `timestamp` column = real-world time when row was written (not validated)
- CSV `session_time` column = backtest time (simulated market time) - **this is what we validate**
- Validation checks backtest time progression, not real-time between rows

### Recommended Speed for Testing
```json
{
  "backtest_config": {
    "speed_multiplier": 60.0  // Fast replay (60x) - validation is speed-agnostic
  }
}
```

**Why 60x?**: Completes full trading day in ~6.5 minutes instead of 6.5 hours. Validation is identical at any speed.

## CSV Export (Automatic by Default)

**Default behavior**: `data session` automatically exports to `validation/test_session.csv` (overwrites on each run)

**Custom export**: `data session 1 my_output.csv`

### Visible Fields (Shown in UI)
- System: `system_state`, `system_mode`
- Session: `session_date`, `session_time`, `session_active`, `session_ended`
- Per-Symbol: `{SYMBOL}_volume`, `{SYMBOL}_high`, `{SYMBOL}_low`, `{SYMBOL}_1m_bars`, `{SYMBOL}_5m_bars`, `{SYMBOL}_bar_quality`
- Queues: `{SYMBOL}_queue_BAR_size`, `{SYMBOL}_queue_BAR_oldest`, `{SYMBOL}_queue_BAR_newest`

### Internal State Fields (CSV Only)
- **`{SYMBOL}_bars_updated`**: Flag indicating new bars added (triggers derived bar computation)
- **`{SYMBOL}_first_bar_ts`**: Timestamp of first bar in session_data (verifies completeness)
- **`{SYMBOL}_last_bar_ts`**: Timestamp of last bar in session_data (verifies continuity with queue)
- **`{SYMBOL}_pending_bar_ts`**: Timestamp of item in pending_items staging area (verifies chronological ordering)

### Why These Fields Matter

**bars_updated**: 
- Should flip to True when bars added
- Should reset to False after derived bars computed
- Stuck at True > 10 rows = upkeep thread issue

**first_bar_ts / last_bar_ts**:
- Verifies session_data contains expected range
- Validates continuity: last_bar_ts + 1min = queue_oldest
- Detects gaps: last_bar_ts to queue_oldest should be consecutive

**pending_bar_ts**:
- Exposes stream coordinator's "peek" mechanism
- Should match queue_oldest (they are the same item)
- Enables validation of chronological interleaving across symbols
- Example: If AAPL_pending = 09:30 and RIVN_pending = 09:31, AAPL should be consumed first

## What Gets Validated

### Config-Based Validation (NEW)
1. **Expected Symbols**: All symbols from config appear in CSV
2. **Expected Stream Types**: All configured streams (bars 1m, ticks, quotes) present
3. **Expected Derived Intervals**: All configured derived intervals (5m, 15m) present and computed
4. **No Unexpected Data**: Warns if CSV has symbols not in config

### Critical Invariants (Errors if violated)
1. **System State**: State transitions are valid, no restarts after stop
2. **Temporal**: Session time never goes backwards, stays within market hours
3. **Queue Sizes**: Non-negative, monotonically decreasing
4. **Queue Timestamps**: Oldest monotonically advancing, oldest <= newest
5. **Bar Counts**: Monotonically increasing, never decrease
6. **Price/Volume**: High >= Low, volumes monotonically increasing
7. **Data Consistency**: No partial updates, synchronized across symbols
8. **Data Completeness**: last_bar + queue_oldest consecutive (no gaps)
9. **Chronological Ordering**: Pending items match queue oldest, properly interleaved

### Performance Warnings (Warnings if violated)
1. **Time Stalls**: Backtest time (session_time) stuck for > 10 rows
2. **Derived Bar Lag**: 5m bars not computed within 60s of having enough data
3. **Queue Drainage**: Queue not draining at expected rate
4. **Backtest Time Gaps**: Large gaps in session_time (> 5 minutes)
5. **Total Bar Count**: Full day should have ~390 bars total (session_data + queue)

## Understanding the Output

### Successful Run
```
VALIDATION REPORT
================================================================================

Total Rows: 1543
Total Checks: 23,145
Passed: 23,145 (100.0%)
Failed: 0
Warnings: 0

✅ All checks passed!
```

### Failed Run Example
```
VALIDATION REPORT
================================================================================

Total Rows: 1543
Total Checks: 23,145
Passed: 23,130 (99.9%)
Failed: 10
Warnings: 5

🚨 ERRORS (10):
  Row 45: [queue_oldest_monotonic] AAPL: Queue oldest went backwards: 09:45:00 -> 09:44:55
  Row 123: [bars_1m_monotonic] RIVN: 1m bars decreased: 250 -> 249
  ...

⚠️  WARNINGS (5):
  Row 234: [derived_bars_timely] AAPL: 5m bars not computed yet despite 128 1m bars available
  ...
```

## Common Issues and Fixes

### Issue: Queue oldest going backwards
**Cause**: Race condition in timestamp tracking or worker thread bug  
**Fix**: Check `_pending_items` update logic in `backtest_stream_coordinator.py`

### Issue: Bar counts decreasing
**Cause**: Critical bug in session_data management  
**Fix**: Check `add_bar()` implementation for data loss

### Issue: Session time going backwards
**Cause**: TimeProvider bug or incorrect time advancement logic  
**Fix**: Check `set_backtest_time()` in TimeProvider

### Issue: Derived bars lag > 60s
**Cause**: Data upkeep thread not running or check interval too long  
**Fix**: Verify upkeep thread is started, check `DATA_UPKEEP_CHECK_INTERVAL_SECONDS`

### Issue: Queue size increasing
**Cause**: Producer faster than consumer (shouldn't happen in backtest)  
**Fix**: Check merge worker thread is consuming data, verify speed multiplier

## Advanced Usage

### Export Specific Symbols to Separate CSV
```bash
# TODO: Add symbol filtering
python validate_session_dump.py test_session.csv --symbol AAPL
```

### Database Cross-Validation
```bash
# Validate against database (requires DB connection)
python validate_session_dump.py test_session.csv --db-check
```

### Generate Detailed Report
```bash
python validate_session_dump.py test_session.csv --output report.json
```

## Continuous Integration

Add to CI/CD pipeline:
```bash
#!/bin/bash
# Run validation test
./validation/run_validation_test.sh

# Check exit code
if [ $? -eq 0 ]; then
  echo "✅ Validation passed"
else
  echo "❌ Validation failed"
  exit 1
fi
```

## Extending Validation

To add new checks:

1. Add requirement to `session_validation_requirements.md`
2. Implement check method in `SessionValidator` class
3. Call method in `validate_all()`
4. Test with known good and bad data

Example:
```python
def validate_custom_requirement(self):
    """Validate custom requirement."""
    for idx, row in enumerate(self.rows):
        row_num = idx + 1
        
        # Check something
        if condition_violated:
            self.stats.add_result(ValidationResult(
                check_name="custom_check",
                passed=False,
                row_number=row_num,
                details="Description of violation",
                severity="ERROR",  # or "WARNING"
            ))
```

## Troubleshooting

### Script fails to load CSV
- Check file path is correct
- Verify CSV has headers
- Ensure file is not corrupted

### No symbols detected
- Verify CSV has columns like `AAPL_volume`, `RIVN_volume`
- Check data session command exported data correctly

### All checks report as passed but issues visible
- Add more specific checks to the script
- Review `session_validation_requirements.md` for missing coverage

## Performance Benchmarks

Expected validation times (for reference only):
- 1000 rows: ~4 seconds
- 2000 rows: ~8 seconds  
- 5000 rows: ~20 seconds

**Note**: Number of CSV rows depends on:
- Refresh interval (1s = more rows, 5s = fewer rows)
- How long you let the backtest run
- Backtest speed does NOT affect CSV rows (only how fast you capture them)

If validation is significantly slower, check:
- Large number of violations (slows reporting)
- Database checks enabled (much slower)
- CSV file size (should be < 10 MB for typical full-day session)
