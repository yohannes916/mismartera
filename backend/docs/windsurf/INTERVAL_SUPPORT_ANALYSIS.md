# Complete Interval Support Analysis

**Date**: December 7, 2025  
**Analysis Type**: Full Pipeline Audit  
**Requested Support**: `1s, 2s, 3s, ..., 1m, 2m, 3m, ..., 1d, 2d, 3d, ..., 1w, 2w, 3w`

---

## Executive Summary

### ✅ **CURRENTLY SUPPORTED**
- **Seconds**: `1s, 2s, 3s, ..., 59s` ✅
- **Minutes**: `1m, 2m, 3m, ..., N` ✅  
- **Hours**: `1h, 2h, 3h, ..., N` ⚠️ (parsing only, limited storage)
- **Days**: `1d` ✅ (limited multi-day support)

### ❌ **NOT SUPPORTED**
- **Multi-day bars**: `2d, 3d, 4d, ...` ❌
- **Week bars**: `1w, 2w, 3w, ...` ❌ (NO parsing, NO storage, NO computation)

### ⚠️ **PARTIAL SUPPORT**
- **Multi-hour bars**: `2h, 3h, ...` ⚠️ (parsing works, no storage, derived computation untested)

---

## Detailed Component Analysis

### 1. **Interval Parsing Functions**

#### A. `parse_interval_to_minutes()` - quality_helpers.py
**Location**: `/app/threads/quality/quality_helpers.py` lines 16-110

**Supported Units**:
- ✅ `s` - Seconds (converted to fractional minutes: 1s = 1/60 min)
- ✅ `m` - Minutes
- ✅ `h` - Hours (converted to minutes: 1h = 60min)
- ✅ `d` - Days (SPECIAL: queries TimeManager for actual trading minutes)
- ❌ `w` - **NOT SUPPORTED**

**Code**:
```python
if interval.endswith("m"):
    return float(interval[:-1])
elif interval.endswith("s"):
    return int(interval[:-1]) / 60.0
elif interval.endswith("h"):
    return float(int(interval[:-1]) * 60)
elif interval.endswith("d"):
    # Special handling via TimeManager
    return trading_minutes  # 390 for regular, varies for early close
else:
    # Falls back to trying float() - accepts plain numbers
```

**Gaps**:
- ❌ No week support (`w` unit)
- ⚠️ Daily (`d`) only works for `1d`, not `2d, 3d`

---

#### B. `parse_interval()` - requirement_analyzer.py
**Location**: `/app/threads/quality/requirement_analyzer.py` lines 102-174

**Supported Units**:
- ✅ `s` - Seconds
- ✅ `m` - Minutes  
- ✅ `h` - Hours
- ✅ `d` - Days
- ✅ `quotes` - Special case
- ❌ `w` - **NOT SUPPORTED**

**Regex Pattern**:
```python
match = re.match(r'^(\d+)([smhd])$', interval_lower)
```

**Base Intervals** (is_base=True):
- `1s` - Base second interval
- `1m` - Base minute interval
- `1d` - Base daily interval

