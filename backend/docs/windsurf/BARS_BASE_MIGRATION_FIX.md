# Migration Fix: bars_base to V2 Structure

**Date:** 2025-12-04  
**Issue:** `'SymbolSessionData' object has no attribute 'bars_base'`  
**Status:** ✅ FIXED

---

## Problem

The codebase had references to the old V1 structure attributes `bars_base` and `bars_derived` that no longer exist in the V2 structure defined in `SYMBOL_DATA_STRUCTURE_V2.md`.

### Error Location
```
session_coordinator.py:474 - Error in coordinator loop: 
'SymbolSessionData' object has no attribute 'bars_base'
```

---

## Root Cause

The V2 structure changed from:
```python
# OLD V1 Structure
class SymbolSessionData:
    bars_base: Deque[BarData]  # Base interval bars
    bars_derived: Dict[str, List[BarData]]  # Derived interval bars
```

To:
```python
# NEW V2 Structure
class SymbolSessionData:
    bars: Dict[str, BarIntervalData]  # All intervals (base + derived)
    
@dataclass
class BarIntervalData:
    derived: bool               # Is this computed from another interval?
    base: Optional[str]         # Source interval (None if streamed)
    data: Union[Deque[BarData], List[BarData]]  # Actual bars
    quality: float = 0.0
    gaps: List[Any] = field(default_factory=list)
    updated: bool = False
```

---

## Files Fixed

### 1. session_coordinator.py (Lines 2765-2777)

**Before:**
```python
bars_before = len(symbol_data.bars_base)
symbol_data.bars_base.append(bar)
bars_after = len(symbol_data.bars_base)
```

**After:**
```python
# Get base interval data
base_interval = symbol_data.base_interval
if base_interval not in symbol_data.bars:
    from app.managers.data_manager.session_data import BarIntervalData
    symbol_data.bars[base_interval] = BarIntervalData(
        derived=False,
        base=None,
        data=deque()
    )

base_bars = symbol_data.bars[base_interval].data
bars_before = len(base_bars)
base_bars.append(bar)
bars_after = len(base_bars)
```

### 2. data_quality_manager.py (Line 341)

**Before:**
```python
if interval == symbol_data.base_interval:
    bars = list(symbol_data.bars_base)
else:
    bars = symbol_data.bars_derived.get(interval, [])
```

**After:**
```python
interval_data = symbol_data.bars.get(interval)
if interval_data:
    bars = list(interval_data.data)
else:
    bars = []
```

### 3. data_quality_manager.py (Lines 670-686)

**Before:**
```python
if hasattr(symbol_data, 'bars_derived') and symbol_data.bars_derived:
    for derived_key, derived_bars in symbol_data.bars_derived.items():
        if isinstance(derived_key, int):
            derived_interval = f"{derived_key}m"
        else:
            derived_interval = derived_key
        
        if not derived_bars or derived_interval == interval:
            continue
```

**After:**
```python
if symbol_data.bars:
    for interval_key, interval_data in symbol_data.bars.items():
        if not interval_data.derived or interval_key == interval or not interval_data.data:
            continue
```

### 4. session_data.py (Line 808)

**Updated comment from:**
```python
# Do NOT add to bars_base to prevent duplicates!
# symbol_data.bars_base.append(bar)  # REMOVED
```

**To:**
```python
# Do NOT add to session bars to prevent duplicates!
# (V2 structure uses symbol_data.bars[interval].data)
```

---

## V2 Structure Access Patterns

### Access Base Interval Bars
```python
base_interval = symbol_data.base_interval  # e.g., "1m"
base_bars = symbol_data.bars[base_interval].data
```

### Access Derived Interval Bars
```python
derived_bars = symbol_data.bars["5m"].data  # For 5m bars
```

### Check if Interval is Derived
```python
interval_data = symbol_data.bars.get("5m")
if interval_data and interval_data.derived:
    print(f"Derived from: {interval_data.base}")
```

### Iterate All Intervals
```python
for interval_key, interval_data in symbol_data.bars.items():
    bars = interval_data.data
    is_derived = interval_data.derived
    quality = interval_data.quality
```

### Create New Interval Entry
```python
from app.managers.data_manager.session_data import BarIntervalData
from collections import deque

# For base (streamed) interval
symbol_data.bars["1m"] = BarIntervalData(
    derived=False,
    base=None,
    data=deque()
)

# For derived interval
symbol_data.bars["5m"] = BarIntervalData(
    derived=True,
    base="1m",
    data=[]  # List for derived, deque for base
)
```

---

## Benefits of V2 Structure

1. **Self-Describing**: Each interval knows if it's derived and from what
2. **No Duplicate Tracking**: Quality, gaps, and metadata stored per interval
3. **Consistent Access**: Same pattern for base and derived intervals
4. **Type Safety**: `derived` flag prevents mixing concerns
5. **Extensibility**: Easy to add new interval types

---

## Verification

All active code now uses V2 structure:
- ✅ session_coordinator.py - Bar addition
- ✅ data_quality_manager.py - Quality calculation
- ✅ data_quality_manager.py - Quality propagation
- ✅ data_processor.py - Derived bar computation (already correct)
- ✅ session_data.py - Comments updated

Only backup files retain old references (as expected).

---

## Related Documents

- `/docs/windsurf/SYMBOL_DATA_STRUCTURE_V2.md` - V2 structure specification
- `/app/managers/data_manager/session_data.py` - Implementation
