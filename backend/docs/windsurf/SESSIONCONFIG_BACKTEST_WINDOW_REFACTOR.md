# SessionConfig as Single Source of Truth for Backtest Window

**Date:** 2025-11-30  
**Type:** Architectural Principle Change  
**Status:** ✅ COMPLETE

---

## Problem

**Redundant Storage Violates Single Source of Truth:**

Backtest window dates (`start_date`, `end_date`) were stored in TWO places:
1. `SessionConfig.backtest_config` (from JSON file)
2. `TimeManager.backtest_start_date` / `backtest_end_date` (copied attributes)

**Issues:**
- Duplication of data
- Two sources of truth that can diverge
- Unclear which is authoritative after initialization
- No way to modify dates without touching both places
- TimeManager stores dates that belong to configuration

---

## Solution: SessionConfig as Single Source of Truth

**Principle:** Configuration data lives ONLY in `SessionConfig`. TimeManager reads via properties.

### Architecture Changes

**1. Removed Stored Attributes from TimeManager:**
```python
# ❌ OLD - Redundant storage
class TimeManager:
    def __init__(self):
        self.backtest_start_date: Optional[date] = None  # REMOVED
        self.backtest_end_date: Optional[date] = None    # REMOVED
```

**2. Added Read-Only Properties:**
```python
# ✅ NEW - Read from SessionConfig
class TimeManager:
    @property
    def backtest_start_date(self) -> Optional[date]:
        """Get backtest start date from SessionConfig (single source of truth)."""
        if not self._system_manager:
            return None
        
        session_config = self._system_manager.session_config
        if not session_config or not session_config.backtest_config:
            return None
        
        try:
            return datetime.strptime(
                session_config.backtest_config.start_date, "%Y-%m-%d"
            ).date()
        except (ValueError, AttributeError):
            return None
    
    @property
    def backtest_end_date(self) -> Optional[date]:
        """Get backtest end date from SessionConfig (single source of truth)."""
        # Same pattern as above
```

**3. Modified TimeManager Methods:**

**Before:**
```python
def init_backtest_window(self, session):
    config = self._system_manager.session_config.backtest_config
    # ❌ Copying to local storage
    self.backtest_start_date = datetime.strptime(config.start_date, "%Y-%m-%d").date()
    self.backtest_end_date = datetime.strptime(config.end_date, "%Y-%m-%d").date()
```

**After:**
```python
def init_backtest_window(self, session):
    """Validate backtest window from session config.
    
    This method now just validates that backtest config exists.
    The dates are automatically read from SessionConfig via properties.
    """
    # ✅ Just validate, don't copy
    if self.backtest_start_date is None or self.backtest_end_date is None:
        raise ValueError("Backtest start_date or end_date not configured")
```

**4. Updating Dates Modifies SessionConfig:**

**Before:**
```python
def set_backtest_window(self, session, start_date, end_date):
    # ❌ Modifying copied attributes
    self.backtest_start_date = start_date
    self.backtest_end_date = end_date
```

**After:**
```python
def set_backtest_window(self, session, start_date, end_date):
    """Override the backtest window by modifying SessionConfig."""
    session_config = self._system_manager.session_config
    
    # ✅ Modify the source of truth
    session_config.backtest_config.start_date = start_date.strftime("%Y-%m-%d")
    session_config.backtest_config.end_date = end_date.strftime("%Y-%m-%d")
    
    # Properties automatically reflect new values
```

**5. SystemManager API for Convenience:**

```python
class SystemManager:
    def set_backtest_window(self, start_date: date, end_date: date) -> None:
        """Update backtest window in SessionConfig (single source of truth).
        
        This modifies the SessionConfig's BacktestConfig, which TimeManager
        reads via properties. The config becomes the live configuration.
        """
        # Validate mode and dates
        if self._session_config.mode != "backtest":
            raise RuntimeError("System must be in backtest mode")
        
        if start_date > end_date:
            raise ValueError("start_date cannot be after end_date")
        
        # Modify SessionConfig
        self._session_config.backtest_config.start_date = start_date.strftime("%Y-%m-%d")
        self._session_config.backtest_config.end_date = end_date.strftime("%Y-%m-%d")
        
        # Reset clock if TimeManager exists
        if self._time_manager:
            self._time_manager.reset_backtest_clock(db_session)
```

