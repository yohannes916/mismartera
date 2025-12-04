# SessionData Refactor Plan: Single Source of Truth Architecture

**Date:** December 4, 2025  
**Goal:** Eliminate duplicate tracking, establish hierarchical data structure, enable automatic synchronization

---

## Executive Summary

### Current Problems
1. **Duplicate symbol tracking** across 4+ locations
2. **Duplicate derived/base interval tracking** across 3 components
3. **Fragmented gap information** (computed but not stored)
4. **Manual synchronization** required when adding/removing symbols
5. **Scattered data** makes cleanup error-prone

### Solution Principles
1. **Single Source of Truth:** All symbol data lives in `SessionData._symbols`
2. **Self-Describing Data:** Each object contains all its metadata
3. **Automatic Discovery:** Components iterate `SessionData`, no manual registration
4. **Hierarchical Cleanup:** Remove from `SessionData` → everything cascades
5. **No Inference:** If data can be stored, store it explicitly

---

## Part 1: Current State Analysis

### 1.1 Duplicate Symbol Tracking

| Location | Data Structure | Purpose | Status |
|----------|---------------|---------|--------|
| `SessionData._active_symbols` | `Set[str]` | Quick lookup of active symbols | ❌ **REDUNDANT** |
| `SessionData._symbols` | `Dict[str, SymbolSessionData]` | Actual symbol data storage | ✅ **SOURCE OF TRUTH** |
| `SessionCoordinator._loaded_symbols` | `Set[str]` | Symbols fully loaded | ❌ **REDUNDANT** |
| `SessionCoordinator._pending_symbols` | `Set[str]` | Symbols waiting to load | ⚠️ **TEMPORARY STATE** |

**Problem:** 4 places track "which symbols exist"
- When adding symbol: Must update 2-3 places
- When removing symbol: Must update 2-3 places
- Synchronization bugs likely

**Solution:** 
- Remove `_active_symbols` → infer from `_symbols.keys()`
- Remove `_loaded_symbols` → infer from `SymbolSessionData.is_loaded` flag
- Keep `_pending_symbols` (temporary operation state only)

### 1.2 Duplicate Derived Interval Tracking

| Location | Data Structure | Purpose | Status |
|----------|---------------|---------|--------|
| `SessionCoordinator._streamed_data` | `Dict[str, List[str]]` | Which intervals are streamed | ❌ **REDUNDANT** |
| `SessionCoordinator._generated_data` | `Dict[str, List[str]]` | Which intervals are derived | ❌ **REDUNDANT** |
| `DataProcessor._derived_intervals` | `Dict[str, List[str]]` | Which intervals to generate | ❌ **REDUNDANT** |
| `BarData.interval` | `str` | Interval of this bar | ✅ **EXISTS** |

**Problem:** 3 places track "which intervals are derived"
- DataProcessor must be told explicitly
- No per-bar metadata about derived status
- When symbol removed: Must notify DataProcessor

**Solution:**
- Add `SymbolSessionData.derived_intervals: List[str]` 
- Add `SymbolSessionData.base_interval: str` (already exists!)
- DataProcessor iterates `SessionData`, discovers derived intervals automatically
- Remove `DataProcessor._derived_intervals`
- Remove `SessionCoordinator._streamed_data/_generated_data` (or move to config-time only)

### 1.3 Gap Information Not Stored

| Location | Data Structure | Purpose | Status |
|----------|---------------|---------|--------|
| `DataQualityManager._failed_gaps` | `Dict[str, List[GapInfo]]` | Track retry state | ⚠️ **TEMPORARY STATE** |
| `SymbolSessionData.bar_quality` | `Dict[str, float]` | Quality percentage | ✅ **STORED** |
| `SymbolSessionData.bar_gaps` | **MISSING** | Gap details | ❌ **NOT STORED** |

