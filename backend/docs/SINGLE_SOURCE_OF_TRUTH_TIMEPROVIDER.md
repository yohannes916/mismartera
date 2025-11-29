# Single Source of Truth: TimeProvider

## Architectural Change

**Previously:** Multiple places stored and managed the current date/time
**Now:** `TimeProvider` is the **single source of truth** for current date/time

## Problem (Before)

### Multiple Date Sources
```python
# ❌ BAD: Multiple sources of truth
session_data.current_session_date = date(2024, 11, 18)  # SessionData had its own copy
data_manager.backtest_start_date = date(2024, 11, 18)   # DataManager had another
time_provider.set_current_time(...)                      # TimeProvider had the real one
```

### Synchronization Issues
- Dates could get out of sync
- Hard to know which one to trust
- Updates needed in multiple places
- Bugs from stale data

## Solution (After)

### Single Source of Truth
```python
# ✓ GOOD: One source of truth
time_provider = get_time_provider()
current_time = time_provider.get_current_time()
current_date = current_time.date()

# Everyone gets date from TimeProvider
session_data.get_current_session_date()  # Queries TimeProvider
data_manager.get_current_time()          # Uses TimeProvider
```

## Changes Made

### 1. Removed `current_session_date` from SessionData

**Before:**
```python
class SessionData:
    def __init__(self):
        self.current_session_date: Optional[date] = None  # ❌ Duplicate
```

**After:**
```python
class SessionData:
    def __init__(self):
        # No current_session_date field ✓
    
    def get_current_session_date(self) -> Optional[date]:
        """Get from TimeProvider (single source of truth)."""
        time_provider = get_time_provider()
        return time_provider.get_current_time().date()
```

### 2. Added Helper Methods

**New Method: `get_current_session_date()`**
```python
def get_current_session_date(self) -> Optional[date]:
    """Get current session date from TimeProvider.
    
    Returns:
        Current date from TimeProvider (single source of truth)
    """
    try:
        from app.managers.data_manager.time_provider import get_time_provider
        time_provider = get_time_provider()
        current_time = time_provider.get_current_time()
        return current_time.date()
    except Exception as e:
        logger.warning(f"Could not get current date: {e}")
        return None
```

**New Method: `is_session_active()`**
```python
def is_session_active(self) -> bool:
    """Check if session is currently active.
    
    Returns:
        True if we have active symbols and valid session date
    """
    return (
        len(self._active_symbols) > 0 and 
        self.get_current_session_date() is not None
    )
```

### 3. Renamed `start_new_session()` to `reset_session()`

**Before:**
```python
# ❌ Implied it set the date
session_data.start_new_session(date(2024, 11, 18))
```

**After:**
```python
# ✓ Just resets data, date comes from TimeProvider
session_data.reset_session()  # No date parameter!
```

### 4. Updated `roll_session()`

**Before:**
```python
session_data.roll_session(new_date)
self.current_session_date = new_date  # ❌ Stored locally
```

**After:**
```python
session_data.roll_session(new_date)
# Date is informational only, TimeProvider should be updated separately
# session_data gets date from TimeProvider automatically ✓
```

### 5. Updated All References

**Status Display:**
```python
# Before
if session_data.current_session_date:  # ❌ Direct access

# After
current_date = session_data.get_current_session_date()  # ✓ From TimeProvider
if current_date:
```

**System Start:**
```python
# Before
session_data.start_new_session(session_date)  # ❌ Set date

# After
# No need to set date - TimeProvider already has it! ✓
session_date = data_manager.get_current_time().date()
logger.info(f"Session date from TimeProvider: {session_date}")
```

## Benefits

### 1. Single Source of Truth
- ✅ One place to check current date/time
- ✅ No synchronization issues
- ✅ Consistency guaranteed

### 2. Simplified Code
```python
# Before: Multiple places to update
time_provider.set_current_time(new_time)
session_data.current_session_date = new_time.date()
data_manager.backtest_start_date = new_time.date()

# After: Update once
time_provider.set_current_time(new_time)
# Everyone else queries TimeProvider automatically ✓
```

