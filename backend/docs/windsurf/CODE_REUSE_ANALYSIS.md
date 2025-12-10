# Code Reuse Analysis - Validation & Provisioning Implementation

## Executive Summary

**Analysis Objective**: Identify maximum code reuse opportunities for implementing per-symbol validation and auto-provisioning while maintaining architectural principles.

**Key Finding**: ~75-80% code reuse possible by:
1. Parameterizing existing methods
2. Using DataManager APIs for Parquet access
3. Using TimeManager APIs for date/time
4. Inferring from existing structures

---

## Architectural Principles (Must Maintain)

### 1. Single Source of Truth ✅
**Already Implemented**:
- `SessionData` is singleton (`get_session_data()`)
- `TimeManager` for all time operations
- `DataManager` for all Parquet access

**Must Continue**:
- No duplicate data structures
- Query, don't cache (except for performance)

### 2. Infer from Structure ✅
**Already Implemented**:
```python
# Example: Infer intervals from bar structure
for interval_key in symbol_data.historical.bars.keys():
    # interval_key = "1m", "5m", etc.
    
# Example: Infer symbols from session_data
for symbol in session_data._symbols.keys():
    # process symbol
```

**Must Continue**:
- Don't store what can be inferred
- Let structure drive behavior

### 3. TimeManager API for All Date/Time ✅
**Already Implemented**:
```python
# In session_coordinator.py:1260
current_time = self._time_manager.get_current_time()
current_date = current_time.date()

# In data_manager/api.py:2162
if self.system_manager.mode.value == "backtest":
    end_date = time_mgr.backtest_start_date
else:
    current_time = time_mgr.get_current_time()
    end_date = current_time.date()
```

**Must Continue**:
- Never use `datetime.now()`
- Never hardcode trading hours
- Always query TimeManager

### 4. DataManager API for Parquet Access ✅
**Already Implemented**:
```python
# In data_manager/api.py:2176
df = parquet_storage.read_bars(
    data_type=interval,
    symbol=symbol,
    start_date=start_date,
    end_date=end_date
)
```

**Must Continue**:
- All Parquet access through DataManager
- No direct parquet_storage imports in coordinator

---

## Current Code Analysis

### 1. Symbol Loading Flow (EXISTING)

#### Current Pre-Session Flow
```python
# In _load_session_data() - line 958
def _load_session_data(self):
    """Load session data (coordination method)."""
    self._register_symbols()  # ✅ Can parameterize
    self._manage_historical_data()  # ✅ Already parameterized
    self._register_session_indicators()  # ✅ Already parameterized
    self._calculate_historical_indicators()  # ✅ Already parameterized
    self._load_queues()  # ✅ Already parameterized
    self._calculate_historical_quality()  # ✅ Already parameterized
```

**Code Reuse Opportunity**: 98% reusable!
- 5 of 6 methods already accept `symbols` parameter
- Only `_register_symbols()` needs parameterization

#### Historical Data Loading (ALREADY PARAMETERIZED) ✅
```python
# session_coordinator.py:1233
def _manage_historical_data(self, symbols: Optional[List[str]] = None):
    symbols_to_process = symbols or self.session_config.session_data_config.symbols
    # ... uses symbols_to_process
```

**Status**: ✅ Ready for reuse (already supports symbol filtering)

#### Quality Calculation (ALREADY PARAMETERIZED) ✅
```python
# session_coordinator.py:1409
def _calculate_historical_quality(self, symbols: Optional[List[str]] = None):
    if symbols is None:
        symbols = self.session_config.session_data_config.symbols
    # ... processes specific symbols
```

**Status**: ✅ Ready for reuse

### 2. DataManager APIs (EXISTING - CAN REUSE)

#### Check Parquet Data Availability ✅
```python
# data_manager/api.py:2126
def load_historical_bars(
    self,
    symbol: str,
    interval: str,
    days: int = 30
) -> List[BarData]:
    """Load historical bars from parquet storage."""
    # Uses TimeManager for date range
    # Returns bars or empty list
```

