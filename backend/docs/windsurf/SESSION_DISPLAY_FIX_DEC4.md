# Session Display Fix - December 4, 2025

**Date:** 2025-12-04  
**Issue:** `'SystemManager' object has no attribute 'to_json'`  
**Status:** ✅ FIXED

---

## Problem

The session data display command was calling a non-existent method on SystemManager:

```python
# ❌ WRONG - Method doesn't exist
status = system_mgr.to_json(complete=True)
```

**Error:**
```
app.cli.session_data_display:data_session_command:369 - 
Error in session display: 'SystemManager' object has no attribute 'to_json'
```

---

## Root Cause

The SystemManager API method is named `system_info()`, not `to_json()`.

**Correct API:**
```python
def system_info(self, complete: bool = True) -> dict:
    """Export system state to JSON format.
    
    Args:
        complete: If True, return full data including historical.
                 If False, return delta (only new session data, excludes historical).
    
    Returns:
        Dictionary matching SYSTEM_JSON_EXAMPLE.json format
    """
```

---

## Fix

**File:** `/app/cli/session_data_display.py` (Line 29)

**Before:**
```python
system_mgr = get_system_manager()
status = system_mgr.to_json(complete=True)
```

**After:**
```python
system_mgr = get_system_manager()
status = system_mgr.system_info(complete=True)
```

---

## SystemManager API Reference

### Correct Method Name
- **Method:** `system_info(complete: bool = True) -> dict`
- **Purpose:** Export complete system state to JSON format
- **Location:** `/app/managers/system_manager/api.py` line 753

### Other Objects with to_json()

These classes DO have `to_json()` methods (not affected by this fix):
- `SessionData.to_json()` - Session data export
- `TimeManager.to_json()` - Time manager state
- `SessionCoordinator.to_json()` - Coordinator state  
- `DataProcessor.to_json()` - Processor state
- `DataQualityManager.to_json()` - Quality manager state
- `AnalysisEngine.to_json()` - Analysis engine state
- `SymbolSessionData.to_json()` - Per-symbol data export

---

## Delta vs Complete Mode

The `system_info()` method supports two modes:

### Complete Mode (Default)
```python
status = system_mgr.system_info(complete=True)
```
- Returns ~17K lines
- Includes all historical data
- Use for initial snapshot or full export

### Delta Mode
```python
status = system_mgr.system_info(complete=False)
```
- Returns ~10-50 lines
- Only new session data since last export
- Excludes historical data
- Includes metadata with `last_update` timestamp

---

## Verification

The fix allows the `data session` command to work correctly:
```bash
system@mismartera: data session
# Now displays session data without error
```

---

## Related Files

- `/app/cli/session_data_display.py` - Fixed call site
- `/app/managers/system_manager/api.py` - SystemManager with system_info() API
- `/app/managers/data_manager/session_data.py` - SessionData with to_json() API

---

## Summary

Single-line fix: Changed `to_json()` to `system_info()` to match the actual SystemManager API.
