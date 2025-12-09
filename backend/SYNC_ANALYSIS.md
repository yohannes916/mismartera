# Thread Synchronization & Performance Tracking Analysis

## Current State

### 1. StreamSubscription Infrastructure ✅
**File:** `app/threads/sync/stream_subscription.py`

**Design:** Mode-aware synchronization with three modes:
- `data-driven`: Blocks indefinitely (`wait()` with no timeout)
- `clock-driven`: Timeout-based with overrun detection  
- `live`: Timeout-based

**Features:**
- One-shot pattern: signal → wait → reset
- Overrun detection (clock-driven mode only)
- Thread-safe using `threading.Event`

### 2. Subscriptions Created ✅
**File:** `app/managers/system_manager/api.py:541-556`

Mode determined by config:
```python
if speed_multiplier == 0:
    subscription_mode = "data-driven"
elif mode == "live":
    subscription_mode = "live"
else:
    subscription_mode = "clock-driven"
```

**Created subscription:**
- `coordinator->data_processor` (StreamSubscription)

### 3. DataProcessor Behavior ✅
**File:** `app/threads/data_processor.py:290-360`

**Flow:**
1. Waits on notification queue (line 309)
2. Processes derived bars
3. **Signals ready to coordinator** (line 334) via `subscription.signal_ready()`
4. Notifies analysis engine

### 4. SessionCoordinator Behavior ⚠️ **ISSUE FOUND**
**File:** `app/threads/session_coordinator.py:2095-2270`

**Current flow:**
1. Advances time (data-driven or clock-driven)
2. Processes bars from queues (line 2250)
3. For each bar:
   - Adds to session_data
   - **Notifies data_processor** (line 3518) - non-blocking queue
   - Notifies quality_manager (line 3525)
4. **Continues immediately** - NO WAIT

**Missing:** Coordinator never calls `subscription.wait_until_ready()`!

## Problems Identified

### ❌ Problem 1: No Synchronization in Data-Driven Mode

**Expected behavior (user description):**
> session_coordinator does not push more data until data_processor signals that it is ready

**Actual behavior:**
- Coordinator notifies processor (line 3518)
- Coordinator **immediately continues** to next iteration
- No wait for processor completion
- StreamSubscription exists but **never used by coordinator**!

**Impact:**
- Data-driven mode behaves same as clock-driven (no blocking)
- DataProcessor may lag behind coordinator
- Session may flood processor with data faster than it can process

### ❌ Problem 2: Lag Detection Not Mode-Aware

**File:** `app/threads/session_coordinator.py:3415-3436`

**Current behavior:**
- Lag detection happens in BOTH modes
- Deactivates session if lag > threshold (default 60s)
- No differentiation between modes

**Problem:**
- In data-driven mode, lag shouldn't matter (we wait anyway)
- In clock-driven mode, lag detection makes sense
- Current implementation may inappropriately deactivate in data-driven

### ✅ Good: Performance Tracking Exists

**Lag tracking:**
- Per-symbol counters: `_symbol_check_counters` (line 169)
- Check interval: `_catchup_check_interval` (default 10 bars)
- Threshold: `_catchup_threshold` (default 60 seconds)
- Deactivates/reactivates session based on lag

**Overrun tracking:**
- StreamSubscription tracks overruns (line 85-91)
- Only in clock-driven mode
- Logs warning when producer signals before consumer resets

**Metrics:**
- PerformanceMetrics used throughout
- `metrics.record_data_processor()` called (data_processor.py:350)

## Recommended Fixes

### Fix 1: Add Coordinator Wait in Data-Driven Mode

**Location:** `session_coordinator.py` after line 2253

```python
# After processing bars
bars_processed = self._process_queue_data_at_timestamp(next_time)
total_bars_processed += bars_processed

# WAIT for processor to finish (data-driven mode only)
if self.mode == "backtest" and self.session_config.backtest_config:
    speed_multiplier = self.session_config.backtest_config.speed_multiplier
    
    if speed_multiplier == 0 and bars_processed > 0:
        # Data-driven: Block until processor ready
        if self._processor_subscription:
            logger.debug("Waiting for processor to finish...")
            self._processor_subscription.wait_until_ready()
            self._processor_subscription.reset()
            logger.debug("Processor ready, continuing")
```

