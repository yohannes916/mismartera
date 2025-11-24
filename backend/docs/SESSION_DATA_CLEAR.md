# Session Data Clear Behavior

## Overview

`session_data.clear()` now properly clears all session state, and `data_manager.stop_all_streams()` automatically calls it.

## Changes Made

### 1. Added `session_data.clear()` Method

**Location:** `/app/managers/data_manager/session_data.py`

```python
async def clear(self) -> None:
    """Clear all session data including symbols, bars, and session state.
    
    This method:
    - Clears all symbol data (bars, ticks, quotes, metrics)
    - Removes all registered symbols
    - Resets session date and ended flag
    
    Use this when stopping the system or starting a fresh session.
    """
```

**What it clears:**
- ✅ All registered symbols (`_symbols`)
- ✅ Active symbols set (`_active_symbols`)
- ✅ All bars (1m, derived, historical)
- ✅ All ticks and quotes
- ✅ Session metrics (volume, high, low)
- ✅ Current session date
- ✅ Session ended flag

### 2. Updated `data_manager.stop_all_streams()`

**Location:** `/app/managers/data_manager/api.py`

Now automatically clears session data after stopping streams:

```python
async def stop_all_streams(self) -> None:
    # Stop all streams
    await self.stop_bars_stream()
    await self.stop_ticks_stream()
    await self.stop_quotes_stream()
    
    # Stop coordinator worker
    coordinator.stop_worker()
    
    # NEW: Clear session data
    session_data = get_session_data()
    await session_data.clear()
```

## Impact on System Behavior

### Before (Old Behavior)

```bash
# Stop streams
data stop-all-streams

# Session data remained in memory
system status
# Shows: Session Active: Yes, Active Symbols: 2 ❌
```

**Problem:** Session data persisted after stopping streams, causing confusion.

### After (New Behavior)

```bash
# Stop streams
data stop-all-streams

# Session data automatically cleared
system status
# Shows: Session Active: No, Active Symbols: 0 ✓
```

**Benefit:** Clean state after stopping streams.

## When Session Data is Cleared

### 1. Manual Stream Stop
```bash
data stop-all-streams
# ✓ Clears session data
```

### 2. System Stop
```bash
system stop
# Calls stop_all_streams() internally
# ✓ Clears session data
```

### 3. System Start (stops existing streams first)
```bash
system start ./config.json
# Stops existing streams first
# ✓ Clears old session data
# ✓ Starts new streams with fresh session
```

### 4. Backtest Initialization
```bash
# When DataManager reinitializes backtest
await data_manager.init_backtest(session)
# Calls stop_all_streams() internally
# ✓ Clears session data
```

## API Methods

### Direct Clear
```python
from app.managers.data_manager.session_data import get_session_data

session_data = get_session_data()
await session_data.clear()
```

### Via DataManager
```python
data_manager = get_data_manager()
await data_manager.stop_all_streams()  # Clears automatically
```

### Via SystemManager
```python
system_manager = get_system_manager()
await system_manager.stop()  # Calls stop_all_streams() → clears
```

## Backwards Compatibility

`clear_all()` is kept as an alias:

```python
# Both work identically
await session_data.clear()
await session_data.clear_all()  # Alias for backwards compatibility
```

## Example Workflows

### Clean System Restart

```bash
# Stop everything
system stop
# Session data cleared ✓

# Start fresh
system start ./config.json
# New session with clean state ✓
```

### Switch Between Configs

```bash
# Running with config A
system start ./config_a.json
# Session Active: Yes, Symbols: AAPL, MSFT

# Switch to config B
system stop
# Session cleared ✓

system start ./config_b.json
# Session Active: Yes, Symbols: TSLA, NVDA
# No residual data from config A ✓
```

### Manual Stream Cleanup

```bash
# Stop all streams manually
data stop-all-streams
# Session cleared ✓

system status
# Session Active: No
# Active Symbols: 0
# Clean state ✓
```

## Benefits

### 1. Clean State Management
- No residual data between sessions
- Clear separation between runs
- Predictable behavior

### 2. Memory Management
- Frees memory when streams stop
- Prevents memory leaks
- Efficient resource usage

### 3. Debugging Easier
- Clear when session is active vs stopped
- No confusion from stale data
- Accurate status reporting

### 4. Safer Restarts
- Each `system start` begins fresh
- No interference from previous runs
- Reduced risk of data corruption

## Testing

### Verify Clear Behavior

```bash
# Start with data
system start ./config.json
system status
# Session Active: Yes ✓
# Active Symbols: 2 ✓

# Stop streams
data stop-all-streams

# Verify cleared
system status
# Session Active: No ✓
# Active Symbols: 0 ✓
```

### Verify System Stop

```bash
# Start system
system start ./config.json

# Stop system
system stop

# Verify cleared
system status
# State: STOPPED ✓
# Session Active: No ✓
```

## Implementation Details

### Thread-Safe Clearing

```python
async def clear(self) -> None:
    async with self._lock:  # Thread-safe
        self._symbols.clear()
        self._active_symbols.clear()
        self.current_session_date = None
        self.session_ended = False
```

### Order of Operations in stop_all_streams()

1. Stop bar streams
2. Stop tick streams
3. Stop quote streams
4. Stop coordinator worker
5. **Clear session data** ← New step

### Logging

```
INFO: All active streams stopped
INFO: Session data cleared (all symbols and session state)
SUCCESS: ✓ All streams stopped and session data cleared
```

## Summary

✅ **`session_data.clear()`** - New method to clear all session state
✅ **Auto-clear on stop** - `stop_all_streams()` clears session automatically
✅ **Clean state** - No residual data between sessions
✅ **Backwards compatible** - `clear_all()` still works as alias
✅ **Thread-safe** - Uses async lock for concurrent access
✅ **Better UX** - Clear indication when session is active vs stopped

**Result:** Cleaner, more predictable session lifecycle management! 🎉
