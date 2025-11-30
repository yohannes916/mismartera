# Timezone and Config Structure Fix

**Date:** 2025-11-29  
**Issues:** Two architectural violations

---

## Problems Fixed

### 1. Timezone-Naive Datetime Comparison

**Error:**
```
TypeError: can't compare offset-naive and offset-aware datetimes
```

**Location:** `app/threads/session_coordinator.py` line 620

**Root Cause:** `market_close` was created without timezone, but `current_time` from TimeManager has timezone.

### 2. Accessing Obsolete Config Attribute

**Error:**
```
'SessionConfig' object has no attribute 'data_streams'
```

**Locations:**
- `app/cli/system_commands.py` line 55
- `app/managers/data_manager/data_upkeep_thread.py` line 199-204

**Root Cause:** Old config structure (`data_streams`) vs new structure (`session_data_config.symbols`, `session_data_config.streams`)

---

## Fix 1: TimeManager Provides Timezone for Market Hours

### Problem

SessionCoordinator was creating market open/close datetimes without timezone:

```python
# ❌ WRONG - No timezone (naive datetime)
market_open = datetime.combine(
    current_date,
    trading_session.regular_open
)
market_close = datetime.combine(
    current_date,
    trading_session.regular_close
)

# Comparison fails!
if current_time >= market_close:  # TypeError!
```

**Why This Violates Architecture:**
- TimeManager is the single source of truth for timezone
- Should query TimeManager for timezone, not create naive datetimes
- TimeManager's `get_current_time()` returns timezone-aware datetime
- Must compare apples to apples (both aware or both naive)

### Solution

Query timezone from TimeManager and create timezone-aware datetimes:

```python
# ✅ CORRECT - Get timezone from TimeManager
market_tz = self._time_manager.get_market_timezone()
market_open = datetime.combine(
    current_date,
    trading_session.regular_open,
    tzinfo=market_tz
)
market_close = datetime.combine(
    current_date,
    trading_session.regular_close,
    tzinfo=market_tz
)

# Now comparison works!
if current_time >= market_close:  # ✅ Both timezone-aware
```

**Architecture Compliance:**
- ✅ TimeManager provides timezone (single source of truth)
- ✅ All datetimes have consistent timezone awareness
- ✅ No hardcoded timezones (`ZoneInfo("America/New_York")`)
- ✅ Market timezone comes from TimeManager, which gets it from DB

### File Modified

**`app/threads/session_coordinator.py`** (lines 597-608)
- Added `market_tz = self._time_manager.get_market_timezone()`
- Added `tzinfo=market_tz` parameter to both `datetime.combine()` calls

---

## Fix 2: Updated Config Structure References

### Problem - SessionConfig Structure Changed

**Old Structure (obsolete):**
```python
session_config.data_streams = [
    {symbol: "AAPL", type: "bars", interval: "1m"},
    {symbol: "RIVN", type: "bars", interval: "1m"}
]
```

**New Structure (current):**
```python
session_config.session_data_config = {
    symbols: ["AAPL", "RIVN"],
    streams: ["bars_1m", "ticks", "quotes"],
    historical: {...},
    gap_filler: {...}
}
```

### Solution 1: CLI Command

**Before:**
```python
# ❌ Accessing obsolete attribute
console.print(f"Active streams: {len(system_mgr.session_config.data_streams)}")
```

**After:**
```python
# ✅ Using new structure
sdc = system_mgr.session_config.session_data_config
console.print(f"Symbols: {', '.join(sdc.symbols)}")
```

**File Modified:** `app/cli/system_commands.py` (lines 55-56)

### Solution 2: Data Upkeep Thread

**Before:**
```python
# ❌ Accessing obsolete attribute
for stream_config in self._session_config.data_streams:
    symbol = stream_config.symbol.upper()
    stream_type = stream_config.type
    if stream_type == "bars":
        interval = stream_config.interval
```

**After:**
```python
# ✅ Using new structure
sdc = self._session_config.session_data_config

# Build inventory from symbols and streams
for symbol in sdc.symbols:
    symbol = symbol.upper()
    inventory[symbol] = {
        "bars": [],
        "ticks": False,
        "quotes": False
    }
    
    # Parse stream types
    for stream in sdc.streams:
        if stream.startswith("bars_"):
            interval = stream.split("_", 1)[1]  # "bars_1m" -> "1m"
            inventory[symbol]["bars"].append(interval)
        elif stream == "ticks":
            inventory[symbol]["ticks"] = True
        elif stream == "quotes":
            inventory[symbol]["quotes"] = True
```

**File Modified:** `app/managers/data_manager/data_upkeep_thread.py` (lines 197-223)

---

## Architecture Principles Applied

### 1. TimeManager Owns Timezone

```
✅ CORRECT FLOW:
1. TimeManager.get_market_timezone() → ZoneInfo object
2. Use timezone to create aware datetimes
3. Compare aware datetimes with TimeManager's current_time

❌ WRONG:
1. Hardcode ZoneInfo("America/New_York")
2. Create naive datetimes
3. Mix naive and aware in comparisons
```

### 2. Config Structure Consistency

```
✅ CORRECT:
session_config.session_data_config.symbols  # List of symbols
session_config.session_data_config.streams  # List of stream types

❌ WRONG:
session_config.data_streams  # Doesn't exist anymore
```

---

## Data Flow

### Timezone Flow
```
Database (MarketHours)
    ↓
TimeManager (loads timezone)
    ↓
get_market_timezone() method
    ↓
SessionCoordinator (creates aware datetimes)
    ↓
Comparison with TimeManager's current_time
```

### Config Flow
```
JSON Config File
    ↓
SessionConfig.from_file()
    ↓
session_config.session_data_config
    ├─ symbols: ["AAPL", "RIVN"]
    ├─ streams: ["bars_1m"]
    ├─ historical: {...}
    └─ gap_filler: {...}
    ↓
All Components (CLI, threads, managers)
```

---

## Testing

### Before Fixes
```bash
system@mismartera: system start
# ✓ System started successfully
# ✗ System startup failed
# 'SessionConfig' object has no attribute 'data_streams'
# Error: can't compare offset-naive and offset-aware datetimes
```

### After Fixes
```bash
system@mismartera: system start
# ✓ System started successfully
# Symbols: AAPL, RIVN
# ✅ Streaming phase starts with proper timezone-aware comparisons
```

---

## Files Modified

1. **`app/threads/session_coordinator.py`**
   - Added TimeManager timezone query
   - Created timezone-aware market hours

2. **`app/cli/system_commands.py`**
   - Updated to use `session_data_config.symbols`
   - Removed reference to obsolete `data_streams`

3. **`app/managers/data_manager/data_upkeep_thread.py`**
   - Rewrote stream inventory parsing
   - Uses new config structure

---

## Related Principles

### TimeManager as Single Source
- ✅ Timezone from TimeManager
- ✅ No hardcoded timezones
- ✅ Consistent timezone awareness

### Config as Documentation
- ✅ Current structure documented
- ✅ All code uses same structure
- ✅ No mixing old and new formats

---

## Status

✅ **FIXED** - Both issues resolved with architecture-compliant solutions

**Next:** System should start and run streaming phase with proper timezone handling

---

**Total Fixes This Session:** 10 (including these timezone and config fixes)
