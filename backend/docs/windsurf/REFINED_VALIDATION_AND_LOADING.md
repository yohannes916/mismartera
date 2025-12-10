# Refined Validation and Loading Architecture

## Core Principles (CORRECTED)

1. **NO persistence between sessions** - Every session starts fresh
2. **Per-symbol validation** - Step 0 validates each symbol individually
3. **Graceful degradation** - Failed symbols dropped, others proceed
4. **Terminate if all fail** - If no symbols pass validation, terminate
5. **Adhoc has lighter validation** - Per-bar/indicator validation only
6. **Maximum code reuse** - Parameterized validation functions

---

## Step 0: Per-Symbol Validation (REVISED)

### Purpose
Validate EACH symbol individually to determine if Step 3 (data loading) is possible.

### Validation Questions (Per Symbol)

```python
class SymbolValidationResult:
    """Result of per-symbol validation."""
    symbol: str
    can_proceed: bool  # Can we proceed to Step 3?
    reason: str  # Why or why not
    
    # Data source validation
    data_source_available: bool
    data_source: Optional[str]  # "alpaca", "schwab", "parquet"
    
    # Interval validation
    intervals_supported: List[str]  # Which intervals are available
    base_interval: Optional[str]  # What base interval to use
    
    # Historical data validation
    has_historical_data: bool
    historical_date_range: Optional[Tuple[date, date]]
    
    # Requirements validation
    meets_config_requirements: bool
```

### Validation Logic

```python
def _validate_symbol_for_loading(self, symbol: str) -> SymbolValidationResult:
    """Step 0: Validate single symbol for full loading.
    
    Determines if symbol can proceed to Step 3 (data loading).
    This is the per-symbol component of Step 0.
    
    Returns:
        SymbolValidationResult with can_proceed flag
    """
    logger.info(f"[STEP_0] Validating {symbol}")
    
    result = SymbolValidationResult(symbol=symbol)
    
    # Check 1: Already loaded?
    if self.session_data.get_symbol_data(symbol):
        metadata = self.session_data.get_symbol_metadata(symbol)
        if metadata and metadata.meets_session_config_requirements:
            result.can_proceed = False
            result.reason = "already_loaded"
            return result
    
    # Check 2: Data source available?
    # Query data_manager: Does any source have this symbol?
    data_source = self._check_data_source_for_symbol(symbol)
    if not data_source:
        result.can_proceed = False
        result.reason = "no_data_source"
        result.data_source_available = False
        return result
    
    result.data_source = data_source
    result.data_source_available = True
    
    # Check 3: Intervals supported?
    # Query data_manager: What intervals are available for this symbol?
    available_intervals = self._check_available_intervals(symbol, data_source)
    required_intervals = self._get_required_intervals()  # From config
    
    if not self._validate_interval_compatibility(required_intervals, available_intervals):
        result.can_proceed = False
        result.reason = "intervals_not_supported"
        result.intervals_supported = available_intervals
        return result
    
    result.intervals_supported = available_intervals
    result.base_interval = self._base_interval
    
    # Check 4: Historical data available?
    # Query data_manager: Do we have historical data for this symbol?
    has_historical = self._check_historical_data_availability(symbol)
    if not has_historical and self.session_config.session_data_config.historical.enabled:
        result.can_proceed = False
        result.reason = "no_historical_data"
        result.has_historical_data = False
        return result
    
    result.has_historical_data = has_historical
    
    # Check 5: Meets all requirements?
    result.meets_config_requirements = True
    result.can_proceed = True
    result.reason = "validated"
    
    logger.info(f"[STEP_0] {symbol}: Validation passed ✅")
    return result
```

### Batch Validation with Graceful Degradation

