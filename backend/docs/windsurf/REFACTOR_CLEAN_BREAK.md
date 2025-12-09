# SessionData Refactor: Clean Break Approach

**Date:** December 4, 2025  
**Decision:** No backward compatibility - complete replacement of old structure

---

## Decision Rationale

### Why Clean Break?

1. **Simpler Implementation** - No dual-write, no fallback logic
2. **No Technical Debt** - Don't carry old structure forward
3. **Cleaner Code** - Single pattern, easier to understand
4. **Faster Development** - No transition period, just implement new design
5. **Better Testing** - Test one structure, not two

### Trade-offs Accepted

- ⚠️ **All consuming code must be updated at once**
- ⚠️ **Cannot incrementally migrate**  
- ⚠️ **Requires coordinated changes across threads**

**Decision:** Accept trade-offs for long-term benefit of cleaner architecture

---

## Implementation Strategy

### Phase 1: Update Core Data Structures ✅ COMPLETE

**Completed:**
- ✅ Added 5 new dataclasses (`BarIntervalData`, `SessionMetrics`, etc.)
- ✅ Updated `SymbolSessionData` with new fields
- ✅ Removed all old fields (bars_base, bars_derived, bar_quality, session_volume, etc.)
- ✅ Simplified to clean structure only

**Current SymbolSessionData:**
```python
@dataclass
class SymbolSessionData:
    symbol: str
    base_interval: str = "1m"  # Performance helper
    
    # Self-describing structure
    bars: Dict[str, BarIntervalData]
    quotes: List
    ticks: List[TickData]
    
    # Grouped data
    metrics: SessionMetrics
    indicators: Dict[str, Any]
    historical: HistoricalData
    
    # Internal
    _latest_bar: Optional[BarData]
    _last_export_indices: Dict[str, Any]
```

---

### Phase 2: Update SessionData Class Methods 🔄 IN PROGRESS

**Methods to Update:**

#### 2.1 Data Access Methods
- [ ] `get_latest_bar()` - Query `bars[interval].data[-1]`
- [ ] `get_last_n_bars()` - Query `bars[interval].data[-n:]`
- [ ] `get_bars_since()` - Query `bars[interval].data` with filter
- [ ] `get_bar_count()` - Query `len(bars[interval].data)`

#### 2.2 Data Modification Methods
- [ ] `append_bar()` - Add to `bars[interval].data`
- [ ] `append_bars()` - Batch add to `bars[interval].data`
- [ ] `clear_session_bars()` - Clear all `bars` dict
- [ ] `clear_historical_bars()` - Clear `historical.bars`

#### 2.3 Export Methods
- [ ] `to_json()` - Export from `bars`, `metrics`, `historical`
- [ ] Update delta export tracking

#### 2.4 Quality Methods
- [ ] `set_quality()` - Set `bars[interval].quality`
- [ ] `get_quality_metric()` - Get `bars[interval].quality`
- [ ] NEW: `set_gaps()` - Set `bars[interval].gaps`
- [ ] NEW: `get_gaps()` - Get `bars[interval].gaps`

#### 2.5 Helper Methods
- [ ] NEW: `get_symbols_with_derived()` - Return derived intervals per symbol
- [ ] NEW: `get_intervals()` - Get all intervals for a symbol
- [ ] NEW: `is_interval_derived()` - Check if interval is derived

---

### Phase 3: Update SessionCoordinator 🔄 TO DO

**Changes Needed:**

#### 3.1 Symbol Loading
```python
# OLD: Multiple operations
self._symbols[symbol] = SymbolSessionData(symbol=symbol)
self._active_symbols.add(symbol)
self._loaded_symbols.add(symbol)

# NEW: Single operation with structure
symbol_data = SymbolSessionData(
    symbol=symbol,
    base_interval="1m",
    bars={
        "1m": BarIntervalData(derived=False, base=None, data=deque()),
        "5m": BarIntervalData(derived=True, base="1m", data=[]),
    }
)
session_data.register_symbol_data(symbol_data)
```

#### 3.2 Remove Duplicate Tracking
- [ ] Remove `_loaded_symbols` set
- [ ] Remove `_streamed_data` dict
- [ ] Remove `_generated_data` dict
- [ ] Query from `SessionData` instead

