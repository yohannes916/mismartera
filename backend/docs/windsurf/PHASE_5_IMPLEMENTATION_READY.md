# Phase 5 Implementation Ready - Unified Provisioning Architecture

## Status: ✅ ARCHITECTURE COMPLETE, READY TO IMPLEMENT

**Documentation Updated**: 
- ✅ `SESSION_ARCHITECTURE.md` - Flow updated with three-phase pattern
- ✅ `UNIFIED_PROVISIONING_ARCHITECTURE.md` - Complete architecture design
- ✅ Phases 1-4 Complete - Validation infrastructure in place

---

## What We're Building

### Unified Three-Phase Pattern for ALL Additions

```
┌────────────────────────────────────────────────────────┐
│  PHASE 1: REQUIREMENT ANALYSIS                         │
│  What do we need?                                      │
│  - analyze_requirements(operation, symbol, source)     │
└────────────────┬───────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────┐
│  PHASE 2: VALIDATION                                   │
│  Can we get it?                                        │
│  - REUSES Step 0 validation (Phases 1-4)             │
└────────────────┬───────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────┐
│  PHASE 3: PROVISIONING + LOADING                       │
│  Create and load                                       │
│  - _execute_provisioning(requirements)                 │
│  - REUSES Step 3 loading methods (Phases 1-4)        │
└────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 5a: Core Infrastructure (2-3 hours)

**Goal**: Create unified requirement analysis system

**Files to Modify**:
1. `/app/threads/session_coordinator.py` - Add requirement analysis
2. New file: `/app/threads/provisioning/requirements.py` - Dataclasses and helpers

**What to Create**:

#### 1. `ProvisioningRequirements` Dataclass (~50 lines)
```python
@dataclass
class ProvisioningRequirements:
    """Unified requirements for any addition operation."""
    operation_type: str  # "bar", "indicator", "symbol"
    source: str  # "config", "scanner", "strategy"
    
    # Symbol requirements
    symbol: str
    symbol_exists: bool = False
    symbol_validated: bool = False
    
    # Bar requirements
    required_intervals: List[str] = field(default_factory=list)
    base_interval: Optional[str] = None
    
    # Historical requirements
    needs_historical: bool = False
    historical_days: int = 0
    historical_bars: int = 0
    
    # Indicator requirements
    indicator_config: Optional[Any] = None
    
    # Validation results
    can_proceed: bool = False
    validation_errors: List[str] = field(default_factory=list)
    provisioning_steps: List[str] = field(default_factory=list)
    
    # Metadata
    meets_session_config_requirements: bool = False
    added_by: str = "adhoc"
    reason: str = ""
```

#### 2. `analyze_requirements()` Dispatcher (~100 lines)
```python
def analyze_requirements(
    operation_type: str,
    symbol: str,
    source: str,
    session_data: SessionData,
    session_coordinator: SessionCoordinator,
    **kwargs
) -> ProvisioningRequirements:
    """Unified requirement analysis dispatcher."""
    
    req = ProvisioningRequirements(...)
    
    # Phase 1: Check existing
    existing = session_data.get_symbol_data(symbol)
    req.symbol_exists = existing is not None
    
    # Phase 2: Analyze by type
    if operation_type == "indicator":
        _analyze_indicator_requirements(req, **kwargs)
    elif operation_type == "bar":
        _analyze_bar_requirements(req, **kwargs)
    elif operation_type == "symbol":
        _analyze_symbol_requirements(req, coordinator)
    
    # Phase 3: Validate
    if operation_type in ["symbol", "bar"]:
        validation = coordinator._validate_symbol_for_loading(symbol)
        req.can_proceed = validation.can_proceed
        # ...
    
    # Phase 4: Determine steps
    _determine_provisioning_steps(req, existing)
    
    return req
```

#### 3. Helper Functions (~150 lines)
- `_analyze_indicator_requirements()` - Calls existing analyzer
- `_analyze_bar_requirements()` - Uses parse_interval()
- `_analyze_symbol_requirements()` - Uses config
- `_determine_provisioning_steps()` - Builds step list

**Testing for Phase 5a**:
```python
# Test requirement analysis standalone
req = analyze_requirements(
    operation_type="indicator",
    symbol="AAPL",
    source="scanner",
    session_data=session_data,
    session_coordinator=coordinator,
    indicator_config=sma_config,
    system_manager=system_manager
)