### Fix 2: Make Lag Detection Mode-Aware

**Location:** `session_coordinator.py:3415-3436`

```python
# Only check lag in clock-driven/live modes
if self._should_check_lag():
    if self._symbol_check_counters[symbol] % self._catchup_check_interval == 0:
        # existing lag detection code
        ...

def _should_check_lag(self) -> bool:
    """Lag detection only in clock-driven/live modes."""
    if self.mode == "live":
        return True
    if self.mode == "backtest" and self.session_config.backtest_config:
        return self.session_config.backtest_config.speed_multiplier > 0
    return False
```

### Fix 3: Analysis Engine Synchronization

**Check if similar pattern exists for processor->analysis**

DataProcessor has `_analysis_subscription` (line 126) but may not be using it.
Need to verify if analysis engine also needs wait logic.

## Summary (AFTER FIXES)

| Component | Data-Driven | Clock-Driven | Status |
|-----------|-------------|--------------|--------|
| StreamSubscription | ✅ Blocks indefinitely | ✅ Timeout + overrun | ✅ Implemented |
| DataProcessor signals | ✅ Signals ready | ✅ Signals ready | ✅ Implemented |
| **Coordinator waits** | ✅ **WAITS for processor** | N/A (free-running) | ✅ **FIXED** |
| **Processor waits** | ✅ **WAITS for analysis** | N/A (async) | ✅ **FIXED** |
| **Analysis signals** | ✅ **SIGNALS to processor** | ✅ Signals | ✅ **WIRED** |
| Lag detection | ✅ Skipped (not needed) | ✅ Runs correctly | ✅ **FIXED** |
| Overrun detection | N/A (blocks) | ✅ Tracks in subscription | ✅ Implemented |
| Performance metrics | ✅ Recording | ✅ Recording | ✅ Implemented |

## Fixes Implemented

### ✅ Fix 1: Coordinator Waits for Processor (Data-Driven)
**File:** `session_coordinator.py:2258-2277`

```python
if speed_multiplier == 0:
    # DATA-DRIVEN: Wait for processor to finish before continuing
    if bars_processed > 0 and self._processor_subscription:
        self._processor_subscription.wait_until_ready()
        self._processor_subscription.reset()
```

### ✅ Fix 2: Lag Detection Mode-Aware
**File:** `session_coordinator.py:3433, 3560-3578`

- Added `_should_check_lag()` helper method
- Skips lag detection in data-driven mode (since we block anyway)
- Only runs in clock-driven and live modes

### ✅ Fix 3: Processor Waits for Analysis Engine (Data-Driven)
**File:** `data_processor.py:338-345, 554-572`

```python
if self._should_wait_for_analysis():
    if self._analysis_subscription:
        self._analysis_subscription.wait_until_ready()
        self._analysis_subscription.reset()
```

### ✅ Fix 4: Analysis Subscription Created and Wired
**File:** `system_manager/api.py:562-587`

- Created `analysis_subscription` 
- Wired bidirectionally: processor ↔ analysis engine
- Mode-aware (data-driven blocks, others async)

## Synchronization Chain (Data-Driven Mode)

```
SessionCoordinator
  ↓ (notify)
  ↓ bars available
  ↓
DataProcessor
  ↓ (process derived bars)
  ↓ (notify)
  ↓
AnalysisEngine
  ↓ (run strategies)
  ↓ (signal ready) ← WAITS HERE
  ↑
DataProcessor
  ↓ (signal ready) ← WAITS HERE
  ↑
SessionCoordinator
  ↓ (continues to next bar)
```

Each stage BLOCKS until downstream completes, ensuring:
- No data flooding
- Deterministic execution
- Full subscriber processing before next data
- Proper backpressure