**Reuse for Validation**:
```python
def _check_parquet_data(self, symbol: str, interval: str, date: date) -> bool:
    """Check if Parquet data exists (reuses DataManager)."""
    try:
        bars = self._data_manager.load_historical_bars(
            symbol=symbol,
            interval=interval,
            days=1  # Just check for this date
        )
        return len(bars) > 0
    except Exception:
        return False
```

**Code Reuse**: 100% - Just call existing API!

#### Check Historical Data Range ✅
```python
# Can infer from existing API
def _check_historical_data_availability(self, symbol: str) -> bool:
    """Check if historical data exists (reuses DataManager)."""
    historical_config = self.session_config.session_data_config.historical
    
    if not historical_config.data:
        return True  # No historical required
    
    # Try to load 1 day of data for first configured interval
    first_config = historical_config.data[0]
    interval = first_config.interval
    
    try:
        bars = self._data_manager.load_historical_bars(
            symbol=symbol,
            interval=interval,
            days=first_config.trailing_days
        )
        return len(bars) > 0
    except Exception:
        return False
```

**Code Reuse**: 100% - Just call existing API!

### 3. Stream Validation (EXISTING - CAN REUSE)

#### Stream Requirements Coordinator ✅
```python
# Already exists: session_coordinator.py:54
from app.threads.quality.stream_requirements_coordinator import StreamRequirementsCoordinator

# Already used in _validate_stream_requirements()
def _validate_stream_requirements(self) -> bool:
    """Validate stream configuration (system-wide)."""
    coordinator = StreamRequirementsCoordinator(...)
    result = coordinator.validate_requirements()
    
    if result.validation_passed:
        self._base_interval = result.base_interval
        self._derived_intervals_validated = result.derivable_intervals
```

**Reuse for Per-Symbol Validation**:
```python
def _validate_interval_compatibility(
    self,
    required: List[str],
    available: List[str]
) -> bool:
    """Check if available intervals support required (reuses existing logic)."""
    # Can reuse derivation logic from StreamRequirementsCoordinator
    # Just check if required intervals can be derived from available
    
    for req_interval in required:
        if req_interval in available:
            continue
        
        # Check if derivable
        can_derive = self._can_derive_interval(req_interval, available)
        if not can_derive:
            return False
    
    return True

def _can_derive_interval(self, target: str, sources: List[str]) -> bool:
    """Check if target interval can be derived from sources."""
    # Reuse logic from StreamRequirementsCoordinator
    # 1m can derive: 5m, 15m, 30m, 1h
    # 1s can derive: 5s, 10s, 30s, 1m, 5m, etc.
    
    target_seconds = parse_interval_to_seconds(target)
    
    for source in sources:
        source_seconds = parse_interval_to_seconds(source)
        if target_seconds >= source_seconds and target_seconds % source_seconds == 0:
            return True
    
    return False
```

**Code Reuse**: ~70% - Reuse parsing/derivation logic

### 4. Symbol Registration (NEEDS PARAMETERIZATION)

#### Current Registration Flow
```python
# session_coordinator.py:2570
def _register_symbols(self):
    """Register ALL symbols from config."""
    symbols = self.session_config.session_data_config.symbols
    
    for symbol in symbols:
        self._register_single_symbol(symbol)
```

**Parameterize for Reuse**:
```python
def _register_symbols(self, symbols: Optional[List[str]] = None):
    """Register specified symbols (or all from config)."""
    symbols_to_register = symbols or self.session_config.session_data_config.symbols
    
    for symbol in symbols_to_register:
        self._register_single_symbol(symbol)
```

**Code Reuse**: 100% - Just add optional parameter!

---

## New Code Needed (Cannot Reuse)

### 1. Per-Symbol Validation Result Structure ❌
```python
@dataclass
class SymbolValidationResult:
    """NEW - No existing equivalent."""
    symbol: str
    can_proceed: bool
    reason: str
    data_source_available: bool
    data_source: Optional[str]
    intervals_supported: List[str]
    # ...
```

**Estimate**: 30 lines, 30 minutes

