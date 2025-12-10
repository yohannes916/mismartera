# Per-Symbol Validation Design

## Problem Statement

Current validation is **system-wide only**. We need **per-symbol validation** to handle:
1. Duplicate symbol detection (don't reload already-active symbols)
2. Config vs ad-hoc symbol distinction
3. Per-symbol data source verification
4. Symbol-specific interval requirements
5. Persistence decisions

---

## Step 0 Redesign: Two-Part Validation

### Part A: Common Validation (System Capability) - ONCE

**Questions Answered:**
- ❓ "Can we derive 5m from 1m?" → Technical capability
- ❓ "What intervals can our system generate?" → [5, 15, 30, ...]
- ❓ "What's our base streaming interval?" → 1m (or 1s, 1d)

**Execution:**
- Runs ONCE at startup (before main loop)
- Results stored in coordinator instance variables
- Shared by ALL symbols (config + ad-hoc)

**Current Implementation:** ✅ Already done via `_validate_stream_requirements()`

### Part B: Per-Symbol Validation - EVERY SYMBOL

**Questions Answered:**
- ❓ "Is this symbol already active?" → Check `session_data.get_symbol_data(symbol)`
- ❓ "Is this a config symbol or ad-hoc?" → Compare to `session_config.symbols`
- ❓ "What data source provides this symbol?" → Check API capabilities
- ❓ "Does this symbol's data support required intervals?" → Verify availability
- ❓ "Should this symbol persist to next session?" → Based on origin

**Execution:**
- Runs for EVERY symbol (pre-session + mid-session)
- Results tracked per-symbol
- Enables intelligent loading decisions

**Current Implementation:** ❌ MISSING (needs to be added)

---

## Symbol Metadata Tracking

### Proposed: Add SymbolMetadata to SessionData

```python
@dataclass
class SymbolMetadata:
    """Metadata about symbol origin and configuration."""
    symbol: str
    
    # Origin tracking
    from_config: bool  # True if in session_config.symbols
    added_mid_session: bool  # True if added after session start
    added_by: Optional[str] = None  # "scanner", "strategy", "manual", "config"
    added_at: Optional[datetime] = None  # When added
    
    # Validation status
    meets_session_config_requirements: bool = False
    data_source: Optional[str] = None  # "alpaca", "schwab", "csv", etc.
    intervals_validated: List[str] = field(default_factory=list)
    
    # Persistence
    persist_to_next_session: bool = False
    export_to_json: bool = True

# In SessionData
class SessionData:
    def __init__(self):
        self._symbols: Dict[str, SymbolSessionData] = {}
        self._symbol_metadata: Dict[str, SymbolMetadata] = {}  # NEW!
```

### Usage Examples

#### Pre-Session (Config Symbol)
```python
# Load AAPL from config
metadata = SymbolMetadata(
    symbol="AAPL",
    from_config=True,
    added_mid_session=False,
    added_by="config",
    meets_session_config_requirements=True,
    persist_to_next_session=True,
    export_to_json=True
)
session_data.set_symbol_metadata("AAPL", metadata)
```

#### Mid-Session (Scanner Ad-hoc)
```python
# Scanner adds TSLA
metadata = SymbolMetadata(
    symbol="TSLA",
    from_config=False,
    added_mid_session=True,
    added_by="scanner",
    added_at=coordinator.get_current_time(),
    meets_session_config_requirements=False,
    persist_to_next_session=False,  # Don't persist ad-hoc
    export_to_json=True  # But do export for analysis
)
session_data.set_symbol_metadata("TSLA", metadata)
```

---

## Per-Symbol Validation Logic

### New Method: `_validate_symbol_addition()`

```python
def _validate_symbol_addition(self, symbol: str, added_by: str = "manual") -> tuple[bool, str]:
    """Validate whether a symbol should be added (per-symbol validation).
    
    Part B of Step 0 validation - runs for EVERY symbol.
    
    Args:
        symbol: Symbol to validate
        added_by: Source of addition ("config", "scanner", "strategy", "manual")
    
    Returns:
        (should_add, reason) tuple
    """
    # Check 1: Already active?
    if self.session_data.get_symbol_data(symbol):
        metadata = self.session_data.get_symbol_metadata(symbol)
        if metadata:
            logger.info(
                f"{symbol}: Already active (added by {metadata.added_by}), "
                f"skipping duplicate addition"
            )
            return (False, "already_active")
    
    # Check 2: Is this a config symbol?
    from_config = symbol in self.session_config.session_data_config.symbols
    
    # Check 3: Data source validation
    # TODO: Query data_manager if symbol is available from configured sources
    # For now, assume available
    data_source = "alpaca"  # Would query dynamically
    
    # Check 4: Interval validation
    # Use stored common validation results
    base_interval = self._base_interval
    derived_intervals = self._derived_intervals_validated
    
    # Create metadata
    metadata = SymbolMetadata(
        symbol=symbol,
        from_config=from_config,
        added_mid_session=self._session_active,  # True if session running
        added_by=added_by,
        added_at=self._time_manager.get_current_time() if self._session_active else None,
        meets_session_config_requirements=from_config,
        data_source=data_source,
        intervals_validated=[base_interval] + derived_intervals,
        persist_to_next_session=from_config,  # Only persist config symbols
        export_to_json=True
    )
    
    # Store metadata
    self.session_data.set_symbol_metadata(symbol, metadata)
    
    logger.info(
        f"{symbol}: Validated for addition "
        f"(from_config={from_config}, added_by={added_by})"
    )
    
    return (True, "validated")
```

### Updated: `add_symbol()` - Entry Point

```python
def add_symbol(self, symbol: str, added_by: str = "manual") -> bool:
    """Add symbol to session (with per-symbol validation).
    
    Args:
        symbol: Symbol to add
        added_by: Source ("config", "scanner", "strategy", "manual")
    """
    with self._symbol_operation_lock:
        # Per-symbol validation (Part B of Step 0)
        should_add, reason = self._validate_symbol_addition(symbol, added_by)
        
        if not should_add:
            if reason == "already_active":
                return True  # Already loaded, that's fine
            else:
                logger.error(f"{symbol}: Validation failed: {reason}")
                return False
        
        # Add to config (for current session)
        if symbol not in self.session_config.session_data_config.symbols:
            self.session_config.session_data_config.symbols.append(symbol)
        
        # Mark as pending for loading
        self._pending_symbols.add(symbol)
        
        logger.info(f"{symbol}: Added to pending (will load on next iteration)")
        return True
```

### Updated: `_register_symbols()` - Pre-Session

```python
def _register_symbols(self):
    """Register all symbols from config (pre-session)."""
    symbols = self.session_config.session_data_config.symbols
    
    for symbol in symbols:
        # Per-symbol validation
        should_add, reason = self._validate_symbol_addition(symbol, added_by="config")
        
        if should_add:
            self._register_single_symbol(symbol)
        else:
            logger.warning(f"{symbol}: Skipped registration: {reason}")
```

### Updated: `_process_pending_symbols()` - Mid-Session

```python
def _process_pending_symbols(self):
    """Process pending symbols (mid-session)."""
    with self._symbol_operation_lock:
        pending = list(self._pending_symbols)
        self._pending_symbols.clear()
    
    if not pending:
        return
    
    # Filter: Remove already-active symbols
    symbols_to_load = []
    for symbol in pending:
        if self.session_data.get_symbol_data(symbol):
            logger.info(f"{symbol}: Already active, skipping")
            continue
        symbols_to_load.append(symbol)
    
    if not symbols_to_load:
        logger.info("All pending symbols already active, nothing to load")
        return
    
    logger.info(f"[SYMBOL] Loading {len(symbols_to_load)} new symbols: {symbols_to_load}")
    
    # Pause, load, unpause
    self._stream_paused.clear()
    time.sleep(0.1)
    
    try:
        gap_start = self.metrics.start_timer()
        self._load_symbols_mid_session(symbols_to_load)
        self.metrics.record_session_gap(gap_start)
        
    except Exception as e:
        logger.error(f"[SYMBOL] Error loading symbols: {e}", exc_info=True)
    finally:
        self._stream_paused.set()
```

---

## Use Cases Enabled

### Use Case 1: Config Symbol Pre-Session
```python
# session_config.json: symbols=["AAPL"]
system.start()
→ _validate_symbol_addition("AAPL", added_by="config")
  → from_config=True
  → meets_session_config_requirements=True
  → persist_to_next_session=True
→ Load AAPL
```

### Use Case 2: Scanner Ad-hoc Mid-Session
```python
# Session running with AAPL
scanner.on_scan():
    coordinator.add_symbol("TSLA", added_by="scanner")
    
→ _validate_symbol_addition("TSLA", added_by="scanner")
  → from_config=False
  → meets_session_config_requirements=False
  → persist_to_next_session=False (don't persist)
→ Load TSLA (available this session only)
```

### Use Case 3: Duplicate Prevention
```python
# AAPL already loaded
scanner.on_scan():
    coordinator.add_symbol("AAPL", added_by="scanner")
    
→ _validate_symbol_addition("AAPL", added_by="scanner")
  → Already active! Skip loading
  → Return (False, "already_active")
→ No duplicate load ✅
```

### Use Case 4: Multi-Day Persistence
```python
# Day 1: Scanner adds TSLA (ad-hoc)
→ metadata.persist_to_next_session=False

# End of Day 1: Teardown
→ Only AAPL persists to Day 2 config
→ TSLA discarded

# Day 2: Fresh start
→ Only AAPL loaded (from config)
→ TSLA must be re-discovered by scanner
```

---

## Implementation Plan

### Phase 1: Add Metadata Tracking
1. Create `SymbolMetadata` dataclass
2. Add `_symbol_metadata` dict to `SessionData`
3. Add `get_symbol_metadata()` / `set_symbol_metadata()` methods

### Phase 2: Per-Symbol Validation
4. Create `_validate_symbol_addition()` method
5. Update `add_symbol()` to use validation
6. Update `_register_symbols()` to use validation
7. Update `_process_pending_symbols()` to check duplicates

### Phase 3: Persistence Logic
8. Update `_teardown_and_cleanup()` to filter ad-hoc symbols
9. Update config save to only persist `meets_session_config_requirements=True`
10. Update JSON export to include metadata

### Phase 4: Testing
11. Test duplicate symbol addition (should skip)
12. Test ad-hoc symbol (should not persist)
13. Test config symbol (should persist)
14. Test mid-session addition by scanner

---

## Questions for User

### 1. Persistence Behavior
**Should ad-hoc symbols persist to next session?**
- Option A: No (scanner re-discovers each day)
- Option B: Yes (once added, stays in session)
- Option C: Configurable per addition

### 2. Data Source Validation
**Should we validate symbol availability before loading?**
- Query data_manager: "Does Alpaca support TSLA with 1m bars?"
- Query database: "Do we have historical data for TSLA?"
- Or: Attempt load and fail gracefully?

### 3. Interval Flexibility
**Should ad-hoc symbols support different intervals?**
```python
coordinator.add_symbol("TSLA", intervals=["1s", "5s"])  # Different from config!
```
- Currently: All symbols share same intervals
- Enhancement: Per-symbol interval configuration

### 4. Export Behavior
**Should ad-hoc symbols be in JSON export?**
- Option A: Yes (for analysis)
- Option B: No (only config symbols)
- Option C: Separate section (config vs ad-hoc)

---

## Summary

Your insight is **100% correct**! We need:

1. **Two-part Step 0 validation**:
   - Part A: Common (system capability) - ✅ Done
   - Part B: Per-symbol (duplicate check, metadata) - ❌ TODO

2. **Symbol metadata tracking**:
   - `from_config` flag
   - `meets_session_config_requirements` flag
   - `added_by` tracking
   - Persistence decisions

3. **Duplicate prevention**:
   - Check if symbol already active
   - Skip re-loading
   - Log appropriately

This is a critical architectural enhancement that will make the system much more robust!

**Should I proceed with implementation, or do you want to discuss the design questions first?**
