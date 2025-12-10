# Implementation Plan: Per-Symbol Validation & Auto-Provisioning

## Overview

Implementing the refined validation and loading architecture with:
- Per-symbol Step 0 validation (graceful degradation)
- Full Step 3 loading for validated symbols
- Lightweight adhoc bar/indicator addition
- Parameterized validation helpers
- NO session-to-session persistence

---

## Phase 1: Parameterized Validation Helpers

### Files to Modify
- `session_coordinator.py`

### Methods to Add

```python
def _check_data_source_for_symbol(self, symbol: str) -> Optional[str]:
    """Check which data source has this symbol."""
    # Query data_manager to find available source
    # Priority: 1) Parquet (local), 2) Alpaca, 3) Schwab
    pass

def _check_available_intervals(self, symbol: str, source: str) -> List[str]:
    """Get available intervals for symbol from source."""
    # Query data_manager API capabilities
    pass

def _check_historical_data_availability(self, symbol: str) -> bool:
    """Check if historical data exists for symbol."""
    # Query data_manager database
    pass

def _check_parquet_data(self, symbol: str, interval: str, date: date) -> bool:
    """Check if Parquet data exists for specific date."""
    # Query data_manager parquet index
    pass

def _validate_interval_compatibility(
    self,
    required: List[str],
    available: List[str]
) -> bool:
    """Validate if available intervals can satisfy required."""
    # Check derivation capability
    # 1m can derive: 5m, 15m, 30m, 1h
    # 1s can derive: 5s, 10s, 30s, 1m, 5m, etc.
    pass
```

**Estimate**: 2-3 hours (requires data_manager API queries)

---

## Phase 2: Per-Symbol Validation (Step 0)

### Files to Modify
- `session_coordinator.py`

### Classes to Add

```python
@dataclass
class SymbolValidationResult:
    """Result of per-symbol validation."""
    symbol: str
    can_proceed: bool = False
    reason: str = ""
    
    # Data source
    data_source_available: bool = False
    data_source: Optional[str] = None
    
    # Intervals
    intervals_supported: List[str] = field(default_factory=list)
    base_interval: Optional[str] = None
    
    # Historical
    has_historical_data: bool = False
    historical_date_range: Optional[Tuple[date, date]] = None
    
    # Requirements
    meets_config_requirements: bool = False
```

### Methods to Add

```python
def _validate_symbol_for_loading(self, symbol: str) -> SymbolValidationResult:
    """Step 0: Validate single symbol for full loading."""
    # 5 validation checks (already designed)
    pass

def _validate_symbols_for_loading(self, symbols: List[str]) -> List[str]:
    """Step 0: Batch validate symbols with graceful degradation."""
    # Returns list of validated symbols
    # Logs warnings for failed symbols
    # Raises error if ALL symbols fail
    pass
```

### Methods to Modify

```python
def _load_session_data(self):
    """Load session data with per-symbol validation."""
    # OLD:
    # symbols = self.session_config.symbols
    # self._register_symbols(symbols)
    
    # NEW:
    config_symbols = self.session_config.symbols
    validated_symbols = self._validate_symbols_for_loading(config_symbols)
    self._load_symbols_full(validated_symbols)
```

**Estimate**: 3-4 hours

---

## Phase 3: Symbol Metadata Integration

### Files to Modify
- `session_data.py` (SymbolSessionData dataclass)
- `session_coordinator.py`

### SymbolSessionData Changes

**Add metadata fields directly to SymbolSessionData**:

