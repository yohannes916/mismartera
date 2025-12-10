# Unified Auto-Provisioning Architecture

## Executive Summary

**Goal**: Create a unified, parameterized auto-provisioning system that handles ALL addition scenarios (bars, indicators, symbols) with requirement analysis before any operation.

**Key Insight**: Every addition (whether from config, scanner, strategy, or adhoc) must go through:
1. **Requirement Analysis** - What do we need? (symbols, bars, intervals, historical data)
2. **Validation** - Do we have it? Can we get it?
3. **Provisioning** - Create missing pieces (symbols, bars, intervals)
4. **Loading** - Load data (historical, session, indicators)

---

## Current State Analysis

### Existing Auto-Provisioning Code ✅

**File**: `/app/managers/data_manager/session_data.py`

#### 1. `add_indicator()` - Lines 2244-2375
```python
def add_indicator(symbol: str, indicator_type: str, config: dict) -> bool:
    """Add indicator with automatic bar provisioning."""
    
    # Step 1: Analyze requirements (EXISTING!)
    requirements = analyze_indicator_requirements(
        indicator_config, system_manager, warmup_multiplier=2.0
    )
    
    # Step 2: Provision required bars automatically (EXISTING!)
    for required_interval in requirements.required_intervals:
        # Add historical bars
        self.add_historical_bars(symbol, required_interval, requirements.historical_days)
        
        # Add session bars  
        self.add_session_bars(symbol, required_interval)
    
    # Step 3: Register indicator
    symbol_data.indicators[key] = IndicatorData(...)
```

**What Works**: ✅ Requirement analysis, ✅ Bar provisioning  
**What's Missing**: ⚠️ Symbol validation, ⚠️ Calls incomplete methods (TODOs)

#### 2. `add_historical_bars()` - Lines 2178-2210
```python
def add_historical_bars(symbol: str, interval: str, days: int) -> bool:
    """Provision historical bars only (no streaming)."""
    
    # Register symbol if not exists
    if symbol not in self._symbols:
        self.register_symbol(symbol)
    
    # TODO: Call coordinator method to load historical bars
    # self._session_coordinator.load_historical_bars(symbol, interval, days)
```

**What Works**: ✅ Symbol auto-registration  
**What's Missing**: ❌ No validation, ❌ Coordinator call is TODO

#### 3. `add_session_bars()` - Lines 2212-2242
```python
def add_session_bars(symbol: str, interval: str) -> bool:
    """Provision live streaming bars only (no historical)."""
    
    # Register symbol if not exists
    if symbol not in self._symbols:
        self.register_symbol(symbol)
    
    # TODO: Call coordinator method to start streaming
    # self._session_coordinator.start_bar_stream(symbol, interval)
```

**What Works**: ✅ Symbol auto-registration  
**What's Missing**: ❌ No validation, ❌ Coordinator call is TODO

#### 4. Requirement Analyzer ✅
**File**: `/app/threads/quality/requirement_analyzer.py` (lines 466-570)

```python
def analyze_indicator_requirements(
    indicator_config,
    system_manager,
    warmup_multiplier=2.0
) -> IndicatorRequirements:
    """Analyze bar requirements for an indicator."""
    
    # Parse interval
    interval_info = parse_interval(interval)
    
    # Determine required intervals (base + derived)
    required_intervals = [interval]
    if not interval_info.is_base:
        base_interval = determine_required_base(interval)
        required_intervals.insert(0, base_interval)
    
    # Calculate bars needed
    warmup_bars = indicator_config.warmup_bars()
    historical_bars_needed = int(warmup_bars * warmup_multiplier)
    
    # Use TimeManager to calculate calendar days
    historical_days = _estimate_calendar_days_via_timemanager(...)
    
    return IndicatorRequirements(
        required_intervals=required_intervals,
        historical_bars=historical_bars_needed,
        historical_days=historical_days
    )
```

