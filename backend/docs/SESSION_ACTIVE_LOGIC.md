# Session Active Logic

## Definition

`session_data.is_session_active()` determines whether a trading session is currently active based on delegated checks to other managers.

## Logic

A session is considered **active** when **ALL** of the following are true:

### 1. ✅ Session Not Explicitly Ended (self)
```python
self.session_ended == False
```
Session data checks its own `session_ended` flag.

### 2. ✅ System State = RUNNING (system_manager)
```python
system_manager.is_running() == True
```
Delegates to system_manager to check if system is in RUNNING state.

### 3. ✅ Market is Open (data_manager)
```python
data_manager.check_market_open() == True
```
Delegates to data_manager's clean API to check if market is currently open.

## Key Points

**✓ No Active Symbols Required**
- Session can be active even with 0 symbols streaming
- Active = System running + Market open + Not ended

**✓ Proper Delegation**
- System state: `system_manager`
- Market status: `data_manager`  
- Session ended: `self`

**✓ Single Responsibility**
- Each manager checks what it's responsible for
- session_data doesn't duplicate market/system logic

## Implementation

```python
def is_session_active(self) -> bool:
    """Check if a session is currently active."""
    
    # 1. Check if session explicitly ended (self)
    if self.session_ended:
        return False
    
    # 2. Check system state - must be RUNNING (system_manager)
    system_manager = get_system_manager()
    if not system_manager.is_running():
        return False
    
    # 3. Check market status - must be OPEN (data_manager)
    data_manager = get_data_manager()
    return data_manager.check_market_open()
```

## Behavior Examples

### Example 1: Active Session (No Symbols Required)
```
Time: 2024-11-18 10:00:00 ET (Monday, market hours)
System State: RUNNING
Session Ended: False
Market Status: OPEN
Active Symbols: 0

is_session_active() → True ✓
Reason: System running + Market open + Not ended
        (No symbols required!)
```

### Example 2: Active Session (With Symbols)
```
Time: 2024-11-18 10:00:00 ET (Monday, market hours)
System State: RUNNING
Session Ended: False
Market Status: OPEN
Active Symbols: 2 (AAPL, MSFT)

is_session_active() → True ✓
Reason: System running + Market open + Not ended
```

### Example 3: Before Market Open
```
Time: 2024-11-18 09:00:00 ET (before 9:30 AM)
System State: RUNNING
Session Ended: False
Market Status: CLOSED

is_session_active() → False ✗
Reason: Market not open yet
```

### Example 4: After Market Close
```
Time: 2024-11-18 16:30:00 ET (after 4:00 PM)
System State: RUNNING
Session Ended: False
Market Status: CLOSED

is_session_active() → False ✗
Reason: Market closed
```

### Example 5: System Stopped
```
Time: 2024-11-18 10:00:00 ET (market hours)
System State: STOPPED
Session Ended: False
Market Status: OPEN (but system stopped)

is_session_active() → False ✗
Reason: System not running
```

### Example 6: System Paused
```
Time: 2024-11-18 10:00:00 ET (market hours)
System State: PAUSED
Session Ended: False
Market Status: OPEN

is_session_active() → False ✗
Reason: System paused, not running
```

### Example 7: Session Explicitly Ended
```
Time: 2024-11-18 10:00:00 ET (market hours)
System State: RUNNING
Session Ended: True
Market Status: OPEN

is_session_active() → False ✗
Reason: Session explicitly ended
```

### Example 8: Weekend/Holiday
```
Time: 2024-11-16 10:00:00 ET (Saturday)
System State: RUNNING
Session Ended: False
Market Status: CLOSED (weekend)

is_session_active() → False ✗
Reason: Market closed (weekend)
```

## Status Display

### When Active
```
Session Data
├─ Session Date: 2024-11-18
├─ Session Active: Yes ✓
├─ Market Status: OPEN
```

### When Inactive (Market Closed)
```
Session Data
├─ Session Date: 2024-11-18
├─ Session Active: No
├─ Market Status: CLOSED
├─ Reason: Market not open
```

