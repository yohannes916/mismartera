# SessionData Refactor: Implementation Checklist

**Goal:** Transform from fragmented tracking to single source of truth  
**Status:** Planning Complete, Ready for Implementation

---

## Phase 1: Add New Fields (Safe, Non-Breaking)

### ✅ Task 1.1: Enhance SymbolSessionData
- [ ] Add `derived_intervals: List[str] = field(default_factory=list)`
- [ ] Add `is_loaded: bool = False`
- [ ] Add `bar_gaps: Dict[str, List[GapInfo]] = field(default_factory=dict)`
- [ ] Test: Instantiate SymbolSessionData with new fields
- [ ] Test: Verify backward compatibility (existing code still works)

### ✅ Task 1.2: Add SessionData Helper Methods
- [ ] Add `get_loaded_symbols() -> Set[str]`
  ```python
  def get_loaded_symbols(self) -> Set[str]:
      with self._lock:
          return {sym for sym, data in self._symbols.items() if data.is_loaded}
  ```
- [ ] Add `get_symbols_with_derived() -> Dict[str, List[str]]`
  ```python
  def get_symbols_with_derived(self) -> Dict[str, List[str]]:
      with self._lock:
          return {sym: data.derived_intervals.copy() 
                  for sym, data in self._symbols.items()
                  if data.derived_intervals}
  ```
- [ ] Add `set_gaps(symbol, interval, gaps)`
  ```python
  def set_gaps(self, symbol: str, interval: str, gaps: List[GapInfo]):
      symbol_data = self.get_symbol_data(symbol)
      if symbol_data:
          symbol_data.bar_gaps[interval] = gaps
  ```
- [ ] Test: Call new methods, verify they work

### ✅ Task 1.3: Populate New Fields in SessionCoordinator
- [ ] Update `_load_symbols_phase_3()` to set `is_loaded = True`
- [ ] Update `_load_symbols_phase_3()` to populate `derived_intervals`
  ```python
  for symbol in symbols:
      symbol_data = self.session_data.get_symbol_data(symbol)
      if symbol_data:
          symbol_data.is_loaded = True
          symbol_data.derived_intervals = self._generated_data.get(symbol, [])
  ```
- [ ] Test: Load symbols, verify flags are set
- [ ] Test: Verify `session_data.get_loaded_symbols()` returns correct set

### ✅ Task 1.4: Store Gaps in DataQualityManager
- [ ] Update `_calculate_quality()` to store gaps
  ```python
  def _calculate_quality(self, symbol: str, interval: str):
      gaps = detect_gaps(...)
      quality = calculate_quality(...)
      
      self.session_data.set_quality(symbol, interval, quality)
      self.session_data.set_gaps(symbol, interval, gaps)  # NEW!
  ```
- [ ] Test: Trigger quality calculation, verify gaps stored
- [ ] Test: Query `symbol_data.bar_gaps[interval]`, verify gap details

### ✅ Task 1.5: Export Gaps to JSON
- [ ] Update `SymbolSessionData.to_json()` to include gaps
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
- [ ] Test: Export JSON, verify gaps section exists
- [ ] Test: Verify gap details match computed gaps

**Phase 1 Complete:** ✅ New fields added, gaps stored and exported, fully backward compatible

---

## Phase 2: Migrate DataProcessor (Test Carefully)

### ⚠️ Task 2.1: Add Fallback Query Method
- [ ] Add `_get_derived_intervals(symbol)` with fallback
  ```python
  def _get_derived_intervals(self, symbol: str) -> List[str]:
      """Get derived intervals with fallback to old method."""
      # Try new way first
      symbol_data = self.session_data.get_symbol_data(symbol)
      if symbol_data and symbol_data.derived_intervals:
          return symbol_data.derived_intervals
      
      # Fallback to old way
      return self._derived_intervals.get(symbol, [])
  ```
- [ ] Test: Verify method returns correct intervals
- [ ] Test: Verify fallback works if `derived_intervals` empty