**What Works**: ✅ Interval analysis, ✅ TimeManager usage, ✅ Warmup calculation  
**What's Missing**: ⚠️ Only handles indicators, not bars or symbols

---

## Problem Statement

### Current Issues

1. **Fragmented Approach** ❌
   - `add_indicator()` has requirement analysis
   - `add_historical_bars()` has no requirement analysis
   - `add_session_bars()` has no requirement analysis
   - `add_symbol()` in coordinator has validation but no requirement analysis
   - No unified pattern!

2. **Incomplete Methods** ❌
   - `add_historical_bars()` has TODO for coordinator call
   - `add_session_bars()` has TODO for coordinator call
   - No connection to actual data loading

3. **Missing Validation** ❌
   - `add_historical_bars()` doesn't validate data availability
   - `add_session_bars()` doesn't validate interval support
   - No graceful error handling

4. **No Source Tracking** ❌
   - Methods don't know if called from config, scanner, or strategy
   - Can't set correct `added_by` metadata
   - Can't set `meets_session_config_requirements` correctly

5. **No Integration with Step 0/Step 3** ❌
   - Provisioning methods bypass validation
   - Don't integrate with coordinator's validation flow
   - Duplicate logic instead of reusing

---

## Unified Architecture Design

### Core Principle: Three-Phase Pattern

**ALL additions (bars, indicators, symbols) go through 3 phases:**

```
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 1: REQUIREMENT ANALYSIS             │
│  What do we need? (symbols, bars, intervals, historical)    │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 2: VALIDATION                       │
│  Do we have it? Can we get it? (Step 0 validation)         │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 3: PROVISIONING + LOADING           │
│  Create missing pieces, load data (Step 3 loading)          │
└─────────────────────────────────────────────────────────────┘
```

### Unified Requirements Dataclass

```python
@dataclass
class ProvisioningRequirements:
    """Unified requirements for any addition operation.
    
    Used by bars, indicators, and symbols.
    """
    operation_type: str  # "bar", "indicator", "symbol"
    source: str  # "config", "scanner", "strategy", "adhoc"
    
    # Symbol requirements
    symbol: str
    symbol_exists: bool = False
    symbol_validated: bool = False
    
    # Bar requirements
    required_intervals: List[str] = field(default_factory=list)
    base_interval: Optional[str] = None
    intervals_exist: Dict[str, bool] = field(default_factory=dict)
    
    # Historical requirements
    needs_historical: bool = False
    historical_days: int = 0
    historical_bars: int = 0
    historical_available: bool = False
    
    # Session requirements
    needs_session: bool = False
    session_available: bool = False
    
    # Indicator requirements (if applicable)
    indicator_config: Optional[Any] = None
    indicator_key: Optional[str] = None
    
    # Validation results
    can_proceed: bool = False
    validation_errors: List[str] = field(default_factory=list)
    provisioning_steps: List[str] = field(default_factory=list)
    
    # Metadata
    meets_session_config_requirements: bool = False
    added_by: str = "adhoc"
    reason: str = ""
```

### Unified Requirement Analyzer