### When Inactive (System Stopped)
```
Session Data
├─ Session Date: No active session
├─ Session Active: No
├─ System State: STOPPED
```

## Use Cases

### Analysis Engine
```python
# Check if can analyze current market
if session_data.is_session_active():
    # Market is open, system running, analyze!
    latest_bar = session_data.get_latest_bar("AAPL")
    analyze(latest_bar)
else:
    # Market closed or system not running
    logger.info("Session not active, skipping analysis")
```

### Trading Logic
```python
# Check if can place trades
if session_data.is_session_active():
    # All conditions met, can trade
    execution_manager.place_order(order)
else:
    # Don't trade when session inactive
    logger.warning("Session inactive, cannot place order")
```

### Data Upkeep
```python
# Check if should process real-time data
if session_data.is_session_active():
    # Process incoming bars
    process_bars()
else:
    # Pause data processing
    logger.info("Session inactive, pausing data processing")
```

### Session Boundaries
```python
# Check if should roll to next session
if not session_data.is_session_active():
    # Market closed, check if should roll
    if should_roll_session():
        session_data.roll_session(next_date)
```

## Compared to Previous Logic

### Before (Overly Simple)
```python
def is_session_active(self) -> bool:
    # ❌ Too simple, didn't consider market hours or system state
    return (
        len(self._active_symbols) > 0 and 
        self.get_current_session_date() is not None
    )
```

**Problems:**
- Said "active" even when market closed
- Said "active" even when system stopped
- Didn't respect session_ended flag
- Only checked if had symbols and date

### After (Comprehensive)
```python
def is_session_active(self) -> bool:
    # ✓ Comprehensive check of all conditions
    return (
        not self.session_ended and
        self.get_current_session_date() is not None and
        system_manager.is_running() and
        market_status.is_open
    )
```

**Benefits:**
- Accurately reflects trading session state
- Considers market hours
- Respects system state
- Honors explicit session end
- Prevents operations when inappropriate

## Backtest Mode

### Simulated Time
In backtest mode, `is_session_active()` uses **simulated time** from TimeProvider:

```python
# Backtest at 10:00 AM on a trading day
time_provider.set_current_time(datetime(2024, 11, 18, 10, 0))

# Check session
session_data.is_session_active()  # → True (simulated market open)

# Advance to after close
time_provider.set_current_time(datetime(2024, 11, 18, 16, 30))

# Check again
session_data.is_session_active()  # → False (simulated market closed)
```

### Fast Forward
When fast-forwarding through backtest:

```python
# At 9:00 AM (before open)
is_session_active()  # → False

# Fast forward to 9:30 AM
is_session_active()  # → True (market just opened)

# Fast forward to 4:00 PM
is_session_active()  # → True (still open)

# Fast forward to 4:01 PM
is_session_active()  # → False (market just closed)
```

## Live Mode

In live mode, uses **real-time** from TimeProvider:

```python
# Check current real time
time_provider.get_current_time()  # → datetime.now()

# Session active follows real market hours
if is_weekday() and is_market_hours():
    is_session_active()  # → True
else:
    is_session_active()  # → False
```

## Fallback Behavior

If market status cannot be determined (rare edge case):

```python
try:
    # Try to get market status
    market_status = detector.get_market_status(current_time)
    return market_status.is_open
except Exception as e:
    logger.debug(f"Could not check market status: {e}")
    # Fallback: check if we have registered symbols
    return len(self._active_symbols) > 0
```

This ensures some level of functionality even if market status detection fails.

## Summary

✅ **Comprehensive:** Checks system state, market hours, and flags
✅ **Accurate:** Reflects actual trading session state
✅ **Useful:** Prevents operations when inappropriate
✅ **Backtest-aware:** Works with simulated time
✅ **Live-aware:** Works with real-time

**Key Principle:** Session is active ONLY when system is running AND market is open AND session hasn't been ended.

🎯 **Result:** Accurate session state that components can trust for decision-making!