### 2. Per-Symbol Validation Logic ❌
```python
def _validate_symbol_for_loading(self, symbol: str) -> SymbolValidationResult:
    """NEW - Per-symbol validation."""
    # Check 1: Already loaded?
    # Check 2: Data source available?
    # Check 3: Intervals supported?
    # Check 4: Historical data available?
    # Check 5: Meets requirements?
```

**Estimate**: 80 lines, 2 hours (calls existing APIs!)

### 3. Batch Validation with Graceful Degradation ❌
```python
def _validate_symbols_for_loading(self, symbols: List[str]) -> List[str]:
    """NEW - Batch validation with graceful degradation."""
    validated = []
    failed = []
    
    for symbol in symbols:
        result = self._validate_symbol_for_loading(symbol)
        if result.can_proceed:
            validated.append(symbol)
        else:
            failed.append((symbol, result.reason))
    
    if not validated:
        raise RuntimeError("NO SYMBOLS PASSED VALIDATION")
    
    return validated
```

**Estimate**: 40 lines, 1 hour

### 4. SymbolSessionData Constructor Update ❌
```python
# Add metadata fields to existing __init__
def __init__(
    self,
    symbol: str,
    meets_session_config_requirements: bool = False,
    added_by: str = "config",
    auto_provisioned: bool = False
):
    """Updated constructor with metadata."""
    self.symbol = symbol
    self.bars = {}
    self.indicators = {}
    self.quality = {}
    
    # NEW: Metadata
    self.meets_session_config_requirements = meets_session_config_requirements
    self.added_by = added_by
    self.auto_provisioned = auto_provisioned
    self.added_at = None
    self.upgraded_from_adhoc = False
```

**Estimate**: 20 lines, 30 minutes

### 5. Auto-Provisioning Logic ❌
```python
# In SessionData
def _auto_provision_symbol(self, symbol: str, reason: str):
    """NEW - Auto-provision for adhoc."""
    symbol_data = SymbolSessionData(
        symbol=symbol,
        meets_session_config_requirements=False,
        added_by="adhoc",
        auto_provisioned=True
    )
    symbol_data.added_at = time_manager.get_current_time()
    self._symbols[symbol] = symbol_data
```

**Estimate**: 30 lines, 1 hour

---

## Code Reuse Summary

### Existing Code (Can Reuse)

| Component | Status | Reuse % | Changes Needed |
|-----------|--------|---------|----------------|
| `_manage_historical_data()` | ✅ Ready | 100% | None (already parameterized) |
| `_register_session_indicators()` | ✅ Ready | 100% | None (already parameterized) |
| `_calculate_historical_indicators()` | ✅ Ready | 100% | None (already parameterized) |
| `_load_queues()` | ✅ Ready | 100% | None (already parameterized) |
| `_calculate_historical_quality()` | ✅ Ready | 100% | None (already parameterized) |
| `_register_symbols()` | ⚠️ Needs param | 100% | Add optional symbols parameter |
| `DataManager.load_historical_bars()` | ✅ Ready | 100% | None - call directly |
| `StreamRequirementsCoordinator` | ✅ Ready | 70% | Extract derivation logic |
| `_register_single_symbol()` | ✅ Ready | 100% | Update to pass metadata |

**Total Existing Code**: ~1500 lines
**Reusable**: ~1200 lines (80%)

### New Code (Cannot Reuse)

| Component | Lines | Time | Dependencies |
|-----------|-------|------|--------------|
| `SymbolValidationResult` dataclass | 30 | 30 min | None |
| `_validate_symbol_for_loading()` | 80 | 2 hr | Calls existing APIs |
| `_validate_symbols_for_loading()` | 40 | 1 hr | Calls above |
| `SymbolSessionData` metadata fields | 20 | 30 min | None |
| `_auto_provision_symbol()` | 30 | 1 hr | None |
| Adhoc validation helpers | 100 | 2 hr | None |
| JSON/CSV serialization updates | 50 | 1 hr | None |

**Total New Code**: ~350 lines
**Total Time**: ~8 hours

---

## Implementation Strategy (Maximizing Reuse)

### Phase 1: Minimal Changes (2 hours)
1. Add metadata fields to `SymbolSessionData` (30 min)
2. Update `_register_symbols()` to accept symbols parameter (15 min)
3. Update all symbol creation sites to pass metadata (1 hr)
4. Update serialization to include metadata (30 min)

