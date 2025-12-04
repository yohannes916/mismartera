# System Status Command Fixes

**Date:** Dec 3, 2025  
**Status:** ✅ Complete

---

## Overview

Fixed multiple architecture violations in `system_status_impl.py` where code was incorrectly accessing attributes and methods that don't exist or violate the single-source-of-truth pattern.

---

## Issues Fixed

### 1. ❌ `data_mgr.backtest_start_date` Does Not Exist

**Error:**
```
'DataManager' object has no attribute 'backtest_start_date'
```

**Root Cause:**
Code was trying to access `backtest_start_date` from DataManager, but this attribute **only exists in TimeManager** (single source of truth).

**Fix (Line 30):**
```python
# BEFORE (WRONG)
if data_mgr and system_mgr.mode.value == "backtest" and data_mgr.backtest_start_date is None:
    with SessionLocal() as session:
        data_mgr.init_backtest(session)

# AFTER (CORRECT)
if system_mgr.mode.value == "backtest":
    time_mgr = system_mgr.get_time_manager()
    if time_mgr.backtest_start_date is None:
        with SessionLocal() as session:
            time_mgr.init_backtest(session)
```

**Principle:** TimeManager is the ONLY source for `backtest_start_date` and `backtest_end_date`.

---

### 2. ❌ `system_mgr.is_initialized` Does Not Exist

**Error:**
```
'SystemManager' object has no attribute 'is_initialized'
```

**Root Cause:**
SystemManager does not have an `is_initialized` property. Need to check manager instances directly.

**Fix (Lines 66-72, 463-470):**
```python
# BEFORE (WRONG)
if system_mgr.is_initialized:
    health_table.add_row("[green]✓ All managers initialized[/green]")

# AFTER (CORRECT)
is_initialized = (
    system_mgr._time_manager is not None and 
    system_mgr._data_manager is not None
)
if is_initialized:
    health_table.add_row("[green]✓ All managers initialized[/green]")
```

**Principle:** Check manager instances directly instead of relying on non-existent properties.

---

### 3. ❌ `data_mgr.get_current_time()` Requires SystemManager

**Error:**
```
DataManager requires SystemManager to access TimeManager
```

**Root Cause:**
`data_mgr.get_current_time()` is a convenience method that delegates to TimeManager via SystemManager. However, DataManager doesn't always have the SystemManager reference set.

**Fix (Lines 74-83, 188-197):**
```python
# BEFORE (WRONG)
current_time = data_mgr.get_current_time()

# AFTER (CORRECT)
time_mgr = system_mgr.get_time_manager()
current_time = time_mgr.get_current_time()
```

**Principle:** Go directly to TimeManager instead of through DataManager's convenience method.

---

### 4. ❌ `data_mgr.get_current_day_market_info()` Does Not Exist

**Error:**
```
'DataManager' object has no attribute 'get_current_day_market_info'
```

**Root Cause:**
Old method that no longer exists. Market info should come from TimeManager.

**Fix (Lines 233-290):**
```python
# BEFORE (WRONG)
def _show_market_status(data_mgr):
    with SessionLocal() as session:
        market_info = data_mgr.get_current_day_market_info(session)
    # ... use market_info attributes ...

# AFTER (CORRECT)
def _show_market_status(system_mgr):
    time_mgr = system_mgr.get_time_manager()
    current_time = time_mgr.get_current_time()
    current_date = current_time.date()
    
    with SessionLocal() as session:
        trading_session = time_mgr.get_trading_session(session, current_date)
        is_holiday = time_mgr.is_holiday(session, current_date)
        is_market_open = time_mgr.is_market_open(session, current_time)
    # ... use TimeManager data ...
```

**Principle:** Use TimeManager methods for all market/calendar information.

---

### 5. ❌ `get_coordinator()` Helper Does Not Exist

**Error:**
```
name 'get_coordinator' is not defined
```

**Root Cause:**
Undefined helper function.

**Fix (Lines 389-393):**
```python
# BEFORE (WRONG)
coordinator = get_coordinator(system_mgr)

# AFTER (CORRECT)
coordinator = system_mgr._session_coordinator if hasattr(system_mgr, '_session_coordinator') else None

if not coordinator:
    return
```

**Principle:** Access coordinator directly from SystemManager.

---

## Architecture Principles Enforced

### 1. **TimeManager is Single Source of Truth for Time/Calendar**

**TimeManager owns:**
- Current time (`get_current_time()`)
- Backtest dates (`backtest_start_date`, `backtest_end_date`)
- Trading sessions (`get_trading_session()`)
- Market status (`is_market_open()`)
- Holidays (`is_holiday()`)
- Calendar navigation

**Everyone else queries TimeManager, never:**
- Uses `datetime.now()`
- Stores dates as attributes
- Has their own holiday logic
- Hardcodes trading hours

### 2. **Access Managers Through SystemManager**

```python
# ✅ CORRECT
time_mgr = system_mgr.get_time_manager()
data_mgr = system_mgr.get_data_manager()
```

**SystemManager provides:**
- `get_time_manager()` → TimeManager singleton
- `get_data_manager()` → DataManager singleton
- Direct access to threads: `_session_coordinator`, `_data_processor`, etc.

### 3. **Check Attributes Exist Before Using**

```python
# ✅ CORRECT
is_initialized = (
    system_mgr._time_manager is not None and 
    system_mgr._data_manager is not None
)

coordinator = system_mgr._session_coordinator if hasattr(system_mgr, '_session_coordinator') else None
```

---

## Files Modified

### `/app/cli/system_status_impl.py`

| Lines | Change | Description |
|-------|--------|-------------|
| 30-39 | Fixed | Access `backtest_start_date` from TimeManager |
| 66-72 | Fixed | Check manager instances instead of `is_initialized` |
| 74-83 | Fixed | Get current time from TimeManager directly |
| 188-197 | Fixed | Get current time from TimeManager directly |
| 233-290 | Fixed | Rewrote `_show_market_status` to use TimeManager |
| 389-393 | Fixed | Access coordinator from SystemManager directly |
| 463-470 | Fixed | Check manager instances instead of `is_initialized` |

---

## Testing

### Manual Test
```bash
./start_cli.sh
system@mismartera: system status
```

### Expected Output
```
═════════════════════════════════════════════════════════════════════════
                              SYSTEM STATUS                              
═════════════════════════════════════════════════════════════════════════

┌─────────────────────────┬────────────────────────────────────────┐
│ Property                │ Value                                  │
├─────────────────────────┼────────────────────────────────────────┤
│ State                   │ STOPPED                                │
│ Mode                    │ BACKTEST                               │
│ Initialized             │ Yes                                    │
│ System Time             │ 2024-11-15 09:30:00 ET (simulated)    │
└─────────────────────────┴────────────────────────────────────────┘
...
```

---

## Related Documentation

- `/backend/docs/windsurf/SYSTEM_JSON_EXPORT_IMPLEMENTATION.md` - System JSON export
- Memory: CRITICAL ARCHITECTURE RULE - TimeManager is single source of truth
- Memory: All time/calendar functionality migrated to time_manager

---

## Summary

✅ **Fixed all architecture violations in system status command**
- Removed access to non-existent attributes (`backtest_start_date`, `is_initialized`, `get_current_day_market_info`)
- Enforced TimeManager as single source of truth for time/calendar operations
- Direct access to managers and threads through SystemManager
- Proper attribute existence checks

**Status:** Ready to test! 🚀
