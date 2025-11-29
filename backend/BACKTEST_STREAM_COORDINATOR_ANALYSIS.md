# Backtest Stream Coordinator - Complete Lifecycle Analysis

## Overview
The `BacktestStreamCoordinator` is a critical background thread responsible for merging multiple backtest data streams (bars, ticks, quotes) across different symbols in **chronological order**. It is the **ONLY component** that advances backtest time forward, making it the central timing controller for the entire backtest system.

## Thread Lifecycle

### 1. Creation & Initialization
**Location:** `backtest_stream_coordinator.py:74-149` (`__init__`)
**Created by:** `DataManager` when system starts
**Called from:** `app/managers/data_manager/api.py` (singleton pattern via `get_coordinator()`)

```python
# Initialization via singleton getter
coordinator = get_coordinator(
    system_manager=system_manager,
    data_manager=data_manager
)
```

**What happens during initialization:**
- Stores references to `system_manager`, `data_manager`
- Initializes active streams dictionary `_active_streams`
- Creates thread-safe output queue `_output_queue`
- Sets up shutdown event `_shutdown`
- Gets `TimeManager` reference via SystemManager
- Gets `SessionData` reference for storing streamed data
- Initializes worker thread variables (not started yet)
- Sets up clock thread variables for speed > 0 mode

### 2. Starting the Worker Thread
**Location:** `backtest_stream_coordinator.py:410-446` (`start_worker()`)

```python
coordinator.start_worker()  # Called by DataManager
```

**What happens:**
- Creates main merge worker thread (`_merge_worker`)
- Thread name: `"BacktestStreamWorker"` (daemon)
- If speed > 0: Creates clock thread (`_clock_worker`)
- Thread name: `"BacktestClockWorker"` (daemon)
- Both threads start immediately

### 3. Two Operating Modes

#### Mode 1: Data-Driven (speed = 0)
**How it works:**
- Worker thread pulls data from queues
- Immediately advances time to match data
- Streams as fast as consumers can process
- No independent clock thread

**Use case:** Testing, fast backtesting, debugging

#### Mode 2: Clock-Driven (speed > 0)
**How it works:**
- Clock thread advances time independently
- Worker thread waits for time to reach data
- Respects backtest speed multiplier (1x, 10x, 360x)
- More realistic timing simulation

**Use case:** Realistic backtesting, strategy testing with timing constraints

### 4. Stream Registration Flow
**Location:** `backtest_stream_coordinator.py:151-187` (`register_stream`)

```python
# DataManager registers a stream
success, input_queue = coordinator.register_stream(
    symbol="AAPL",
    stream_type=StreamType.BAR
)

# If successful, DataManager feeds data
coordinator.feed_data_list("AAPL", StreamType.BAR, bar_list)
```

**What happens:**
1. Creates thread-safe input queue for this stream
2. Stores in `_active_streams` dict with key `(symbol, stream_type)`
3. Initializes timestamp tracking for queue stats
4. Returns queue to caller for data feeding

### 5. Main Merge Worker Loop
**Location:** `backtest_stream_coordinator.py:492-794` (`_merge_worker`)

This is the **heart** of the coordinator. It runs continuously in a `while` loop.

**Loop Structure:**
```python
while not self._shutdown.is_set():
    1. CHECK: Market close reached?
       if current_time >= market_close + 1min:
           → Pause (wait for upkeep thread to handle EOD)
    
    2. FETCH: Pull next item from each stream
       → Fill pending_items dict
       → Skip streams that already have pending data
       → Skip stale data (older than current time)
    
    3. FIND OLDEST: Scan pending_items for oldest timestamp
       → Use simple comparison (all times in system timezone)
    
    4. FILTER: Check if oldest item is within trading hours
       if bar_date == current_date:
           if timestamp < market_open: discard
           if timestamp > market_close + 1min: discard
       → Future day data preserved in queue
    
    5. ADVANCE TIME: (CRITICAL - ONLY place this happens)
       Mode A (speed = 0): Set time immediately to bar end time
       Mode B (speed > 0): Wait for clock to reach bar end time
    
    6. WRITE: Store data in session_data
       → add_bar() for bar data
       → Update quality metrics immediately
    
    7. YIELD: Put data into output queue
       → Mark pending item as consumed (None)
```

### 6. Clock Worker Thread (Speed > 0 Only)
**Location:** `backtest_stream_coordinator.py:356-408` (`_clock_worker`)