**Problem:** Gap analysis computed but immediately discarded
- Can't see gap details in exports
- Can't audit data quality retroactively
- Quality percentage alone doesn't tell full story

**Solution:**
- Add `SymbolSessionData.bar_gaps: Dict[str, List[GapInfo]]`
- Store gaps when quality calculated
- Export gaps nested under each interval
- Keep `_failed_gaps` for retry state only (live mode)

### 1.4 Quality Manager State

| Location | Data Structure | Purpose | Status |
|----------|---------------|---------|--------|
| `DataQualityManager._last_quality_calc` | `Dict[str, datetime]` | Throttling | ✅ **OPERATIONAL STATE** |
| `DataQualityManager._failed_gaps` | `Dict[str, List[GapInfo]]` | Retry tracking | ✅ **OPERATIONAL STATE** |

**Problem:** None - these are legitimate operational state
- Throttling state must be tracked per operation
- Retry state is temporary (live mode only)

**Solution:** Keep as-is (operational state, not data)

---

## Part 2: Proposed Architecture

### 2.1 Enhanced SymbolSessionData Structure

```python
@dataclass
class SymbolSessionData:
    """Per-symbol data for current trading session.
    
    This is THE single source of truth for all symbol data.
    All threads/components query this structure, nothing is tracked elsewhere.
    """
    
    # === IDENTITY ===
    symbol: str
    base_interval: str = "1m"  # "1s" or "1m" - already exists!
    
    # === NEW: DERIVED INTERVALS ===
    derived_intervals: List[str] = field(default_factory=list)
    # Example: ["5m", "15m", "30m"]
    # DataProcessor discovers these by iterating symbols
    
    # === NEW: LOADING STATE ===
    is_loaded: bool = False  # True when historical + queues loaded
    # Replaces SessionCoordinator._loaded_symbols
    
    # === BARS (Current Session) ===
    bars_base: Deque[BarData]
    bars_derived: Dict[str, List[BarData]]  # Already exists
    _latest_bar: Optional[BarData]
    
    # === QUALITY & GAPS ===
    bar_quality: Dict[str, float]  # Already exists!
    bar_gaps: Dict[str, List[GapInfo]] = field(default_factory=dict)  # NEW!
    # Structure: {interval: [gap1, gap2, ...]}
    
    # === SESSION METRICS ===
    session_volume: int = 0
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    last_update: Optional[datetime] = None
    
    # === UPDATE FLAGS ===
    bars_updated: bool = False
    quotes_updated: bool = False
    ticks_updated: bool = False
    
    # === HISTORICAL DATA ===
    historical_bars: Dict[str, Dict[date, List[BarData]]]
    historical_indicators: Dict[str, Any]
    
    # === OTHER DATA TYPES ===
    quotes: List[QuoteData]
    ticks: List[TickData]
    
    # === DELTA EXPORT TRACKING ===
    _last_export_indices: Dict[str, Any]  # Internal
```

### 2.2 Simplified SessionData

```python
class SessionData:
    """Session-wide data manager.
    
    Simplified: Only tracks symbols and session state.
    No duplicate tracking of symbols or intervals.
    """
    
    def __init__(self):
        # Core storage - SINGLE SOURCE OF TRUTH
        self._symbols: Dict[str, SymbolSessionData] = {}
        
        # REMOVED: self._active_symbols (infer from _symbols.keys())
        
        # Session state
        self._session_active: bool = False
        self._current_session_date: Optional[date] = None
        
        # Active streams tracking (keeps existing)
        self._active_streams: Dict[Tuple[str, str], bool] = {}
        
        # Thread safety
        self._lock = threading.RLock()
        self._data_arrival_event = threading.Event()
    
    def get_active_symbols(self) -> Set[str]:
        """Get active symbols by querying storage (not separate set)."""
        with self._lock:
            return set(self._symbols.keys())
    
    def get_loaded_symbols(self) -> Set[str]:
        """Get fully loaded symbols (NEW)."""
        with self._lock:
            return {sym for sym, data in self._symbols.items() 
                    if data.is_loaded}
    
    def get_symbols_with_derived(self) -> Dict[str, List[str]]:
        """Get derived intervals per symbol (NEW).
        
        DataProcessor calls this instead of maintaining its own list.
        """
        with self._lock:
            return {sym: data.derived_intervals.copy() 
                    for sym, data in self._symbols.items()
                    if data.derived_intervals}
```

