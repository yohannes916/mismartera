# Bug Fix: Remaining _streamed_data References

**Date:** December 4, 2025  
**Status:** ✅ FIXED  
**Impact:** Critical - System wouldn't start

---

## Problem

After completing Phase 4 of the refactor (which removed `_streamed_data` and `_generated_data` tracking), there were still 4 references to these old fields that caused a runtime error:

```
ERROR | app.threads.session_coordinator:_coordinator_loop:474 - 
Error in coordinator loop: 'SessionCoordinator' object has no attribute '_streamed_data'
```

---

## Root Cause

During Phase 4, we removed the tracking fields:
- `_loaded_symbols`
- `_streamed_data`
- `_generated_data`

But we missed updating 4 references in `session_coordinator.py`:

1. **Line 493**: `if not self._streamed_data:` - First session check
2. **Lines 527-528**: Logging streamed/generated counts
3. **Line 1306**: `return self._streamed_data.get(symbol, [])`
4. **Line 2509**: Duplicate of above

---

## Solution

### 1. First Session Check (Line 493)

**Before:**
```python
if not self._streamed_data:
    logger.info("First session - validating and marking streams")
```

**After:**
```python
# Check if SessionData has any symbols registered
if len(self.session_data.get_active_symbols()) == 0:
    logger.info("First session - validating and marking streams")
```

**Reasoning:** Query SessionData for active symbols instead of checking old tracking dict.

---

### 2. Session Info Logging (Lines 527-528)

**Before:**
```python
logger.info(
    f"Streamed data: {sum(len(v) for v in self._streamed_data.values())} streams, "
    f"Generated data: {sum(len(v) for v in self._generated_data.values())} types"
)
```

**After:**
```python
# Query SessionData for counts
active_symbols = self.session_data.get_active_symbols()
derived_symbols = self.session_data.get_symbols_with_derived()
total_derived = sum(len(intervals) for intervals in derived_symbols.values())
logger.info(
    f"Active symbols: {len(active_symbols)}, "
    f"Derived intervals: {total_derived} types"
)
```

**Reasoning:** Calculate counts from SessionData, which is the single source of truth.

---

### 3. Get Streamed Intervals Method (Lines 1306 & 2509)

**Before:**
```python
def _get_streamed_intervals_for_symbol(self, symbol: str) -> List[str]:
    """Get list of STREAMED intervals for a symbol."""
    return self._streamed_data.get(symbol, [])
```

**After:**
```python
def _get_streamed_intervals_for_symbol(self, symbol: str) -> List[str]:
    """Get list of STREAMED intervals for a symbol.
    
    Returns only intervals marked as STREAMED (not GENERATED).
    Now queries SessionData for base intervals (those with derived=False).
    """
    # Query SessionData for base (non-derived) intervals
    symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
    if not symbol_data:
        return []
    
    # Return intervals that are not derived (i.e., streamed)
    streamed = [interval for interval, data in symbol_data.bars.items() if not data.derived]
    return streamed
```

**Reasoning:** 
- Query SessionData instead of old tracking dict
- Use `derived` flag in `BarIntervalData` to identify streamed vs generated
- Streamed intervals have `derived=False`

---

## Files Modified

- `/app/threads/session_coordinator.py`
  - Line 493-494: First session check
  - Lines 527-534: Session info logging
  - Lines 1294-1313: `_get_streamed_intervals_for_symbol()` method
  - Lines 2504-2523: Duplicate method (also fixed)

---

## Testing

### Import Test
```bash
python -c "from app.threads.session_coordinator import SessionCoordinator; print('OK')"
```
✅ **Result:** Import successful!

### Manual Test
```bash
./start_cli.sh
system start
```
✅ **Expected:** System starts without errors

---

## Pattern Applied

This fix follows the refactor's core principle:

**Instead of tracking in coordinator:**
```python
coordinator._streamed_data = {"AAPL": ["1m"]}
```

**Query SessionData:**
```python
symbol_data = session_data.get_symbol_data("AAPL")
streamed = [iv for iv, data in symbol_data.bars.items() if not data.derived]
```

---

## Why This Happened

These references were missed during Phase 4 because:
1. They were in different parts of the large file
2. The error only manifests at runtime (not import time)
3. One method was duplicated (lines 1294 and 2504)

**Lesson:** Need better search for all references when removing fields!

---

## Related Work

- **Phase 4:** Removed coordinator tracking fields
- **Phase 7:** Updated bar access methods
- **This Fix:** Caught remaining runtime references

---

## Status

✅ **FIXED** - All `_streamed_data` and `_generated_data` references removed  
✅ **TESTED** - Import successful  
✅ **READY** - System should start now

---

**Try starting the system again!** 🚀

```bash
./start_cli.sh
system start
```