**Runs independently when speed > 0:**
```python
while not _shutdown:
    1. Wait for system to be running
       if not system_manager.is_running():
           → Pause clock
           → Sleep 0.1s
    
    2. Initialize clock on first run
       → backtest_start_time = current time
       → clock_start_time = wall clock time.time()
    
    3. Calculate elapsed time
       wall_elapsed = time.time() - clock_start_time
       backtest_elapsed = wall_elapsed * speed
       new_time = backtest_start_time + backtest_elapsed
    
    4. Advance time
       → time_manager.set_backtest_time(new_time)
    
    5. Sleep 10ms (100 Hz update rate)
```

### 7. Time Advancement Logic (Critical)
**Location:** `backtest_stream_coordinator.py:674-765`

**Bar Timestamp Interpretation:**
- **1m bar with timestamp 09:30:00** = interval [09:30:00 - 09:30:59]
- **Target time**: 09:31:00 (end of interval, bar complete)
- **1s bar with timestamp 09:30:00** = interval [09:30:00.000 - 09:30:00.999]
- **Target time**: 09:30:01 (end of interval)

**Two Modes:**

#### Data-Driven (Speed = 0)
```python
# Advance immediately when yielding data
target_time = bar.timestamp + timedelta(minutes=1)  # For 1m bar
time_manager.set_backtest_time(target_time)
# Then stream data
```

#### Clock-Driven (Speed > 0)
```python
# Wait for clock to reach target
target_time = bar.timestamp + timedelta(minutes=1)
while current_time < target_time:
    time.sleep(0.01)  # Poll every 10ms
# Clock thread has advanced time, now stream data
```

### 8. Market Hours Filtering
**Location:** `backtest_stream_coordinator.py:629-672`

**For each data item about to be yielded:**
```python
1. Get bar_date and current_date
2. If bar_date == current_date:
   a. Get trading session for current_date
   b. If bar.timestamp < market_open:
      → Discard (pre-market)
   c. If bar.timestamp > market_close + 1min:
      → Discard (after-hours)
3. If bar_date > current_date:
   → Keep in queue (future day, prefetched)
4. If bar_date < current_date:
   → Skip as stale (shouldn't happen)
```

**Result:** Only regular trading hours data (09:30-16:01) is processed.

### 9. Stopping the Worker Thread
**Location:** `backtest_stream_coordinator.py:448-490` (`stop_worker()`)

```python
coordinator.stop_worker()
```

**What happens:**
1. Set `_shutdown` event (signals threads to exit)
2. Stop clock thread (if running)
   - Join with 2s timeout
   - Reset clock state variables
3. Send None sentinel to all input queues (unblocks worker)
4. Join worker thread with 5s timeout
5. Clean up thread references

## Thread Coordination

### With DataManager
- **Creation:** DataManager creates coordinator singleton
- **Stream Setup:** DataManager registers streams and feeds data
- **Data Flow:** DataManager → Coordinator queues → Merged output

### With TimeManager
- **Single source of truth** for current time
- **CRITICAL:** Coordinator is ONLY place that advances time forward in backtest mode
- All other components query time via `time_mgr.get_current_time()`

### With SessionData
- **Shared resource:** Protected by `_lock`
- **Data Flow:** Coordinator writes bars → SessionData → Upkeep thread analyzes
- **Quality Updates:** Coordinator updates quality immediately after writing

### With DataUpkeepThread
- **Independent operation:** Both threads run concurrently
- **Coordination:** Data arrival event signals upkeep thread
- **EOD Handling:** Coordinator pauses at market close, upkeep handles transitions

## Key Responsibilities Summary

### Stream Management
- Register/deregister streams per (symbol, stream_type)
- Thread-safe queue management
- Track queue timestamps for statistics

### Chronological Merging (CORE)
- Pull data from multiple streams
- Find oldest timestamp across all active streams
- Yield data in perfect chronological order
- No sorting needed (data pre-sorted from DB)

### Time Advancement (CRITICAL)
- **ONLY component** that advances backtest time forward
- Respects bar intervals (1m bar → advance to end of minute)
- Two modes: data-driven (fast) and clock-driven (realistic)

### Market Hours Enforcement
- Filters pre-market data (before 09:30)
- Filters after-hours data (after 16:01)
- Preserves future day data in queues
- Date-aware filtering (only filters current day)