### 2.3 Simplified SessionCoordinator

```python
class SessionCoordinator:
    """Session coordinator with simplified symbol tracking."""
    
    def __init__(self, system_manager, data_manager):
        # ...
        
        # REMOVED: self._loaded_symbols (use SessionData.get_loaded_symbols())
        
        # Keep only temporary operation state
        self._pending_symbols: Set[str] = set()  # Symbols being loaded NOW
        
        # Stream/Generate marking (config-time only, not runtime tracking)
        # These are determined once at startup from config
        self._initial_stream_marking: Dict[str, List[str]] = {}
        self._initial_derived_marking: Dict[str, List[str]] = {}
    
    def _load_symbols_phase_3(self, symbols: List[str]):
        """Load symbols and mark as loaded in SessionData."""
        # ... load historical, queues, etc ...
        
        # Mark as loaded in SessionData
        for symbol in symbols:
            symbol_data = self.session_data.get_symbol_data(symbol)
            if symbol_data:
                symbol_data.is_loaded = True  # NEW!
                symbol_data.derived_intervals = self._initial_derived_marking.get(symbol, [])
        
        # No need to maintain separate _loaded_symbols set
    
    def remove_symbol(self, symbol: str):
        """Remove symbol (single operation)."""
        # BEFORE: Had to update _loaded_symbols, _pending_symbols, notify processor
        # AFTER: Just remove from SessionData
        
        self.session_data.remove_symbol(symbol)
        
        # That's it! Threads discover removal automatically on next iteration
```

### 2.4 Simplified DataProcessor

```python
class DataProcessor:
    """Data processor with automatic discovery."""
    
    def __init__(self, session_data, ...):
        # ...
        
        # REMOVED: self._derived_intervals (discover from SessionData)
    
    def _process_bar_data(self, symbol: str, interval: str):
        """Process bar data with automatic derived bar discovery."""
        
        # Get symbol data
        symbol_data = self.session_data.get_symbol_data(symbol)
        if not symbol_data:
            return  # Symbol was removed, skip
        
        # Check if this symbol has derived intervals to compute
        if interval == symbol_data.base_interval:
            # This is a base bar, check for derived intervals
            derived_intervals = symbol_data.derived_intervals
            
            if derived_intervals:
                self._generate_derived_bars(symbol, derived_intervals)
        
        # No manual tracking needed - all info is in SessionData!
    
    def get_derived_intervals_for_symbol(self, symbol: str) -> List[str]:
        """Get derived intervals (query SessionData, not internal state)."""
        symbol_data = self.session_data.get_symbol_data(symbol)
        return symbol_data.derived_intervals if symbol_data else []
```

### 2.5 Simplified DataQualityManager