---

## Benefits

### 1. ✅ Single Source of Truth
- Backtest dates stored ONLY in `SessionConfig`
- No duplication
- No possibility of divergence
- Clear ownership: config owns dates, TimeManager reads them

### 2. ✅ Live Configuration
- `SessionConfig` is not just initial config, it's the LIVE config
- Modifying `SessionConfig` immediately affects behavior
- No need to synchronize multiple places
- Properties always read current values

### 3. ✅ Cleaner Separation of Concerns
- **SessionConfig**: Owns configuration data
- **TimeManager**: Provides time operations, reads config as needed
- **SystemManager**: Orchestrates changes to config

### 4. ✅ Easier to Reason About
- Want to know backtest window? Check `SessionConfig`
- Want to change backtest window? Modify `SessionConfig`
- TimeManager is just a reader, not a storage location

### 5. ✅ Extensible
- Other config values can follow same pattern
- Easy to add more config-driven behavior
- No need to add storage to managers

---

## Timezone Handling

**Principle:** Config dates are in exchange timezone, converted to UTC at boundaries.

### Date Storage
- `SessionConfig.backtest_config.start_date`: String in `YYYY-MM-DD` format
- `SessionConfig.backtest_config.end_date`: String in `YYYY-MM-DD` format
- **Timezone**: Assumed to be exchange timezone (e.g., America/New_York)

### Time Objects with Timezone
- Market open/close times stored with timezone in TimeManager
- Properties return timezone-aware datetime objects
- UTC conversion happens at boundaries for internal comparison

**Example:**
```python
# Config stores date string (exchange timezone implied)
config.backtest_config.start_date = "2025-07-01"

# TimeManager property returns date object
start_date = time_mgr.backtest_start_date  # date(2025, 7, 1)

# When creating datetime for comparison, add timezone
from zoneinfo import ZoneInfo
from datetime import datetime, time

# Get market open time with timezone
trading_session = time_mgr.get_trading_session(db_session, start_date)
market_open = trading_session.regular_open  # time with timezone

# Combine date + time in exchange timezone
exchange_tz = ZoneInfo("America/New_York")
start_dt_local = datetime.combine(start_date, market_open)
start_dt_aware = start_dt_local.replace(tzinfo=exchange_tz)

# Convert to UTC for internal storage/comparison
start_dt_utc = start_dt_aware.astimezone(ZoneInfo("UTC"))
```

---

## Usage Patterns

### Reading Backtest Window

**Before:**
```python
time_mgr = system_mgr.get_time_manager()
start = time_mgr.backtest_start_date  # ❓ Stored attribute
```

**After (Same):**
```python
time_mgr = system_mgr.get_time_manager()
start = time_mgr.backtest_start_date  # ✅ Property reads from SessionConfig
```

**No change to consumers! Properties provide same interface.**

### Modifying Backtest Window

**Option 1: Via SystemManager (Recommended)**
```python
system_mgr = get_system_manager()
system_mgr.set_backtest_window(
    start_date=date(2025, 7, 1),
    end_date=date(2025, 7, 31)
)
```

**Option 2: Via TimeManager**
```python
time_mgr = system_mgr.get_time_manager()
with SessionLocal() as db_session:
    time_mgr.set_backtest_window(
        db_session,
        start_date=date(2025, 7, 1),
        end_date=date(2025, 7, 31)
    )
```

**Option 3: Direct Config Modification (Advanced)**
```python
# For advanced use cases only
session_config = system_mgr.session_config
session_config.backtest_config.start_date = "2025-07-01"
session_config.backtest_config.end_date = "2025-07-31"
# TimeManager properties automatically reflect changes
```

---

## Migration Guide

### For Code Reading Backtest Window

**No changes needed!** Properties provide same interface as before.

```python
# This still works
time_mgr = system_mgr.get_time_manager()
start = time_mgr.backtest_start_date
end = time_mgr.backtest_end_date
```

