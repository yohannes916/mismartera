# Data Upkeep Thread - Complete Lifecycle Analysis

## Overview
The `DataUpkeepThread` is a background thread responsible for maintaining data quality and managing session lifecycle in the trading system. It coordinates with the main stream coordinator to ensure data integrity throughout the trading day.

## Thread Lifecycle

### 1. Creation & Initialization
**Location:** `data_upkeep_thread.py:46-122` (`__init__`)
**Created by:** `DataManager` when starting data streams
**Called from:** `app/managers/data_manager/api.py`

```python
# Initialization happens in DataManager.start_bar_streams() or similar
upkeep_thread = DataUpkeepThread(
    session_data=self._session_data,
    system_manager=self.system_manager,
    data_manager=self,
    data_repository=None
)
```

**What happens during initialization:**
- Stores references to `session_data`, `system_manager`, `data_manager`
- Loads configuration from `session_config` (check intervals, retry settings, derived intervals)
- Scales check interval based on backtest speed multiplier
- Builds **stream inventory** (what data types each symbol has: bars, ticks, quotes)
- Creates `PrefetchWorker` instance (a 3rd thread for data loading)
- Initializes tracking variables (`_failed_gaps`, `_session_activated_for_day`)

### 2. Starting the Thread
**Location:** `data_upkeep_thread.py:290-306` (`start()`)

```python
upkeep_thread.start()  # Called by DataManager
```

**What happens:**
- Sets `_running = True` and clears shutdown event
- Creates a daemon thread with target `_upkeep_worker`
- Thread name: `"DataUpkeep"`
- Starts the thread (now running independently)

### 3. Main Worker Execution
**Location:** `data_upkeep_thread.py:334-347` (`_upkeep_worker`)

**Flow:**
```
_upkeep_worker()
    └─> try:
            _run_upkeep_loop()  # The main loop
        except Exception:
            log critical error
        finally:
            cleanup
```

### 4. The Main Upkeep Loop
**Location:** `data_upkeep_thread.py:349-557` (`_run_upkeep_loop`)

This is the **heart** of the thread. It runs continuously in a `while` loop.

**Loop Structure:**
```python
while not self._shutdown.is_set():
    1. Get current time from TimeManager
    2. Get trading session for current date
    
    3. CHECK: End-of-Day (EOD) Detection
       if current_time >= market_close:
           → Deactivate session
           → Check if backtest complete
           → Advance to next trading day
           → Activate session for new day
           → Launch prefetch
           → continue (skip to next cycle)
    
    4. CHECK: Initial Activation
       elif not session_activated_for_day:
           if current_time >= market_open:
               → Activate session
               → Launch prefetch for current day
               → Wait for prefetch completion
    
    5. CHECK: Streams Exhausted Early?
       if session_active and no_active_streams and before_close:
           → Force advance time to market close
           → continue (let next iteration handle EOD)
    
    6. REGULAR UPKEEP: Data Quality Tasks
       if session_active:
           → _run_symbol_upkeep()
    
    7. WAIT: Event-driven with timeout fallback
       → Wait for data arrival event (1 second timeout)
       → Ensures frequent EOD checking
```

### 5. Symbol Upkeep Tasks
**Location:** `data_upkeep_thread.py:559-643` (`_run_symbol_upkeep`, `_upkeep_symbol`)

**For each active symbol:**
```
_upkeep_symbol(symbol)
    0. _ensure_base_bars()
       ├─ Check if symbol has bar stream (1m or 1s)
       ├─ If not, but has tick stream:
       │  └─> _create_bars_from_ticks() [lines 948-1066]
       └─ Return True if base data available
    
    1. _update_bar_quality() [lines 645-715]
       ├─ Get trading session times
       ├─ Detect gaps using gap_detection module
       ├─ Calculate quality = (actual_bars / expected_bars) * 100
       └─ Update symbol_data.bar_quality
    
    2. _check_and_fill_gaps() [lines 717-797]
       ├─ Detect gaps in 1m bars
       ├─ Merge with previously failed gaps
       ├─ For each gap:
       │  └─> _fill_gap() [lines 799-889]
       │      ├─ Load bars from Parquet storage
       │      ├─ Convert to BarData objects
       │      └─ Insert using add_bars_batch(insert_mode="gap_fill")
       └─ Track remaining failed gaps
    
    3. _update_derived_bars() [lines 891-946]
       ├─ Check if 1m bars were updated
       ├─ For each configured derived interval (5m, 15m, etc.):
       │  ├─ Skip if interval already streamed
       │  ├─ Check if enough 1m bars available
       │  └─> compute_all_derived_intervals()
       └─ Update symbol_data.bars_derived
```