```python
def analyze_requirements(
    operation_type: str,  # "bar", "indicator", "symbol"
    symbol: str,
    source: str,  # "config", "scanner", "strategy"
    session_data: SessionData,
    session_coordinator: SessionCoordinator,
    **kwargs  # operation-specific args
) -> ProvisioningRequirements:
    """Unified requirement analysis for ANY addition operation.
    
    Args:
        operation_type: What are we adding? ("bar", "indicator", "symbol")
        symbol: Symbol to add
        source: Who is adding? ("config", "scanner", "strategy")
        session_data: SessionData instance
        session_coordinator: SessionCoordinator instance
        **kwargs: Operation-specific arguments
            For "bar": interval, days, historical_only
            For "indicator": indicator_config
            For "symbol": None (gets from config)
    
    Returns:
        ProvisioningRequirements with complete analysis
    """
    req = ProvisioningRequirements(
        operation_type=operation_type,
        source=source,
        symbol=symbol,
        added_by=source
    )
    
    # Phase 1: Check symbol existence
    existing_symbol = session_data.get_symbol_data(symbol)
    req.symbol_exists = existing_symbol is not None
    
    # Phase 2: Analyze based on operation type
    if operation_type == "indicator":
        _analyze_indicator_requirements(req, **kwargs)
    elif operation_type == "bar":
        _analyze_bar_requirements(req, **kwargs)
    elif operation_type == "symbol":
        _analyze_symbol_requirements(req, session_coordinator)
    
    # Phase 3: Validate using Step 0
    if operation_type in ["symbol", "bar"]:
        # Use existing Step 0 validation
        validation_result = session_coordinator._validate_symbol_for_loading(symbol)
        req.symbol_validated = validation_result.can_proceed
        req.historical_available = validation_result.has_historical_data
        if not validation_result.can_proceed:
            req.validation_errors.append(validation_result.reason)
    
    # Phase 4: Determine provisioning steps
    _determine_provisioning_steps(req, existing_symbol)
    
    # Phase 5: Set metadata flags
    req.meets_session_config_requirements = (source == "config")
    req.can_proceed = len(req.validation_errors) == 0
    
    return req
```

### Helper Functions

```python
def _analyze_indicator_requirements(
    req: ProvisioningRequirements,
    indicator_config: IndicatorConfig,
    system_manager
):
    """Analyze indicator-specific requirements.
    
    REUSES: analyze_indicator_requirements() from requirement_analyzer
    """
    from app.threads.quality.requirement_analyzer import analyze_indicator_requirements
    
    indicator_reqs = analyze_indicator_requirements(
        indicator_config=indicator_config,
        system_manager=system_manager,
        warmup_multiplier=2.0
    )
    
    req.indicator_config = indicator_config
    req.indicator_key = indicator_reqs.indicator_key
    req.required_intervals = indicator_reqs.required_intervals
    req.historical_bars = indicator_reqs.historical_bars
    req.historical_days = indicator_reqs.historical_days
    req.needs_historical = indicator_reqs.historical_days > 0
    req.needs_session = True
    req.reason = indicator_reqs.reason


def _analyze_bar_requirements(
    req: ProvisioningRequirements,
    interval: str,
    days: int,
    historical_only: bool = False
):
    """Analyze bar-specific requirements."""
    from app.threads.quality.requirement_analyzer import parse_interval, determine_required_base
    
    interval_info = parse_interval(interval)
    
    # Determine required intervals
    req.required_intervals = [interval]
    if not interval_info.is_base:
        base_interval = determine_required_base(interval)
        if base_interval:
            req.required_intervals.insert(0, base_interval)
            req.base_interval = base_interval
    
    req.historical_days = days
    req.needs_historical = days > 0
    req.needs_session = not historical_only
    req.reason = f"Bar {interval} requires {req.required_intervals}, {days} days historical"


def _analyze_symbol_requirements(
    req: ProvisioningRequirements,
    session_coordinator: SessionCoordinator
):
    """Analyze symbol-specific requirements.
    
    REUSES: Session config to determine requirements
    """
    config = session_coordinator.session_config.session_data_config
    
    # Get intervals from config
    req.required_intervals = config.streams  # Base intervals
    req.required_intervals.extend(config.derived_intervals)  # Derived intervals
    
    # Get historical requirements from config
    if config.historical.enabled and config.historical.data:
        first_config = config.historical.data[0]
        req.historical_days = first_config.trailing_days
        req.needs_historical = True
    
    req.needs_session = True
    req.reason = f"Symbol requires intervals={req.required_intervals}, {req.historical_days} days historical"


def _determine_provisioning_steps(
    req: ProvisioningRequirements,
    existing_symbol
):
    """Determine what provisioning steps are needed."""
    
    # Step 1: Symbol provisioning
    if not req.symbol_exists:
        req.provisioning_steps.append("create_symbol")
    elif existing_symbol and not existing_symbol.meets_session_config_requirements:
        req.provisioning_steps.append("upgrade_symbol")
    
    # Step 2: Bar provisioning
    for interval in req.required_intervals:
        if existing_symbol:
            if interval not in existing_symbol.bars:
                req.provisioning_steps.append(f"add_interval_{interval}")
        else:
            req.provisioning_steps.append(f"add_interval_{interval}")
    
    # Step 3: Historical provisioning
    if req.needs_historical and not req.historical_available:
        req.provisioning_steps.append("load_historical")
    
    # Step 4: Session provisioning
    if req.needs_session:
        req.provisioning_steps.append("load_session")
    
    # Step 5: Indicator provisioning
    if req.indicator_config:
        req.provisioning_steps.append("register_indicator")
```

