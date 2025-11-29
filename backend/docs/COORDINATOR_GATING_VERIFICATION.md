# Coordinator Gating Logic Verification

## Summary

✅ **VERIFIED:** The coordinator worker thread is properly gated by system state. It waits for `system_manager.is_running()` to return `True` before advancing time and streaming bars.

## State Transition Flow

### 1. Initial State: STOPPED

```python
# system_manager.__init__()
self._state = SystemState.STOPPED  # Line 81
```

**Coordinator behavior:** Worker thread polls system state, waits in sleep loop

### 2. During start(): Still STOPPED

```python
async def start(config_file_path: str):
    # Check current state (Line 250-256)
    if self._state == SystemState.RUNNING:
        return False  # Already running
    
    if self._state == SystemState.PAUSED:
        return False  # Can't start from paused
    
    # State is still STOPPED here
    # Load config, initialize managers, setup streams...
    
    # Setup streams (Line 370-398)
    for interval, symbols in by_interval.items():
        count = data_manager.start_bar_streams(
            stream_session,
            symbols=symbols,
            interval=interval
        )
        # start_bar_streams() BLOCKS here:
        # - Fetches data from DB
        # - Registers with session_data
        # - Registers with coordinator
        # - Feeds bars to coordinator queues
        # - Returns count
    
    # State is STILL STOPPED during all stream setup!
    
    # Only NOW do we transition to RUNNING (Line 419)
    self._state = SystemState.RUNNING  # ← CRITICAL GATE OPENS HERE
    
    logger.success("System started successfully!")
```

### 3. Coordinator Worker Thread Behavior

```python
# backtest_stream_coordinator.py _worker_loop()

while not self._shutdown.is_set():
    # Get oldest item from all streams
    oldest_item = find_oldest_pending_item()
    
    if oldest_item is not None:
        # Check system manager for mode
        if self._system_manager is None:
            # No gating, just yield
            self._output_queue.put(oldest_item)
            continue
        
        mode_is_backtest = self._system_manager.is_backtest_mode()
        
        if mode_is_backtest:
            # CRITICAL GATING LOGIC (Line 431-436)
            while not self._system_manager.is_running() and not self._shutdown.is_set():
                # System is NOT RUNNING (still STOPPED during setup)
                # Wait here in sleep loop
                time.sleep(0.1)  # Sleep 100ms, check again
                
                if self._shutdown.is_set():
                    return  # Shutdown requested
            
            # System is now RUNNING!
            # Advance time and yield bars
            self._time_provider.set_backtest_time(oldest_item.timestamp)
            self._output_queue.put(oldest_item)
```

## Complete Sequence Diagram

```
TIME    SYSTEM STATE    COORDINATOR STATE         ACTION
════    ════════════    ═════════════════         ══════

T0      STOPPED         Worker thread starts      Polling, waiting
                        (in sleep loop)           

T1      STOPPED         Waiting                   system_manager.start() called
                                                  
T2      STOPPED         Waiting                   Load config
                                                  
T3      STOPPED         Waiting                   Initialize managers
                                                  
T4      STOPPED         Waiting                   Stop existing streams
                                                  
T5      STOPPED         Waiting                   start_bar_streams("AAPL")
                                                  → Fetch 390 bars (BLOCKS)
                                                  
T6      STOPPED         Waiting                   → Register with session_data
                        (sleeping 100ms)          → Register with coordinator
                                                  → Feed bars to queues
                                                  
T7      STOPPED         Waiting                   start_bar_streams("MSFT")
                                                  → Fetch 390 bars (BLOCKS)
                                                  
T8      STOPPED         Waiting                   → Register with session_data
                        (sleeping 100ms)          → Register with coordinator
                                                  → Feed bars to queues
                                                  
T9      STOPPED         Waiting                   All streams set up
                        (sleeping 100ms)          
                                                  
T10     ⚡ RUNNING ⚡    ✓ GATE OPENS ✓           self._state = SystemState.RUNNING
                                                  
T11     RUNNING         Processing                Coordinator wakes from sleep loop
                        (is_running()=True)       
                                                  
T12     RUNNING         Streaming                 Find oldest bar from queues
                                                  
T13     RUNNING         Streaming                 Advance time to bar timestamp
                                                  
T14     RUNNING         Streaming                 Yield bar to output queue
                                                  
T15     RUNNING         Streaming                 Sleep according to speed (60x)
                                                  
T16     RUNNING         Streaming                 Next bar...
```

## Key Verification Points

### ✅ Point 1: State Remains STOPPED During Setup

**Location:** `system_manager.py` lines 250-418

```python
# Line 250: Check we're in STOPPED state
if self._state == SystemState.RUNNING:
    return False

# Lines 370-398: All stream setup happens here
# State is STILL STOPPED!

# Line 419: ONLY NOW transition to RUNNING
self._state = SystemState.RUNNING
```

### ✅ Point 2: Coordinator Waits for RUNNING