### ⚠️ Task 2.2: Update `_process_bar_data()`
- [ ] Replace direct `_derived_intervals` access with `_get_derived_intervals()`
  ```python
  def _process_bar_data(self, symbol: str, interval: str):
      symbol_data = self.session_data.get_symbol_data(symbol)
      if not symbol_data:
          return  # Symbol removed, skip gracefully
      
      if interval == symbol_data.base_interval:
          derived = self._get_derived_intervals(symbol)
          if derived:
              self._generate_derived_bars(symbol, derived)
  ```
- [ ] Test: Process bars, verify derived bars generated
- [ ] Test: Remove symbol mid-processing, verify graceful skip

### ⚠️ Task 2.3: Update All References
- [ ] Search for all uses of `self._derived_intervals` in DataProcessor
- [ ] Replace with `_get_derived_intervals()` calls
- [ ] Test each change individually

### ⚠️ Task 2.4: Integration Testing
- [ ] Full backtest: Verify all derived bars computed
- [ ] Add symbol mid-session: Verify processing works
- [ ] Remove symbol mid-session: Verify no errors
- [ ] Compare output with previous version (should be identical)

### ⚠️ Task 2.5: Remove Old Code
- [ ] Remove `self._derived_intervals` field from `__init__`
- [ ] Remove `set_generated_data()` method
- [ ] Remove fallback logic from `_get_derived_intervals()`
  ```python
  def _get_derived_intervals(self, symbol: str) -> List[str]:
      """Get derived intervals from SessionData."""
      symbol_data = self.session_data.get_symbol_data(symbol)
      return symbol_data.derived_intervals if symbol_data else []
  ```
- [ ] Final test: Full backtest validation

**Phase 2 Complete:** ✅ DataProcessor queries SessionData, no internal tracking

---

## Phase 3: Migrate SessionCoordinator (Test Carefully)

### ⚠️ Task 3.1: Add Compatibility Method
- [ ] Update `get_loaded_symbols()` to delegate to SessionData
  ```python
  def get_loaded_symbols(self) -> Set[str]:
      """Get loaded symbols (delegates to SessionData)."""
      return self.session_data.get_loaded_symbols()
  ```
- [ ] Test: Verify method returns correct symbols

### ⚠️ Task 3.2: Update All References
- [ ] Search for `self._loaded_symbols` in SessionCoordinator
- [ ] Replace with `self.get_loaded_symbols()` or `self.session_data.get_loaded_symbols()`
- [ ] Test each change individually

### ⚠️ Task 3.3: Integration Testing
- [ ] Full session lifecycle: Start, add symbols, remove symbols, stop
- [ ] Verify loaded status tracked correctly
- [ ] Verify no stale references to `_loaded_symbols`

### ⚠️ Task 3.4: Remove Old Code
- [ ] Remove `self._loaded_symbols` field from `__init__`
- [ ] Remove `.add()` and `.discard()` calls (should be compile errors if any remain)
- [ ] Remove `self._streamed_data` and `self._generated_data` (if safe)
- [ ] Final test: Full session validation

**Phase 3 Complete:** ✅ SessionCoordinator queries SessionData, no duplicate tracking

---

## Phase 4: Remove `_active_symbols` (Final Cleanup)

### ⚠️⚠️ Task 4.1: Update `get_active_symbols()`
- [ ] Change implementation to query `_symbols.keys()`
  ```python
  def get_active_symbols(self) -> Set[str]:
      if not self._check_session_active():
          return set()
      with self._lock:
          return set(self._symbols.keys())
  ```
- [ ] Test: Verify returns correct symbols

### ⚠️⚠️ Task 4.2: Remove All `.add()` and `.discard()` Calls
- [ ] Search for `_active_symbols.add`
- [ ] Search for `_active_symbols.discard`
- [ ] Remove these lines (data now tracked via `_symbols` dict only)
- [ ] Test each removal

### ⚠️⚠️ Task 4.3: Remove Field
- [ ] Remove `self._active_symbols: Set[str] = set()` from `__init__`
- [ ] Remove from `to_json()` export
- [ ] Test: Verify compilation, no references remain

### ⚠️⚠️ Task 4.4: Final Integration Testing
- [ ] Full backtest: Verify symbols tracked correctly
- [ ] Add/remove symbols: Verify correct behavior
- [ ] Compare CSV output with previous version
- [ ] Verify no performance regression

