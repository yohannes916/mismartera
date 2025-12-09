# Unified Config Implementation Plan

**Date**: December 7, 2025  
**Goal**: String-based intervals everywhere - NO integers, NO hourly support  
**Approach**: Clean break - delete old code

---

## Current State

### **Problem: Mixed Integer/String Usage** ❌

**Config Files** (Integers):
```json
{
  "data_upkeep": {
    "derived_intervals": [5, 15, 30]  // ❌ Integers (assumes minutes)
  }
}
```

**Code** (Strings):
```python
compute_derived_bars(bars_1m, "1m", "5m")  # ✅ Strings
parse_interval("5m")  # ✅ Strings
```

**Issues**:
1. ❌ Inconsistent: Integers in config, strings in code
2. ❌ Ambiguous: What does `60` mean? (60s? 60m?)
3. ❌ Limited: Can't specify days (`1d`) or weeks (`1w`)
4. ❌ Integer→String conversion required
5. ❌ Confusing for users

---

## Goal State

### **Unified: Strings Everywhere** ✅

**Config Files** (Strings):
```json
{
  "historical": {
    "data": [{
      "trailing_days": 5,
      "intervals": ["1m", "5m", "15m", "1d"]  // ✅ Strings with units
    }]
  }
}
```

**Benefits**:
1. ✅ **Consistent**: Strings everywhere (config + code)
2. ✅ **Self-documenting**: `"1d"` is clear, `1` is ambiguous
3. ✅ **Flexible**: Seconds, minutes, days, weeks all supported
4. ✅ **No conversion**: Direct string usage
5. ✅ **Extensible**: Future intervals (months, quarters) just work

---

## Supported Intervals

### **YES** ✅
- **Seconds**: `"1s"`, `"5s"`, `"10s"`, `"30s"`, ..., `"Ns"`
- **Minutes**: `"1m"`, `"2m"`, `"5m"`, `"15m"`, `"30m"`, ..., `"Nm"`
- **Days**: `"1d"`, `"2d"`, `"5d"`, ..., `"Nd"`
- **Weeks**: `"1w"`, `"2w"`, `"4w"`, ..., `"Nw"`

### **NO** ❌
- **Hourly**: `"1h"`, `"2h"` → Use `"60m"`, `"120m"` instead
- **Integers**: `5`, `15`, `30` → Use `"5m"`, `"15m"`, `"30m"`

---

## Architecture Review

### **Already Unified** ✅

1. **IntervalStorageStrategy** - Generic storage for ALL intervals
   ```python
   # parquet_storage.py uses this - NO hardcoding!
   strategy.get_file_path("1s", "AAPL", 2025, 7, 15)  # ✅ Works
   strategy.get_file_path("5m", "AAPL", 2025, 7, 15)  # ✅ Works
   strategy.get_file_path("1d", "AAPL", 2025, None, None)  # ✅ Works
   strategy.get_file_path("1w", "AAPL", 2025, None, None)  # ✅ Works
   ```

2. **Bar Aggregation** - Unified compute for ALL intervals
   ```python
   # derived_bars.py - parameterized, NO hardcoding!
   compute_derived_bars(bars, "1m", "5m")   # ✅ Works
   compute_derived_bars(bars, "1m", "15m")  # ✅ Works
   compute_derived_bars(bars, "1m", "1d")   # ✅ Works
   compute_derived_bars(bars, "1d", "1w")   # ✅ Works
   ```

3. **Interval Parsing** - Parse ANY interval string
   ```python
   # requirement_analyzer.py
   parse_interval("1s")  # ✅ IntervalInfo(type=SECOND, seconds=1)
   parse_interval("5m")  # ✅ IntervalInfo(type=MINUTE, seconds=300)
   parse_interval("1d")  # ✅ IntervalInfo(type=DAY, seconds=23400)
   parse_interval("1w")  # ✅ IntervalInfo(type=WEEK, seconds=117000)
   parse_interval("1h")  # ❌ Raises ValueError (hourly not supported)
   ```

### **Needs Unification** ❌

1. **Config Schema** - Still uses integers
2. **Config Validation** - Validates integers, needs string validation
3. **Historical Bar Generation** - Has hardcoded minute assumptions
4. **Example Configs** - Show integers, need string examples

---

## Files to Modify

### **1. Config Schema** (app/models/session_config.py)

**Current** (Lines 106-112):
```python
valid_intervals = ["1s", "1m", "5m", "10m", "15m", "30m", "1h", "1d"]
for interval in self.intervals:
    if interval not in valid_intervals:
        raise ValueError(f"Invalid interval '{interval}'")
```

