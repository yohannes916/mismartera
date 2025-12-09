# Unified Bar Aggregation Framework - Design Plan

**Date**: December 7, 2025  
**Goal**: Generic, parameterized bar aggregation system with zero code duplication  
**Scope**: Ticks→1s, 1s→1m, 1m→Nm, 1m→1d, 1d→1w

---

## Executive Summary

### **Current State** (3 separate implementations)
1. **`aggregate_ticks_to_1s()`** - Ticks → 1s bars (parquet_storage.py)
2. **`compute_derived_bars()`** - 1m → Nm bars (derived_bars.py)
3. **No implementations** for: 1s→1m, 1m→1d, 1d→1w

### **Problem**: Code Duplication
- All do OHLCV aggregation (open=first, high=max, low=min, close=last, volume=sum)
- All group by time windows
- All handle chronological ordering
- All validate continuity
- **~80% of logic is identical**

### **Solution**: Unified Framework
Create a single, parameterized aggregation engine that handles ALL bar types with shared code.

---

## Analysis of Existing Code

### **1. Tick → 1s Aggregation** (parquet_storage.py lines 345-387)

**Input**: `List[Dict]` with keys: `timestamp, symbol, close, volume`  
**Output**: `List[Dict]` with keys: `timestamp, symbol, open, high, low, close, volume, trade_count`

**Algorithm**:
```python
# 1. Group by time window
by_second = defaultdict(list)
for tick in ticks:
    second_key = tick['timestamp'].replace(microsecond=0)  # Round to second
    by_second[second_key].append(tick)

# 2. Aggregate OHLCV per group
for second, ticks_in_second in sorted(by_second.items()):
    prices = [t['close'] for t in ticks_in_second]
    bar = {
        'timestamp': second,
        'open': ticks_in_second[0]['close'],    # First tick
        'high': max(prices),                    # Max price
        'low': min(prices),                     # Min price
        'close': ticks_in_second[-1]['close'],  # Last tick
        'volume': sum(t['volume'] for t in ticks_in_second)
    }
```

**Key Characteristics**:
- ✅ Handles sub-second ticks (microsecond precision)
- ✅ Groups by rounding timestamps
- ✅ Works with dict format (not BarData objects)
- ❌ No gap detection
- ❌ No continuity validation

---

### **2. Minute → N-Minute Aggregation** (derived_bars.py lines 16-86)

**Input**: `List[BarData]` (1-minute bars)  
**Output**: `List[BarData]` (N-minute bars)

**Algorithm**:
```python
# 1. Group by fixed-size chunks
i = 0
while i < len(bars_1m):
    chunk = bars_1m[i:i+interval]  # Get N bars
    
    # 2. Validate chunk completeness
    if len(chunk) < interval:
        break  # Incomplete chunk
    
    # 3. Validate continuity (no gaps)
    for j in range(1, len(chunk)):
        expected_time = chunk[j-1].timestamp + timedelta(minutes=1)
        if chunk[j].timestamp != expected_time:
            # Gap detected, skip chunk
            continue
    
    # 4. Aggregate OHLCV
    derived_bar = BarData(
        timestamp=chunk[0].timestamp,
        open=chunk[0].open,
        high=max(b.high for b in chunk),
        low=min(b.low for b in chunk),
        close=chunk[-1].close,
        volume=sum(b.volume for b in chunk)
    )
    
    i += interval  # Move to next chunk
```

**Key Characteristics**:
- ✅ Works with BarData objects
- ✅ Validates continuity (detects gaps)
- ✅ Validates completeness (requires full chunk)
- ✅ Fixed-size chunking (N consecutive bars)
- ❌ Only works for minute intervals
- ❌ No calendar awareness (assumes continuous timestamps)

---

## Common Patterns (80% Shared)

