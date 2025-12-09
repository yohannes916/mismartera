# Remaining Interval Support Work

**Date**: December 7, 2025  
**Status**: Post Unified Aggregation Implementation

---

## What We've Accomplished ✅

### **Unified Bar Aggregation Framework** (COMPLETE)
- ✅ Single codebase for all bar aggregations
- ✅ Week parsing (`1w`, `2w`, etc.)
- ✅ Week computation (`1d → 1w`)
- ✅ Daily computation (`1m → 1d`)
- ✅ All minute/second aggregations
- ✅ Calendar-aware grouping
- ✅ TimeManager integration

**Impact**: Can now compute ANY interval from its source (ticks→1s, 1s→1m, 1m→Nm, 1m→1d, 1d→1w)

---

## What Remains ❌

Based on our original analysis, here's what's NOT yet unified/integrated:

### **Priority 1: Parquet Storage** (HIGH - Data Persistence)
**Current State**: Hardcoded for only `1s`, `1m`, `1d`

**Problem**: 
```python
# parquet_storage.py lines 277-343
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
- ❌ No storage for `1w`, `2w` (weekly bars)
- ❌ No storage for multi-second (`2s`, `5s`, etc.)
- ❌ No storage for multi-day (`2d`, `5d`, etc.)
- ❌ Hardcoded interval list (not extensible)

**Impact**: 
- Weekly bars can be computed but not persisted
- Multi-day bars can be computed but not persisted
- Every restart requires recomputation

**Unified Solution Needed**:
```python
# Generic storage path determination
def get_storage_path(interval: str, symbol: str, timestamp: datetime):
    """Determine storage path based on interval type.
    
    Rules:
    - Sub-minute (1s, 2s, etc.) → Monthly files
    - Minute (1m-59m) → Monthly files
    - Hourly (1h+) → Monthly files
    - Daily (1d+) → Yearly files
    - Weekly (1w+) → Yearly files
    """
    interval_info = parse_interval(interval)
    
    if interval_info.type in [IntervalType.SECOND, IntervalType.MINUTE, IntervalType.HOUR]:
        # Sub-daily: monthly files
        return f"bars/{interval}/{symbol}/{timestamp.year}/{timestamp.month:02d}.parquet"
    else:
        # Daily+: yearly files
        return f"bars/{interval}/{symbol}/{timestamp.year}.parquet"
```

---

### **Priority 2: Config System** (MEDIUM - Usability)
**Current State**: Mixed integer/string usage, inconsistent

**Problem**:
```python
# Config uses INTEGERS (assumes minutes)
"derived_intervals": [5, 15, 30, 60]

# But everywhere else uses STRINGS with units
compute_derived_bars(bars_1m, "1m", "5m")
parse_interval("5m")
```

**Gaps**:
- ❌ Cannot specify hours in config (`"1h"`)
- ❌ Cannot specify seconds in config (`"5s"`)
- ❌ Cannot specify daily/weekly in config (`"1d"`, `"1w"`)
- ⚠️ Confusing for users (why integers here but strings elsewhere?)

**Impact**:
- Users can't configure weekly derived bars
- Users can't configure hourly derived bars
- Inconsistent API

**Unified Solution**:
```python
# Update config schema to accept interval strings
{
  "data_upkeep": {
    "derived_intervals": ["5m", "15m", "1h", "1d", "1w"]  // ✅ Strings with units
  }
}

# Update data_upkeep_thread.py to parse strings
for interval_str in derived_intervals:
    # Now can handle ANY interval type!
    derived_bars = compute_derived_bars(
        source_bars,
        source_interval="1m",
        target_interval=interval_str  // "5m", "1h", "1d", "1w" all work!
    )
```

---

### **Priority 3: Multi-Day Quality Calculation** (MEDIUM - Data Quality)
**Current State**: `parse_interval_to_minutes()` only handles `1d`

**Problem**:
```python
# quality_helpers.py
elif interval.endswith("d"):
    # Gets trading_session for a SINGLE date
    # But "2d", "3d" need MULTIPLE days!
    trading_minutes = (close_dt - open_dt).total_seconds() / 60
    return trading_minutes  # ❌ Only works for 1d
