# Phase 4-5 Progress: SessionCoordinator & DataProcessor

**Date:** December 4, 2025  
**Status:** In Progress - Core infrastructure updated, stream marking needs update

---

## Completed So Far ✅

### SessionData Helper Methods (Complete)
- ✅ Added `register_symbol_data(symbol_data)` - Register pre-configured symbol
- ✅ Added `get_symbols_with_derived()` - Query derived intervals per symbol

### SessionCoordinator (Partial)
- ✅ Removed `_loaded_symbols` field from __init__
- ✅ Removed `_streamed_data` field from __init__
- ✅ Removed `_generated_data` field from __init__
- ✅ Updated `get_loaded_symbols()` - Queries SessionData
- ✅ Updated `get_generated_data()` - Queries SessionData
- ✅ Updated `get_streamed_data()` - Queries SessionData
- ✅ Updated `remove_symbol()` - Removed references to deleted fields

---

## Remaining Work ⏳

### SessionCoordinator Stream Marking (Critical)

**Problem:** Stream determination results still try to populate removed fields.

**Locations to Update:**
1. `_validate_and_mark_streams()` - Line ~1837-1843
2. `_mark_backtest_streams()` - Line ~1914-1934
3. `_mark_live_streams()` - Line ~1958-1959

**Current Code (Bad):**
```python
# Lines 1837-1839
self._streamed_data[symbol] = [result.required_base_interval]
self._generated_data[symbol] = result.derivable_intervals.copy()
```

**New Approach (Good):**
```python
# Create SymbolSessionData with bar structure
from app.managers.data_manager.session_data import BarIntervalData

symbol_data = SymbolSessionData(
    symbol=symbol,
    base_interval=result.required_base_interval,
    bars={
        # Base interval (streamed)
        result.required_base_interval: BarIntervalData(
            derived=False,
            base=None,
            data=deque(),
            quality=0.0,
            gaps=[],
            updated=False
        ),
        # Derived intervals (generated)
        **{
            interval: BarIntervalData(
                derived=True,
                base=result.required_base_interval,
                data=[],
                quality=0.0,
                gaps=[],
                updated=False
            )
            for interval in result.derivable_intervals
        }
    }
)

# Register with SessionData
self.session_data.register_symbol_data(symbol_data)
```

---

## Implementation Plan

### Step 1: Update Stream Determination ⏳
1. Import `BarIntervalData` from session_data
2. Find `_validate_and_mark_streams()`
3. Replace _streamed_data/_generated_data assignment with symbol creation
4. Do same for `_mark_backtest_streams()` and `_mark_live_streams()`

### Step 2: Update Symbol Loading ⏳
1. Find `_load_symbols_for_session()`
2. Ensure it calls stream marking (which now registers symbols)
3. Remove any references to `_loaded_symbols.update()`

### Step 3: Update DataProcessor References ⏳
1. Remove `set_derived_intervals()` call from coordinator
2. DataProcessor will query SessionData directly

### Step 4: Test & Validate ⏳
1. Test symbol registration creates bar structure
2. Test DataProcessor can query derived intervals
3. Test symbol removal cleans up properly

---

## Code Changes Summary

### Files Modified

**1. `/app/managers/data_manager/session_data.py`**
- Added `register_symbol_data()` method (lines ~668-684)
- Added `get_symbols_with_derived()` method (lines ~686-704)

**2. `/app/threads/session_coordinator.py`**
- Removed fields from __init__ (lines ~128-136)
- Updated `get_loaded_symbols()` (line ~252)
- Updated `get_generated_data()` (line ~270)
- Updated `get_streamed_data()` (lines ~279-286)
- Updated `remove_symbol()` (lines ~349-367)

### Still Need to Update

**3. `/app/threads/session_coordinator.py`** (Continued)
- `_validate_and_mark_streams()` - Create bar structure
- `_mark_backtest_streams()` - Create bar structure
- `_mark_live_streams()` - Create bar structure
- `_load_symbols_for_session()` - Remove _loaded_symbols reference
- DataProcessor integration - Remove set_derived_intervals call

**4. `/app/threads/data_processor.py`**
- Remove `_derived_intervals` field
- Remove `set_derived_intervals()` method
- Update processing loop to query SessionData

---

## Next Session Tasks

1. **Complete SessionCoordinator Stream Marking** (1-2 hours)
   - Update 3 stream marking methods
   - Test symbol registration

2. **Update DataProcessor** (2-3 hours)
   - Remove _derived_intervals
   - Query SessionData for work
   - Update bar appending

3. **Integration Testing** (1 hour)
   - Test full flow
   - Verify no regressions

---

## Benefits So Far

### ✅ Infrastructure Ready
- Helper methods in SessionData
- Accessor methods query single source
- Symbol removal cleaned up

### ✅ No Duplicate Tracking
- `_active_symbols` removed (Phase 3)
- `_loaded_symbols`, `_streamed_data`, `_generated_data` removed (Phase 4)

### 🔄 Almost There
- Just need to wire up symbol registration with bar structure
- Then update DataProcessor to query SessionData

---

## Testing Requirements

### Unit Tests
- [ ] Test `register_symbol_data()` creates symbol with structure
- [ ] Test `get_symbols_with_derived()` returns correct intervals
- [ ] Test symbol removal from SessionData
- [ ] Test accessor methods query SessionData

### Integration Tests
- [ ] Test coordinator registers symbols with bar structure
- [ ] Test DataProcessor finds derived intervals
- [ ] Test symbol add/remove lifecycle
- [ ] Test derived bar generation works

---

**Status:** ~70% complete for Phase 4, 0% for Phase 5  
**Next:** Complete stream marking methods, then tackle DataProcessor  
**Estimated Time Remaining:** 4-5 hours
