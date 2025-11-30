# Backtest Config Integration Fix

**Date:** 2025-11-29  
**Issues:** Two related configuration errors

---

## Problems

### 1. BacktestConfig Has No 'backtest_days' Attribute

**Error:**
```
System startup failed: 'BacktestConfig' object has no attribute 'backtest_days'
```

**Root Cause:** TimeManager was trying to access `backtest_config.backtest_days` but BacktestConfig has `start_date` and `end_date` instead.

### 2. SystemManager Has No 'mode' Attribute

**Error:**
```
'SystemManager' object has no attribute 'mode'
Traceback:
  File "app/managers/time_manager/api.py", line 229, in get_current_time
    mode = self._system_manager.mode.value
           ^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'SystemManager' object has no attribute 'mode'
```

**Root Cause:** TimeManager was trying to access `self._system_manager.mode` but SystemManager didn't expose this as a property.

---

## BacktestConfig Structure

```python
@dataclass
class BacktestConfig:
    """Backtest configuration for historical simulation."""
    start_date: str          # "YYYY-MM-DD"
    end_date: str            # "YYYY-MM-DD"
    speed_multiplier: float  # 0=max, >0=realtime multiplier
    prefetch_days: int       # Days to prefetch
```

**Key Point:** Config has explicit `start_date` and `end_date`, NOT `backtest_days`

---

## Solutions

### Fix 1: Add Mode Property to SystemManager

SystemManager has `self._session_config.mode` but wasn't exposing it as a property.

**Added property:**
```python
@property
def mode(self) -> OperationMode:
    """Get current operation mode from session config."""
    if self._session_config is None:
        raise RuntimeError("Session config not loaded")
    return OperationMode(self._session_config.mode)
```

**Usage:**
```python
# Before (broken)
mode = self._system_manager.mode.value  # ❌ mode doesn't exist

# After (fixed)
mode = self._system_manager.mode.value  # ✅ Works! Returns OperationMode enum
```

### Fix 2: TimeManager Uses Config Dates Directly

TimeManager was calculating backtest window from `backtest_days` (old approach). Now it uses dates directly from BacktestConfig.

**Before (broken):**
```python
def init_backtest_window(self, session, exchange=None):
    # ❌ Tried to access self.backtest_days
    lookback_days = self.backtest_days * 3
    
    # Complex logic to walk backwards N trading days
    while len(trading_days) < self.backtest_days:
        # ... 50+ lines of date calculation ...
```

**After (fixed):**
```python
def init_backtest_window(self, session, exchange=None):
    """Initialize backtest window from session config dates."""
    
    # ✅ Get dates from config
    backtest_config = self._system_manager.session_config.backtest_config
    
    # ✅ Parse and use directly
    self.backtest_start_date = datetime.strptime(
        backtest_config.start_date, "%Y-%m-%d"
    ).date()
    self.backtest_end_date = datetime.strptime(
        backtest_config.end_date, "%Y-%m-%d"
    ).date()
    
    logger.info(
        "Backtest window initialized from config: %s to %s",
        self.backtest_start_date,
        self.backtest_end_date,
    )
```

**Benefits:**
- 50+ lines of complex code → 10 lines simple code
- No database queries needed
- Explicit dates from config (more control)
- Faster initialization

---

## Example Session Config

```json
{
  "session_name": "Example Backtest Session",
  "mode": "backtest",
  "backtest_config": {
    "start_date": "2024-01-02",    // ← Used by TimeManager
    "end_date": "2024-01-31",      // ← Used by TimeManager
    "speed_multiplier": 0.0,
    "prefetch_days": 1
  }
}
```

**TimeManager now:**
- ✅ Reads `start_date` and `end_date` directly
- ✅ No need to calculate from trading days
- ✅ User has explicit control over date range

---

## Files Modified

### SystemManager
**`app/managers/system_manager/api.py`**
- Added `mode` property (lines 564-569)
- Returns `OperationMode` enum from `self._session_config.mode`

### TimeManager
**`app/managers/time_manager/api.py`**
- Removed `self.backtest_days` attribute (line 53)
- Simplified `init_backtest_window()` method (lines 1041-1076)
- Now reads dates directly from BacktestConfig
- Reduced from ~60 lines to ~35 lines

---

## Before vs After

### TimeManager Initialization

**Before:**
```python
# TimeManager __init__
self.backtest_days = getattr(settings, 'DATA_MANAGER_BACKTEST_DAYS', 5)  # ❌
self.backtest_start_date = None
self.backtest_end_date = None

# init_backtest_window - complex 60+ line method
# - Query holidays
# - Walk backwards N days
# - Skip weekends/holidays
# - Build trading day list
```

**After:**
```python
# TimeManager __init__
self.backtest_start_date = None  # ✅ Will be set from config
self.backtest_end_date = None

# init_backtest_window - simple 35 line method
# - Get dates from config
# - Parse to date objects
# - Done!
```

### TimeManager Getting Mode

**Before:**
```python
# ❌ AttributeError: 'SystemManager' object has no attribute 'mode'
mode = self._system_manager.mode.value
```

**After:**
```python
# ✅ Works! SystemManager exposes mode property
mode = self._system_manager.mode.value  # Returns "backtest" or "live"
```

---

## Impact

### Performance
- ✅ **Faster initialization** - No need to query holidays or calculate trading days
- ✅ **Simpler code** - 60 lines → 35 lines

### Correctness
- ✅ **Explicit dates** - User specifies exact date range
- ✅ **No calculation errors** - No complex date math
- ✅ **Clear intent** - Config shows exactly what dates will be used

### Maintainability
- ✅ **Less code** - Fewer lines to maintain
- ✅ **Clearer logic** - Read from config vs complex calculation
- ✅ **Better separation** - Config is source of truth

---

## Migration Notes

**Old approach (removed):**
- Used `backtest_days` setting from config file
- Calculated dates by walking backwards N trading days
- Required holiday database queries
- Complex date arithmetic

**New approach (current):**
- Uses explicit `start_date` and `end_date` from BacktestConfig
- No calculation needed
- No database queries for initialization
- Simple date parsing

**Config files should now specify:**
```json
"backtest_config": {
  "start_date": "2024-01-02",  // Required
  "end_date": "2024-01-31"     // Required
}
```

---

## Testing

### Before Fixes
```bash
system@mismartera: system start
# ERROR: 'BacktestConfig' object has no attribute 'backtest_days'
# ERROR: 'SystemManager' object has no attribute 'mode'
```

### After Fixes
```bash
system@mismartera: system start
# INFO | Backtest window initialized from config: 2024-01-02 to 2024-01-31
# ✅ System starts successfully
```

---

## Related Changes

This simplification aligns with the principle of:
- **Config as source of truth** - All settings in session config
- **Less magic** - No hidden calculations
- **Explicit is better than implicit** - Dates clearly stated

---

## Status

✅ **Fixed** - Both issues resolved

**Fixes:**
1. ✅ SystemManager now exposes `mode` property
2. ✅ TimeManager reads dates directly from BacktestConfig
3. ✅ Removed obsolete `backtest_days` attribute
4. ✅ Simplified initialization logic

**Next:** System should initialize backtest window successfully