```

**Gaps**:
- ❌ `parse_interval_to_minutes("2d")` fails
- ❌ `parse_interval_to_minutes("5d")` fails
- ⚠️ Quality calculation broken for multi-day bars

**Impact**:
- Multi-day bars show 0% quality
- Gap detection doesn't work for multi-day

**Unified Solution**:
```python
elif interval.endswith("d"):
    days = int(interval[:-1])
    
    if days == 1:
        # Single day: use trading_session
        if trading_session.is_holiday:
            return 0.0
        trading_minutes = (close_dt - open_dt).total_seconds() / 60
        return trading_minutes
    else:
        # Multi-day: approximate (would need calendar for accuracy)
        return days * 390.0  # Approximate: 390 min/day
```

---

### **Priority 4: Data Upkeep Thread Integration** (LOW - Already Mostly Works)
**Current State**: Uses integers, calls `compute_derived_bars()`

**Problem**:
```python
# data_upkeep_thread.py
derived_intervals = [5, 15, 30]  # Integers only

for interval in sorted_intervals:
    derived_bars = compute_derived_bars(
        bars_base,
        source_interval="1m",
        target_interval=f"{interval}m"  # ✅ Already updated!
    )
```

**Gaps**:
- ⚠️ Config still expects integers
- ⚠️ Only supports minute intervals (no hours, days, weeks)

**Impact**:
- Cannot auto-derive hourly bars
- Cannot auto-derive daily/weekly bars

**Unified Solution**:
```python
# Accept interval strings from config
derived_intervals = ["5m", "15m", "1h", "1d", "1w"]  # ✅ Any interval!

for interval_str in derived_intervals:
    # Determine appropriate source
    source_interval = determine_source_for_target(interval_str)
    source_bars = get_bars(symbol, source_interval)
    
    # Compute (already unified!)
    derived_bars = compute_derived_bars(
        source_bars,
        source_interval=source_interval,
        target_interval=interval_str,
        time_manager=self._time_manager
    )
```

---

### **Priority 5: Session Coordinator Historical** (LOW - Edge Case)
**Current State**: Generates derived historical bars for minutes only

**Problem**:
```python
# session_coordinator.py _generate_derived_historical_bars()
# Only handles minute intervals
if not interval_str.endswith('m'):
    continue  # Skip non-minute intervals
```

**Gaps**:
- ❌ Cannot generate historical daily bars from 1m
- ❌ Cannot generate historical weekly bars from 1d

**Impact**:
- Historical data only available for minute intervals
- Must compute daily/weekly from scratch each session

**Unified Solution**:
```python
# Support ANY derived interval for historical
for interval_str in intervals_to_generate:
    # Determine source interval
    if interval_str.endswith('m'):
        source_interval = "1m"
        source_bars = hist_1m_data.data_by_date[hist_date]
    elif interval_str.endswith('d'):
        source_interval = "1d"
        source_bars = hist_1d_data.data_by_date[hist_date]
    
    # Compute (unified!)
    derived_bars = compute_derived_bars(
        source_bars,
        source_interval=source_interval,
        target_interval=interval_str
    )