```python
class DataQualityManager:
    """Quality manager with gap storage."""
    
    def __init__(self, session_data, ...):
        # ...
        
        # Keep operational state only
        self._last_quality_calc: Dict[str, datetime] = {}
        self._failed_gaps: Dict[str, List[GapInfo]] = {}  # Retry state (live mode)
    
    def _calculate_quality(self, symbol: str, interval: str):
        """Calculate quality and STORE gaps."""
        
        # Detect gaps
        gaps = detect_gaps(...)
        quality = calculate_quality(...)
        
        # Store in SessionData (NEW!)
        self.session_data.set_quality(symbol, interval, quality)
        self.session_data.set_gaps(symbol, interval, gaps)  # NEW!
        
        # Keep failed gaps for retry (operational state)
        if self.gap_filling_enabled:
            gap_key = f"{symbol}_{interval}"
            self._failed_gaps[gap_key] = [g for g in gaps if g.retry_count > 0]
    
    def run(self):
        """Main loop discovers symbols automatically."""
        while self._running:
            # Get active symbols from SessionData (no separate tracking)
            active_symbols = self.session_data.get_active_symbols()
            
            for symbol in active_symbols:
                symbol_data = self.session_data.get_symbol_data(symbol)
                if not symbol_data:
                    continue  # Symbol was removed
                
                # Check if this symbol has data to quality-check
                if symbol_data.bars_updated:
                    self._calculate_quality(symbol, symbol_data.base_interval)
                
                # Check derived intervals too
                for interval in symbol_data.derived_intervals:
                    if len(symbol_data.bars_derived.get(interval, [])) > 0:
                        self._calculate_quality(symbol, interval)
```

---

## Part 3: Migration Benefits

### 3.1 Simplified Add Symbol Flow

**BEFORE (Fragmented):**
```python
# Step 1: Add to config
config.symbols.append(symbol)

# Step 2: Register in SessionData
session_data.register_symbol(symbol)
# → Updates _symbols dict
# → Updates _active_symbols set

# Step 3: Mark in SessionCoordinator
coordinator._loaded_symbols.add(symbol)
coordinator._pending_symbols.add(symbol)

# Step 4: Notify DataProcessor
processor.set_generated_data({symbol: derived_intervals})
# → Updates processor._derived_intervals

# Step 5: Quality Manager discovers via polling
# (automatic, but delayed)
```

**AFTER (Centralized):**
```python
# Single operation
symbol_data = SymbolSessionData(
    symbol=symbol,
    base_interval="1m",
    derived_intervals=["5m", "15m"],
    is_loaded=False
)
session_data.register_symbol_data(symbol_data)

# That's it! All threads discover automatically:
# - DataProcessor sees new symbol on next iteration
# - QualityManager sees new symbol on next iteration
# - No manual notification needed
```

### 3.2 Simplified Remove Symbol Flow

**BEFORE (Fragmented):**
```python
# Step 1: Remove from SessionData
session_data.remove_symbol(symbol)
# → Removes from _symbols
# → Removes from _active_symbols

# Step 2: Update SessionCoordinator
coordinator._loaded_symbols.discard(symbol)
coordinator._pending_symbols.discard(symbol)

# Step 3: Notify DataProcessor
new_derived = {s: intervals for s, intervals in processor._derived_intervals.items() 
               if s != symbol}
processor.set_generated_data(new_derived)

# Step 4: Quality Manager discovers via polling
# (automatic, but might process one more time)
```

**AFTER (Centralized):**
```python
# Single operation
session_data.remove_symbol(symbol)

# That's it! All threads see removal immediately:
# - DataProcessor skips if symbol not found
# - QualityManager skips if symbol not found
# - Automatic synchronization
```

### 3.3 Automatic Synchronization

**Key Insight:** When all threads iterate `SessionData`, they automatically stay synchronized:

```python
# DataProcessor main loop
for symbol in session_data.get_active_symbols():
    symbol_data = session_data.get_symbol_data(symbol)
    if not symbol_data:
        continue  # Symbol was removed mid-iteration, skip gracefully
    
    # Process based on data in SymbolSessionData
    if symbol_data.bars_updated:
        for interval in symbol_data.derived_intervals:
            generate_derived_bars(symbol, interval)

# DataQualityManager main loop
for symbol in session_data.get_active_symbols():
    symbol_data = session_data.get_symbol_data(symbol)
    if not symbol_data:
        continue  # Symbol was removed mid-iteration, skip gracefully
    
    # Check quality for all intervals
    check_quality(symbol, symbol_data.base_interval)
    for interval in symbol_data.derived_intervals:
        check_quality(symbol, interval)
```

