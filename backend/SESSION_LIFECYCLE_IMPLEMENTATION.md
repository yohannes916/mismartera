# Session Lifecycle Architecture - Implementation Complete

## Overview

Implemented a 3-thread architecture for managing trading session lifecycle with automatic day-to-day transitions in backtest mode.

## Architecture

### Thread Model

| Thread | Owner | Responsibility |
|--------|-------|----------------|
| **Stream Coordinator** | BacktestStreamCoordinator | Chronological streaming, stops at market close |
| **Data Upkeep** | DataUpkeepThread | Session lifecycle orchestration, quality checks, derived bars |
| **Prefetch Worker** | PrefetchWorker (pool of 1) | Background data loading, signals completion |

### State Management

**Session Active State:**
- Managed by upkeep thread via `session_data.activate_session()` / `deactivate_session()`
- Simple boolean flag (`_session_active`), GIL-safe for reads
- No complex locks needed

**Flow:**
1. **System Start** → Upkeep activates session → Launches prefetch (blocking wait) → Coordinator streams
2. **Market Close** → Coordinator stops streaming (independent check) → Upkeep deactivates session → Advances to next day
3. **Next Day** → Upkeep activates session → Launches prefetch (async) → Coordinator resumes streaming

## Files Modified

### 1. New Files Created

#### `/app/managers/data_manager/prefetch_worker.py`
**Purpose:** Background thread for loading market data into coordinator queues

**Key Features:**
- Runs in ThreadPoolExecutor (max_workers=1)
- Supports two modes:
  - **Mid-session start:** Load from market open to current time (blocking wait)
  - **EOD transition:** Load full next day (async, no wait)
- Returns Future for async completion tracking
- 30-second timeout for blocking waits

**API:**
```python
def start_prefetch(target_date, symbols, interval, start_time=None) -> Future
def wait_for_completion(timeout=30.0) -> bool
def is_prefetch_running() -> bool
def shutdown()
```

### 2. Modified Files

#### `/app/managers/data_manager/session_data.py`

**Changes:**
- Added `_session_active` flag
- Added `activate_session()` method - called by upkeep when session starts
- Added `deactivate_session()` method - called by upkeep at market close
- Added `is_session_active()` method - checked by coordinator
- Deprecated `session_ended` (kept for backward compatibility)

**Code:**
```python
def activate_session(self) -> None:
    """Activate trading session (called by upkeep)"""
    self._session_active = True
    logger.info("✓ Session activated")

def deactivate_session(self) -> None:
    """Deactivate trading session (called by upkeep at close)"""
    self._session_active = False
    logger.info("✓ Session deactivated")

def is_session_active(self) -> bool:
    """Check if session is active (GIL-safe read)"""
    return self._session_active
```

#### `/app/managers/data_manager/data_upkeep_thread.py`

**Major Rewrite:** Added session lifecycle management

**Changes:**
- Added `data_manager` parameter to __init__
- Created `PrefetchWorker` instance
- Replaced `_run_upkeep_cycle()` with async `_run_upkeep_loop()`
- Added session lifecycle orchestration logic
- Manages day-to-day transitions

**Lifecycle Logic:**
```python
async def _run_upkeep_loop(self):
    while running:
        # Check if market close reached
        if current_time >= close_time:
            # 1. Deactivate session
            session_data.deactivate_session()
            
            # 2. Check if backtest complete
            if current_date >= backtest_end_date:
                system_mgr.stop()
                break
            
            # 3. Get next trading day
            next_date = time_mgr.get_next_trading_date(...)
            
            # 4. Advance time to next day's open
            time_mgr.set_backtest_time(next_open)
            
            # 5. Activate session
            session_data.activate_session()
            
            # 6. Launch prefetch for next day (async, no wait)
            prefetch_worker.start_prefetch(next_date, symbols, interval)
        
        # Initial activation (mid-session start)
        elif not session_activated_for_day:
            session_data.activate_session()
            
            # Launch prefetch (BLOCKING wait for initial load)
            prefetch_worker.start_prefetch(current_date, symbols, interval, current_time)
            success = prefetch_worker.wait_for_completion(timeout=30.0)
        
        # Regular upkeep (gaps, derived bars, quality)
        if session_data.is_session_active():
            _run_symbol_upkeep(db_session)
```