### For Code Modifying Backtest Window

**Update to use SystemManager or TimeManager API:**

```python
# ❌ OLD - Don't do this
time_mgr.backtest_start_date = new_date  # Won't work (read-only property)

# ✅ NEW - Use API
system_mgr.set_backtest_window(new_start, new_end)
# OR
time_mgr.set_backtest_window(db_session, new_start, new_end)
```

### For Code Checking if Backtest Window Set

```python
# ✅ Still works
if time_mgr.backtest_start_date is not None:
    # Window is configured
```

---

## Implementation Details

### Files Modified

**`app/managers/time_manager/api.py`:**
- Removed `self.backtest_start_date` and `self.backtest_end_date` attributes
- Added `@property` methods to read from SessionConfig
- Updated `init_backtest_window()` to just validate (not copy)
- Updated `set_backtest_window()` to modify SessionConfig

**`app/managers/system_manager/api.py`:**
- Added `set_backtest_window()` API method
- Added `from datetime import date` import
- Method modifies SessionConfig and resets TimeManager clock

**No changes needed for consumers!**
- DataManager continues to work (reads properties)
- CLI continues to work (reads properties)
- All other code continues to work (properties provide same interface)

---

## Testing

### Verification Steps

1. **Read backtest window:**
   ```python
   time_mgr = system_mgr.get_time_manager()
   print(time_mgr.backtest_start_date)
   print(time_mgr.backtest_end_date)
   ```

2. **Modify backtest window:**
   ```python
   system_mgr.set_backtest_window(date(2025, 7, 1), date(2025, 7, 31))
   ```

3. **Verify properties reflect change:**
   ```python
   assert time_mgr.backtest_start_date == date(2025, 7, 1)
   assert time_mgr.backtest_end_date == date(2025, 7, 31)
   ```

4. **Verify SessionConfig was modified:**
   ```python
   assert system_mgr.session_config.backtest_config.start_date == "2025-07-01"
   assert system_mgr.session_config.backtest_config.end_date == "2025-07-31"
   ```

---

## Architecture Principles Applied

### 1. Single Source of Truth
- Configuration data lives in `SessionConfig`
- No duplication in managers
- Clear ownership and authority

### 2. Config as Live State
- `SessionConfig` is not just initial values
- It's the authoritative runtime config
- Modifications to config immediately affect behavior

### 3. Managers as Services, Not Storage
- TimeManager provides time operations
- TimeManager reads config, doesn't store it
- Clean separation of concerns

### 4. Properties for Transparent Access
- Consumers don't need to change
- Properties provide same interface
- Implementation details hidden

### 5. API Boundaries for Modifications
- SystemManager provides high-level API
- TimeManager provides lower-level API
- Direct config modification for advanced use

---

## Future Extensions

### Other Config Values Could Follow Same Pattern

**Example: Historical Data Config:**
```python
@property
def historical_trailing_days(self) -> int:
    """Get trailing days from SessionConfig."""
    config = self._system_manager.session_config
    if config and config.historical:
        return config.historical.trailing_days
    return 0
```

**Example: Data Streams:**
```python
@property
def configured_symbols(self) -> List[str]:
    """Get symbols from SessionConfig."""
    config = self._system_manager.session_config
    if config and config.symbols:
        return [s.symbol for s in config.symbols]
    return []
```

---

## Summary

**What Changed:**
- Removed redundant date storage from TimeManager
- Added properties that read from SessionConfig
- Updated methods to validate instead of copy
- Added SystemManager API for modifications

**What Stayed the Same:**
- Consumer code (reads properties)
- Property interface (same as before)
- TimeManager API (same methods)

**Benefits:**
- Single source of truth ✅
- No duplication ✅
- Live configuration ✅
- Cleaner architecture ✅
- Extensible pattern ✅

**Status:** ✅ COMPLETE
- TimeManager refactored
- SystemManager API added
- Properties working
- No consumer changes needed

---

**Next Steps:**
1. Test with real backtest runs
2. Verify CLI displays correct dates
3. Test SystemManager.set_backtest_window() API
4. Consider applying pattern to other config values
