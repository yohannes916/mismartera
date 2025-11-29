# Session Initialization Fix

## Problem

When `system start` ran, the coordinator would start and streams would be configured, but `session_data` showed:
```
Session Date: No active session
Session Active: No
Active Symbols: 0 symbols
```

Even though:
```
Worker Thread: Running
```

## Root Cause

`system_manager.start()` was starting the coordinator and feeding data to it, but **never initialized session_data** with:
1. Current session date
2. Registered symbols

This caused a disconnect between the coordinator (which had streams) and session_data (which didn't know about them).

## Fix Applied

### 1. Initialize Session Data
```python
# Get current time (from backtest or live)
current_time = data_manager.get_current_time()
session_date = current_time.date()

# Initialize session
session_data = get_session_data()
session_data.start_new_session(session_date)
```

### 2. Register Symbols
```python
# When starting each stream, register with session_data
session_data.register_symbol(symbol)
```

## Changes Made

**File:** `/app/managers/system_manager.py`

**Location:** In `async def start()` method, after starting coordinator

**Before:**
```python
coordinator = get_coordinator(self)
coordinator.start_worker()

# Start each configured stream
for stream_config in data_streams:
    # ... start stream
    coordinator.register_stream(symbol, stream_type)
    coordinator.feed_data_list(symbol, stream_type, data)
```

**After:**
```python
coordinator = get_coordinator(self)
coordinator.start_worker()

# Initialize session data with current date
session_data = get_session_data()
current_time = data_manager.get_current_time()
session_date = current_time.date()
session_data.start_new_session(session_date)

# Start each configured stream
for stream_config in data_streams:
    # ... start stream
    coordinator.register_stream(symbol, stream_type)
    session_data.register_symbol(symbol)  # NEW
    coordinator.feed_data_list(symbol, stream_type, data)
```

## Result

Now `system status` will show:

```
Session Data
├─ Session Date: 2024-11-18        ✓ Set correctly
├─ Session Active: Yes              ✓ Active
├─ Active Symbols: 2 (AAPL, MSFT)  ✓ Tracked
```

```
Backtest Stream Coordinator
├─ Worker Thread: Running           ✓ Running
├─ Active Streams: 2                ✓ Streams active
```

## Why This Matters

### 1. Accurate Status Reporting
`system status` now reflects actual system state

### 2. Analysis Engine Can Access Data
Analysis engine queries session_data for latest bars:
```python
latest_bar = session_data.get_latest_bar("AAPL")  # Now works!
```

### 3. Session Boundaries Work
Session boundary manager can check session state:
```python
if session_data.current_session_date:
    # Can check if session should roll
```

### 4. Data Upkeep Can Track Symbols
Data upkeep thread knows which symbols to maintain:
```python
active_symbols = session_data.get_active_symbols()  # Now populated!
```

## Testing

### Verify Fix Works

```bash
# Start system
system start ./configs/my_session.json

# Check status
system status
```

**Expected:**
```
Session Data
├─ Session Date: 2024-11-18
├─ Session Active: Yes
├─ Active Symbols: 2 symbols

Backtest Stream Coordinator
├─ Worker Thread: Running
├─ Active Streams: 2 streams
```

### Compare Before/After

**Before (Broken):**
```
Session Active: No              ❌
Active Symbols: 0 symbols       ❌
Active Streams: 0 streams       ❌
```

**After (Fixed):**
```
Session Active: Yes             ✓
Active Symbols: 2 symbols       ✓
Active Streams: 2 streams       ✓
```

## Summary

✅ **Session initialization** - start_new_session() called on system start
✅ **Symbol registration** - Symbols registered with session_data when streams start
✅ **Consistent state** - Coordinator and session_data now in sync
✅ **Accurate reporting** - system status reflects reality
✅ **Analysis ready** - Analysis engine can access session data

**Result:** Complete session lifecycle management from system start! 🎉
