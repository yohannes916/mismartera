# Phase 4: SessionCoordinator Strategy

## Current State Analysis

### Duplicate Tracking (To Remove)
```python
self._loaded_symbols: Set[str] = set()  # Tracks loaded symbols
self._streamed_data: Dict[str, List[str]] = {}  # Tracks streamed intervals per symbol
self._generated_data: Dict[str, List[str]] = {}  # Tracks generated intervals per symbol
```

### Problem
- Symbol loading status tracked separately from SessionData
- Stream/generate marking stored outside the data structure
- DataProcessor queries coordinator instead of SessionData

---

## New Approach

### 1. Remove Duplicate Tracking
- ❌ Remove `_loaded_symbols` - Query `session_data.get_active_symbols()` instead
- ❌ Remove `_streamed_data` - Store in `bars[interval].derived = False`
- ❌ Remove `_generated_data` - Store in `bars[interval].derived = True`

### 2. Symbol Registration Flow

**When loading a symbol:**
```python
# 1. Determine intervals (via stream determination)
result = stream_determiner.determine_streams(...)
base_interval = result.required_base_interval  # e.g., "1m"
derived_intervals = result.derivable_intervals  # e.g., ["5m", "15m"]

# 2. Create SymbolSessionData with bar structure
symbol_data = SymbolSessionData(
    symbol=symbol,
    base_interval=base_interval,
    bars={
        # Base interval (streamed)
        base_interval: BarIntervalData(
            derived=False,  # Streamed, not generated
            base=None,      # Not derived from anything
            data=deque(),   # Empty deque for streaming
            quality=0.0,
            gaps=[],
            updated=False
        ),
        # Derived intervals (generated)
        **{
            interval: BarIntervalData(
                derived=True,       # Generated, not streamed
                base=base_interval, # Derived from base
                data=[],            # Empty list for generated
                quality=0.0,
                gaps=[],
                updated=False
            )
            for interval in derived_intervals
        }
    }
)

# 3. Register with SessionData
session_data.register_symbol_data(symbol_data)
```

### 3. DataProcessor Queries SessionData

**Instead of:**
```python
# OLD: Query coordinator
derived_intervals = coordinator.get_generated_data()
```

**Use:**
```python
# NEW: Query SessionData
for symbol in session_data.get_active_symbols():
    symbol_data = session_data.get_symbol_data(symbol)
    for interval, interval_data in symbol_data.bars.items():
        if interval_data.derived and interval_data.updated:
            # Generate this derived interval
            generate_derived_bar(symbol, interval, interval_data)
```

---

## Implementation Steps

### Step 1: Remove Fields from __init__ ✅
- Remove `_loaded_symbols`
- Remove `_streamed_data`
- Remove `_generated_data`

### Step 2: Update Symbol Registration ✅
- Modify `_load_symbols_for_session()` to create bar structure
- Call `session_data.register_symbol_data()` with populated structure

### Step 3: Remove/Update Accessor Methods ✅
- Remove `get_loaded_symbols()` - use `session_data.get_active_symbols()`
- Remove `get_streamed_data()` - query from bar structure
- Remove `get_generated_data()` - query from bar structure

### Step 4: Update Symbol Removal ✅
- Remove references to `_loaded_symbols.discard()`
- Remove references to `_streamed_data.pop()`
- Remove references to `_generated_data.pop()`

### Step 5: Update Stream Determination ✅
- Don't store results in `_streamed_data`/`_generated_data`
- Pass results directly to symbol registration

### Step 6: Update DataProcessor Integration ✅
- Remove `set_derived_intervals()` call
- DataProcessor will query SessionData instead

---

## Benefits

### Single Source of Truth
- Symbol loading: Query `session_data.get_active_symbols()`
- Stream type: Check `bars[interval].derived == False`
- Generate type: Check `bars[interval].derived == True`

### Self-Describing Data
- Each interval knows if it's streamed or generated
- Each interval knows its base source
- No separate tracking needed

### Automatic Discovery
- DataProcessor iterates SessionData
- Finds symbols automatically
- Finds derived intervals automatically

---

## Testing Strategy

### Unit Tests
- Test symbol registration creates bar structure
- Test bar structure has correct derived flags
- Test SessionData query returns correct intervals

### Integration Tests
- Test coordinator + SessionData integration
- Test DataProcessor finds derived intervals
- Test symbol removal cleans up properly

---

## Migration Checklist

- [ ] Remove `_loaded_symbols`, `_streamed_data`, `_generated_data` from __init__
- [ ] Update `_load_symbols_for_session()` to create bar structure
- [ ] Remove `get_loaded_symbols()`, `get_streamed_data()`, `get_generated_data()`
- [ ] Update `remove_symbol()` to not reference removed fields
- [ ] Update stream determination to not store in removed fields
- [ ] Update DataProcessor to query SessionData instead of coordinator
- [ ] Add SessionData helper method: `register_symbol_data(symbol_data)`
- [ ] Add SessionData helper method: `get_symbols_with_derived()` (optional)
- [ ] Test symbol lifecycle end-to-end

---

## Code Snippets

### SessionData Helper Method (New)
```python
def register_symbol_data(self, symbol_data: SymbolSessionData) -> None:
    """Register a fully-populated SymbolSessionData object.
    
    Used by SessionCoordinator to register symbols with pre-populated bar structure.
    """
    symbol = symbol_data.symbol.upper()
    with self._lock:
        self._symbols[symbol] = symbol_data
        logger.info(f"✓ Registered symbol with structure: {symbol}")
```

### SessionData Helper Method (Optional)
```python
def get_symbols_with_derived(self) -> Dict[str, List[str]]:
    """Get map of symbols to their derived intervals.
    
    Returns:
        Dict mapping symbol to list of derived interval names
    """
    result = {}
    with self._lock:
        for symbol, symbol_data in self._symbols.items():
            derived = [
                interval for interval, data in symbol_data.bars.items()
                if data.derived
            ]
            if derived:
                result[symbol] = derived
    return result
```

---

**Status:** Strategy defined, ready for implementation
