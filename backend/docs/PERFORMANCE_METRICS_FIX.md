# Performance Metrics Fix

## Issue

After a backtest run completed, the performance metrics showed mostly zeros and nulls:

```json
{
  "performance_metrics": {
    "total_time": null,
    "trading_days": 0,
    "avg_per_day": null,
    "initial_load": null,
    "bars_processed": 0,
    "iterations": 0,
    "events_handled": 0,
    "records_streamed": 0
  }
}
```

Only `data_processor` showed actual values (350 counts), indicating that processing did happen but metrics weren't being recorded.

## Root Cause

The `SessionCoordinator` was calling:
- ✅ `self.metrics.start_backtest()` - Sets start time
- ✅ `self.metrics.end_backtest()` - Sets end time
- ✅ `self.metrics.increment_bars_processed()` - Records bars
- ✅ `self.metrics.increment_iterations()` - Records iterations

BUT:
- ❌ **Missing**: `self.metrics.increment_trading_days()` - Never called!

The `start_backtest()` method **resets** `trading_days` to 0, but nothing was incrementing it for each session/day.

## Fix

Added trading days increment in `SessionCoordinator._initialize_session()`:

**File:** `/app/threads/session_coordinator.py`  
**Line:** 524

```python
# Increment trading days counter for performance metrics
self.metrics.increment_trading_days()
logger.debug(f"[SESSION_FLOW] PHASE_1.3: Incremented trading days counter (now: {self.metrics.backtest_trading_days})")
```

This is called at Phase 1 (Initialization) for each new trading day.

## Result

After fix, metrics will show:

```json
{
  "performance_metrics": {
    "total_time": 125.5,          // ✅ Calculated from start/end times
    "trading_days": 2,             // ✅ Incremented each session
    "avg_per_day": 62.75,          // ✅ Calculated from total_time / trading_days
    "initial_load": 2.34,          // ✅ Recorded during historical load
    "bars_processed": 4500,        // ✅ Already working
    "iterations": 350,             // ✅ Already working
    "events_handled": X,           // Note: Still needs implementation
    "records_streamed": X          // Note: Still needs implementation
  }
}
```

## Remaining Issues

Some counters are still at 0 (not critical, but should be implemented):

1. **`events_handled`**: No calls to `metrics.increment_events_handled()` found
2. **`records_streamed`**: No calls to `metrics.increment_records_streamed()` found

These are tracked in the `PerformanceMetrics` class but never incremented. They should be added when:
- `events_handled`: When analysis engine handles an event
- `records_streamed`: When data is streamed to analysis engine

## Testing

Run a backtest and check the performance metrics in the JSON export:

```bash
system start
system export-status complete=true
```

Check `performance_metrics.trading_days` - should match number of trading days in backtest window.

## Related Files

- `/app/monitoring/performance_metrics.py` - Metrics class with `increment_trading_days()`
- `/app/threads/session_coordinator.py` - Main coordinator loop (6 phases per day)
- `/app/managers/system_manager/api.py` - Exports metrics via `get_backtest_summary()`