```python
@dataclass
class SymbolSessionData:
    """Session data for a single symbol (with integrated metadata)."""
    symbol: str
    
    # Bar data
    bars: Dict[str, IntervalBars]
    
    # Indicator data
    indicators: Dict[str, IndicatorData]
    
    # Quality data
    quality: Dict[str, float]
    
    # METADATA (INTEGRATED) ✅
    meets_session_config_requirements: bool = False
    added_by: str = "config"  # "config", "strategy", "scanner", "adhoc"
    auto_provisioned: bool = False
    added_at: Optional[datetime] = None
    upgraded_from_adhoc: bool = False
    
    def __init__(
        self,
        symbol: str,
        meets_session_config_requirements: bool = False,
        added_by: str = "config",
        auto_provisioned: bool = False
    ):
        """Initialize with metadata flags set at creation time."""
        self.symbol = symbol
        self.bars = {}
        self.indicators = {}
        self.quality = {}
        
        # Set metadata
        self.meets_session_config_requirements = meets_session_config_requirements
        self.added_by = added_by
        self.auto_provisioned = auto_provisioned
        self.added_at = None
        self.upgraded_from_adhoc = False
```

### SessionData Changes

**NO changes needed!** Metadata is part of SymbolSessionData:

```python
class SessionData:
    def __init__(self):
        self._symbols: Dict[str, SymbolSessionData] = {}
        # NO separate metadata dict needed! ✅
    
    def clear(self):
        """Clear all symbols (metadata cleared automatically)."""
        self._symbols.clear()
```

**Estimate**: 1 hour (simpler than separate structure)

---

## Phase 4: Auto-Provisioning for Adhoc

### Files to Modify
- `session_data.py`
- `session_coordinator.py`

### SessionData Changes

```python
class SessionData:
    def add_bar(self, symbol: str, interval: str, bar: BarData):
        """Add bar (auto-provision if needed)."""
        if symbol not in self._symbols:
            logger.info(f"{symbol}: Auto-provisioning for adhoc bar")
            self._auto_provision_symbol(symbol, reason="bar_addition")
        
        # Add bar to structure
        # ... existing logic ...
    
    def _auto_provision_symbol(self, symbol: str, reason: str):
        """Auto-provision minimal symbol structure."""
        # Create minimal SymbolSessionData with metadata
        symbol_data = SymbolSessionData(
            symbol=symbol,
            meets_session_config_requirements=False,  # Adhoc
            added_by="adhoc",
            auto_provisioned=True
        )
        symbol_data.added_at = time_manager.get_current_time()
        
        self._symbols[symbol] = symbol_data
```

### Coordinator Methods to Add

```python
def _validate_adhoc_bar(
    self,
    symbol: str,
    interval: str,
    bar: BarData
) -> Tuple[bool, str]:
    """Validate adhoc bar addition (lighter than Step 0)."""
    # Check: already exists? interval supported? parquet data?
    pass

def _validate_adhoc_indicator(
    self,
    symbol: str,
    indicator_config: dict
) -> Tuple[bool, str]:
    """Validate adhoc indicator addition."""
    pass

def add_adhoc_bar(
    self,
    symbol: str,
    interval: str,
    bar: BarData,
    source: str = "scanner"
) -> bool:
    """Add adhoc bar (lightweight path)."""
    pass

def add_adhoc_indicator(
    self,
    symbol: str,
    indicator_config: dict,
    source: str = "scanner"
) -> bool:
    """Add adhoc indicator (lightweight path)."""
    pass
```

**Estimate**: 3-4 hours

---

## Phase 5: Update add_symbol() with Validation

### Files to Modify
- `session_coordinator.py`

### Methods to Modify

```python
def add_symbol(self, symbol: str, added_by: str = "strategy") -> bool:
    """Add symbol with FULL session-config loading.
    
    Runs Step 0 validation, then schedules Step 3 loading.
    """
    # Check if already fully loaded
    metadata = self.session_data.get_symbol_metadata(symbol)
    if metadata and metadata.meets_session_config_requirements:
        return True
    
    # Check if exists as adhoc (upgrade path)
    if metadata and not metadata.meets_session_config_requirements:
        logger.info(f"{symbol}: Upgrading from adhoc to full")
    
    # Step 0: Validate
    result = self._validate_symbol_for_loading(symbol)
    if not result.can_proceed:
        logger.error(f"{symbol}: Validation failed - {result.reason}")
        return False
    
    # Schedule Step 3: Full loading
    with self._symbol_operation_lock:
        self._pending_symbols.add(symbol)
    
    return True
```