### 6. Stopping the Thread
**Location:** `data_upkeep_thread.py:308-332` (`stop()`)

```python
upkeep_thread.stop(timeout=5.0)
```

**What happens:**
- Sets `_shutdown` event (signals loop to exit)
- Shuts down prefetch worker
- Waits for thread to join (max: timeout seconds)
- Sets `_running = False`

## Thread Coordination

### With Stream Coordinator
- **Shared resource:** `session_data` (protected by `_lock`)
- **Data flow:** Stream coordinator adds data → upkeep thread analyzes quality
- **Event-driven:** Data arrival triggers `_data_arrival_event` → wakes upkeep thread

### With TimeManager
- **Single source of truth** for current time and trading hours
- Upkeep thread queries `time_mgr.get_current_time()` every cycle
- Advances time during EOD transitions

### With PrefetchWorker (3rd thread)
- **Triggered by:** EOD transitions and initial activation
- **Purpose:** Load historical bars for the new trading day
- **Coordination:** Upkeep thread launches prefetch, optionally waits for completion

## Key Responsibilities Summary

### Session Lifecycle Management (CRITICAL)
- Detect end-of-day based on market close time
- Deactivate session at EOD
- Advance backtest time to next trading day
- Activate session for new day
- Launch data prefetch for new day

### Data Quality Maintenance (REGULAR)
- Calculate bar quality metrics
- Detect gaps in bar data
- Fill missing bars from Parquet storage
- Compute derived intervals (5m, 15m from 1m bars)
- Create bars from tick streams if needed

### Edge Case Handling
- Streams exhausted before market close → force advance to close
- No bar stream but tick stream available → create bars from ticks
- Gap filling with retry logic and max retry limits
- Skip derived intervals if already being streamed

## Configuration

**From session_config.session_data_config.data_upkeep:**
- `check_interval_seconds`: Base time between upkeep cycles (default: 60s)
- `retry_missing_bars`: Enable gap filling (default: True)
- `max_retries`: Max attempts to fill a gap (default: 3)
- `derived_intervals`: Which intervals to compute [5, 15, ...] (minutes)
- `auto_compute_derived`: Enable derived bar computation (default: True)

**Speed scaling:**
- `check_interval = base_interval / speed_multiplier`
- At 360x speed: 60s / 360 = 0.167s (~6 checks/second)
- Minimum: 0.1s to avoid hammering

## Timing & Performance

**First cycle:** Runs immediately after start (0.1s delay)
- Purpose: Provide instant quality feedback on system start

**Subsequent cycles:** Event-driven with 1-second timeout
- Wakes immediately when new data arrives
- Falls back to 1-second timeout for frequent EOD checking
- Ensures EOD detected within 1 second of market close

**Logging frequency:**
- Every 10th cycle: Logs session status and EOD check details
- Every symbol: Logs quality metrics after calculation
- All events: EOD transitions, activations, prefetch launches

## Potential Simplifications

1. **Separate EOD logic** into its own class/method
2. **Extract prefetch coordination** - currently mixed with lifecycle
3. **Simplify upkeep tasks** - too many responsibilities in one method
4. **Remove tick-to-bar conversion** - handle in separate processor
5. **Stream inventory** - could be managed by DataManager instead
6. **Gap filling** - could be on-demand rather than polling

## Dependencies

**External modules:**
- `gap_detection`: Detects missing bars in time series
- `quality_checker`: Calculates session quality metrics  
- `derived_bars`: Computes higher interval bars (5m, 15m from 1m)
- `prefetch_worker`: Loads historical data (runs in separate thread)
- `parquet_storage`: Reads bars from Parquet files

**System managers:**
- `SystemManager`: Provides TimeManager access, mode checks, stop()
- `TimeManager`: Single source of truth for time and trading hours
- `DataManager`: Access to bar data methods

**Shared state:**
- `SessionData`: Thread-safe container for market data (bars, ticks, quotes)