assert req.required_intervals == ["1m", "5m"]  # Base + derived
assert req.historical_days > 0  # Warmup needed
assert len(req.provisioning_steps) > 0
```

---

### Phase 5b: Provisioning Executor (1-2 hours)

**Goal**: Create unified provisioning executor

**Files to Modify**:
1. `/app/threads/session_coordinator.py` - Add executor

**What to Create**:

#### `_execute_provisioning()` Method (~100 lines)
```python
def _execute_provisioning(self, req: ProvisioningRequirements) -> bool:
    """Execute provisioning steps from requirement analysis.
    
    REUSES: All existing Step 3 loading methods!
    """
    logger.info(f"[PROVISION] {req.symbol}: {len(req.provisioning_steps)} steps")
    
    for step in req.provisioning_steps:
        if step == "create_symbol":
            self._register_single_symbol(
                req.symbol,
                meets_session_config_requirements=req.meets_session_config_requirements,
                added_by=req.added_by,
                auto_provisioned=(req.source != "config")
            )
        
        elif step == "upgrade_symbol":
            existing = self.session_data.get_symbol_data(req.symbol)
            existing.meets_session_config_requirements = True
            existing.upgraded_from_adhoc = True
        
        elif step.startswith("add_interval_"):
            # Add bar structure
            # ...
        
        elif step == "load_historical":
            self._manage_historical_data(symbols=[req.symbol])
        
        elif step == "load_session":
            self._load_queues(symbols=[req.symbol])
        
        elif step == "register_indicator":
            self._register_session_indicators(symbols=[req.symbol])
    
    return True
```

**Testing for Phase 5b**:
```python
# Test provisioning executor
req = ProvisioningRequirements(
    symbol="AAPL",
    provisioning_steps=["create_symbol", "load_historical"],
    meets_session_config_requirements=True,
    added_by="config"
)

result = coordinator._execute_provisioning(req)
assert result == True
assert coordinator.session_data.get_symbol_data("AAPL") is not None
```

---

### Phase 5c: Unified Entry Points (1-2 hours)

**Goal**: Create unified entry points for all operations

**Files to Modify**:
1. `/app/managers/data_manager/session_data.py` - Add unified methods

**What to Create**:

#### 1. `add_indicator_unified()` (~50 lines)
```python
def add_indicator_unified(
    self,
    symbol: str,
    indicator_config: IndicatorConfig,
    source: str = "scanner"
) -> bool:
    """Unified indicator addition with three-phase pattern."""
    
    # Phase 1: Analyze
    req = analyze_requirements(
        operation_type="indicator",
        symbol=symbol,
        source=source,
        session_data=self,
        session_coordinator=self._session_coordinator,
        indicator_config=indicator_config,
        system_manager=self._system_manager
    )
    
    # Phase 2: Validate
    if not req.can_proceed:
        logger.error(f"{symbol}: {req.validation_errors}")
        return False
    
    # Phase 3: Provision
    return self._session_coordinator._execute_provisioning(req)
```

#### 2. `add_bar_unified()` (~50 lines)
```python
def add_bar_unified(
    self,
    symbol: str,
    interval: str,
    days: int = 0,
    source: str = "scanner"
) -> bool:
    """Unified bar addition with three-phase pattern."""
    
    # Same three-phase pattern as indicator
    # ...
```

#### 3. Update `add_symbol()` in SessionCoordinator (~20 lines)
```python
def add_symbol(self, symbol: str, added_by: str = "strategy") -> bool:
    """Add symbol with unified pattern (already has validation)."""
    
    # Already has Phase 1 (analyze) and Phase 2 (validate)
    # Just needs to call Phase 3 (provision) via unified executor
    # ...
```

**Testing for Phase 5c**:
```python
# Test unified indicator addition
result = session_data.add_indicator_unified(
    symbol="TSLA",
    indicator_config=sma_config,
    source="scanner"
)
assert result == True

# Verify auto-provisioning
tsla_data = session_data.get_symbol_data("TSLA")
assert tsla_data is not None
assert tsla_data.meets_session_config_requirements == False
assert tsla_data.added_by == "scanner"
assert tsla_data.auto_provisioned == True
```

---

### Phase 5d: Integration & Testing (1-2 hours)

**Goal**: Integrate with existing flow and test all scenarios

**Files to Modify**:
1. `/app/threads/session_coordinator.py` - Update `_load_session_data()`

**What to Update**:

#### Update Pre-Session Loading
```python
def _load_session_data(self):
    """Load session data with unified provisioning."""
    
    config_symbols = self.session_config.session_data_config.symbols
    
    for symbol in config_symbols:
        # Phase 1: Analyze
        req = analyze_requirements(
            operation_type="symbol",
            symbol=symbol,
            source="config",
            session_data=self.session_data,
            session_coordinator=self
        )
        
        # Phase 2: Validate
        if not req.can_proceed:
            logger.warning(f"{symbol}: {req.validation_errors}")
            continue
        
        # Phase 3: Provision
        self._execute_provisioning(req)
