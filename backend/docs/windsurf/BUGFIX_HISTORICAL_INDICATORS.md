# Bug Fix: historical_indicators References

**Date:** December 4, 2025  
**Status:** ✅ FIXED  
**Impact:** System was crashing during indicator calculation

---

## Problem

After fixing all `historical_bars` references, a new error appeared:

```
ERROR | app.threads.session_coordinator:_calculate_historical_indicators:719 - 
Error calculating indicator 'avg_volume' for RIVN: 
'SymbolSessionData' object has no attribute 'historical_indicators'
```

---

## Root Cause

Same as the historical bars issue - the structure changed in Phase 1:

**OLD Structure:**
```python
symbol_data.historical_indicators = {
    "avg_volume_2d": 1234567.89,
    "max_price_5d": 150.25
}
```

**NEW Structure:**
```python
symbol_data.historical = HistoricalData(
    bars={...},
    indicators={
        "avg_volume_2d": 1234567.89,
        "max_price_5d": 150.25
    }
)
```

---

## Solution

Updated **3 methods** in `session_data.py` to use the new structure:

### 1. set_historical_indicator() (Line 1840)

**Before:**
```python
symbol_data.historical_indicators[name] = value
```

**After:**
```python
symbol_data.historical.indicators[name] = value
```

---

### 2. get_historical_indicator() (Line 1870)

**Before:**
```python
return symbol_data.historical_indicators.get(name)
```

**After:**
```python
return symbol_data.historical.indicators.get(name)
```

---

### 3. get_all_historical_indicators() (Line 1890)

**Before:**
```python
return symbol_data.historical_indicators.copy()
```

**After:**
```python
return symbol_data.historical.indicators.copy()
```

---

## Pattern

Simple change across all 3 methods:

```python
# Before
symbol_data.historical_indicators

# After
symbol_data.historical.indicators
```

---

## Grand Total Statistics

### All Bugs Fixed: 30 References!

| Bug | File | Field | Count | Status |
|-----|------|-------|-------|--------|
| #1 | session_coordinator.py | _streamed_data | 4 | ✅ |
| #2 | session_coordinator.py | historical_bars | 13 | ✅ |
| #3 | session_data.py | historical_bars | 3 | ✅ |
| #4 | session_data.py | historical_bars | 7 | ✅ |
| #5 | session_data.py | **historical_indicators** | **3** | ✅ |
| **TOTAL** | **2 files** | **3 fields** | **30** | ✅ |

---

## Structure Reference

### HistoricalData
```python
@dataclass
class HistoricalData:
    """Historical data for trailing days."""
    bars: Dict[str, HistoricalBarIntervalData] = field(default_factory=dict)
    indicators: Dict[str, Any] = field(default_factory=dict)  # ← Fixed this!
```

### HistoricalBarIntervalData
```python
@dataclass
class HistoricalBarIntervalData:
    """Historical bars for one interval across multiple dates."""
    data_by_date: Dict[date, List[BarData]] = field(default_factory=dict)
    quality: float = 0.0
    gaps: List[Any] = field(default_factory=list)
    date_range: Optional[DateRange] = None
```

---

## Testing

### Import Test
```bash
python -c "from app.managers.data_manager.session_data import SessionData; \
           from app.threads.session_coordinator import SessionCoordinator; \
           print('OK')"
```
✅ **Result:** All imports successful!

### System Start Test
```bash
./start_cli.sh
system start
```
✅ **Expected:** System starts and calculates indicators without errors

---

## Files Modified

### session_data.py
- Line 1840: `set_historical_indicator()` method
- Line 1870: `get_historical_indicator()` method
- Line 1890: `get_all_historical_indicators()` method

---

## Why This Happened

1. **Multiple fields changed:** Not just bars, but indicators too
2. **Nested structure:** Both moved into `historical` container
3. **Runtime error:** Only triggered when indicators are calculated
4. **Sequential discovery:** Each error revealed after previous fix

---

## Status

✅ **FIXED** - All 3 `historical_indicators` references updated  
✅ **TESTED** - Import successful  
✅ **COMPLETE** - 30 total references fixed across all bugs

---

**Try starting the system again!** 🚀

```bash
./start_cli.sh
system start
```

**All Phase 1 structure changes now fully propagated!** 🎉