**Benefits:**
- Add symbol → appears in next iteration
- Remove symbol → `get_symbol_data()` returns None, gracefully skipped
- No race conditions
- No explicit notifications needed

---

## Part 4: Implementation Plan

### Phase 1: Add New Fields (Non-Breaking)

**Goal:** Add new fields without breaking existing code

1. **Add to SymbolSessionData:**
   ```python
   derived_intervals: List[str] = field(default_factory=list)
   is_loaded: bool = False
   bar_gaps: Dict[str, List[GapInfo]] = field(default_factory=dict)
   ```

2. **Add to SessionData:**
   ```python
   def get_loaded_symbols(self) -> Set[str]:
       """NEW: Get symbols where is_loaded=True."""
       with self._lock:
           return {sym for sym, data in self._symbols.items() if data.is_loaded}
   
   def get_symbols_with_derived(self) -> Dict[str, List[str]]:
       """NEW: Get derived intervals per symbol."""
       with self._lock:
           return {sym: data.derived_intervals.copy() 
                   for sym, data in self._symbols.items()
                   if data.derived_intervals}
   
   def set_gaps(self, symbol: str, interval: str, gaps: List[GapInfo]):
       """NEW: Store gap information."""
       symbol_data = self.get_symbol_data(symbol)
       if symbol_data:
           symbol_data.bar_gaps[interval] = gaps
   ```

3. **Populate new fields in SessionCoordinator:**
   ```python
   def _load_symbols_phase_3(self, symbols: List[str]):
       # After loading...
       for symbol in symbols:
           symbol_data = self.session_data.get_symbol_data(symbol)
           if symbol_data:
               symbol_data.is_loaded = True
               symbol_data.derived_intervals = self._generated_data.get(symbol, [])
   ```

4. **Store gaps in DataQualityManager:**
   ```python
   def _calculate_quality(self, symbol: str, interval: str):
       gaps = detect_gaps(...)
       quality = calculate_quality(...)
       
       self.session_data.set_quality(symbol, interval, quality)
       self.session_data.set_gaps(symbol, interval, gaps)  # NEW!
   ```

**Status:** ✅ Can be done immediately, fully backward compatible

### Phase 2: Migrate DataProcessor (Test First)

**Goal:** Make DataProcessor query SessionData instead of tracking `_derived_intervals`

1. **Add fallback logic:**
   ```python
   def _get_derived_intervals(self, symbol: str) -> List[str]:
       """Get derived intervals with fallback."""
       # Try new way first
       symbol_data = self.session_data.get_symbol_data(symbol)
       if symbol_data and symbol_data.derived_intervals:
           return symbol_data.derived_intervals
       
       # Fallback to old way
       return self._derived_intervals.get(symbol, [])
   ```

2. **Update `_process_bar_data()` to use new method**

3. **Test thoroughly**

4. **Remove `self._derived_intervals` and fallback logic**

**Status:** ⚠️ Requires testing

### Phase 3: Migrate SessionCoordinator (Test First)

**Goal:** Remove `_loaded_symbols`, query from SessionData

1. **Add compatibility methods:**
   ```python
   def get_loaded_symbols(self) -> Set[str]:
       """Compatibility: Use SessionData.get_loaded_symbols()."""
       return self.session_data.get_loaded_symbols()
   ```

2. **Update all references to `self._loaded_symbols`**

3. **Test thoroughly**

4. **Remove `self._loaded_symbols` set**

**Status:** ⚠️ Requires testing

### Phase 4: Remove `_active_symbols` (Final Cleanup)

**Goal:** Remove redundant `SessionData._active_symbols`

1. **Update `get_active_symbols()` to query `_symbols.keys()`:**
   ```python
   def get_active_symbols(self) -> Set[str]:
       with self._lock:
           return set(self._symbols.keys())
   ```