#### `/app/managers/data_manager/backtest_stream_coordinator.py`

**Changes:**
- Added `data_manager` parameter to __init__ and `get_coordinator()`
- Pass `data_manager` to `DataUpkeepThread` initialization
- Added independent market close check in `_merge_worker()`

**Market Close Check:**
```python
def _merge_worker(self):
    while not shutdown:
        # CRITICAL: Independent close time check
        if system_manager.is_backtest_mode():
            current_time = time_manager.get_current_time()
            trading_session = time_manager.get_trading_session(...)
            
            if trading_session and current_time >= close_time:
                logger.debug("Market close reached, waiting")
                time.sleep(0.1)
                continue  # Stop streaming
        
        # Normal streaming logic...
```

#### `/app/managers/data_manager/api.py`

**Changes:**
- Updated all `get_coordinator()` calls to pass `self` (data_manager)

**Code:**
```python
# OLD
coordinator = get_coordinator(self.system_manager)

# NEW
coordinator = get_coordinator(self.system_manager, self)
```

#### `/app/cli/session_data_display.py`

**Changes:**
- Removed `session_ended` field from CSV export
- Kept `session_active` field

## Synchronization Model

### Critical Synchronization Points

1. **Upkeep deactivates** → Coordinator stops streaming
   - No race condition: Both check close time independently
   - Coordinator's check is defensive, upkeep orchestrates

2. **Upkeep advances time** → TimeManager updates current_time
   - TimeManager has internal lock
   - All time queries are atomic

3. **Upkeep prefetches** → Coordinator queues filled
   - Prefetch worker runs in separate thread
   - Queues are thread-safe (queue.Queue)

4. **Upkeep activates** → Coordinator resumes streaming
   - Simple boolean flag (`_session_active`)
   - GIL-safe reads, no lock needed

### Thread Safety

- **`_session_active` flag:** Simple boolean, GIL-safe for reads
- **Time advancement:** TimeManager has internal lock
- **Queue operations:** Already thread-safe (queue module)
- **Prefetch worker:** Runs in ThreadPoolExecutor, isolated
- **No new locks needed**

## Configuration Changes

### Removed Settings
```json
{
  "prefetch": {
    "window_minutes": 60  // ❌ REMOVED - not needed
  }
}
```

### Kept Settings
```json
{
  "data_upkeep": {
    "enabled": true,
    "check_interval_seconds": 2.0,
    "derived_intervals": [5, 15]
  }
}
```

## CSV Export Changes

### Fields Removed
- `session_ended` - Redundant, use `session_active` instead

### Fields Kept
- `session_active` - Reflects `session_data.is_session_active()`
- `trading_hours_open` - Market open time (e.g., "09:30")
- `trading_hours_close` - Market close time (e.g., "16:00")
- `is_early_close` - Boolean flag for short trading days

## Behavior Changes

### System Start (Mid-Session)
```
1. System initializes → Time set to backtest_start_date @ market open
2. Upkeep detects: not activated AND current_time >= open_time
3. Upkeep activates session
4. Upkeep launches prefetch (open → current_time)
5. Upkeep BLOCKS, waiting for prefetch (max 30s)
6. Prefetch completes → Data loaded into queues
7. Coordinator starts streaming from queue
```

### End of Day Transition
```
1. Coordinator detects: current_time >= close_time → Stops streaming
2. Upkeep detects: current_time >= close_time
3. Upkeep deactivates session
4. Upkeep checks: current_date >= backtest_end_date?
   - YES → Call system_mgr.stop() → Exit
   - NO → Continue to step 5
5. Upkeep gets next_trading_date (skips holidays)
6. Upkeep advances time to next_open
7. Upkeep activates session for new day
8. Upkeep launches prefetch for next day (async, no wait)
9. Coordinator resumes streaming when queues fill
```