```

---

## Prioritized Roadmap

### **Phase 1: Unified Parquet Storage** (2-3 days)
**Goal**: Generic, extensible storage that handles ANY interval

**Tasks**:
1. Create `IntervalStorageStrategy` class
2. Implement generic path resolution
3. Remove hardcoded `['1s', '1m', '1d']` checks
4. Support weekly storage (`1w`, `2w`)
5. Support multi-second storage (optional)
6. Support multi-day storage (optional)

**Benefits**:
- ✅ Weekly bars can be persisted
- ✅ No restart recomputation
- ✅ Extensible to ANY interval
- ✅ Clean architecture

---

### **Phase 2: Config Unification** (1 day)
**Goal**: Consistent interval representation everywhere

**Tasks**:
1. Update config schema to accept interval strings
2. Update data_upkeep_thread to parse strings
3. Remove integer-only assumptions
4. Support hours/days/weeks in config

**Benefits**:
- ✅ Users can configure ANY derived interval
- ✅ Consistent API (strings everywhere)
- ✅ Self-documenting configs

---

### **Phase 3: Multi-Day Quality** (1 day)
**Goal**: Accurate quality for multi-day bars

**Tasks**:
1. Update `parse_interval_to_minutes()` for multi-day
2. Add approximate calculation (days × 390)
3. Consider calendar-aware calculation (use TimeManager)

**Benefits**:
- ✅ Multi-day bars show correct quality
- ✅ Gap detection works for multi-day

---

### **Phase 4: Full Data Upkeep Integration** (0.5 days)
**Goal**: Auto-derive ANY interval

**Tasks**:
1. Update to accept interval strings from config
2. Auto-determine source interval for target
3. Support hours, days, weeks

**Benefits**:
- ✅ Users can auto-derive hourly bars
- ✅ Users can auto-derive daily bars from 1m
- ✅ Users can auto-derive weekly bars from 1d

---

### **Phase 5: Historical Bars Extension** (0.5 days)
**Goal**: Generate ANY derived historical bars

**Tasks**:
1. Remove minute-only restriction
2. Support daily/weekly historical derivation
3. Auto-determine source interval

**Benefits**:
- ✅ Historical daily bars from 1m
- ✅ Historical weekly bars from 1d
- ✅ Faster session startup

---

## Integration Strategy (Same Philosophy)

Following the same unified approach as bar aggregation:

### **Principle 1: Single Source of Truth**
- **Interval metadata**: `parse_interval()` (already done)
- **Storage paths**: New `IntervalStorageStrategy`
- **Quality calculation**: Unified `calculate_quality()`

### **Principle 2: Parameterization**
- Storage strategy based on `IntervalType` (SECOND, MINUTE, HOUR, DAY, WEEK)
- File granularity based on interval (monthly vs yearly)
- Quality calculation based on interval type

### **Principle 3: No Hardcoding**
- ❌ No `['1s', '1m', '1d']` lists
- ❌ No special cases for weeks
- ✅ Generic logic that works for ANY interval

### **Principle 4: Extensibility**
- Adding `1M` (month) interval = 0 code changes (config only)
- Adding `1Q` (quarter) interval = 0 code changes (config only)

---

## Estimated Effort

| Phase | Effort | Priority | Complexity |
|-------|--------|----------|------------|
| **Phase 1: Parquet Storage** | 2-3 days | HIGH | Medium |
| **Phase 2: Config Unification** | 1 day | MEDIUM | Low |
| **Phase 3: Multi-Day Quality** | 1 day | MEDIUM | Low |
| **Phase 4: Data Upkeep** | 0.5 days | LOW | Low |
| **Phase 5: Historical Bars** | 0.5 days | LOW | Low |
| **Total** | **5-6 days** | | |

---

## Success Criteria

### **After All Phases**:

✅ **Storage**: Any interval can be persisted
```python
# All these work:
storage.write_bars(bars, "1s", symbol)
storage.write_bars(bars, "5m", symbol)
storage.write_bars(bars, "1h", symbol)
storage.write_bars(bars, "1d", symbol)
storage.write_bars(bars, "1w", symbol)
```

✅ **Config**: Consistent interval representation
```python
{
  "derived_intervals": ["5m", "15m", "1h", "1d", "1w"]  // ✅ Works!
}
```

✅ **Quality**: All intervals show correct quality
```python
parse_interval_to_minutes("1d") → 390.0
parse_interval_to_minutes("2d") → 780.0  // ✅ Works!
parse_interval_to_minutes("1w") → 1950.0  // ✅ Works!
```

✅ **Data Upkeep**: Auto-derive any interval
```python
# Config
"derived_intervals": ["5m", "1h", "1d", "1w"]

# All auto-computed! ✅
```

✅ **Historical**: Generate any derived historical bars
```python
# Historical 1d from 1m ✅
# Historical 1w from 1d ✅
```

---

## Recommendation

**Start with Phase 1 (Parquet Storage)** - Highest impact

**Reasons**:
1. **Unblocks everything else**: Without storage, weekly/multi-day bars are lost on restart
2. **Highest reuse**: Storage is used by ALL components
3. **Clean architecture**: Generic solution benefits all future intervals
4. **User-facing**: Users want to persist weekly bars NOW

**After Phase 1**, phases 2-5 are quick wins that build on the foundation.

---

## Next Action

Shall we tackle **Phase 1: Unified Parquet Storage**?

**Approach** (same as bar aggregation):
1. Create `IntervalStorageStrategy` class
2. Implement generic path/filename logic
3. Replace hardcoded checks with strategy pattern
4. Test with 1w, 2d, 5s intervals
5. Update all calling code
6. Remove old hardcoded logic

**Deliverable**: Generic storage that works for ANY interval, no hardcoding!