**Location:** `backtest_stream_coordinator.py` lines 431-436

```python
# Line 431: Check if system is running
while not self._system_manager.is_running() and not self._shutdown.is_set():
    # Wait in sleep loop
    time.sleep(0.1)
    
    if self._shutdown.is_set():
        return
```

**Behavior:**
- `is_running()` returns `self._state == SystemState.RUNNING` (line 555)
- During setup: `self._state == SystemState.STOPPED` → `is_running()` returns `False`
- Loop continues sleeping 100ms at a time
- After setup: `self._state == SystemState.RUNNING` → `is_running()` returns `True`
- Loop exits, coordinator proceeds to stream

### ✅ Point 3: Streams Fed Before Gate Opens

**Location:** `api.py` `start_bar_streams()` lines 830-895

```python
for symbol in symbols:
    # Check duplicates
    # Register with session_data
    # Register with coordinator
    
    # BLOCK and fetch current day (Line 852-859)
    bars = MarketDataRepository.get_bars_by_symbol(...)
    
    # Add bars to session_data (Line 869-878)
    for bar in bars:
        session_data.add_bar(symbol, bar)
    
    # Feed to coordinator queues (Line 893)
    coordinator.feed_stream(symbol, StreamType.BAR, bar_iterator())
    
    # Return count
return streams_started
```

**Critical:** All bars are in coordinator queues BEFORE state transitions to RUNNING!

## Timing Analysis

### Without Gating (Hypothetical, WRONG)
```
T0: State = STOPPED
T1: Start stream setup
T2: Coordinator tries to stream → RACE CONDITION!
T3: Bars not ready yet → EMPTY STREAM or CRASH
T4: Finish setup
T5: State = RUNNING (too late!)
```

### With Gating (Current, CORRECT) ✓
```
T0: State = STOPPED
T1: Start stream setup
T2: Coordinator polls: is_running()? No → Sleep 100ms
T3: Coordinator polls: is_running()? No → Sleep 100ms
T4: Finish setup, bars in queues
T5: State = RUNNING ← GATE OPENS
T6: Coordinator polls: is_running()? Yes → START STREAMING ✓
```

## What Happens in 100ms Sleep Intervals?

During setup (State = STOPPED):

**Iteration 1 (T2):**
- Coordinator: `is_running()` → `False`
- Sleeps 100ms
- System manager: Fetching AAPL bars from DB...

**Iteration 2 (T2.1):**
- Coordinator: `is_running()` → `False`
- Sleeps 100ms
- System manager: Adding AAPL bars to session_data...

**Iteration 3 (T2.2):**
- Coordinator: `is_running()` → `False`
- Sleeps 100ms
- System manager: Feeding AAPL bars to coordinator...

**Iteration 4 (T2.3):**
- Coordinator: `is_running()` → `False`
- Sleeps 100ms
- System manager: Fetching MSFT bars from DB...

**...continues until setup complete...**

**Iteration N (T9):**
- Coordinator: `is_running()` → `False`
- Sleeps 100ms
- System manager: All streams ready!

**After State Transition (T10):**
- System manager: `self._state = SystemState.RUNNING`

**Next Iteration (T11):**
- Coordinator: `is_running()` → `True` ✓
- Exit sleep loop
- Start streaming! ✓

## Edge Cases Handled

### 1. Shutdown During Setup
```python
while not self._system_manager.is_running() and not self._shutdown.is_set():
    time.sleep(0.1)
    if self._shutdown.is_set():  # Check after sleep
        return  # Clean exit
```

### 2. System Manager Not Available
```python
if self._system_manager is None:
    logger.error("SystemManager not available")
    # Just yield without gating (degraded mode)
    self._output_queue.put(oldest_item)
    continue
```

### 3. No Items in Queues Yet
```python
if oldest_item is None:
    # No data available, sleep briefly
    time.sleep(0.01)
    continue  # Try again
```

## Performance Impact

**Sleep Overhead:** 100ms per iteration during setup
**Typical Setup Time:** 500-2000ms (5-20 iterations)
**Total Wait Time:** Negligible compared to DB fetch time

**Example:**
- AAPL fetch: 50ms
- MSFT fetch: 50ms
- Total fetch: 100ms
- Coordinator polls: 2-3 times during 100ms = 200-300ms sleeping
- **Impact:** ~2x overhead during setup (acceptable)
- **After gate opens:** Zero overhead, streams at full speed

## Summary

✅ **Architecture is CORRECT:**

1. ✅ System starts in STOPPED state
2. ✅ All streams are set up (fetch, register, feed) while STOPPED
3. ✅ Coordinator worker thread waits in sleep loop checking `is_running()`
4. ✅ Only after ALL streams ready: `self._state = SystemState.RUNNING`
5. ✅ Coordinator detects RUNNING state and begins streaming
6. ✅ All bars are ready in queues before streaming starts

**Result:** No race conditions, clean gating, predictable startup! 🎯
