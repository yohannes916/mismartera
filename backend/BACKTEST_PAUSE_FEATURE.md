# Backtest Pause Feature

## Overview

The backtest pause feature allows stopping and resuming the streaming/time advancement in both data-driven and clock-driven backtest modes. This is useful for:
- Debugging strategies at specific points
- Dynamic symbol addition (automatic internal pause)
- Manual inspection of system state
- Step-by-step backtesting

## Public API

### SystemManager Methods (Recommended)

```python
system_manager.pause()      # Pause backtest (updates state to PAUSED)
system_manager.resume()     # Resume backtest (updates state to RUNNING)
system_manager.is_paused()  # Check if paused (returns bool)
system_manager.get_state()  # Get SystemState (STOPPED/RUNNING/PAUSED)
```

**Usage:**
```python
from app.managers.system_manager import get_system_manager

system_manager = get_system_manager()

# Pause
system_manager.pause()

# Check status
if system_manager.is_paused():
    print("Backtest is paused")
    print(f"State: {system_manager.get_state()}")  # SystemState.PAUSED

# Resume
system_manager.resume()
```

### SessionCoordinator Methods (Lower-Level)

For direct access (not typically needed):
```python
coordinator = system_manager.get_coordinator()
coordinator.pause_backtest()   # Pause streaming/time advancement
coordinator.resume_backtest()  # Resume streaming
coordinator.is_paused()        # Check if currently paused (returns bool)
```

## System State Management

The pause feature integrates with the SystemManager's state machine:

```
STOPPED ──start()──> RUNNING ──pause()──> PAUSED
   ↑                    ↓                    ↓
   └─────stop()────────┘        resume()────┘
```

**State Transitions:**
- `start()`: STOPPED → RUNNING
- `pause()`: RUNNING → PAUSED (backtest only)
- `resume()`: PAUSED → RUNNING
- `stop()`: RUNNING/PAUSED → STOPPED

**State Queries:**
- `is_running()`: True if RUNNING (not stopped, not paused)
- `is_stopped()`: True if STOPPED
- `is_paused()`: True if PAUSED
- `get_state()`: Returns SystemState enum value

**Key Points:**
- Can only pause when RUNNING
- Can only resume when PAUSED
- Pause only applies to backtest mode (ignored in live)
- Threads remain alive when paused (blocked on event)
- State persists in `system_manager._state`

## How It Works

### Implementation Details

**Event-Based Control:**
- Uses `threading.Event` for thread-safe pause/resume
- Event name: `_stream_paused`
- Initially set (not paused)
- Cleared when paused, set when running

**Pause Location in Streaming Loop:**
```python
# Line 2223 in session_coordinator.py
while not self._stop_event.is_set():
    iteration += 1
    current_time = self._time_manager.get_current_time()
    
    # Process pending symbols
    self._process_pending_symbols()
    
    # PAUSE CHECK HERE - blocks if paused
    self._stream_paused.wait()  # ← Blocks until event is set
    
    # Time advancement (doesn't execute while paused)
    # Bar processing (doesn't execute while paused)
    # Synchronization (doesn't execute while paused)
```

### What Gets Paused

When `pause_backtest()` is called, the streaming loop blocks **before**:

1. ✅ **Time advancement** (both modes)
   - Data-driven: No jump to next bar timestamp
   - Clock-driven: No 1-minute interval advancement

2. ✅ **Bar processing**
   - No bars consumed from queues
   - No data added to session_data
   - No notifications to processor

3. ✅ **Processor synchronization** (data-driven)
   - No wait for processor
   - Processor not signaled

4. ✅ **Clock delays** (clock-driven)
   - No sleep delays applied
   - No simulated real-time advancement

### What Continues Running

When paused, these components continue:

- ✅ **DataProcessor thread** - keeps running but idle (no new notifications)
- ✅ **AnalysisEngine thread** - keeps running but idle (no new notifications)
- ✅ **DataQualityManager thread** - keeps running but idle
- ✅ **Live data streams** - if in hybrid mode (backtest with live data)

## Mode-Specific Behavior

### Data-Driven Mode (speed_multiplier = 0)

**Normal Flow:**
```
Get current time → Process pending → Check pause → Get next timestamp → 
Advance time → Process bars → Wait for processor → Next iteration
```

**When Paused:**
```
Get current time → Process pending → Check pause → BLOCKED
                                         ↑
                                    Resume here
```

**Impact:**
- Time frozen at current bar
- No bar processing
- Processor idle (waiting for notifications)
- Analysis engine idle

### Clock-Driven Mode (speed_multiplier > 0)

**Normal Flow:**
```
Get current time → Process pending → Check pause → Calculate next time (+ 1 min) → 
Advance time → Process bars → Apply delay → Next iteration
```