**New**:
```python
# Parse and validate using existing parse_interval()
from app.threads.quality.requirement_analyzer import parse_interval, IntervalType

for interval in self.intervals:
    try:
        info = parse_interval(interval)
        
        # Reject hourly intervals
        if info.type == IntervalType.HOUR:
            raise ValueError(
                f"Hourly intervals not supported. Use minutes (e.g., '60m') instead."
            )
    except ValueError as e:
        raise ValueError(f"Invalid interval '{interval}': {e}")
```

---

### **2. Session Coordinator** (app/threads/session_coordinator.py)

**Current** (Lines 1218-1226):
```python
# Hardcoded list
derived_intervals = ["5m", "15m", "30m", "1h"]

for derived_interval in derived_intervals:
    # Parse to int for historical_bars dict key
    if derived_interval.endswith('m'):
        interval_int = int(derived_interval[:-1])
```

**New**:
```python
# Get derived intervals from session requirements (already computed)
# No hardcoding - use what's in SessionRequirements
symbol_data = self.session_data.get_symbol_data(symbol)
if not symbol_data:
    return

derived_intervals = [
    interval for interval, iv_data in symbol_data.bars.items()
    if iv_data.derived
]

for derived_interval in derived_intervals:
    # Use interval string directly - no conversion needed!
    derived_bars = compute_derived_bars(
        source_bars,
        source_interval=symbol_data.base_interval,
        target_interval=derived_interval,
        time_manager=self._time_manager
    )
```

---

### **3. Example Configs** (session_configs/*.json)

**Current**:
```json
{
  "data_upkeep": {
    "derived_intervals": [5, 15]  // ❌ Integers
  }
}
```

**New**:
```json
{
  "historical": {
    "data": [{
      "trailing_days": 5,
      "intervals": ["1m", "5m", "15m", "1d"]  // ✅ Strings
    }]
  }
}
```

---

## Implementation Tasks

### **Phase 1: Config Schema** ✅
- [x] Update `HistoricalDataConfig.validate()` to parse interval strings
- [x] Remove hardcoded `valid_intervals` list
- [x] Use `parse_interval()` for validation
- [x] Reject hourly intervals explicitly
- [x] Update docstrings

### **Phase 2: Session Coordinator** ✅
- [x] Remove hardcoded `derived_intervals` list
- [x] Query derived intervals from `SessionRequirements`
- [x] Remove integer parsing logic
- [x] Use interval strings directly
- [x] Delete conversion code

### **Phase 3: Example Configs** ✅
- [x] Update all JSON files to use string arrays
- [x] Remove integer examples
- [x] Add comments explaining string format
- [x] Show examples of seconds, minutes, days, weeks

### **Phase 4: Delete Old Code** ✅
- [x] Remove integer→string conversion functions
- [x] Remove hardcoded interval lists
- [x] Clean up legacy validation code

---

## Validation Strategy

### **Config Validation Flow**

```python
# User specifies in config
"intervals": ["1m", "5m", "1d", "1w"]

# ↓ Validation (session_config.py)
for interval in self.intervals:
    info = parse_interval(interval)  # Validates format
    if info.type == IntervalType.HOUR:
        raise ValueError("Hourly not supported")

# ↓ Requirement Analysis (requirement_analyzer.py)
SessionRequirements(
    explicit_intervals=["1m", "5m", "1d", "1w"],
    required_base_interval="1m",  # Smallest interval
    derivable_intervals=["5m", "1d", "1w"]  # Derived from 1m
)

# ↓ Registration (session_coordinator.py)
for symbol in symbols:
    bars = {
        "1m": BarIntervalData(derived=False, base=None),  # Base
        "5m": BarIntervalData(derived=True, base="1m"),   # Derived
        "1d": BarIntervalData(derived=True, base="1m"),   # Derived
        "1w": BarIntervalData(derived=True, base="1d"),   # Derived (from 1d)
    }
    symbol_data = SymbolSessionData(symbol=symbol, base_interval="1m", bars=bars)
    session_data.register_symbol_data(symbol_data)

# ↓ Computation (data_processor.py + derived_bars.py)
compute_derived_bars(bars_1m, "1m", "5m")  # Strings all the way down!
```

---

## Testing Plan

