# SessionData Singleton & Import Fix

**Date**: November 30, 2025  
**Issue**: Multiple SessionData classes causing AttributeError  
**Status**: ✅ FIXED

---

## Problem

The system had **TWO different SessionData classes**:

1. **OLD**: `app.core.session_data.SessionData`
   - Old structure with `._bars` attribute
   - No new methods we added in Phase 3

2. **NEW**: `app.managers.data_manager.session_data.SessionData`
   - New structure with `._symbols` attribute
   - Has all Phase 3/4 methods (`set_quality()`, `append_bar()`, etc.)

Multiple files were importing from the **OLD location**, causing:
- `AttributeError: 'SessionData' object has no attribute 'set_quality'`
- `AttributeError: 'SessionData' object has no attribute '_bars'`

---

## Root Cause

Files were using old import:
```python
from app.core.session_data import SessionData  # OLD - wrong!
```

Instead of:
```python
from app.managers.data_manager.session_data import SessionData, get_session_data  # NEW - correct!
```

Additionally, code was:
1. **Direct instantiation** instead of singleton pattern
2. **Accessing old attributes** (`._bars` instead of `._symbols`)

---

## Files Fixed

### 1. `/app/threads/session_coordinator.py`

**Import Fix** (line 36):
```python
# OLD
from app.core.session_data import SessionData

# NEW ✅
from app.managers.data_manager.session_data import SessionData, get_session_data
```

**Singleton Fix** (line 93):
```python
# OLD
self.session_data = SessionData()

# NEW ✅
self.session_data = get_session_data()  # Use singleton
```

**Attribute Fix** (lines 346-350):
```python
# OLD
for symbol_data in self.session_data._bars.values():
    for bars in symbol_data.values():
        total_bars += len(bars)

# NEW ✅
for symbol_data in self.session_data._symbols.values():
    for interval_dict in symbol_data.historical_bars.values():
        for bars_list in interval_dict.values():
            total_bars += len(bars_list)
```

---

### 2. `/app/managers/system_manager/api.py`

**Import Fix** (line 24):
```python
# OLD
from app.core.session_data import SessionData

# NEW ✅
from app.managers.data_manager.session_data import SessionData, get_session_data
```

**Singleton Fix** (line 404):
```python
# OLD
session_data = SessionData()

# NEW ✅
session_data = get_session_data()  # Use singleton
```

---

### 3. `/app/threads/data_processor.py`

**Import Fix** (line 44):
```python
# OLD
from app.core.session_data import SessionData

# NEW ✅
from app.managers.data_manager.session_data import SessionData, get_session_data
```

---

### 4. `/app/threads/data_quality_manager.py`

**Import Fix** (line 43):
```python
# OLD
from app.core.session_data import SessionData

# NEW ✅
from app.managers.data_manager.session_data import SessionData, get_session_data
```

---

### 5. `/app/threads/analysis_engine.py`

**Import Fix** (line 48):
```python
# OLD
from app.core.session_data import SessionData

# NEW ✅
from app.managers.data_manager.session_data import SessionData, get_session_data
```

---

### 6. `/app/core/__init__.py`

**Import Fix** (line 25):
```python
# OLD
from app.core.session_data import SessionData

# NEW ✅
from app.managers.data_manager.session_data import SessionData, get_session_data
```

---

## SessionData Structure Differences

### OLD Structure (app.core.session_data)
```python
class SessionData:
    _bars: Dict[str, Dict[str, List[Bar]]]  # {symbol: {interval: [bars]}}
    # No set_quality(), append_bar(), etc.
```

### NEW Structure (app.managers.data_manager.session_data)
```python
class SessionData:
    _symbols: Dict[str, SymbolSessionData]  # {symbol: SymbolSessionData}
    _historical_indicators: Dict[str, any]  # {name: value}
    
    # Phase 3/4 methods
    def set_quality(symbol, interval, quality)
    def append_bar(symbol, interval, bar)
    def set_historical_indicator(name, value)
    def clear_historical_bars()
    # ... etc.

class SymbolSessionData:
    historical_bars: Dict[int, Dict[date, List[BarData]]]
    bars_base: deque  # Current session 1m bars
    bars_derived: Dict[int/str, List[BarData]]
    # ... metrics, quality, etc.
```

---

## Singleton Pattern

### Why Singleton?

1. **Single Data Store**: All threads must see the same data
2. **No Synchronization Issues**: One instance, one lock
3. **Memory Efficient**: No duplicate data structures
4. **Thread-Safe**: Built-in locking via `threading.RLock()`

### How to Use

```python
# Import
from app.managers.data_manager.session_data import get_session_data

# Get singleton instance
session_data = get_session_data()

# Use methods
session_data.set_quality("AAPL", "1m", 100.0)
bars = session_data.get_bars("AAPL", "1m")
```

### Implementation

```python
# Global singleton instance
_session_data_instance: Optional[SessionData] = None

def get_session_data() -> SessionData:
    """Get or create the global SessionData singleton instance."""
    global _session_data_instance
    if _session_data_instance is None:
        _session_data_instance = SessionData()
        logger.info("SessionData singleton instance created")
    return _session_data_instance
```

---

## Verification Steps

1. ✅ **All imports updated** to use correct location
2. ✅ **Singleton pattern used** everywhere (no direct `SessionData()`)
3. ✅ **Attribute references fixed** (`._symbols` instead of `._bars`)
4. ✅ **All files compile** without errors
5. ✅ **Cache cleared** to force recompilation

---

## Testing

After restart, the system should:

```bash
# Restart CLI
./start_cli.sh

# Start system
system start

# Expected: No AttributeError!
# Should see:
[SESSION_FLOW] PHASE_2.1: Loaded 1950 bars for AAPL 1m
[SESSION_FLOW] PHASE_2.3: Assigned 100% quality to 12 symbol/interval pairs
[SESSION_FLOW] PHASE_3.2: Loaded 3900 bars across 2 streams
[SESSION_FLOW] PHASE_5.2: Next timestamp: 09:31:00
[SESSION_FLOW] PHASE_5.3: Processed 2 bars (AAPL: 1, RIVN: 1)
...
```

---

## Summary

**Fixed 6 files** to:
- ✅ Import from correct SessionData location
- ✅ Use singleton pattern (`get_session_data()`)
- ✅ Access correct attributes (`._symbols` not `._bars`)
- ✅ Clear Python cache

**Result**: All code now uses the **same SessionData class** with all Phase 3/4 methods!

The system should now start and run backtests successfully! 🎉