### Methods to Rename

```python
# OLD: _load_symbols_mid_session()
# NEW: _load_symbols_full()
def _load_symbols_full(self, symbols: List[str]):
    """Step 3: Full data loading (used by pre-session and mid-session)."""
    # Existing implementation
    # Just rename for clarity
```

**Estimate**: 1-2 hours

---

## Phase 6: Update Session Teardown (No Persistence)

### Files to Modify
- `session_coordinator.py`

### Methods to Modify

```python
def _teardown_and_cleanup(self):
    """End of session cleanup - NO PERSISTENCE."""
    
    logger.info("[SESSION_FLOW] PHASE_0: Starting teardown and cleanup")
    
    # Clear ALL symbols (no persistence)
    self.session_data.clear()  # Also clears metadata now
    
    # Clear queues
    self._bar_queues.clear()
    
    # Clear symbol tracking
    with self._symbol_operation_lock:
        self._pending_symbols.clear()
    
    # Advance clock
    await self._advance_to_next_trading_day()
    
    logger.info("Session cleared - fresh start for next session")
```

**Estimate**: 30 minutes

---

## Phase 7: Update JSON Serialization

### Files to Modify
- `session_data.py`
- `session_coordinator.py`

### SessionData Changes

```python
def to_json(self) -> dict:
    """Export SessionData including metadata."""
    symbols_json = {}
    
    for symbol, symbol_data in self._symbols.items():
        metadata = self._symbol_metadata.get(symbol)
        
        symbols_json[symbol] = {
            "bars": symbol_data.to_json(),
            "indicators": # ... ,
            "metadata": metadata.to_dict() if metadata else None  # NEW
        }
    
    return {"symbols": symbols_json, ...}
```

### SymbolMetadata Changes

```python
@dataclass
class SymbolMetadata:
    # ... fields ...
    
    def to_dict(self) -> dict:
        """Serialize to dict for JSON export."""
        return {
            "meets_session_config_requirements": self.meets_session_config_requirements,
            "added_by": self.added_by,
            "added_mid_session": self.added_mid_session,
            "auto_provisioned": self.auto_provisioned,
            "provisioned_reason": self.provisioned_reason,
            "upgraded_from_adhoc": self.upgraded_from_adhoc
        }
```

**Estimate**: 1 hour

---

## Phase 8: Update CSV Export & Validation

### Files to Modify
- `app/cli/session_data_display.py`
- `validation/validate_session_dump.py`

### CSV Export Updates

Add metadata columns:
```python
columns = [
    # ... existing columns ...
    f"{symbol}_meets_config_req",
    f"{symbol}_added_by",
    f"{symbol}_auto_provisioned"
]
```

### Validation Updates

Add metadata checks:
```python
def validate_symbol_metadata(self, symbol: str):
    """Validate symbol metadata consistency."""
    # Check: If auto_provisioned=True, then meets_session_config_requirements=False
    # Check: If added_by="config", then meets_session_config_requirements=True
    # etc.
```

**Estimate**: 2-3 hours

---

## Phase 9: Testing

### Test Cases

1. **Per-Symbol Validation**
   - Config with 3 symbols: 1 valid, 1 no data source, 1 no historical
   - Expected: 1 loads, 2 drop with warnings, session proceeds

2. **All Symbols Fail Validation**
   - Config with 3 invalid symbols
   - Expected: Session terminates with error

3. **Adhoc Bar Addition**
   - Session running with AAPL
   - Scanner adds bar for TSLA (not loaded)
   - Expected: TSLA auto-provisions (meets_session_config_requirements=False)