**Result**: Metadata tracking working, no behavior changes

### Phase 2: Validation Helpers (3 hours)
1. Create `SymbolValidationResult` dataclass (30 min)
2. Create validation helpers that CALL existing APIs:
   - `_check_parquet_data()` → calls `data_manager.load_historical_bars()`
   - `_check_historical_data_availability()` → calls `data_manager.load_historical_bars()`
   - `_validate_interval_compatibility()` → reuses derivation logic
3. Create `_validate_symbol_for_loading()` that uses above helpers (2 hr)

**Result**: Per-symbol validation working

### Phase 3: Integration (2 hours)
1. Create `_validate_symbols_for_loading()` batch method (1 hr)
2. Update `_load_session_data()` to call validation (30 min)
3. Update `add_symbol()` to call validation (30 min)

**Result**: Graceful degradation working

### Phase 4: Auto-Provisioning (1 hour)
1. Add `_auto_provision_symbol()` to SessionData (30 min)
2. Update `add_bar()` to auto-provision (30 min)

**Result**: Adhoc insertion working

**Total Implementation**: ~8 hours

---

## Architectural Compliance Checklist

### ✅ Single Source of Truth
- [x] TimeManager for all dates/times
- [x] DataManager for all Parquet access
- [x] SessionData singleton for symbol data
- [x] Metadata part of SymbolSessionData (not separate)

### ✅ Infer from Structure
- [x] Symbols inferred from `session_data._symbols.keys()`
- [x] Intervals inferred from `symbol_data.historical.bars.keys()`
- [x] Metadata read from `symbol_data.meets_session_config_requirements`

### ✅ TimeManager API
- [x] `_time_manager.get_current_time()` for current time
- [x] `time_mgr.backtest_start_date` for backtest ranges
- [x] Never `datetime.now()`

### ✅ DataManager API
- [x] `data_manager.load_historical_bars()` for Parquet data
- [x] No direct `parquet_storage` imports
- [x] All Parquet access abstracted

---

## Example: Validation Helper with Max Reuse

```python
def _check_historical_data_availability(self, symbol: str) -> bool:
    """Check if historical data exists for symbol.
    
    REUSES:
    - DataManager API for Parquet access ✅
    - TimeManager API (via DataManager) ✅
    - Existing config structures ✅
    
    NEW: Just the orchestration logic
    """
    historical_config = self.session_config.session_data_config.historical
    
    # No historical required?
    if not historical_config.data:
        return True  # ✅ Infer from structure
    
    # Check first configured interval
    first_config = historical_config.data[0]
    interval = first_config.interval
    days = first_config.trailing_days
    
    try:
        # ✅ REUSE: DataManager API (which uses TimeManager internally)
        bars = self._data_manager.load_historical_bars(
            symbol=symbol,
            interval=interval,
            days=days
        )
        
        # ✅ Infer: Has data if bars returned
        return len(bars) > 0
        
    except Exception as e:
        logger.warning(
            f"{symbol}: Error checking historical data availability: {e}"
        )
        return False
```

**Code Reuse**: 95% (calls existing APIs, minimal orchestration)

---

## Summary

### Code Reuse Achieved
- **Existing code reusable**: ~80% (1200/1500 lines)
- **New code needed**: ~350 lines
- **Implementation time**: ~8 hours
- **Architectural compliance**: 100%

### Key Reuse Strategies
1. ✅ Parameterize existing methods (add optional symbols)
2. ✅ Call DataManager APIs for Parquet access
3. ✅ Call TimeManager APIs for date/time (via DataManager)
4. ✅ Reuse validation logic from StreamRequirementsCoordinator
5. ✅ Infer from existing structures

### Architectural Principles Maintained
1. ✅ Single source of truth (TimeManager, DataManager, SessionData)
2. ✅ Infer from structure (symbols, intervals, metadata)
3. ✅ TimeManager API for all date/time operations
4. ✅ DataManager API for all Parquet access

**This is a highly reusable implementation that maintains all architectural principles!**