### **A. OHLCV Aggregation** (100% identical)
```python
# Same logic for ALL bar types
aggregated = {
    'open': items[0].price_or_open,      # First
    'high': max(item.high for item in items),  # Max
    'low': min(item.low for item in items),    # Min
    'close': items[-1].price_or_close,   # Last
    'volume': sum(item.volume for item in items)  # Sum
}
```

### **B. Time Window Grouping** (80% similar)
```python
# Group items by time window
by_window = defaultdict(list)
for item in items:
    window_key = calculate_window(item.timestamp, window_size, window_type)
    by_window[window_key].append(item)
```

**Difference**: Window calculation varies by type
- **Seconds**: Round to second (`.replace(microsecond=0)`)
- **Minutes**: Round to minute (`.replace(second=0, microsecond=0)`)
- **Days**: Extract date (`.date()`)
- **Weeks**: Calculate week number (`isocalendar()`)

### **C. Chronological Ordering** (100% identical)
```python
# Sort by timestamp
for window_key, items in sorted(by_window.items()):
    # Aggregate...
```

### **D. Validation** (70% similar)
```python
# Check completeness (some aggregations require full chunks)
if len(items) < expected_count:
    skip_or_partial()

# Check continuity (some aggregations require no gaps)
for i in range(1, len(items)):
    if items[i].timestamp != items[i-1].timestamp + expected_delta:
        handle_gap()
```

**Difference**: Validation rules vary
- **Ticks→1s**: No validation (allow any number of ticks)
- **1m→Nm**: Require complete chunks + continuity
- **1m→1d**: Require trading calendar awareness
- **1d→1w**: Require trading calendar awareness

---

## Differences (20% Varies)

### **1. Input Type**
| Aggregation | Input Type | Attributes |
|-------------|-----------|------------|
| Ticks→1s | `Dict` | `timestamp, symbol, close, volume` |
| 1s→1m | `BarData` | `timestamp, symbol, open, high, low, close, volume` |
| 1m→Nm | `BarData` | Same |
| 1m→1d | `BarData` | Same |
| 1d→1w | `BarData` | Same |

**Solution**: Normalize to common interface (use `BarData` everywhere, convert dicts on input)

---

### **2. Time Window Type**
| Aggregation | Window Type | Size | Rounding |
|-------------|------------|------|----------|
| Ticks→1s | Second | 1s | `replace(microsecond=0)` |
| 1s→1m | Minute | 60s | `replace(second=0, microsecond=0)` |
| 1m→Nm | Minute | N min | Aligned to session start |
| 1m→1d | Day | 1 day | `.date()` |
| 1d→1w | Week | 5 days | `isocalendar().week` |

**Solution**: Parameterize window calculation

---

### **3. Chunking Strategy**
| Aggregation | Strategy | Reason |
|-------------|----------|--------|
| Ticks→1s | Time-based grouping | Multiple ticks per second |
| 1s→1m | Fixed chunks (60 bars) | Require complete minute |
| 1m→Nm | Fixed chunks (N bars) | Require complete interval |
| 1m→1d | Calendar-based | Respect trading days |
| 1d→1w | Calendar-based | Respect trading weeks (5 days) |

**Solution**: Support both chunking modes (fixed-size vs calendar-based)

---

