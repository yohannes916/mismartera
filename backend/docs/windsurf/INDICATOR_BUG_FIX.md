# Indicator Serialization Bug - ROOT CAUSE FOUND & FIXED

## The Bug 🐛

**File**: `/app/managers/data_manager/session_data.py`  
**Method**: `SymbolSessionData.reset_session_metrics()` (line 293)

### What Was Wrong

```python
def reset_session_metrics(self) -> None:
    """Reset session metrics for a new session."""
    self.metrics = SessionMetrics()
    self.indicators = {}  # ← BUG: Cleared entire dict!
```

This method **deleted all indicators** instead of just resetting their values!

### Why This Caused Empty JSON

**Timeline**:
1. ✅ SessionCoordinator calls `indicator_manager.register_symbol_indicators()`
   - Creates `IndicatorData` objects in `symbol_data.indicators`
   - Logs: "Registering 14 indicators"
2. ✅ DataProcessor calls `indicator_manager.update_indicators()`  
   - Updates indicator values
   - Logs: "Updated indicators for 1m (2 bars)"
3. ❌ **SessionData.reset_session()** is called
   - Calls `reset_session_metrics()` 
   - **DELETES ALL INDICATORS** with `self.indicators = {}`
4. ❌ System export happens
   - `to_json()` iterates over empty `self.indicators`
   - Result: `"indicators": {}`

### Where reset_session_metrics() is Called

```python
# session_data.py line 1634
def roll_session():
    symbol_data.reset_session_metrics()  # Called when rolling to new day

# session_data.py line 1662  
def reset_session():
    symbol_data.reset_session_metrics()  # Called when resetting session
```

## The Fix ✅

**Changed**: Reset indicator **VALUES** instead of deleting the structures

```python
def reset_session_metrics(self) -> None:
    """Reset session metrics for a new session.
    
    NOTE: This does NOT clear indicators! Indicators are configuration-driven
    and persist across sessions. Only their VALUES are reset (current_value, valid, etc.),
    not the IndicatorData structures themselves.
    """
    self.metrics = SessionMetrics()
    
    # Reset indicator VALUES but keep structures
    for ind_data in self.indicators.values():
        ind_data.current_value = None
        ind_data.last_updated = None
        ind_data.valid = False
        # Keep: config, state (for stateful indicators like EMA)
    
    self.quotes_updated = False
    self.ticks_updated = False
    self._latest_bar = None
```

### Why This is Correct

**Indicators are CONFIGURATION, not session data**:
- Created from `session_config.session_data_config.indicators.session`
- Registered ONCE during initialization
- **Persist across sessions** (just like derived intervals)
- Only their **values** change per session

**What gets reset**:
- ✅ `current_value` → `None` (will be recalculated)
- ✅ `last_updated` → `None` (new timestamp coming)
- ✅ `valid` → `False` (warmup needed again)

**What persists**:
- ✅ `config` - IndicatorConfig (name, period, params, etc.)
- ✅ `state` - Last IndicatorResult (for stateful indicators)
- ✅ The IndicatorData object itself

## Architecture Principle

This aligns with the **Single Source of Truth** pattern:

### ❌ OLD (Wrong Pattern)
```python
# Separate tracking
indicator_manager._realtime_indicators = []  # Duplicate list
symbol_data.indicators = {}  # Gets cleared randomly
```

### ✅ NEW (Correct Pattern)
```python
# Single source
symbol_data.indicators = {
    "sma_20_5m": IndicatorData(...),  # Created from config
    "rsi_14_5m": IndicatorData(...),  # Persists across sessions
}

# Reset session = reset VALUES only
for ind in symbol_data.indicators.values():
    ind.current_value = None  # Clear value, keep structure
```

## Related Changes

This fix works together with the serialization improvements:

1. **Serialization** (already fixed):
   - Added `_serialize_indicator_config()` helper
   - Added `_serialize_indicator_state()` helper
   - Exports config/state/historical_values metadata

2. **Logging** (already added):
   - Tracks indicator count during registration
   - Warns if indicators dict is empty during serialization
   - Verifies post-registration state

3. **Bug Fix** (this change):
   - **Don't delete indicator structures**
   - Only reset their runtime values
   - Preserves configuration-driven data

## Expected Behavior After Fix

### Registration (Startup)
```
INFO: AAPL: About to register 14 indicators (14 session, 0 historical)
INFO: AAPL: Registering 14 indicators
INFO: AAPL: Indicator registration complete - 14 indicators in symbol_data.indicators
```

### Update (During Session)
```
DEBUG: AAPL: Updated indicators for 5m (20 bars)
DEBUG: AAPL: sma_20_5m = 225.43
DEBUG: AAPL: rsi_14_5m = 58.2
```

### Reset (New Session)
```
INFO: Reset session data for date: 2025-07-03
# Indicators still exist, just values cleared
```

### Export (System Status)
```json
{
  "symbols": {
    "AAPL": {
      "indicators": {
        "sma_20_5m": {
          "name": "sma",
          "type": "trend",
          "interval": "5m",
          "value": 225.43,
          "valid": true,
          "config": {
            "name": "sma",
            "period": 20,
            "interval": "5m",
            "warmup_bars": 20
          },
          "state": {
            "timestamp": "2025-07-02T12:39:00-04:00",
            "value": 225.43,
            "valid": true
          }
        }
      }
    }
  }
}
```

## Testing

Run the backtest again:

```bash
./start_cli.sh
system@mismartera: system start
# Wait for completion
system@mismartera: system export-status
```

**Expected**: JSON should now contain indicators with full metadata (config, state, values).

## Files Modified

1. `/app/managers/data_manager/session_data.py`
   - Fixed `reset_session_metrics()` to preserve indicator structures
   - Added serialization helpers (already done)
   - Added debug logging (already done)

2. `/app/indicators/manager.py`
   - Added registration verification logging (already done)

3. `/app/threads/session_coordinator.py`
   - Added pre/post registration logging (already done)

## Lesson Learned

**Indicators are configuration, not session data.**

Just like:
- Symbols don't get deleted when session resets
- Derived intervals don't get deleted when session resets  
- Stream configurations don't get deleted when session resets

**Indicators** also don't get deleted when session resets!

Only their **runtime values** (current_value, valid, last_updated) should reset.