---

## Integration with Existing Flow

### Pre-Session (Config Loading)

```python
def _load_session_data(self):
    """Phase 2: Load session data with unified provisioning."""
    
    config_symbols = self.session_config.session_data_config.symbols
    
    # For each symbol from config
    for symbol in config_symbols:
        # Phase 1: Analyze requirements
        req = analyze_requirements(
            operation_type="symbol",
            symbol=symbol,
            source="config",
            session_data=self.session_data,
            session_coordinator=self
        )
        
        # Phase 2: Validate (REUSE existing Step 0)
        if not req.can_proceed:
            logger.warning(f"{symbol}: Validation failed - {req.validation_errors}")
            continue
        
        # Phase 3: Provision + Load (REUSE existing Step 3)
        self._execute_provisioning(req)
```

### Mid-Session (Scanner/Strategy Addition)

```python
def add_indicator_unified(
    self,
    symbol: str,
    indicator_config: IndicatorConfig,
    source: str = "scanner"
) -> bool:
    """Unified indicator addition with requirement analysis."""
    
    # Phase 1: Analyze requirements
    req = analyze_requirements(
        operation_type="indicator",
        symbol=symbol,
        source=source,
        session_data=self.session_data,
        session_coordinator=self._session_coordinator,
        indicator_config=indicator_config,
        system_manager=self._system_manager
    )
    
    # Phase 2: Validate
    if not req.can_proceed:
        logger.error(f"{symbol}: Cannot add indicator - {req.validation_errors}")
        return False
    
    # Phase 3: Provision + Load
    return self._execute_provisioning(req)


def add_bar_unified(
    self,
    symbol: str,
    interval: str,
    days: int = 0,
    source: str = "scanner"
) -> bool:
    """Unified bar addition with requirement analysis."""
    
    # Phase 1: Analyze requirements
    req = analyze_requirements(
        operation_type="bar",
        symbol=symbol,
        source=source,
        session_data=self.session_data,
        session_coordinator=self._session_coordinator,
        interval=interval,
        days=days
    )
    
    # Phase 2: Validate
    if not req.can_proceed:
        logger.error(f"{symbol}: Cannot add bar - {req.validation_errors}")
        return False
    
    # Phase 3: Provision + Load
    return self._execute_provisioning(req)
```

### Unified Provisioning Executor

```python
def _execute_provisioning(self, req: ProvisioningRequirements) -> bool:
    """Execute provisioning steps determined by requirement analysis.
    
    REUSES: All existing loading methods!
    """
    logger.info(f"[PROVISION] {req.symbol}: Executing {len(req.provisioning_steps)} steps")
    
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
            existing.added_by = req.added_by
        
        elif step.startswith("add_interval_"):
            interval = step.replace("add_interval_", "")
            # Add bar structure for this interval
            # (reuse existing bar creation logic)
        
        elif step == "load_historical":
            # REUSE existing method
            self._manage_historical_data(symbols=[req.symbol])
        
        elif step == "load_session":
            # REUSE existing method
            self._load_queues(symbols=[req.symbol])
        
        elif step == "register_indicator":
            # REUSE existing method
            self._register_session_indicators(symbols=[req.symbol])
    
    logger.info(f"[PROVISION] {req.symbol}: ✅ Complete")
    return True
```