#### 3.3 Historical Data Loading
```python
# OLD: session_data.historical_bars[interval][date] = bars

# NEW: session_data.historical.bars[interval].data_by_date[date] = bars
```

---

### Phase 4: Update DataProcessor 🔄 TO DO

**Changes Needed:**

#### 4.1 Remove Internal Tracking
- [ ] Remove `_derived_intervals` dict
- [ ] Query `session_data.get_symbols_with_derived()` instead

#### 4.2 Update Processing Logic
```python
# OLD: Check _derived_intervals dict
if symbol in self._derived_intervals:
    for interval in self._derived_intervals[symbol]:
        generate_derived_bar(symbol, interval)

# NEW: Query bars structure
symbol_data = session_data.get_symbol_data(symbol)
for interval, interval_data in symbol_data.bars.items():
    if interval_data.derived and interval_data.updated:
        generate_derived_bar(symbol, interval, interval_data)
```

#### 4.3 Update Bar Storage
```python
# OLD: Append to bars_derived dict
symbol_data.bars_derived[interval].append(derived_bar)

# NEW: Append to bars structure
symbol_data.bars[interval].data.append(derived_bar)
symbol_data.bars[interval].updated = True
```

---

### Phase 5: Update DataQualityManager 🔄 TO DO

**Changes Needed:**

#### 5.1 Store Gaps
```python
# OLD: Gaps computed and discarded
gaps = detect_gaps(...)
quality = calculate_quality(...)
session_data.set_quality(symbol, interval, quality)
# gaps lost!

# NEW: Store gaps
gaps = detect_gaps(...)
quality = calculate_quality(...)
session_data.set_quality(symbol, interval, quality)
session_data.set_gaps(symbol, interval, gaps)  # NEW!
```

#### 5.2 Update Quality Setting
```python
# OLD: Set in separate dict
symbol_data.bar_quality[interval] = quality

# NEW: Set in structure
symbol_data.bars[interval].quality = quality
```

#### 5.3 Failed Gaps Storage
- Keep `_failed_gaps` for retry state (operational, not data)
- But also store in `bars[interval].gaps` for export

---

### Phase 6: Update Analysis Engine 🔄 TO DO

**Changes Needed:**

#### 6.1 Bar Access
```python
# OLD: Multiple checks
if interval == symbol_data.base_interval:
    bars = symbol_data.bars_base
else:
    bars = symbol_data.bars_derived.get(interval, [])

# NEW: Single lookup
interval_data = symbol_data.bars.get(interval)
if interval_data:
    bars = interval_data.data
    quality = interval_data.quality
    is_derived = interval_data.derived
```

#### 6.2 Metrics Access
```python
# OLD: Direct fields
volume = symbol_data.session_volume
high = symbol_data.session_high

# NEW: Grouped metrics
volume = symbol_data.metrics.volume
high = symbol_data.metrics.high
```

#### 6.3 Historical Access
```python
# OLD: Nested dicts
historical_bars = symbol_data.historical_bars[interval][date]

# NEW: Structured
historical_bars = symbol_data.historical.bars[interval].data_by_date[date]
```

---

### Phase 7: Update CLI Display 🔄 TO DO

**Files to Update:**
- `session_data_display.py` - Update bar access
- `system_status_impl.py` - Update metrics display

**Changes:**
```python
# OLD
quality = symbol_data.bar_quality.get(interval, 0)
bars_count = len(symbol_data.bars_base)

# NEW
interval_data = symbol_data.bars.get(interval)
quality = interval_data.quality if interval_data else 0
bars_count = len(interval_data.data) if interval_data else 0
```

---

### Phase 8: Update Tests 🔄 TO DO

**Changes Needed:**
- [ ] Update all test assertions to use new structure
- [ ] Remove tests for old fields
- [ ] Add tests for new fields (gaps, derived flag, base field)
- [ ] Test self-describing behavior

---

## Files Requiring Updates

### Core Data Layer ✅ DONE
- [x] `/app/managers/data_manager/session_data.py` - Data structures updated

### Data Management 🔄 IN PROGRESS
- [ ] `/app/managers/data_manager/session_data.py` - Methods (in progress)