```

**Test Scenarios**:

1. **Config Loading with Validation**
   - Config: AAPL, RIVN, BADTICKER
   - Expected: AAPL & RIVN load, BADTICKER dropped

2. **Mid-Session Full Addition**
   - Add TSLA via strategy
   - Expected: Full load with validation

3. **Mid-Session Adhoc Indicator**
   - Scanner adds SMA for MSFT
   - Expected: Auto-provision MSFT, load minimal bars

4. **Upgrade Path**
   - TSLA exists as adhoc
   - Strategy calls add_symbol("TSLA")
   - Expected: Upgrade to full

5. **Duplicate Detection**
   - AAPL already loaded
   - Strategy calls add_symbol("AAPL")
   - Expected: Skip, return success

---

## Code Reuse Summary

### Reusing from Phases 1-4 ✅

1. **Step 0 Validation** (100% reuse)
   - `_validate_symbol_for_loading()`
   - `_check_data_source_for_symbol()`
   - `_check_historical_data_availability()`
   - `_check_parquet_data()`

2. **Step 3 Loading** (100% reuse)
   - `_register_single_symbol()`
   - `_manage_historical_data()`
   - `_register_session_indicators()`
   - `_load_queues()`
   - `_calculate_historical_quality()`

3. **Existing Analyzers** (90% reuse)
   - `analyze_indicator_requirements()` - for indicators
   - `parse_interval()` - for bar analysis
   - `determine_required_base()` - for derived intervals

### New Code for Phase 5 🆕

1. **Core Infrastructure** (~300 lines)
   - `ProvisioningRequirements` dataclass
   - `analyze_requirements()` dispatcher
   - Helper functions

2. **Provisioning Executor** (~100 lines)
   - `_execute_provisioning()` orchestrator

3. **Unified Entry Points** (~150 lines)
   - `add_indicator_unified()`
   - `add_bar_unified()`
   - Update `add_symbol()`

**Total New Code**: ~550 lines  
**Code Reuse**: ~90%

---

## Architectural Compliance Checklist

### ✅ TimeManager
- All date/time via `time_manager.get_current_time()`
- Calendar calculations via `analyze_indicator_requirements()` (uses TimeManager)

### ✅ DataManager
- All Parquet access via `load_historical_bars()`
- Validation uses existing `_check_parquet_data()`

### ✅ Infer from Config
- Symbol requirements from `session_config.session_data_config`
- Interval requirements from config
- Historical requirements from config

### ✅ Single Source of Truth
- Config drives requirements
- Validation results stored once
- Metadata part of SymbolSessionData

### ✅ Thread-Safe
- All operations use `_symbol_operation_lock`
- Metadata updates atomic

---

## Benefits of This Architecture

### 1. Consistency ✅
- Same pattern for bars, indicators, symbols
- Same validation for all sources
- Same metadata tracking

### 2. Maintainability ✅
- Single place for requirement analysis
- Single place for provisioning logic
- Clear separation of concerns

### 3. Flexibility ✅
- Easy to add new operation types
- Easy to add new sources
- Easy to add new validation rules

### 4. Visibility ✅
- Clear logging at each phase
- Clear error messages
- Clear provisioning steps

### 5. Correctness ✅
- Always validates before provisioning
- Always sets correct metadata
- Always integrates with existing flow

---

## Next Steps

### Option 1: Start Phase 5a (Core Infrastructure) ✅ RECOMMENDED
Implement requirement analysis system first, then test thoroughly before continuing.

### Option 2: Implement All Phases at Once
If confident in design, implement all phases together (~5-9 hours total).

### Option 3: Test Current Implementation First
Test Phases 1-4 validation with real data, then add Phase 5 if needed.

---

## Readiness Status

✅ **Architecture Complete**
- Three-phase pattern designed
- Integration points identified
- Code reuse maximized

✅ **Documentation Complete**
- Flow updated in SESSION_ARCHITECTURE.md
- Complete design in UNIFIED_PROVISIONING_ARCHITECTURE.md
- Implementation plan ready

✅ **Foundation Ready**
- Phases 1-4 validation in place
- Step 3 loading methods parameterized
- Metadata infrastructure complete

✅ **Ready to Implement**
- Clear implementation phases
- Testing strategy defined
- Code reuse mapped

---

## Implementation Command

**To start Phase 5a implementation:**

```
Implement Phase 5a: Core Infrastructure for unified provisioning.

Start with:
1. Create ProvisioningRequirements dataclass
2. Implement analyze_requirements() dispatcher
3. Implement helper functions
4. Test requirement analysis standalone

Use maximum code reuse from existing analyzers and validation.
```

**Estimated Time**: 2-3 hours for Phase 5a  
**Total Phase 5**: 5-9 hours

---

## Conclusion

**Architecture is production-ready and implementation-ready!**

✅ Three-phase pattern unified  
✅ Maximum code reuse planned (~90%)  
✅ Integration points clear  
✅ Testing strategy defined  
✅ Documentation complete  

**Ready to implement Phase 5a!** 🚀