4. **Adhoc to Full Upgrade**
   - TSLA auto-provisioned (adhoc)
   - Strategy calls add_symbol("TSLA")
   - Expected: Upgrade to full (meets_session_config_requirements=True)

5. **Duplicate add_symbol()**
   - AAPL fully loaded
   - Strategy calls add_symbol("AAPL")
   - Expected: Skip loading (already done)

6. **No Persistence Between Sessions**
   - Day 1: Load AAPL, RIVN, adhoc TSLA
   - Day 2: Only AAPL, RIVN from config (TSLA gone)
   - Expected: Fresh start, no TSLA

7. **JSON Export with Metadata**
   - Export session with mix of config/adhoc symbols
   - Expected: Metadata fields present and accurate

8. **CSV Validation with Metadata**
   - Run validation with metadata columns
   - Expected: Consistency checks pass

**Estimate**: 4-6 hours

---

## Total Implementation Estimate

| Phase | Description | Hours |
|-------|-------------|-------|
| 1 | Parameterized validation helpers | 2-3 |
| 2 | Per-symbol validation (Step 0) | 3-4 |
| 3 | Symbol metadata tracking | 1-2 |
| 4 | Auto-provisioning for adhoc | 3-4 |
| 5 | Update add_symbol() | 1-2 |
| 6 | Update teardown (no persistence) | 0.5 |
| 7 | JSON serialization | 1 |
| 8 | CSV export & validation | 2-3 |
| 9 | Testing | 4-6 |
| **TOTAL** | | **18-25 hours** |

---

## Implementation Order

### Critical Path (Do First)
1. Phase 3: Metadata tracking (foundation)
2. Phase 2: Per-symbol validation (core logic)
3. Phase 5: Update add_symbol() (integration)
4. Phase 6: Update teardown (no persistence)

### Enhancement Path (Do Second)
5. Phase 4: Auto-provisioning (adhoc support)
6. Phase 1: Validation helpers (if data_manager queries available)
7. Phase 7: JSON serialization
8. Phase 8: CSV export

### Verification Path (Do Last)
9. Phase 9: Testing

---

## Rollout Strategy

### Week 1: Foundation
- Implement metadata tracking
- Implement per-symbol validation
- Update add_symbol() flow
- Update teardown (no persistence)

### Week 2: Enhancement
- Implement auto-provisioning
- Implement adhoc bar/indicator addition
- Update serialization

### Week 3: Testing & Refinement
- Comprehensive testing
- Bug fixes
- Documentation updates

---

## Risk Assessment

### Low Risk
- Metadata tracking (additive)
- JSON serialization (non-breaking)

### Medium Risk
- Per-symbol validation (new logic)
- Auto-provisioning (new behavior)

### High Risk
- No persistence change (behavioral change)
- Validation helper integration (depends on data_manager API)

### Mitigation
- Feature flag for per-symbol validation (can fall back to bulk)
- Extensive testing before production
- Incremental rollout (metadata first, then validation)

---

## Success Criteria

1. ✅ Per-symbol validation working (graceful degradation)
2. ✅ Failed symbols dropped, others proceed
3. ✅ Session terminates if all symbols fail
4. ✅ Adhoc bar/indicator addition working
5. ✅ Auto-provisioning working
6. ✅ Upgrade path working (adhoc → full)
7. ✅ No persistence between sessions
8. ✅ Metadata exported to JSON
9. ✅ CSV validation includes metadata checks
10. ✅ All tests passing

---

## Next Steps

**Immediate**: Begin Phase 3 (Metadata Tracking)
- Add SymbolMetadata dataclass
- Update SessionData to track metadata
- Add get/set methods
- Update clear() to clear metadata

**Then**: Phase 2 (Per-Symbol Validation)
- Add SymbolValidationResult dataclass
- Implement _validate_symbol_for_loading()
- Implement _validate_symbols_for_loading()
- Update _load_session_data()

**Ready to proceed?**