**Gaps**:
- ❌ No week parsing (regex doesn't include `w`)
- ⚠️ Multi-day intervals (`2d, 3d`) parse successfully but no downstream support

---

### 2. **Parquet Storage** - parquet_storage.py

**Location**: `/app/managers/data_manager/parquet_storage.py`

**Supported Intervals** (Hard-coded):
- ✅ `1s` - Second bars (stored in `bars/1s/SYMBOL/YEAR/MONTH.parquet`)
- ✅ `1m` - Minute bars (stored in `bars/1m/SYMBOL/YEAR/MONTH.parquet`)
- ✅ `1d` - Daily bars (stored in `bars/1d/SYMBOL/YEAR.parquet`)
- ✅ `quotes` - Quote data (stored in `quotes/SYMBOL/YEAR/MONTH/DAY.parquet`)

**Critical Code** (lines 277-343):
```python
if data_type in ['1s', '1m']:
    # Monthly files
    dir_path = self.base_path / self.exchange_group / "bars" / data_type / symbol / str(year)
elif data_type == '1d':
    # Yearly files
    dir_path = self.base_path / self.exchange_group / "bars" / "1d" / symbol
else:
    raise ValueError(f"Invalid data_type: {data_type}. Must be 1s, 1m, 1d, or quotes")
```

**Gaps**:
- ❌ **No multi-second support**: `2s, 3s, ...` not stored (can only be derived)
- ❌ **No multi-minute support**: `2m, 3m, 5m, 15m` not stored (can only be derived)
- ❌ **No hour support**: `1h, 2h, 3h` not stored (can only be derived)
- ❌ **No multi-day support**: `2d, 3d, 5d` not stored
- ❌ **No week support**: `1w, 2w, 52w` not stored

**Architecture**:
- Only **BASE intervals** are stored: `1s`, `1m`, `1d`
- All other intervals must be **derived** at runtime

---

### 3. **Derived Bars Computation** - derived_bars.py

**Location**: `/app/managers/data_manager/derived_bars.py`

**Input**: 1-minute bars (`List[BarData]`)  
**Output**: N-minute bars (`List[BarData]`)  

**Supported Intervals** (documented):
- ✅ `5m, 15m, 30m, 60m` (explicitly documented)
- ✅ **ANY integer minutes** (code accepts any positive int)

**Code** (lines 16-24):
```python
def compute_derived_bars(
    bars_1m: List[BarData],
    interval: int  # Interval in MINUTES
) -> List[BarData]:
```

**Logic**:
- Groups 1m bars into chunks of size `interval`
- Verifies continuity (no gaps)
- Aggregates OHLCV (open=first, high=max, low=min, close=last, volume=sum)

**Gaps**:
- ⚠️ **Only works with 1m source** - cannot derive from 1s
- ❌ **Hours must be converted to minutes**: `1h` → `60`, `2h` → `120`
- ❌ **No daily derivation support**: Cannot compute `2d` from `1d`
- ❌ **No week support**: Cannot compute `1w` from `1d`
- ⚠️ **Incomplete bars skipped**: If session has 7 bars and interval=5, only 1 bar computed (2 bars discarded)

---

### 4. **Session Coordinator** - session_coordinator.py

**Streaming Support**:
- ✅ **1m bars ONLY** - Hard validation (lines 364-369 in system_manager.py)
- ❌ All other intervals **rejected** at stream level

**Historical Support**:
- ✅ Can load any interval from historical config
- ⚠️ Quality/gaps calculation supports: `1s, 1m, 1d` (via parse functions)

**Code**:
```python
if stream_config.interval != "1m":
    raise ValueError(
        f"Stream coordinator only supports 1m bars. "
        f"Derived intervals (5m, 15m, etc.) are automatically computed by the data upkeep thread."
    )
```

---

### 5. **Data Processor** - data_processor.py

**Supports**: Derived interval computation from 1m bars  
**Method**: Calls `compute_derived_bars()` with interval in minutes

**Code** (lines 410-419):
```python
intervals_parsed = []
for interval_str in symbol_intervals:
    if interval_str.endswith('m'):
        interval_int = int(interval_str[:-1])
        intervals_parsed.append(interval_int)

sorted_intervals = sorted(intervals_parsed)
```

**Gaps**:
- ⚠️ **Only parses minute intervals** (`Xm`)
- ❌ **Hours/days/weeks not handled**

---

### 6. **Data Quality Manager** - data_quality_manager.py

**Uses**: `parse_interval_to_minutes()` for quality calculation

**Supported Intervals**:
- ✅ `1s, 2s, ..., Ns` (via quality_helpers)
- ✅ `1m, 2m, ..., Nm` (via quality_helpers)
- ✅ `1h, 2h, ..., Nh` (via quality_helpers)
- ✅ `1d` only (via quality_helpers with TimeManager)
- ❌ Multi-day, weeks not supported

**Code** (lines 367-374):
```python
# Uses parse_interval_to_minutes for interval parsing
trading_session = self._time_manager.get_trading_session(db_session, current_date)
interval_minutes = parse_interval_to_minutes(interval, trading_session)

if interval_minutes is None:
    logger.warning(f"Cannot parse interval {interval} for gap detection")
    gaps = []
```

---

### 7. **Gap Detection** - gap_detection.py

**Supports**: Any interval parsed to minutes

**Method**: 
- Generates expected timestamps based on `interval_minutes`
- Compares with actual bar timestamps
- Reports gaps

**Gaps**:
- ⚠️ **Days**: Only works for `1d` (each day = 1 bar)
- ❌ **Multi-day**: Cannot detect gaps in `2d, 3d` bars
- ❌ **Weeks**: No support

---

## Missing Support Summary

### **Critical Gaps** ❌

#### 1. **Week Intervals** (NO SUPPORT ANYWHERE)
- ❌ Parsing: `parse_interval()` regex doesn't include `w`
- ❌ Storage: Parquet has no `bars/1w/` directory
- ❌ Computation: No weekly aggregation logic
- ❌ Quality: Cannot calculate quality for weeks
- ❌ Gaps: Cannot detect weekly gaps

**To Add**:
```python
# In parse_interval()
elif unit == 'w':
    interval_type = IntervalType.WEEK
    seconds = value * 604800  # 7 days * 86400
    is_base = (value == 1)
```

But this alone is insufficient - needs full pipeline changes.

---

#### 2. **Multi-Day Intervals** (PARTIAL SUPPORT)
- ✅ Parsing: `2d, 3d` parse successfully
- ❌ Storage: No `bars/2d/`, `bars/3d/` directories
- ❌ Computation: Cannot aggregate `1d` → `2d`
- ⚠️ Quality: `parse_interval_to_minutes()` only works for `1d`
- ❌ Gaps: No gap detection for multi-day

**Issue with Quality**:
```python
# In parse_interval_to_minutes()
elif interval.endswith("d"):
    # This assumes interval == "1d"
    # For "2d", it would try to get trading minutes for "2 days"
    # But trading_session is for a single date!
```

**To Fix**:
- Extend `parse_interval_to_minutes()` to handle `2d, 3d` (multiply by trading days)
- Add storage paths for multi-day
- Add aggregation: `compute_derived_bars_from_daily()`
- Update gap detection for multi-day sequences

---

#### 3. **Multi-Hour Intervals** (PARSING ONLY)
- ✅ Parsing: `2h, 3h` parse successfully  
- ❌ Storage: No storage (must be derived)
- ⚠️ Computation: Could work (convert to minutes: `2h = 120m`)
- ⚠️ Quality: Untested but should work
- ⚠️ Gaps: Untested but should work

**Likely Works (with conversion)**:
```python
# User specifies "2h"
parse_interval_to_minutes("2h") → 120.0
compute_derived_bars(bars_1m, 120) → 2-hour bars ✅
```

But this is **untested** and may have edge cases.

---

### **Minor Gaps** ⚠️

#### 4. **Multi-Second Intervals**
- ✅ Parsing: `2s, 3s, 5s` parse successfully
- ❌ Storage: No storage (only `1s` stored)
- ⚠️ Computation: Would need `compute_derived_bars_from_seconds()`
- ✅ Quality: Should work (fractional minutes)
- ⚠️ Gaps: Should work but untested

**Current limitation**: 
- Can only derive minutes from 1m
- Cannot derive `5s` from `1s` (no aggregation function)

---

## Configuration Issues

### **Historical Config** - Supports any interval string
```json
{
  "historical": {
    "data": [
      {"trailing_days": 3, "intervals": ["1m"]},  // ✅ Works
      {"trailing_days": 5, "intervals": ["1d"]},  // ✅ Works
      {"trailing_days": 10, "intervals": ["2d"]}, // ⚠️ Parses but breaks downstream
      {"trailing_days": 52, "intervals": ["1w"]}  // ❌ Parse error!
    ]
  }
}
```

### **Derived Intervals Config** - Expects minutes
```json
{
  "data_upkeep": {
    "derived_intervals": [5, 15, 30, 60],  // ✅ Works (minutes)
    "derived_intervals": ["5m", "1h"],     // ❌ Expects integers!
  }
}
```

**Issue**: Config uses integers (assumes minutes), but rest of system uses strings with units.

---

## Recommended Changes for Full Support

### **Phase 1: Week Support** (High Priority)

1. **Update Parsers**:
   ```python
   # requirement_analyzer.py line 136
   match = re.match(r'^(\d+)([smhdw])$', interval_lower)  # Add 'w'
   
   # Add week handling
   elif unit == 'w':
       interval_type = IntervalType.WEEK
       seconds = value * 604800
       is_base = (value == 1)
   ```

2. **Update quality_helpers.py**:
   ```python
   elif interval.endswith("w"):
       # Weeks: multiply days by 5 (trading days)
       return value * 5 * 390.0  # Approximate
   ```

3. **Add Parquet Storage**:
   ```python
   elif data_type == '1w':
       # bars/1w/<SYMBOL>/<YEAR>.parquet
   ```

4. **Add Weekly Aggregation**:
   ```python
   def compute_weekly_bars(bars_1d: List[BarData], weeks: int) -> List[BarData]:
       # Group 1d bars by week, aggregate
   ```

---

### **Phase 2: Multi-Day Support** (Medium Priority)

1. **Fix `parse_interval_to_minutes()` for multi-day**:
   ```python
   elif interval.endswith("d"):
       days = int(interval[:-1])
       if days == 1:
           # Current logic for 1d
       else:
           # Multi-day: multiply by trading days
           return days * 390.0  # Approximate
   ```

2. **Add Multi-Day Aggregation**:
   ```python
   def compute_multiday_bars(bars_1d: List[BarData], days: int) -> List[BarData]:
       # Group 1d bars by N-day chunks
   ```

3. **Add Storage** (optional - can remain derived):
   ```python
   elif data_type.endswith('d') and data_type != '1d':
       # bars/5d/<SYMBOL>/<YEAR>.parquet
   ```

---

### **Phase 3: Multi-Second Support** (Low Priority)

1. **Add Second-to-Second Aggregation**:
   ```python
   def compute_derived_seconds(bars_1s: List[BarData], seconds: int) -> List[BarData]:
       # Similar to compute_derived_bars but for seconds
   ```

2. **Update Data Upkeep** to support second-level derivation

---

### **Phase 4: Unify Config** (Cleanup)

**Problem**: `derived_intervals` uses integers, everywhere else uses strings

**Solution**: 
```python
# Change config to accept strings
"derived_intervals": ["5m", "15m", "1h", "1d"]

# Parse in data_upkeep_thread.py
for interval_str in derived_intervals:
    interval_minutes = parse_interval_to_minutes(interval_str)
```

---

## Testing Requirements

### **New Intervals to Test**

1. **Week bars**:
   - `1w` from `1d` bars (5 trading days)
   - `2w` from `1d` bars (10 trading days)
   - Quality calculation for weeks
   - Gap detection (missing weeks)

2. **Multi-day bars**:
   - `2d` from `1d` bars
   - `5d` (1 week) from `1d` bars
   - Quality for multi-day
   - Gaps in multi-day sequences

3. **Multi-hour bars**:
   - `2h` from `1m` bars (120 minutes)
   - `4h` from `1m` bars (240 minutes)
   - Quality for multi-hour
   - Gaps across hours

4. **Multi-second bars**:
   - `5s` from `1s` bars
   - `10s` from `1s` bars
   - Quality for sub-minute
   - Gaps in second sequences

---

## Current Support Matrix

| Interval | Parse | Store | Derive | Quality | Gaps | Notes |
|----------|-------|-------|--------|---------|------|-------|
| `1s` | ✅ | ✅ | N/A | ✅ | ✅ | Base second |
| `2s-59s` | ✅ | ❌ | ❌ | ✅ | ⚠️ | Parsing only |
| `1m` | ✅ | ✅ | N/A | ✅ | ✅ | Base minute |
| `2m-Nm` | ✅ | ❌ | ✅ | ✅ | ✅ | Derived from 1m |
| `1h-Nh` | ✅ | ❌ | ⚠️ | ⚠️ | ⚠️ | Convert to minutes |
| `1d` | ✅ | ✅ | N/A | ✅ | ✅ | Base daily |
| `2d-Nd` | ⚠️ | ❌ | ❌ | ❌ | ❌ | Parsing only |
| `1w-Nw` | ❌ | ❌ | ❌ | ❌ | ❌ | **NOT SUPPORTED** |
| `quotes` | ✅ | ✅ | N/A | N/A | N/A | Special case |

**Legend**:
- ✅ Fully supported
- ⚠️ Partially supported (works but untested or edge cases)
- ❌ Not supported

---

## Conclusion

### **What Works Today**
- ✅ Second bars: `1s` only (base)
- ✅ Minute bars: `1m` (base) + any derived (`2m, 3m, 5m, 15m, 30m, 60m`)
- ✅ Daily bars: `1d` only (base)
- ✅ Hour bars: Likely works if converted to minutes (`1h = 60m`)

### **What Doesn't Work**
- ❌ Multi-second bars: `2s, 3s, 5s` (no aggregation function)
- ❌ Multi-day bars: `2d, 3d, 5d` (parsing only, no downstream support)
- ❌ Week bars: `1w, 2w, 52w` (NO support anywhere)

### **Effort Required**

**To add full support**:
1. **Week support**: 5-8 files to modify, 2-3 days work
2. **Multi-day support**: 3-5 files to modify, 1-2 days work  
3. **Multi-second support**: 2-3 files to modify, 1 day work
4. **Multi-hour**: May already work (needs testing)

**Total**: ~1 week of development + testing

---

## Files Requiring Changes

### **For Week Support**:
1. `/app/threads/quality/requirement_analyzer.py` - Add `w` to regex
2. `/app/threads/quality/quality_helpers.py` - Add week parsing
3. `/app/managers/data_manager/parquet_storage.py` - Add `1w` storage path
4. `/app/managers/data_manager/derived_bars.py` - Add `compute_weekly_bars()`
5. `/app/threads/data_upkeep_thread.py` - Support weekly computation
6. `/app/threads/session_coordinator.py` - Update quality/gaps for weeks
7. `/app/cli/session_data_display.py` - Display week intervals

### **For Multi-Day Support**:
1. `/app/threads/quality/quality_helpers.py` - Fix `parse_interval_to_minutes()` for multi-day
2. `/app/managers/data_manager/derived_bars.py` - Add `compute_multiday_bars()`
3. `/app/threads/session_coordinator.py` - Update quality/gaps for multi-day

### **For Multi-Second Support**:
1. `/app/managers/data_manager/derived_bars.py` - Add `compute_derived_seconds()`
2. `/app/threads/data_upkeep_thread.py` - Support second-level derivation