```python
def _validate_symbols_for_loading(self, symbols: List[str]) -> List[str]:
    """Step 0: Validate all symbols, drop failures, proceed with successes.
    
    Returns:
        List of validated symbols that can proceed to Step 3
    """
    logger.info(f"[STEP_0] Validating {len(symbols)} symbols")
    
    validated_symbols = []
    failed_symbols = []
    
    for symbol in symbols:
        result = self._validate_symbol_for_loading(symbol)
        
        if result.can_proceed:
            validated_symbols.append(symbol)
            logger.info(f"[STEP_0] {symbol}: ✅ Validated")
        else:
            failed_symbols.append((symbol, result.reason))
            logger.warning(
                f"[STEP_0] {symbol}: ❌ Validation failed - {result.reason}"
            )
    
    # Report results
    if failed_symbols:
        logger.warning(
            f"[STEP_0] {len(failed_symbols)} symbols failed validation: "
            f"{[s for s, _ in failed_symbols]}"
        )
        for symbol, reason in failed_symbols:
            logger.warning(f"  - {symbol}: {reason}")
    
    # Check if ANY symbols passed
    if not validated_symbols:
        raise RuntimeError(
            "[STEP_0] NO SYMBOLS PASSED VALIDATION - Cannot proceed to session. "
            f"Failed symbols: {failed_symbols}"
        )
    
    logger.info(
        f"[STEP_0] {len(validated_symbols)} symbols validated, "
        f"proceeding to Step 3"
    )
    
    return validated_symbols
```

### Integration into Session Flow

```python
def _load_session_data(self):
    """Phase 2: Load session data (with per-symbol validation)."""
    
    # Get symbols from config
    config_symbols = self.session_config.session_data_config.symbols
    
    # STEP 0: Validate each symbol (graceful degradation)
    validated_symbols = self._validate_symbols_for_loading(config_symbols)
    
    # STEP 3: Load validated symbols only
    self._register_symbols(validated_symbols)
    self._manage_historical_data(symbols=validated_symbols)
    self._register_session_indicators(symbols=validated_symbols)
    self._calculate_historical_indicators(symbols=validated_symbols)
    self._load_queues(symbols=validated_symbols)
    self._calculate_historical_quality(symbols=validated_symbols)
```

---

## Step 3: Full Data Loading (For Validated Symbols)

### Applies To
- Pre-session config symbols (after Step 0 validation)
- Mid-session `add_symbol()` calls (after Step 0 validation)

### What Gets Loaded
```python
def _load_symbols_full(self, symbols: List[str]):
    """Step 3: Full data loading for validated symbols.
    
    This is the FULL session-config loading path.
    Used by both pre-session and mid-session add_symbol().
    """
    # 1. Register symbol structures
    for symbol in symbols:
        self._register_single_symbol(symbol)
    
    # 2. Load historical data
    self._manage_historical_data(symbols=symbols)
    
    # 3. Register session indicators
    self._register_session_indicators(symbols=symbols)
    
    # 4. Calculate historical indicators
    self._calculate_historical_indicators(symbols=symbols)
    
    # 5. Load queues
    self._load_queues(symbols=symbols)
    
    # 6. Calculate quality
    self._calculate_historical_quality(symbols=symbols)
    
    # 7. Mark as fully loaded
    for symbol in symbols:
        self.session_data.set_symbol_metadata(symbol, SymbolMetadata(
            symbol=symbol,
            meets_session_config_requirements=True,
            # ... other fields
        ))
```

---

## Adhoc Bar/Indicator Addition (Lighter Validation)

### Purpose
Add specific bar or indicator without full symbol loading.

### Validation (Parameterized for Reuse)

```python
def _validate_adhoc_bar(
    self, 
    symbol: str, 
    interval: str, 
    bar: BarData
) -> Tuple[bool, str]:
    """Validate adhoc bar addition (lighter than Step 0).
    
    Parameterized for reuse across different bar types.
    
    Returns:
        (can_add, reason) tuple
    """
    # Check 1: Does bar already exist?
    existing_bar = self.session_data.get_bar(symbol, interval, bar.timestamp)
    if existing_bar:
        return (False, "bar_already_exists")
    
    # Check 2: Is interval supported?
    if interval not in self._supported_intervals:
        return (False, f"interval_{interval}_not_supported")
    
    # Check 3: Do we have data in Parquet for this symbol/interval/date?
    # This is optional - might load from live stream
    if self.mode == "backtest":
        has_data = self._check_parquet_data(symbol, interval, bar.timestamp.date())
        if not has_data:
            return (False, "no_parquet_data")
    
    # Check 4: Is symbol already provisioned?
    symbol_data = self.session_data.get_symbol_data(symbol)
    if not symbol_data:
        # Will need to auto-provision
        return (True, "needs_provisioning")
    
    return (True, "validated")

def _validate_adhoc_indicator(
    self,
    symbol: str,
    indicator_config: dict
) -> Tuple[bool, str]:
    """Validate adhoc indicator addition.
    
    Parameterized for reuse.
    """
    # Check 1: Is symbol provisioned?
    if not self.session_data.get_symbol_data(symbol):
        return (True, "needs_provisioning")
    
    # Check 2: Does indicator already exist?
    indicator_name = indicator_config.get('name')
    existing = self.indicator_manager.get_indicator(symbol, indicator_name)
    if existing:
        return (False, "indicator_already_exists")
    
    # Check 3: Is indicator type supported?
    indicator_type = indicator_config.get('type')
    if not self.indicator_manager.is_supported(indicator_type):
        return (False, f"indicator_type_{indicator_type}_not_supported")
    
    return (True, "validated")
```

