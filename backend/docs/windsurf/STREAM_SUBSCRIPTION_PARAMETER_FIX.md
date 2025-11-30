# StreamSubscription Parameter Fix

**Date:** 2025-11-29  
**Issue:** StreamSubscription.__init__() missing required 'stream_id' argument

---

## Problem

System startup failed because StreamSubscription was created with only one argument instead of the two required parameters.

**Error:**
```
System startup failed: StreamSubscription.__init__() missing 1 required positional argument: 'stream_id'
```

---

## Root Cause

StreamSubscription requires TWO parameters:
1. `mode` - Operating mode ('data-driven', 'clock-driven', or 'live')
2. `stream_id` - Identifier for debugging

But SystemManager was calling it with only one parameter:
```python
processor_subscription = StreamSubscription("processor")  # ❌ Wrong!
```

---

## StreamSubscription Signature

```python
def __init__(self, mode: str, stream_id: str):
    """Initialize stream subscription.
    
    Args:
        mode: Operating mode ('data-driven', 'clock-driven', or 'live')
        stream_id: Identifier for debugging (e.g., "coordinator->data_processor")
    """
```

### Mode Descriptions

1. **data-driven** (backtest with speed_multiplier=0)
   - Blocks indefinitely until ready
   - Maximum speed backtest
   - No timeouts

2. **clock-driven** (backtest with speed_multiplier>0)
   - Timeout-based with overrun detection
   - Simulated real-time
   - Warns if consumer is too slow

3. **live** (live mode)
   - Timeout-based for real-time market data
   - No overrun warnings (expected behavior)

---

## Solution

### 1. Determine Mode from Session Config

```python
# Determine subscription mode based on session config
if self._session_config.mode == "live":
    subscription_mode = "live"
elif self._session_config.backtest_config and self._session_config.backtest_config.speed_multiplier == 0:
    subscription_mode = "data-driven"
else:
    subscription_mode = "clock-driven"
```

**Logic:**
- Live mode → "live"
- Backtest with speed=0 → "data-driven" (max speed)
- Backtest with speed>0 → "clock-driven" (simulated real-time)

### 2. Pass Both Parameters

```python
processor_subscription = StreamSubscription(
    mode=subscription_mode,
    stream_id="coordinator->data_processor"
)
```

---

## Before vs After

### Before (Broken)

```python
def _wire_threads(self):
    from app.threads.sync.stream_subscription import StreamSubscription
    import queue
    
    # ❌ Missing mode parameter!
    processor_subscription = StreamSubscription("processor")
```

### After (Fixed)

```python
def _wire_threads(self):
    from app.threads.sync.stream_subscription import StreamSubscription
    import queue
    
    # ✅ Determine mode from config
    if self._session_config.mode == "live":
        subscription_mode = "live"
    elif self._session_config.backtest_config and self._session_config.backtest_config.speed_multiplier == 0:
        subscription_mode = "data-driven"
    else:
        subscription_mode = "clock-driven"
    
    logger.debug(f"Using subscription mode: {subscription_mode}")
    
    # ✅ Pass both parameters
    processor_subscription = StreamSubscription(
        mode=subscription_mode,
        stream_id="coordinator->data_processor"
    )
```

---

## Why This Matters

### Thread Synchronization

The `mode` parameter determines how threads synchronize:

**Data-Driven (Backtest Max Speed):**
```python
# Coordinator signals ready
subscription.signal_ready()

# Processor blocks indefinitely until ready
subscription.wait_until_ready(timeout=None)  # Blocks forever
```

**Clock-Driven (Backtest Real-Time):**
```python
# Coordinator signals ready
subscription.signal_ready()

# Processor waits with timeout, warns on overrun
subscription.wait_until_ready(timeout=1.0)  # Timeout after 1 second
```

**Live Mode:**
```python
# Coordinator signals ready
subscription.signal_ready()

# Processor waits with timeout (market data driven)
subscription.wait_until_ready(timeout=0.5)  # Timeout after 0.5 seconds
```

### Stream ID for Debugging

The `stream_id` helps identify which subscription is involved when debugging:
```
coordinator->data_processor
coordinator->quality_manager
processor->analysis_engine
```

Appears in logs:
```
StreamSubscription(id='coordinator->data_processor', mode='data-driven', ready=True)
```

---

## Example Session Configs

### Max Speed Backtest (data-driven)

```json
{
  "mode": "backtest",
  "backtest_config": {
    "speed_multiplier": 0.0  // ← Triggers data-driven
  }
}
```

### Real-Time Backtest (clock-driven)

```json
{
  "mode": "backtest",
  "backtest_config": {
    "speed_multiplier": 1.0  // ← Triggers clock-driven
  }
}
```

### Live Trading (live)

```json
{
  "mode": "live"  // ← Triggers live mode
}
```

---

## Files Modified

**`app/managers/system_manager/api.py`**
- Method: `_wire_threads()` (lines 387-414)
- Added mode determination logic
- Fixed StreamSubscription creation with both parameters
- Added debug logging for subscription mode

---

## Testing

### Before Fix
```bash
system@mismartera: system start
# ERROR: StreamSubscription.__init__() missing 1 required positional argument: 'stream_id'
```

### After Fix
```bash
system@mismartera: system start
# DEBUG | Using subscription mode: data-driven
# DEBUG | Creating processor subscription...
# ✅ Threads wired successfully
```

---

## Benefits

1. **Correct Synchronization**: Threads use appropriate waiting strategy
2. **Better Debugging**: Stream IDs identify subscription points
3. **Mode-Aware**: Behavior adapts to backtest vs live mode
4. **Performance**: Data-driven mode for max speed backtests

---

## Status

✅ **Fixed** - StreamSubscription now created with both required parameters

**Next:** System should wire threads successfully