### **4. Completeness Rules**
| Aggregation | Rule |
|-------------|------|
| Ticks→1s | Allow partial (any # ticks) |
| 1s→1m | Require 60 bars |
| 1m→Nm | Require N bars |
| 1m→1d | Allow partial (handle early close) |
| 1d→1w | Allow partial (handle short weeks) |

**Solution**: Parameterize completeness requirement

---

### **5. Continuity Rules**
| Aggregation | Rule |
|-------------|------|
| Ticks→1s | Not checked (ticks may be sparse) |
| 1s→1m | Check gaps (every second) |
| 1m→Nm | Check gaps (every minute) |
| 1m→1d | Calendar-aware (skip non-trading) |
| 1d→1w | Calendar-aware (skip holidays) |

**Solution**: Parameterize continuity mode (strict vs calendar-aware vs none)

---

## Unified Framework Design

### **Core Abstraction**: Generic Bar Aggregator

```python
class BarAggregator:
    """Generic bar aggregation engine.
    
    Handles all aggregation types via parameterization:
    - Ticks → 1s
    - 1s → 1m
    - 1m → Nm (5m, 15m, etc.)
    - 1m → 1d
    - 1d → 1w
    """
    
    def __init__(
        self,
        source_interval: str,      # "tick", "1s", "1m", "1d"
        target_interval: str,      # "1s", "1m", "5m", "1d", "1w"
        time_manager: TimeManager, # For calendar operations
        mode: AggregationMode      # FIXED_CHUNK, CALENDAR, TIME_WINDOW
    ):
        self.source_interval = source_interval
        self.target_interval = target_interval
        self.time_manager = time_manager
        self.mode = mode
        
        # Parse intervals
        self.source_info = parse_interval(source_interval)
        self.target_info = parse_interval(target_interval)
        
        # Validation
        self._validate_intervals()
    
    def aggregate(
        self,
        items: List[Union[Dict, BarData]],
        require_complete: bool = True,
        check_continuity: bool = True
    ) -> List[BarData]:
        """Aggregate items to target interval.
        
        Args:
            items: Source data (ticks or bars)
            require_complete: Skip incomplete chunks
            check_continuity: Validate no gaps
        
        Returns:
            Aggregated bars
        """
        # 1. Normalize input to BarData
        normalized = self._normalize_input(items)
        
        # 2. Group by time windows
        grouped = self._group_by_window(normalized)
        
        # 3. Validate and aggregate each group
        result = []
        for window_key, group_items in grouped:
            # Validate completeness
            if require_complete and not self._is_complete(group_items):
                continue
            
            # Validate continuity
            if check_continuity and not self._is_continuous(group_items):
                continue
            
            # Aggregate OHLCV
            bar = self._aggregate_ohlcv(window_key, group_items)
            result.append(bar)
        
        return result
```

---

### **Aggregation Modes** (Enum)

```python
class AggregationMode(Enum):
    """Different aggregation strategies."""
    
    # Fixed-size chunks (1s→1m, 1m→5m)
    # Groups N consecutive bars
    FIXED_CHUNK = "fixed_chunk"
    
    # Calendar-based (1m→1d, 1d→1w)
    # Groups by trading day/week
    CALENDAR = "calendar"
    
    # Time window (ticks→1s)
    # Groups by rounding timestamps
    TIME_WINDOW = "time_window"
```

---

### **Supporting Functions** (Shared)

#### 1. **Normalize Input** (Handle Dict vs BarData)
```python
def _normalize_input(self, items: List[Union[Dict, BarData]]) -> List[BarData]:
    """Convert all inputs to BarData objects."""
    if not items:
        return []
    
    # Check first item
    if isinstance(items[0], BarData):
        return items  # Already normalized
    
    # Convert dicts to BarData
    result = []
    for item in items:
        if self.source_interval == "tick":
            # Tick: has timestamp, symbol, close (price), volume
            bar = BarData(
                timestamp=item['timestamp'],
                symbol=item['symbol'],
                open=item['close'],   # Tick price
                high=item['close'],
                low=item['close'],
                close=item['close'],
                volume=item['volume']
            )
        else:
            # Bar dict: has all OHLCV fields
            bar = BarData(**item)
        
        result.append(bar)
    
    return result
```

---

#### 2. **Group by Window** (Parameterized)
```python
def _group_by_window(
    self,
    items: List[BarData]
) -> List[Tuple[datetime, List[BarData]]]:
    """Group items by time window based on mode."""
    
    if self.mode == AggregationMode.FIXED_CHUNK:
        return self._group_fixed_chunks(items)
    
    elif self.mode == AggregationMode.CALENDAR:
        return self._group_calendar(items)
    
    elif self.mode == AggregationMode.TIME_WINDOW:
        return self._group_time_window(items)
```

**2a. Fixed Chunks** (for 1s→1m, 1m→Nm)
```python
def _group_fixed_chunks(
    self,
    items: List[BarData]
) -> List[Tuple[datetime, List[BarData]]]:
    """Group into fixed-size chunks."""
    chunk_size = self._calculate_chunk_size()
    
    result = []
    i = 0
    while i < len(items):
        chunk = items[i:i+chunk_size]
        if chunk:
            result.append((chunk[0].timestamp, chunk))
        i += chunk_size
    
    return result

def _calculate_chunk_size(self) -> int:
    """Calculate bars needed per chunk."""
    # Examples:
    # 1s → 1m: 60 bars (60 seconds)
    # 1m → 5m: 5 bars (5 minutes)
    # 1m → 1d: 390 bars (6.5 hours)
    
    return self.target_info.seconds // self.source_info.seconds
```

**2b. Calendar-Based** (for 1m→1d, 1d→1w)
```python
def _group_calendar(
    self,
    items: List[BarData]
) -> List[Tuple[datetime, List[BarData]]]:
    """Group by trading calendar (days or weeks)."""
    by_period = defaultdict(list)
    
    for item in items:
        if self.target_interval.endswith('d'):
            # Group by trading day
            period_key = item.timestamp.date()
        
        elif self.target_interval.endswith('w'):
            # Group by trading week (ISO week)
            iso = item.timestamp.isocalendar()
            period_key = (iso.year, iso.week)
        
        by_period[period_key].append(item)
    
    # Sort by period
    return sorted(by_period.items())
```

**2c. Time Window** (for ticks→1s)
```python
def _group_time_window(
    self,
    items: List[BarData]
) -> List[Tuple[datetime, List[BarData]]]:
    """Group by rounding timestamps."""
    by_window = defaultdict(list)
    
    for item in items:
        # Round timestamp based on target interval
        if self.target_interval == "1s":
            window_key = item.timestamp.replace(microsecond=0)
        elif self.target_interval == "1m":
            window_key = item.timestamp.replace(second=0, microsecond=0)
        else:
            raise ValueError(f"Unsupported time window: {self.target_interval}")
        
        by_window[window_key].append(item)
    
    return sorted(by_window.items())
```

---

#### 3. **Validate Completeness** (Parameterized)
```python
def _is_complete(self, items: List[BarData]) -> bool:
    """Check if group has required number of items."""
    
    if self.mode == AggregationMode.FIXED_CHUNK:
        # Require exact chunk size
        expected = self._calculate_chunk_size()
        return len(items) == expected
    
    elif self.mode == AggregationMode.CALENDAR:
        # Allow partial (early close, short weeks OK)
        return len(items) > 0
    
    elif self.mode == AggregationMode.TIME_WINDOW:
        # Allow any number (multiple ticks per second OK)
        return len(items) > 0
```

---

#### 4. **Validate Continuity** (Parameterized)
```python
def _is_continuous(self, items: List[BarData]) -> bool:
    """Check if items are continuous (no gaps)."""
    
    if len(items) <= 1:
        return True
    
    if self.mode == AggregationMode.TIME_WINDOW:
        # Ticks can be sparse, no continuity check
        return True
    
    if self.mode == AggregationMode.FIXED_CHUNK:
        # Strict continuity: every bar must be consecutive
        delta = timedelta(seconds=self.source_info.seconds)
        
        for i in range(1, len(items)):
            expected = items[i-1].timestamp + delta
            if items[i].timestamp != expected:
                return False
        
        return True
    
    if self.mode == AggregationMode.CALENDAR:
        # Calendar continuity: check trading days
        with SessionLocal() as session:
            for i in range(1, len(items)):
                prev_date = items[i-1].timestamp.date()
                curr_date = items[i].timestamp.date()
                
                # Get next trading date
                next_trading = self.time_manager.get_next_trading_date(
                    session, prev_date
                )
                
                if curr_date != next_trading:
                    return False
        
        return True
```

---

#### 5. **Aggregate OHLCV** (100% Shared)
```python
def _aggregate_ohlcv(
    self,
    window_key: datetime,
    items: List[BarData]
) -> BarData:
    """Aggregate OHLCV for a group.
    
    THIS IS THE CORE LOGIC - IDENTICAL FOR ALL TYPES.
    """
    if not items:
        raise ValueError("Cannot aggregate empty group")
    
    return BarData(
        symbol=items[0].symbol,
        timestamp=window_key,  # Start of period
        open=items[0].open,    # First bar's open
        high=max(b.high for b in items),  # Max high
        low=min(b.low for b in items),    # Min low
        close=items[-1].close, # Last bar's close
        volume=sum(b.volume for b in items)  # Sum volume
    )
```

---

## Usage Examples

### **Example 1: Ticks → 1s**
```python
aggregator = BarAggregator(
    source_interval="tick",
    target_interval="1s",
    time_manager=time_mgr,
    mode=AggregationMode.TIME_WINDOW
)

bars_1s = aggregator.aggregate(
    ticks,
    require_complete=False,  # Allow any # ticks
    check_continuity=False   # Ticks can be sparse
)
```

---

### **Example 2: 1s → 1m**
```python
aggregator = BarAggregator(
    source_interval="1s",
    target_interval="1m",
    time_manager=time_mgr,
    mode=AggregationMode.FIXED_CHUNK
)

bars_1m = aggregator.aggregate(
    bars_1s,
    require_complete=True,  # Need 60 bars
    check_continuity=True   # No gaps allowed
)
```

---

### **Example 3: 1m → 5m**
```python
aggregator = BarAggregator(
    source_interval="1m",
    target_interval="5m",
    time_manager=time_mgr,
    mode=AggregationMode.FIXED_CHUNK
)

bars_5m = aggregator.aggregate(
    bars_1m,
    require_complete=True,   # Need 5 bars
    check_continuity=True    # No gaps allowed
)
```

---

### **Example 4: 1m → 1d**
```python
aggregator = BarAggregator(
    source_interval="1m",
    target_interval="1d",
    time_manager=time_mgr,
    mode=AggregationMode.CALENDAR
)

bars_1d = aggregator.aggregate(
    bars_1m,
    require_complete=False,  # Allow early close (< 390 bars)
    check_continuity=True    # Check trading calendar
)
```

---

### **Example 5: 1d → 1w**
```python
aggregator = BarAggregator(
    source_interval="1d",
    target_interval="1w",
    time_manager=time_mgr,
    mode=AggregationMode.CALENDAR
)

bars_1w = aggregator.aggregate(
    bars_1d,
    require_complete=False,  # Allow short weeks (< 5 days)
    check_continuity=True    # Check trading calendar
)
```

---

## File Structure

### **New Module**: `app/managers/data_manager/bar_aggregation/`

```
bar_aggregation/
├── __init__.py           # Exports: BarAggregator, AggregationMode
├── aggregator.py         # Core: BarAggregator class
├── modes.py              # Enum: AggregationMode
├── grouping.py           # Logic: Fixed, Calendar, TimeWindow grouping
├── validation.py         # Logic: Completeness, Continuity checks
├── normalization.py      # Logic: Dict → BarData conversion
├── ohlcv.py              # Logic: OHLCV aggregation (shared core)
└── helpers.py            # Utilities: chunk size, window rounding
```

---

## Migration Plan

### **Phase 1: Create Unified Framework** (2-3 days)
1. Create `bar_aggregation/` module
2. Implement `BarAggregator` class
3. Implement aggregation modes (FIXED_CHUNK, CALENDAR, TIME_WINDOW)
4. Implement shared OHLCV aggregation
5. Implement grouping strategies
6. Implement validation logic
7. Write unit tests

### **Phase 2: Migrate Existing Code** (1-2 days)
1. **Refactor `aggregate_ticks_to_1s()`**:
   ```python
   def aggregate_ticks_to_1s(self, ticks: List[Dict]) -> List[Dict]:
       aggregator = BarAggregator("tick", "1s", self.time_mgr, AggregationMode.TIME_WINDOW)
       bars = aggregator.aggregate(ticks, require_complete=False, check_continuity=False)
       return [bar.dict() for bar in bars]  # Convert back to dict
   ```

2. **Refactor `compute_derived_bars()`**:
   ```python
   def compute_derived_bars(bars_1m: List[BarData], interval: int) -> List[BarData]:
       aggregator = BarAggregator("1m", f"{interval}m", time_mgr, AggregationMode.FIXED_CHUNK)
       return aggregator.aggregate(bars_1m, require_complete=True, check_continuity=True)
   ```

3. **Remove old implementations** (keep as deprecated wrappers for compatibility)

### **Phase 3: Add New Aggregations** (1 day)
1. **1s → 1m**:
   ```python
   aggregator = BarAggregator("1s", "1m", time_mgr, AggregationMode.FIXED_CHUNK)
   bars_1m = aggregator.aggregate(bars_1s)
   ```

2. **1m → 1d**:
   ```python
   aggregator = BarAggregator("1m", "1d", time_mgr, AggregationMode.CALENDAR)
   bars_1d = aggregator.aggregate(bars_1m, require_complete=False)
   ```

3. **1d → 1w**:
   ```python
   aggregator = BarAggregator("1d", "1w", time_mgr, AggregationMode.CALENDAR)
   bars_1w = aggregator.aggregate(bars_1d, require_complete=False)
   ```

### **Phase 4: Integration & Testing** (2 days)
1. Update `data_upkeep_thread.py` to use unified framework
2. Update `parquet_storage.py` to use unified framework
3. Integration tests for all aggregation types
4. Performance benchmarks
5. Documentation

---

## Benefits

### **1. Code Reuse** (80% reduction)
- **Before**: 3 separate implementations (~400 lines total)
- **After**: 1 unified implementation (~200 lines) + thin wrappers (~50 lines)
- **Savings**: ~150 lines of duplicated logic

### **2. Consistency**
- All aggregations use identical OHLCV logic
- All validations follow same patterns
- Easier to maintain and debug

### **3. Extensibility**
- Adding new aggregation types is trivial
- Just specify intervals and mode
- Example: `2s → 10s` = `BarAggregator("2s", "10s", time_mgr, FIXED_CHUNK)`

### **4. Testability**
- Single test suite for all aggregation logic
- Parameterized tests cover all cases
- Reduces test code by ~60%

### **5. Performance**
- Shared code can be optimized once
- Benefits all aggregation types
- Potential for Cython/Numba optimization

---

## Testing Strategy

### **Unit Tests** (per component)
- `test_normalization.py` - Dict→BarData conversion
- `test_grouping.py` - Fixed, Calendar, TimeWindow grouping
- `test_validation.py` - Completeness, Continuity checks
- `test_ohlcv.py` - Core aggregation logic
- `test_aggregator.py` - End-to-end aggregation

### **Integration Tests** (per aggregation type)
```python
@pytest.mark.parametrize("source,target,mode", [
    ("tick", "1s", AggregationMode.TIME_WINDOW),
    ("1s", "1m", AggregationMode.FIXED_CHUNK),
    ("1m", "5m", AggregationMode.FIXED_CHUNK),
    ("1m", "1d", AggregationMode.CALENDAR),
    ("1d", "1w", AggregationMode.CALENDAR),
])
def test_aggregation_pipeline(source, target, mode):
    # Generate sample data
    # Aggregate
    # Validate output
```

### **Performance Tests**
- Benchmark each aggregation type
- Compare with old implementations
- Ensure no regression

---

## Edge Cases Handled

### **1. Incomplete Data**
- **Ticks→1s**: Allow (some seconds may have no ticks)
- **1s→1m**: Skip incomplete minutes (< 60 bars)
- **1m→Nm**: Skip incomplete intervals
- **1m→1d**: Allow early close (< 390 bars)
- **1d→1w**: Allow short weeks (< 5 days)

### **2. Gaps in Data**
- **Fixed chunks**: Detect gaps, skip chunk
- **Calendar**: Check trading calendar, allow holidays/weekends
- **Time window**: No gap checking (sparse data OK)

### **3. Time Zones**
- All timestamps assumed in market timezone
- TimeManager handles conversions
- No hardcoded time logic

### **4. Early Closes**
- Calendar mode queries TimeManager for actual trading hours
- Daily bars may have < 390 minutes (handled)
- Weekly bars may have < 5 days (holiday weeks)

---

## Backward Compatibility

### **Option 1: Wrapper Functions** (Recommended)
Keep existing function signatures, delegate to unified framework:

```python
# Old API (keep for compatibility)
def aggregate_ticks_to_1s(ticks: List[Dict]) -> List[Dict]:
    """Deprecated: Use BarAggregator instead."""
    aggregator = BarAggregator("tick", "1s", time_mgr, AggregationMode.TIME_WINDOW)
    bars = aggregator.aggregate(ticks, require_complete=False, check_continuity=False)
    return [bar.dict() for bar in bars]

def compute_derived_bars(bars_1m: List[BarData], interval: int) -> List[BarData]:
    """Deprecated: Use BarAggregator instead."""
    aggregator = BarAggregator("1m", f"{interval}m", time_mgr, AggregationMode.FIXED_CHUNK)
    return aggregator.aggregate(bars_1m, require_complete=True, check_continuity=True)
```

### **Option 2: Direct Migration**
Replace all calls immediately. Riskier but cleaner.

**Recommendation**: Use Option 1, deprecate wrappers in 6 months.

---

## Implementation Timeline

| Phase | Task | Effort | Status |
|-------|------|--------|--------|
| **Phase 1** | Create unified framework | 2-3 days | Pending |
| **Phase 2** | Migrate existing code | 1-2 days | Pending |
| **Phase 3** | Add new aggregations | 1 day | Pending |
| **Phase 4** | Integration & testing | 2 days | Pending |
| **Total** | | **6-8 days** | |

---

## Success Criteria

✅ All 5 aggregation types working:
- Ticks → 1s
- 1s → 1m
- 1m → Nm (5m, 15m, etc.)
- 1m → 1d
- 1d → 1w

✅ Code reduction: ~150 lines removed

✅ Test coverage: >90%

✅ No performance regression

✅ Backward compatible (existing code works)

---

## Next Steps

1. **Review this plan** - Feedback/approval
2. **Create `bar_aggregation/` module** - Start implementation
3. **Implement core `BarAggregator`** - Foundation
4. **Write unit tests** - TDD approach
5. **Migrate existing code** - One function at a time
6. **Add new aggregations** - 1s→1m, 1m→1d, 1d→1w
7. **Integration testing** - Full pipeline
8. **Documentation** - API docs, examples
9. **Performance tuning** - Optimize hot paths
10. **Deploy** - Roll out gradually

---

## Questions for Review

1. **Mode selection**: Is automatic mode selection desirable? Or explicit always better?
2. **Dict vs BarData**: Should we always work with BarData internally, or support both?
3. **Validation flexibility**: Should completeness/continuity be configurable per call or per aggregator instance?
4. **Error handling**: Raise exceptions vs return empty list vs return partial results?
5. **Performance priority**: Should we optimize for memory or speed?

---

## Conclusion

This unified framework will:
- **Eliminate 80% code duplication**
- **Enable all required aggregation types**
- **Improve maintainability and testability**
- **Provide consistent, reliable aggregation logic**
- **Make future extensions trivial**

**Estimated ROI**: 
- Development: 6-8 days
- Maintenance savings: ~2-3 days per year
- Bug reduction: Fewer edge cases, better testing
- Feature velocity: New aggregations in hours instead of days