### 3. Easier Testing
```python
# Mock TimeProvider once, affects everything
with patch('time_provider.get_current_time') as mock_time:
    mock_time.return_value = datetime(2024, 11, 18, 9, 30)
    
    # session_data automatically uses mocked time ✓
    assert session_data.get_current_session_date() == date(2024, 11, 18)
```

### 4. Less Error-Prone
- Can't forget to update session_data when TimeProvider changes
- Can't have mismatched dates
- Always in sync

## Usage Examples

### Getting Current Date

**✓ Correct Way:**
```python
# Get from TimeProvider (via DataManager)
data_manager = get_data_manager()
current_time = data_manager.get_current_time()
current_date = current_time.date()

# Or via session_data convenience method
session_data = get_session_data()
current_date = session_data.get_current_session_date()
```

**❌ Wrong Way:**
```python
# Don't access attribute directly (doesn't exist anymore!)
session_data.current_session_date  # AttributeError!
```

### Checking Session Status

**✓ Correct Way:**
```python
session_data = get_session_data()
if session_data.is_session_active():
    # Session is active
    current_date = session_data.get_current_session_date()
```

**❌ Wrong Way:**
```python
# Don't check attribute (doesn't exist!)
if session_data.current_session_date:  # AttributeError!
```

### Starting System

**✓ Correct Way:**
```python
# Initialize backtest (sets TimeProvider)
data_manager.init_backtest(session)

# Register symbols (session_data gets date from TimeProvider automatically)
session_data.register_symbol("AAPL")

# Date comes from TimeProvider - no need to set it! ✓
```

**❌ Wrong Way:**
```python
# Don't manually set date (method doesn't exist!)
session_data.start_new_session(date(2024, 11, 18))  # Method removed!
```

### Resetting Session

**✓ Correct Way:**
```python
# Just reset data, date comes from TimeProvider
session_data.reset_session()
```

## Migration Guide

### For Code Using `current_session_date`

**Before:**
```python
if session_data.current_session_date:
    date_str = session_data.current_session_date.strftime("%Y-%m-%d")
```

**After:**
```python
current_date = session_data.get_current_session_date()
if current_date:
    date_str = current_date.strftime("%Y-%m-%d")
```

### For Code Using `start_new_session()`

**Before:**
```python
session_data.start_new_session(date(2024, 11, 18))
```

**After:**
```python
# Option 1: Just reset (if TimeProvider already set)
session_data.reset_session()

# Option 2: Set TimeProvider first, then reset
time_provider.set_current_time(datetime(2024, 11, 18, 9, 30))
session_data.reset_session()
```

### For Tests

**Before:**
```python
# Manually set date
session_data.current_session_date = date(2024, 11, 18)
```

**After:**
```python
# Mock TimeProvider
from unittest.mock import patch
with patch('time_provider.get_current_time') as mock:
    mock.return_value = datetime(2024, 11, 18, 9, 30)
    # session_data.get_current_session_date() now returns mocked date ✓
```

## Architecture Diagram

```
┌─────────────────────────────────────────┐
│         TimeProvider (Singleton)        │
│    *** SINGLE SOURCE OF TRUTH ***      │
│                                         │
│  - get_current_time() → datetime       │
│  - set_current_time(datetime)          │
└─────────────────────────────────────────┘
                    ▲
                    │ queries
        ┌───────────┴───────────┐
        │                       │
┌───────────────┐      ┌────────────────┐
│  SessionData  │      │  DataManager   │
│               │      │                │
│  .get_current_│      │  .get_current_ │
│   session_    │      │   time()       │
│   date()      │      │                │
└───────────────┘      └────────────────┘
        │                       │
        └───────────┬───────────┘
                    ▼
            ┌───────────────┐
            │ Analysis      │
            │ Engine        │
            └───────────────┘
```

## Summary

✅ **Single Source:** TimeProvider is the only place that stores current time
✅ **No Duplication:** session_data doesn't store date, queries TimeProvider
✅ **Always Synced:** Can't have mismatched dates
✅ **Simpler Code:** No manual synchronization needed
✅ **Easier Testing:** Mock TimeProvider once, affects everything
✅ **Less Bugs:** Eliminates entire class of synchronization bugs

**Key Principle:** When you need the current date/time, always get it from TimeProvider (directly or via helper methods). Never store it locally!

🎯 **Result:** Cleaner architecture with guaranteed consistency!