**Phase 4 Complete:** ✅ `_active_symbols` removed, single source of truth established

---

## Phase 5: Update Documentation

### 📝 Task 5.1: Update Code Comments
- [ ] Update docstrings in SessionData
- [ ] Update docstrings in SymbolSessionData
- [ ] Update docstrings in SessionCoordinator
- [ ] Update docstrings in DataProcessor

### 📝 Task 5.2: Update Architecture Docs
- [ ] Update SESSION_DATA_STRUCTURE_ANALYSIS.md
- [ ] Update SYMBOL_DATA_STRUCTURE_V2.md (if exists)
- [ ] Create REFACTOR_COMPLETE.md with summary

### 📝 Task 5.3: Update Migration Guide
- [ ] Document what changed
- [ ] Document API changes (if any external consumers)
- [ ] Document testing procedures

**Phase 5 Complete:** ✅ Documentation up to date

---

## Testing Strategy

### Unit Tests
- [ ] Test SymbolSessionData with new fields
- [ ] Test SessionData helper methods
- [ ] Test gap storage and retrieval
- [ ] Test JSON export with gaps

### Integration Tests
- [ ] Full backtest with multiple symbols
- [ ] Add symbol mid-session
- [ ] Remove symbol mid-session
- [ ] Quality calculation with gap storage
- [ ] Derived bar generation

### Regression Tests
- [ ] Compare JSON exports (before vs after)
- [ ] Compare CSV exports (before vs after)
- [ ] Verify performance (should be same or better)
- [ ] Verify memory usage (should be same or better)

### Edge Cases
- [ ] Remove symbol during processing
- [ ] Add duplicate symbol
- [ ] Empty session (no symbols)
- [ ] All symbols removed mid-session
- [ ] Rapid add/remove cycles

---

## Rollback Plan

If anything goes wrong:

1. **Phase 1 rollback:** Just don't use new fields (backward compatible)
2. **Phase 2 rollback:** Restore DataProcessor._derived_intervals tracking
3. **Phase 3 rollback:** Restore SessionCoordinator._loaded_symbols tracking
4. **Phase 4 rollback:** Restore SessionData._active_symbols tracking

**Git branches:**
- `main` - stable before refactor
- `refactor-phase1` - after Phase 1
- `refactor-phase2` - after Phase 2
- `refactor-phase3` - after Phase 3
- `refactor-phase4` - complete (merge to main after validation)

---

## Success Criteria

### Functional
- ✅ All existing tests pass
- ✅ New gap information appears in JSON exports
- ✅ Derived bars computed correctly
- ✅ Symbols can be added/removed dynamically
- ✅ No synchronization bugs

### Performance
- ✅ No performance regression (within 5%)
- ✅ No memory increase (within 5%)
- ✅ Same or faster processing times

### Code Quality
- ✅ Fewer lines of code (200-300 lines removed)
- ✅ Simpler control flow
- ✅ No duplicate tracking
- ✅ Single source of truth established

### Data Quality
- ✅ Gap details visible in exports
- ✅ Quality metrics accurate
- ✅ CSV validation passes

---

## Timeline Estimate

| Phase | Estimated Time | Risk Level |
|-------|---------------|------------|
| Phase 1 | 2-4 hours | Low ✅ |
| Phase 2 | 4-6 hours | Medium ⚠️ |
| Phase 3 | 3-5 hours | Medium ⚠️ |
| Phase 4 | 2-3 hours | Medium-High ⚠️⚠️ |
| Phase 5 | 1-2 hours | Low ✅ |
| **Total** | **12-20 hours** | |

**Recommendation:** Do Phase 1 immediately (safe), then Phase 2-4 together in one focused session with comprehensive testing.

---

## Current Status

- [x] Analysis complete
- [x] Architecture designed
- [x] Implementation plan created
- [ ] Phase 1: Add new fields
- [ ] Phase 2: Migrate DataProcessor
- [ ] Phase 3: Migrate SessionCoordinator
- [ ] Phase 4: Remove duplicate tracking
- [ ] Phase 5: Update documentation
- [ ] Complete: Refactor validated and deployed

**Next Step:** Begin Phase 1 (safe, non-breaking changes)