---

## Code Reuse Summary

### What We Reuse ✅

1. **Step 0 Validation** (Phase 4 implementation)
   - `_validate_symbol_for_loading()`
   - `_check_parquet_data()`
   - `_check_historical_data_availability()`

2. **Step 3 Loading** (Existing coordination methods)
   - `_register_single_symbol()` (with metadata)
   - `_manage_historical_data(symbols=[...])`
   - `_register_session_indicators(symbols=[...])`
   - `_load_queues(symbols=[...])`
   - `_calculate_historical_quality(symbols=[...])`

3. **Requirement Analyzer** (Existing)
   - `analyze_indicator_requirements()` (for indicators)
   - `parse_interval()` (for bar interval analysis)
   - `determine_required_base()` (for derived intervals)

### What We Add 🆕

1. **Unified Analyzer** (~150 lines)
   - `analyze_requirements()` - dispatcher
   - `_analyze_bar_requirements()` - bar analysis
   - `_analyze_symbol_requirements()` - symbol analysis
   - `_determine_provisioning_steps()` - step generator

2. **Unified Executor** (~100 lines)
   - `_execute_provisioning()` - calls existing methods
   - Orchestration logic only, no new loading code

3. **Unified Entry Points** (~50 lines each)
   - `add_indicator_unified()` - replaces `add_indicator()`
   - `add_bar_unified()` - replaces `add_historical_bars()` + `add_session_bars()`

**Total New Code**: ~400 lines  
**Code Reuse**: ~90% (calls existing APIs)

---

## Implementation Phases

### Phase 5a: Core Infrastructure (2-3 hours)
1. Create `ProvisioningRequirements` dataclass
2. Implement `analyze_requirements()` dispatcher
3. Implement helper functions (`_analyze_*`, `_determine_provisioning_steps`)
4. Test requirement analysis standalone

### Phase 5b: Provisioning Executor (1-2 hours)
1. Implement `_execute_provisioning()` in SessionCoordinator
2. Wire to existing Step 3 loading methods
3. Test provisioning with mocked requirements

### Phase 5c: Unified Entry Points (1-2 hours)
1. Implement `add_indicator_unified()` in SessionData
2. Implement `add_bar_unified()` in SessionData
3. Update `add_symbol()` in SessionCoordinator to use unified flow
4. Deprecate old methods

### Phase 5d: Integration & Testing (1-2 hours)
1. Update config loading to use unified flow
2. Test all scenarios (config, scanner, strategy)
3. Verify metadata correctness
4. Update documentation

**Total Estimated Time**: 5-9 hours

---

## Benefits of Unified Approach

### 1. Consistency ✅
- Same pattern for bars, indicators, symbols
- Same validation for all sources
- Same metadata tracking

### 2. Maintainability ✅
- Single place to update provisioning logic
- Reuses existing validation and loading
- Clear separation of concerns

### 3. Flexibility ✅
- Easy to add new operation types
- Easy to add new sources
- Easy to add new validation rules

### 4. Visibility ✅
- Clear logging of requirements
- Clear logging of provisioning steps
- Clear error messages

### 5. Correctness ✅
- Always validates before provisioning
- Always sets correct metadata
- Always integrates with Step 0/Step 3 flow

---

## Next Steps

**Recommendation**: Implement Phase 5a first (Core Infrastructure)

This will:
1. Unify requirement analysis for all operations
2. Integrate with existing Step 0 validation
3. Prepare for unified provisioning executor

**After Phase 5a**, we can:
- Test requirement analysis thoroughly
- Verify integration with existing code
- Decide if we want to continue with full unified provisioning or just use unified analysis

**Would you like me to:**
1. Start implementing Phase 5a (Core Infrastructure)?
2. Create more detailed designs for specific scenarios?
3. Test current validation with requirement analysis?