**When Paused:**
```
Get current time → Process pending → Check pause → BLOCKED
                                         ↑
                                    Resume here
```

**Impact:**
- Clock frozen (no 1-minute advances)
- No bar processing
- No delays applied
- Real-time clock continues (wall time passes, but market time frozen)

## Use Cases

### 1. Manual Debugging

```python
from app.managers.system_manager import get_system_manager

# Use SystemManager API (recommended)
system_manager = get_system_manager()
time_manager = system_manager.get_time_manager()

# Set up a timer or condition
if time_manager.get_current_time().time() == time(10, 30):
    # Pause using SystemManager
    system_manager.pause()
    
    # Verify state
    assert system_manager.is_paused()
    assert system_manager.get_state() == SystemState.PAUSED
    
    # Inspect state, strategies, positions
    print_debug_info()
    
    # Resume when ready
    system_manager.resume()
    
    # Verify state changed back
    assert system_manager.is_running()
    assert system_manager.get_state() == SystemState.RUNNING
```

### 2. Dynamic Symbol Addition (Automatic)

**Internal use - happens automatically:**

```python
# When adding symbol mid-backtest
async def _load_and_catchup_symbol(self, symbol: str):
    # Pause streaming automatically
    self._stream_paused.clear()
    
    # Load historical data
    # Catch up to current time
    
    # Resume automatically
    self._stream_paused.set()
```

User sees:
```bash
$ data add TSLA
✓ Symbol TSLA queued for addition
  Backtest mode: Streaming will pause, load historical data, and catch up
```

### 3. Step-by-Step Execution

```python
# Process one bar at a time
coordinator.pause_backtest()  # Start paused

while not done:
    coordinator.resume_backtest()
    time.sleep(0.1)  # Let one iteration run
    coordinator.pause_backtest()
    
    # Inspect state after each bar
    analyze_state()
```

## Thread Safety

- ✅ **Thread-safe**: Can call from any thread
- ✅ **No race conditions**: Uses `threading.Event`
- ✅ **Blocking behavior**: `wait()` blocks until event is set
- ✅ **Atomic operations**: `clear()` and `set()` are atomic

## Performance Impact

### When Paused
- **CPU**: Near zero - thread blocked on event
- **Memory**: No change - state preserved
- **Time**: Wall time continues, market time frozen

### Pause/Resume Overhead
- **Pause**: < 1ms (atomic event clear)
- **Resume**: < 1ms (atomic event set + thread wake)
- **Check**: < 0.1ms (event wait when not paused)

## Limitations

1. **Backtest mode only**: Ignored in live mode
   ```python
   # In live mode
   coordinator.pause_backtest()  # Logs warning, does nothing
   ```

2. **Blocks entire streaming loop**: Can't pause individual symbols
   - All symbols pause together
   - All time advancement stops

3. **No partial state**: Either fully running or fully paused
   - Can't pause time but continue processing
   - Can't pause one thread but not others

## Testing

**Unit Tests:** `tests/test_dynamic_symbols.py`

```python
def test_stream_paused_event():
    """Test that pause event controls streaming loop."""
    
def test_pause_blocks_time_advancement():
    """Test that pause prevents time from advancing."""
    
def test_pause_blocks_bar_processing():
    """Test that pause prevents bar processing."""
```

## Future Enhancements

Possible improvements:

1. **CLI commands**
   ```bash
   $ backtest pause
   $ backtest resume
   $ backtest status
   ```

2. **Conditional pause**
   ```python
   coordinator.pause_on_condition(lambda: time == target_time)
   ```

3. **Per-symbol pause**
   ```python
   coordinator.pause_symbol("AAPL")  # Pause only AAPL
   ```

4. **Pause callbacks**
   ```python
   coordinator.on_pause(callback)
   coordinator.on_resume(callback)
   ```

## Summary

| Feature | Data-Driven | Clock-Driven | Status |
|---------|-------------|--------------|--------|
| Pause time advancement | ✅ | ✅ | Implemented |
| Pause bar processing | ✅ | ✅ | Implemented |
| Thread-safe | ✅ | ✅ | Implemented |
| SystemManager API | ✅ | ✅ | ✅ **Implemented** |
| System state (PAUSED) | ✅ | ✅ | ✅ **Implemented** |
| SessionCoordinator API | ✅ | ✅ | ✅ Implemented |
| CLI commands | ❌ | ❌ | Future |
| Conditional pause | ❌ | ❌ | Future |

**API Hierarchy:**
- **SystemManager** (Recommended): `pause()`, `resume()`, `is_paused()`, `get_state()`
- **SessionCoordinator** (Lower-level): `pause_backtest()`, `resume_backtest()`, `is_paused()`