2. **Remove all references to `self._active_symbols.add/discard`**

3. **Remove field from `__init__`**

4. **Update JSON export (remove `_active_symbols` key)**

**Status:** ⚠️ Final step, do last

### Phase 5: Export Gap Details

**Goal:** Add gap information to JSON exports

1. **Update `SymbolSessionData.to_json()` to include gaps:**
   ```python
   if interval in self.bar_gaps and self.bar_gaps[interval]:
       gaps = self.bar_gaps[interval]
       interval_data["gaps"] = {
           "gap_count": len(gaps),
           "missing_bars": sum(g.bar_count for g in gaps),
           "ranges": [
               {
                   "start_time": g.start_time.time().isoformat(),
                   "end_time": g.end_time.time().isoformat(),
                   "bar_count": g.bar_count
               }
               for g in gaps
           ]
       }
   ```

2. **Update CSV export if needed**

**Status:** ⚠️ After Phase 1 complete

---

## Part 5: Risk Assessment

### Low Risk Changes (Do First)
- ✅ Add new fields to SymbolSessionData
- ✅ Add new methods to SessionData
- ✅ Store gaps in DataQualityManager
- ✅ Populate `is_loaded` flag in SessionCoordinator
- ✅ Export gaps to JSON

### Medium Risk Changes (Test Thoroughly)
- ⚠️ Migrate DataProcessor to query SessionData
- ⚠️ Migrate SessionCoordinator to query SessionData
- ⚠️ Remove `_derived_intervals` from DataProcessor

### High Risk Changes (Do Last)
- ⚠️⚠️ Remove `_active_symbols` from SessionData
- ⚠️⚠️ Remove `_loaded_symbols` from SessionCoordinator

### Testing Strategy
1. **Unit tests:** Test new methods in isolation
2. **Integration tests:** Full session lifecycle with add/remove symbols
3. **Backtest validation:** Run full backtest, validate CSV output
4. **Live mode verification:** Quick live session test (if safe)

---

## Part 6: Expected Outcomes

### Code Simplification
- **Lines removed:** ~200-300 lines (duplicate tracking)
- **Complexity reduced:** Fewer state machines, simpler flows
- **Bugs prevented:** No synchronization bugs possible

### Data Quality Improvements
- **Gap visibility:** Full gap details in exports
- **Audit trail:** Historical record of data quality
- **Debugging:** Easy to see exactly when gaps occurred

### Maintainability
- **Single source:** One place to look for symbol data
- **Self-documenting:** Data structure tells full story
- **Easy cleanup:** Remove from SessionData → everything updates

### Performance
- **Neutral or better:** No extra iterations needed
- **Less locking:** Fewer separate data structures to synchronize
- **Cleaner code:** Easier for Python to optimize

---

## Summary

### Principles Applied
1. ✅ **Single Source of Truth:** SessionData._symbols is THE source
2. ✅ **Self-Describing Data:** Each SymbolSessionData knows if it's loaded, what's derived, etc.
3. ✅ **Automatic Discovery:** Threads iterate SessionData, no registration
4. ✅ **Hierarchical Cleanup:** Remove symbol → all info gone
5. ✅ **Explicit Storage:** Don't infer, store it

### Key Changes
- Remove `SessionData._active_symbols`
- Remove `SessionCoordinator._loaded_symbols`
- Remove `DataProcessor._derived_intervals`
- Add `SymbolSessionData.is_loaded`
- Add `SymbolSessionData.derived_intervals`
- Add `SymbolSessionData.bar_gaps`
- Store gap details in DataQualityManager

### Migration Path
1. Phase 1: Add new fields (safe)
2. Phase 2-3: Migrate threads (test carefully)
3. Phase 4: Remove redundant fields (final cleanup)
4. Phase 5: Export enhancements

**Result:** Cleaner, more maintainable, less error-prone architecture with full data quality visibility.