### Adhoc Addition Flow

```python
def add_adhoc_bar(
    self,
    symbol: str,
    interval: str,
    bar: BarData,
    source: str = "scanner"
) -> bool:
    """Add adhoc bar (uses PARTS of Step 3, not full).
    
    This is the lightweight addition path for scanners.
    """
    # Validate (lighter than Step 0)
    can_add, reason = self._validate_adhoc_bar(symbol, interval, bar)
    
    if not can_add:
        logger.warning(f"[ADHOC] {symbol}/{interval}: Cannot add bar - {reason}")
        return False
    
    # Auto-provision if needed
    if reason == "needs_provisioning":
        logger.info(f"[ADHOC] {symbol}: Auto-provisioning for bar addition")
        self._auto_provision_symbol_for_bar(symbol, interval)
    
    # Add bar (direct SessionData manipulation)
    self.session_data.add_bar(symbol, interval, bar)
    
    logger.info(f"[ADHOC] {symbol}/{interval}: Bar added (source={source})")
    return True

def add_adhoc_indicator(
    self,
    symbol: str,
    indicator_config: dict,
    source: str = "scanner"
) -> bool:
    """Add adhoc indicator (uses PARTS of Step 3, not full)."""
    
    # Validate
    can_add, reason = self._validate_adhoc_indicator(symbol, indicator_config)
    
    if not can_add:
        logger.warning(f"[ADHOC] {symbol}: Cannot add indicator - {reason}")
        return False
    
    # Auto-provision if needed
    if reason == "needs_provisioning":
        logger.info(f"[ADHOC] {symbol}: Auto-provisioning for indicator")
        self._auto_provision_symbol_for_indicator(symbol, indicator_config)
    
    # Register indicator (uses existing method)
    self.indicator_manager.register_indicator(symbol, indicator_config)
    
    logger.info(f"[ADHOC] {symbol}: Indicator added (source={source})")
    return True
```

### Auto-Provisioning (PARTS of Step 3)

```python
def _auto_provision_symbol_for_bar(self, symbol: str, interval: str):
    """Auto-provision minimal symbol structure for bar addition.
    
    Uses PARTS of Step 3 (not full):
    - Creates symbol structure
    - Registers bar interval structure
    - NO historical data
    - NO indicators
    - NO quality calculation
    """
    # Register minimal structure
    self._register_single_symbol_minimal(symbol, intervals=[interval])
    
    # Mark as adhoc
    self.session_data.set_symbol_metadata(symbol, SymbolMetadata(
        symbol=symbol,
        meets_session_config_requirements=False,
        added_by="adhoc",
        auto_provisioned=True,
        provisioned_reason="bar_addition"
    ))

def _auto_provision_symbol_for_indicator(self, symbol: str, indicator_config: dict):
    """Auto-provision for indicator addition (PARTS of Step 3)."""
    
    # Register minimal structure
    self._register_single_symbol_minimal(symbol)
    
    # Register just this indicator (not all session indicators)
    self.indicator_manager.register_indicator(symbol, indicator_config)
    
    # Mark as adhoc
    self.session_data.set_symbol_metadata(symbol, SymbolMetadata(
        symbol=symbol,
        meets_session_config_requirements=False,
        added_by="adhoc",
        auto_provisioned=True,
        provisioned_reason="indicator_addition"
    ))
```

---

## Updated add_symbol() Flow