### Coordinator Streaming Logic
```
1. Check: current_time >= close_time? → Sleep and wait
2. Check: active_streams empty? → Sleep and wait
3. Fetch next chronological item from queues
4. Write to session_data
5. Advance time (bar interval: +1s or +1m)
6. Loop
```

## Edge Cases Handled

✅ **Mid-session start** - Loads full historical data up to current time, blocks until ready  
✅ **Empty queues at close** - Coordinator stops based on time check, not queue state  
✅ **Prefetch timeout** - 30s timeout with error logging, system continues  
✅ **Holiday detection** - Upkeep skips holidays when advancing days  
✅ **Backtest end** - Upkeep detects end date and calls `system_mgr.stop()`  
✅ **Thread cleanup** - Prefetch worker shutdown on upkeep stop  
✅ **Race conditions** - Both threads check close time independently (defensive)  
✅ **Early close days** - Trading hours fetched from TimeManager (accurate)  

## Testing Recommendations

### Unit Tests
1. **PrefetchWorker:**
   - Test loading full day
   - Test loading up to specific time
   - Test timeout handling
   - Test shutdown during active prefetch

2. **SessionData:**
   - Test activate/deactivate
   - Test concurrent is_session_active reads

3. **DataUpkeepThread:**
   - Test EOD transition logic
   - Test holiday skipping
   - Test backtest end detection
   - Test initial activation

### Integration Tests
1. **Full Day Backtest:**
   - System start @ market open
   - Stream until close
   - Verify EOD transition
   - Verify next day activation

2. **Multi-Day Backtest:**
   - Verify day-to-day transitions
   - Verify queue continuity
   - Verify no data gaps

3. **Early Close Day:**
   - Verify close at 13:00
   - Verify transition to next day

4. **Holiday Handling:**
   - Verify holiday skip
   - Verify next trading day selection

## Performance Considerations

- **Prefetch in background:** No blocking during normal operation
- **Initial load blocks:** Max 30s, ensures data ready before streaming
- **Close time check:** Minimal overhead (simple time comparison)
- **No complex locks:** Simple flag checks, no deadlocks
- **Thread pool size 1:** Single prefetch at a time, prevents resource contention

## Monitoring & Logging

### Key Log Messages

**Session Lifecycle:**
```
✓ Session activated
✓ Session deactivated
EOD: Market close reached at 2025-07-02 16:00:00
Advancing to 2025-07-03 at 2025-07-03 09:30:00
```

**Prefetch:**
```
Starting prefetch for 2025-07-03 (2 symbols, interval=1m, end_time=None)
Prefetch completed for 2025-07-03: success=True
Initial prefetch launched for 2025-07-02 up to 2025-07-02 12:45:00
Initial prefetch completed successfully
```

**Coordinator:**
```
Market close reached at 2025-07-02 16:00:00, waiting
```

### Metrics to Track
- Prefetch duration
- Session activation/deactivation timing
- EOD transition latency
- Queue sizes at EOD
- Bar quality metrics

## Status

✅ **IMPLEMENTATION COMPLETE** - All components updated and integrated

**Next Steps:**
1. System testing with live backtest
2. Validate CSV export format
3. Update validation script expectations
4. Create unit/integration tests
5. Performance profiling

## Related Documentation
- `/backend/SESSION_DISPLAY_ENHANCEMENT.md` - Trading hours in display
- `/backend/CSV_TRADING_HOURS_ENHANCEMENT.md` - Trading hours in CSV
- `/backend/DATA_MANAGER_TIME_FIX.md` - TimeManager integration
- `/backend/TIMEZONE_FIX_COMPLETE.md` - Timezone awareness fixes