### Threads 🔄 TO DO
- [ ] `/app/threads/session_coordinator.py` - Remove duplicate tracking
- [ ] `/app/threads/data_processor.py` - Query structure instead of tracking
- [ ] `/app/threads/data_quality_manager.py` - Store gaps

### Analysis 🔄 TO DO
- [ ] `/app/threads/analysis_engine.py` - Update bar access

### Display/Export 🔄 TO DO
- [ ] `/app/cli/session_data_display.py` - Update display logic
- [ ] `/app/cli/system_status_impl.py` - Update status display

### Tests 🔄 TO DO
- [ ] `/tests/test_session_data.py` - Update all tests
- [ ] `/tests/test_data_processor.py` - Update bar access tests
- [ ] `/tests/test_quality_manager.py` - Update quality tests

---

## Migration Checklist

### Step 1: Core Data Structures ✅ COMPLETE
- [x] Remove old fields from SymbolSessionData
- [x] Keep only new structure
- [x] Update `update_from_bar()`
- [x] Update `reset_session_metrics()`

### Step 2: SessionData Methods 🔄 IN PROGRESS
- [ ] Update data access methods
- [ ] Update data modification methods
- [ ] Update export methods
- [ ] Add helper methods

### Step 3: Test Core Structure ⏳ PENDING
- [ ] Unit tests for new structure
- [ ] Verify dataclass creation
- [ ] Test data access patterns

### Step 4: Update Threads ⏳ PENDING
- [ ] SessionCoordinator
- [ ] DataProcessor
- [ ] DataQualityManager

### Step 5: Update Analysis Engine ⏳ PENDING
- [ ] Bar access patterns
- [ ] Metrics access
- [ ] Historical access

### Step 6: Update CLI/Display ⏳ PENDING
- [ ] session_data_display.py
- [ ] system_status_impl.py

### Step 7: Integration Testing ⏳ PENDING
- [ ] Full session lifecycle test
- [ ] Symbol add/remove test
- [ ] Quality calculation test
- [ ] Gap storage test

### Step 8: Production Validation ⏳ PENDING
- [ ] Backtest validation
- [ ] JSON export validation
- [ ] Performance benchmarks

---

## Benefits of Clean Break

### Code Simplification
- **-500 lines** of old structure code removed
- **No fallback logic** needed
- **Single pattern** throughout codebase

### Architecture Improvements
- **Single source of truth** established
- **Self-describing data** at every level
- **No duplicate tracking** anywhere

### Maintenance Benefits
- **Easier to understand** - one way to do things
- **Easier to extend** - add to structure, not multiple places
- **Easier to debug** - follow single data flow

### Performance
- **Faster access** - single lookup vs multiple checks
- **Less memory** - no duplicate storage
- **Better locality** - related data grouped together

---

## Risk Mitigation

### Risks
1. **All code breaks at once** - cannot run partially migrated
2. **Large coordinated change** - many files must update together
3. **Testing complexity** - must test entire flow

### Mitigations
1. **Comprehensive plan** - document every change needed
2. **Systematic approach** - update one layer at a time
3. **Extensive testing** - test each phase before moving to next
4. **Rollback ready** - git branch, can revert if needed

---

## Timeline Estimate

| Phase | Task | Time | Risk |
|-------|------|------|------|
| 1 | Core structures | 2h | ✅ DONE |
| 2 | SessionData methods | 4h | Low |
| 3 | SessionCoordinator | 3h | Medium |
| 4 | DataProcessor | 3h | Medium |
| 5 | DataQualityManager | 2h | Low |
| 6 | Analysis Engine | 2h | Low |
| 7 | CLI/Display | 2h | Low |
| 8 | Testing | 4h | High |
| **Total** | **22 hours** | **Medium** |

---

## Current Status

**Phase 1: ✅ COMPLETE**
- Core data structures updated
- Old fields removed
- Clean structure established

**Phase 2: 🔄 IN PROGRESS**
- Updating SessionData methods
- Need to update all accessor methods
- Need to add helper methods

**Next Steps:**
1. Complete SessionData method updates
2. Add helper methods for new structure
3. Test core structure thoroughly
4. Move to thread updates

---

**Decision Confirmed:** Clean break - no backward compatibility  
**Status:** Phase 1 complete, Phase 2 in progress  
**Target:** Complete refactor in 20-24 hours of focused work