### Quality Monitoring
- Updates bar quality immediately after consuming data
- Calculates % of expected bars received
- Provides real-time feedback (not waiting for upkeep cycle)

## Configuration

**From settings:**
- `DATA_MANAGER_BACKTEST_SPEED`: Speed multiplier (0 = data-driven, >0 = clock-driven)

**Speed Examples:**
- `0`: As fast as possible (data-driven)
- `1`: Real-time speed (1 second = 1 second)
- `60`: 1 minute per second (60x faster)
- `360`: 6 hours per minute (fast day simulation)

## Timing & Performance

**Clock Thread (speed > 0):**
- Update rate: 100 Hz (10ms sleep)
- Precision: ~10ms time resolution

**Merge Worker:**
- Poll rate: 10ms when waiting for data
- Blocking on queue.get() with 0.1s timeout
- Immediate processing when data available

**Queue Management:**
- Thread-safe input queues per stream
- Single thread-safe output queue
- No locks during data merging (uses pending_items dict)

## Edge Cases Handled

### 1. Stale Data
```python
# Skip data older than current time
if data.timestamp < current_time:
    logger.debug("Skipping stale data")
    continue  # Fetch next item
```

### 2. Market Close Detection
```python
# Pause at market close (upkeep handles transitions)
if current_time >= close_time + 1min:
    logger.debug("Market close reached, waiting")
    time.sleep(0.1)
    continue
```

### 3. System Paused
```python
# Wait while system is paused
while not system_manager.is_running():
    time.sleep(0.1)
    if shutdown.is_set():
        return
```

### 4. Stream Exhaustion
```python
# Handle stream ending (None sentinel)
if data is None:
    pending_items[stream_key] = None
    deregister_stream(symbol, stream_type)
```

### 5. No SystemManager
```python
# Fail-safe: yield data without time advancement
if system_manager is None:
    logger.error("SystemManager not available")
    output_queue.put(data)
    continue
```

## Potential Simplifications

1. **Merge clock logic into merge worker** - Remove separate clock thread
2. **Extract filtering logic** - Separate market hours filter class
3. **Simplify mode switching** - Single code path for both modes
4. **Remove quality updates** - Let upkeep thread handle exclusively
5. **Event-based coordination** - Replace polling with events

## Dependencies

**External modules:**
- `gap_detection`: Detects missing bars for quality calculation
- `queue`: Thread-safe queue for inter-thread communication
- `heapq`: Not used (could optimize oldest-finding with heap)

**System managers:**
- `SystemManager`: Mode checks, state checks, stop() control
- `TimeManager`: Time operations, trading hours, time advancement
- `DataManager`: Stream setup, data feeding

**Shared state:**
- `SessionData`: Thread-safe container for market data
- `_active_streams`: Dict of input queues (protected by `_lock`)
- `_pending_items`: Staging area for merge worker (worker-only, no lock needed)

## Critical Architecture Rules

### 1. Time Advancement
**ONLY the stream coordinator advances time forward in backtest mode.**
- Upkeep thread: Can reset to market open (day transition)
- DataManager: Never touches time
- AnalysisEngine: Only queries time

### 2. Bar Timestamp Lag
**Bar timestamps represent interval START, not END:**
- 1m bar @ 09:30:00 = interval [09:30:00 - 09:30:59]
- Time set to 09:31:00 when yielding (bar complete)
- This matches real-world streaming behavior

### 3. 1m Bars Only
**Stream coordinator only handles 1m bars (and ticks/quotes):**
- Derived bars (5m, 15m) computed by upkeep thread
- Validation in SystemManager and DataManager prevents other intervals
- Configuration must specify "1m" for bar streams

### 4. No Sorting Overhead
**Data flows through in sorted order:**
- Parquet files pre-sorted by timestamp
- Coordinator merges with simple comparison
- No heapq needed for small stream counts

## Testing Recommendations

After any modification:
1. Test chronological ordering (multiple symbols)
2. Test time advancement (both modes: speed=0, speed>0)
3. Test market hours filtering (pre-market, after-hours)
4. Test stream exhaustion handling
5. Test system pause/resume
6. Test EOD detection and coordinator pause
7. Test quality updates
8. Test multiple trading days

---

**Summary:** The coordinator is the central timing controller for backtesting, responsible for chronological merging and the ONLY time advancement forward. All backtest timing flows through this thread.