```python
def add_symbol(self, symbol: str, added_by: str = "strategy") -> bool:
    """Add symbol with FULL session-config loading.
    
    Runs Step 0 validation, then Step 3 loading.
    """
    logger.info(f"[ADD_SYMBOL] {symbol}: Requested by {added_by}")
    
    # Check if already fully loaded
    metadata = self.session_data.get_symbol_metadata(symbol)
    if metadata and metadata.meets_session_config_requirements:
        logger.info(f"[ADD_SYMBOL] {symbol}: Already fully loaded, skipping")
        return True
    
    # Check if exists as adhoc (needs upgrade)
    if metadata and not metadata.meets_session_config_requirements:
        logger.info(f"[ADD_SYMBOL] {symbol}: Exists as adhoc, upgrading to full")
        # Continue to full loading (will upgrade)
    
    # STEP 0: Validate this single symbol
    result = self._validate_symbol_for_loading(symbol)
    
    if not result.can_proceed:
        logger.error(
            f"[ADD_SYMBOL] {symbol}: Validation failed - {result.reason}"
        )
        return False
    
    # STEP 3: Full loading (pause clock if mid-session)
    with self._symbol_operation_lock:
        self._pending_symbols.add(symbol)
    
    logger.info(f"[ADD_SYMBOL] {symbol}: Added to pending for full loading")
    return True
```

---

## Session Lifecycle (Corrected)

### Pre-Session (Step 0 + Step 3)
```python
def _load_session_data(self):
    """Load session data with per-symbol validation."""
    
    # Get symbols from config
    config_symbols = self.session_config.session_data_config.symbols
    
    # STEP 0: Validate each symbol
    validated_symbols = self._validate_symbols_for_loading(config_symbols)
    # → Drops failed symbols
    # → Terminates if all fail
    
    # STEP 3: Load validated symbols
    self._load_symbols_full(validated_symbols)
```

### End of Session (NO Persistence)
```python
def _teardown_and_cleanup(self):
    """End of session - clear everything."""
    
    # Clear ALL symbols (no persistence)
    self.session_data.clear()
    
    # Clear queues
    self._bar_queues.clear()
    
    # Advance clock
    self._advance_to_next_trading_day()
    
    logger.info("Session cleared - fresh start for next session")
```

### Next Session
```python
# Next trading day
→ Load symbols from session_config.json ONLY
→ Run Step 0 validation
→ Load validated symbols
→ Strategies can call add_symbol() if needed (e.g., for positions)
```

---

## Code Reuse: Parameterized Validation

### Validation Helpers (Reusable)

```python
def _check_data_source_for_symbol(self, symbol: str) -> Optional[str]:
    """Check which data source has this symbol (reusable)."""
    # Query data_manager APIs
    # Returns: "alpaca", "schwab", "parquet", or None

def _check_available_intervals(self, symbol: str, source: str) -> List[str]:
    """Check what intervals are available for symbol (reusable)."""
    # Query data_manager for this symbol/source
    # Returns: ["1m", "5m", "1d"] or whatever is available

def _check_historical_data_availability(self, symbol: str) -> bool:
    """Check if historical data exists (reusable)."""
    # Query data_manager: Do we have historical data?
    # Returns: True/False

def _check_parquet_data(self, symbol: str, interval: str, date: date) -> bool:
    """Check if Parquet data exists for specific date (reusable)."""
    # Query data_manager: Do we have Parquet data for this date?
    # Returns: True/False

def _validate_interval_compatibility(
    self,
    required: List[str],
    available: List[str]
) -> bool:
    """Validate interval compatibility (reusable)."""
    # Check if available intervals can satisfy required intervals
    # Considering derivation (1m can derive 5m, etc.)
    # Returns: True/False
```

---

## Summary of Changes

### Validation Architecture
- ✅ Step 0 is PER-SYMBOL validation
- ✅ Failed symbols dropped with warning
- ✅ Other symbols proceed
- ✅ Terminate if NO symbols pass validation
- ✅ Adhoc has lighter validation (per-bar/indicator)
- ✅ Parameterized validation helpers for reuse

### Loading Architecture
- ✅ `add_symbol()` runs Step 0, then Step 3 (full)
- ✅ Adhoc uses PARTS of Step 3 (not full)
- ✅ Auto-provisioning creates minimal structure

### Persistence
- ✅ NO persistence between sessions
- ✅ Fresh start from config each day
- ✅ Strategies can call `add_symbol()` if needed

### Code Reuse
- ✅ Parameterized validation functions
- ✅ Reusable for both full and adhoc paths
- ✅ Maximum code sharing

**This is the correct architecture!**