### **Test 1: Config Validation**
```python
def test_string_intervals():
    config = HistoricalDataConfig(
        trailing_days=5,
        intervals=["1m", "5m", "1d", "1w"]
    )
    config.validate(["AAPL", "RIVN"])  # ✅ Should pass

def test_reject_hourly():
    config = HistoricalDataConfig(
        trailing_days=5,
        intervals=["1m", "1h"]  # ❌ Should fail
    )
    with pytest.raises(ValueError, match="Hourly intervals not supported"):
        config.validate(["AAPL"])

def test_reject_integers():
    config = HistoricalDataConfig(
        trailing_days=5,
        intervals=[5, 15]  # ❌ Should fail (wrong type)
    )
    # This will fail at JSON parsing level (not strings)
```

### **Test 2: Historical Bar Generation**
```python
def test_generate_any_interval():
    # Should work for seconds, minutes, days, weeks
    coordinator._generate_derived_historical_bars(symbol, "5m")   # ✅
    coordinator._generate_derived_historical_bars(symbol, "1d")   # ✅
    coordinator._generate_derived_historical_bars(symbol, "1w")   # ✅
```

### **Test 3: Requirement Analysis**
```python
def test_requirement_analysis():
    result = analyze_session_requirements({
        "intervals": ["1m", "5m", "15m", "1d", "1w"]
    })
    
    assert result.required_base_interval == "1m"
    assert "5m" in result.derivable_intervals
    assert "15m" in result.derivable_intervals
    assert "1d" in result.derivable_intervals
    assert "1w" in result.derivable_intervals
```

---

## Migration Guide

### **For Users**

**Old Config** ❌:
```json
{
  "data_upkeep": {
    "derived_intervals": [5, 15, 30]
  }
}
```

**New Config** ✅:
```json
{
  "historical": {
    "data": [{
      "trailing_days": 5,
      "intervals": ["1m", "5m", "15m", "30m"]
    }]
  }
}
```

**Breaking Change**: Integer arrays no longer supported. Convert to strings:
- `5` → `"5m"`
- `15` → `"15m"`
- `60` → `"60m"` (or consider `"1h"` → NOT SUPPORTED, use `"60m"`)

---

## Success Criteria

### **After Implementation** ✅

1. ✅ **Config uses strings only**
   ```json
   "intervals": ["1m", "5m", "1d", "1w"]
   ```

2. ✅ **No integer parsing**
   ```python
   # NO MORE:
   interval_int = int(interval[:-1])  # ❌ DELETED
   ```

3. ✅ **Hourly explicitly rejected**
   ```python
   parse_interval("1h")  # ❌ ValueError: "Hourly intervals not supported"
   ```

4. ✅ **All intervals work**
   ```python
   # Seconds
   compute_derived_bars(bars, "1s", "5s")  # ✅
   
   # Minutes
   compute_derived_bars(bars, "1m", "15m")  # ✅
   
   # Days
   compute_derived_bars(bars, "1m", "1d")  # ✅
   
   # Weeks
   compute_derived_bars(bars, "1d", "1w")  # ✅
   ```

5. ✅ **Consistent everywhere**
   - Config: Strings ✅
   - Validation: Strings ✅
   - Code: Strings ✅
   - Storage: Strings ✅
   - Computation: Strings ✅

---

## Benefits

### **Immediate**
- ✅ Consistent API (strings everywhere)
- ✅ Self-documenting configs (`"1d"` vs `1`)
- ✅ No conversion overhead
- ✅ Cleaner code (no integer parsing)

### **Long-term**
- ✅ Extensible (new intervals = 0 code changes)
- ✅ Maintainable (single representation)
- ✅ User-friendly (clear meaning)
- ✅ Type-safe (string validation)

---

## Estimated Effort

| Task | Effort | Files |
|------|--------|-------|
| Config Schema Validation | 1 hour | 1 file |
| Session Coordinator Cleanup | 2 hours | 1 file |
| Example Configs Update | 0.5 hours | 3-5 files |
| Delete Old Code | 0.5 hours | 2-3 files |
| Testing | 1 hour | New tests |
| **Total** | **5 hours** | **~10 files** |

---

## Next Steps

1. ✅ Update `session_config.py` validation (use `parse_interval()`)
2. ✅ Update `session_coordinator.py` (remove hardcoded lists)
3. ✅ Update example JSON configs (integers → strings)
4. ✅ Delete integer conversion code
5. ✅ Add tests for string validation
6. ✅ Update documentation

---

## **Status**: ⏳ **READY TO IMPLEMENT**

Clean break approach - delete old integer support, strings only, no backward compatibility.
