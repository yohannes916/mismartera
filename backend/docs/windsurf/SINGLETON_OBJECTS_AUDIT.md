# Singleton Objects Audit - Single Source of Truth

## Audit Summary

Comprehensive analysis of all singleton objects to identify duplicate state tracking and ensure single source of truth architecture.

**Date:** Dec 3, 2025  
**Status:** 🔴 **VIOLATIONS FOUND** - Multiple objects tracking same state

---

## 📊 Singleton Objects Hierarchy

```
SystemManager (Root Singleton)
├── TimeManager
├── DataManager
├── ExecutionManager
└── Thread Pool
    ├── SessionCoordinator
    ├── DataProcessor
    ├── DataQualityManager
    └── AnalysisEngine

SessionConfig (Configuration Object - not singleton, but single source for config)
SessionData (Singleton - market data store)
```

---

## 🚨 VIOLATIONS FOUND

### 1. **`mode` - DUPLICATED IN 7 PLACES** ❌

**Single Source:** `SessionConfig.mode` → exposed via `SystemManager.mode` property

| Object | Location | Storage Type | Violation |
|--------|----------|--------------|-----------|
| **SessionConfig** | `session_config.mode` | ✅ **SOURCE** | Config file value |
| **SystemManager** | `self.mode` (property) | ✅ **CORRECT** | Delegates to session_config |
| **SessionCoordinator** | `self.mode` | ❌ **DUPLICATE** | Stores as string |
| **DataProcessor** | `self.mode` | ❌ **DUPLICATE** | Stores as string |
| **DataQualityManager** | `self.mode` | ❌ **DUPLICATE** | Stores as string |
| **AnalysisEngine** | `self.mode` | ❌ **DUPLICATE** | Stores as string |
| **ExecutionManager** | `self.mode` | ❌ **DUPLICATE** | Stores as string |
| **StreamRequirementsCoordinator** | `self.mode` | ❌ **DUPLICATE** | Stores as string |

**Impact:** 6 duplicate copies + 1 correct property

**Fix Required:**
- All threads and managers should use `self._system_manager.mode`
- Remove all `self.mode` storage except in SystemManager property
- SystemManager property delegates to `session_config.mode` (already correct)

---

### 2. **`backtest_start_date` / `backtest_end_date` - CORRECT** ✅

**Single Source:** `SessionConfig.backtest_config` → exposed via `SystemManager` properties → delegated to `TimeManager`

| Object | Access Pattern | Status |
|--------|---------------|---------|
| **SessionConfig** | `backtest_config.start_date/end_date` | ✅ CONFIG SOURCE |
| **SystemManager** | `self.backtest_start_date/end_date` (property) | ✅ Reads from config |
| **TimeManager** | `self.backtest_start_date/end_date` (property) | ✅ Delegates to SystemManager |
| **All Others** | Query via `time_manager.backtest_start_date` | ✅ CORRECT |

**Status:** ✅ **NO VIOLATIONS** - Proper single source of truth pattern

---

### 3. **`timezone` - CORRECT** ✅

**Single Source:** `SystemManager.timezone` (derived from database)

| Object | Access Pattern | Status |
|--------|---------------|---------|
| **SystemManager** | `self.timezone` | ✅ **SOURCE** (derived from MarketHours DB) |
| **All Others** | Query via `system_manager.timezone` | ✅ CORRECT |

**Status:** ✅ **NO VIOLATIONS** - Proper single source of truth pattern

---

### 4. **`_state` (System State) - CORRECT** ✅

**Single Source:** `SystemManager._state`

| Object | Access Pattern | Status |
|--------|---------------|---------|
| **SystemManager** | `self._state` (SystemState enum) | ✅ **SOURCE** |
| **All Others** | Query via `system_manager.state` or `system_manager.is_running()` | ✅ CORRECT |

**Status:** ✅ **NO VIOLATIONS** - No other objects store state

---

### 5. **`session_config` - REFERENCE PASSING (Needs Review)** ⚠️

**Single Source:** `SystemManager._session_config`

| Object | Storage | Access | Issue |
|--------|---------|--------|-------|
| **SystemManager** | `self._session_config` | ✅ **OWNER** | Loads from file |
| **SessionCoordinator** | `self.session_config` | ⚠️ **STORES REF** | Passed in __init__ |
| **DataProcessor** | `self.session_config` | ⚠️ **STORES REF** | Passed in __init__ |
| **DataQualityManager** | `self.session_config` | ⚠️ **STORES REF** | Passed in __init__ |
| **AnalysisEngine** | `self.session_config` | ⚠️ **STORES REF** | Passed in __init__ |

**Assessment:**
- Not a violation per se (storing reference, not duplicate data)
- **HOWEVER**: Threads should access via `system_manager.session_config` for consistency
- **RISK**: If threads store reference, they can bypass SystemManager

**Recommendation:**
- Remove `self.session_config` from threads
- Access via `self._system_manager.session_config` when needed
- Extract specific values during init (like `derived_intervals`) instead of storing whole config

---

### 6. **Current Time - CORRECT** ✅

**Single Source:** `TimeManager` (via `get_current_time()`)

| Object | Access Pattern | Status |
|--------|---------------|---------|
| **TimeManager** | `get_current_time()` method | ✅ **SOURCE** |
| **All Others** | `time_manager.get_current_time()` or `system_manager.get_time_manager().get_current_time()` | ✅ CORRECT |

**Status:** ✅ **NO VIOLATIONS** - No objects store current time

---

### 7. **Session Active State - CORRECT** ✅

**Single Source:** `SessionData._session_active`

| Object | Access Pattern | Status |
|--------|---------------|---------|
| **SessionData** | `self._session_active` | ✅ **SOURCE** |
| **All Others** | `session_data.is_session_active()` | ✅ CORRECT |

**Status:** ✅ **NO VIOLATIONS**

---

## 📋 Detailed Violations

### Violation #1: Mode Duplication

#### SessionCoordinator (`/app/threads/session_coordinator.py:85-112`)

**Current (WRONG):**
```python
def __init__(
    self,
    system_manager,
    data_manager,
    session_config: SessionConfig,
    mode: str = "backtest"  # ❌ Passed as parameter
):
    super().__init__(name="SessionCoordinator", daemon=True)
    self._system_manager = system_manager
    self._data_manager = data_manager
    self._time_manager = system_manager.get_time_manager()
    self.session_config = session_config
    self.mode = mode  # ❌ DUPLICATE STORAGE
```

**Fixed (CORRECT):**
```python
def __init__(
    self,
    system_manager,
    data_manager,
    session_config: SessionConfig  # ❌ Remove mode parameter
):
    super().__init__(name="SessionCoordinator", daemon=True)
    self._system_manager = system_manager
    self._data_manager = data_manager
    self._time_manager = system_manager.get_time_manager()
    # ❌ Remove self.session_config
    # ❌ Remove self.mode
    
@property
def mode(self) -> str:
    """Get mode from SystemManager (single source)."""
    return self._system_manager.mode.value  # Convert enum to string if needed
```

**Usage Changes:**
```python
# OLD
if self.mode == "backtest":

# NEW
if self._system_manager.mode == OperationMode.BACKTEST:
# OR
if self.mode == "backtest":  # Via property
```

---

#### DataProcessor (`/app/threads/data_processor.py:87-137`)

**Current (WRONG):**
```python
def __init__(
    self,
    session_data: SessionData,
    system_manager,
    session_config: SessionConfig,
    metrics: PerformanceMetrics
):
    # ...
    self.mode = "backtest" if session_config.backtest_config else "live"  # ❌ DUPLICATE
```

**Fixed (CORRECT):**
```python
def __init__(
    self,
    session_data: SessionData,
    system_manager,
    metrics: PerformanceMetrics  # ❌ Remove session_config parameter
):
    # ...
    # ❌ Remove self.mode
    
@property
def mode(self) -> str:
    """Get mode from SystemManager (single source)."""
    return self._system_manager.mode.value
```

---

#### DataQualityManager (`/app/threads/data_quality_manager.py:96-134`)

**Current (WRONG):**
```python
def __init__(
    self,
    session_data: SessionData,
    system_manager,
    session_config: SessionConfig,
    metrics: PerformanceMetrics
):
    # ...
    self.mode = "backtest" if session_config.backtest_config else "live"  # ❌ DUPLICATE
```

**Fixed (CORRECT):**
```python
def __init__(
    self,
    session_data: SessionData,
    system_manager,
    metrics: PerformanceMetrics  # ❌ Remove session_config parameter
):
    # ...
    # Extract needed values during init
    gap_filler_config = system_manager.session_config.session_data_config.gap_filler
    self._enable_quality = gap_filler_config.enable_session_quality
    # ...
    # ❌ Remove self.mode
    
@property
def mode(self) -> str:
    """Get mode from SystemManager (single source)."""
    return self._system_manager.mode.value

@property  
def _gap_filling_enabled(self) -> bool:
    """Compute dynamically from mode."""
    return self.mode == "live" and self._enable_quality
```

---

#### AnalysisEngine (`/app/threads/analysis_engine.py:192-237`)

**Current (WRONG):**
```python
def __init__(
    self,
    session_data: SessionData,
    system_manager,
    session_config: SessionConfig,
    metrics: PerformanceMetrics
):
    # ...
    self.mode = "backtest" if session_config.backtest_config else "live"  # ❌ DUPLICATE
    self.speed = 0
    if self.mode == "backtest" and session_config.backtest_config:
        self.speed = session_config.backtest_config.speed_multiplier
```

**Fixed (CORRECT):**
```python
def __init__(
    self,
    session_data: SessionData,
    system_manager,
    metrics: PerformanceMetrics  # ❌ Remove session_config parameter
):
    # ...
    # ❌ Remove self.mode
    # ❌ Remove self.speed (compute dynamically)
    
@property
def mode(self) -> str:
    """Get mode from SystemManager (single source)."""
    return self._system_manager.mode.value

@property
def speed(self) -> int:
    """Get speed from backtest config (compute dynamically)."""
    if self._system_manager.mode == OperationMode.BACKTEST:
        config = self._system_manager.session_config.backtest_config
        return config.speed_multiplier if config else 0
    return 0
```

---

#### ExecutionManager (`/app/managers/execution_manager/api.py:29-40`)

**Current (WRONG):**
```python
def __init__(
    self,
    mode: str = "backtest",  # ❌ Mode parameter
    brokerage: str = "alpaca",
    system_manager: Optional[Any] = None
):
    self.mode = mode  # ❌ DUPLICATE STORAGE
    self.brokerage_name = brokerage
    self._brokerage: Optional[BrokerageInterface] = None
    self._system_manager = system_manager
```

**Fixed (CORRECT):**
```python
def __init__(
    self,
    brokerage: str = "alpaca",
    system_manager: Optional[Any] = None  # ❌ Remove mode parameter, make system_manager required
):
    if system_manager is None:
        raise ValueError("system_manager is required")
    
    self._system_manager = system_manager
    self.brokerage_name = brokerage
    self._brokerage: Optional[BrokerageInterface] = None
    # ❌ Remove self.mode

@property
def mode(self) -> str:
    """Get mode from SystemManager (single source)."""
    return self._system_manager.mode.value
```

---

#### StreamRequirementsCoordinator (`/app/threads/quality/stream_requirements_coordinator.py:74-89`)

**Current (WRONG):**
```python
def __init__(
    self,
    session_config: SessionConfig,
    time_manager: TimeManager
):
    self.session_config = session_config
    self.time_manager = time_manager
    
    # Extract config values
    self.symbols = session_config.session_data_config.symbols
    self.streams = session_config.session_data_config.streams
    self.mode = session_config.mode  # ❌ DUPLICATE
```

**Fixed (CORRECT):**
```python
def __init__(
    self,
    system_manager,  # ✅ Pass system_manager instead
    time_manager: TimeManager
):
    self._system_manager = system_manager
    self.time_manager = time_manager
    
    # Extract config values ONCE during init
    config = system_manager.session_config
    self.symbols = config.session_data_config.symbols
    self.streams = config.session_data_config.streams
    # ❌ Remove self.mode

@property
def mode(self) -> str:
    """Get mode from SystemManager (single source)."""
    return self._system_manager.mode.value
```

---

## 🔧 Refactoring Checklist

### High Priority (Mode Duplication)

- [ ] **SessionCoordinator**
  - [ ] Remove `mode` parameter from `__init__`
  - [ ] Remove `self.mode` storage
  - [ ] Add `mode` property that delegates to SystemManager
  - [ ] Update all `self.mode` references to use property
  - [ ] Update SystemManager thread creation (remove mode parameter)

- [ ] **DataProcessor**
  - [ ] Remove `session_config` parameter
  - [ ] Remove `self.mode` storage
  - [ ] Add `mode` property
  - [ ] Update all references

- [ ] **DataQualityManager**
  - [ ] Remove `session_config` parameter
  - [ ] Remove `self.mode` storage
  - [ ] Add `mode` property
  - [ ] Update `_gap_filling_enabled` to property

- [ ] **AnalysisEngine**
  - [ ] Remove `session_config` parameter
  - [ ] Remove `self.mode` and `self.speed` storage
  - [ ] Add `mode` and `speed` properties
  - [ ] Update all references

- [ ] **ExecutionManager**
  - [ ] Remove `mode` parameter
  - [ ] Make `system_manager` required
  - [ ] Remove `self.mode` storage
  - [ ] Add `mode` property
  - [ ] Update all references

- [ ] **StreamRequirementsCoordinator**
  - [ ] Change to accept `system_manager` instead of `session_config`
  - [ ] Remove `self.mode` storage
  - [ ] Add `mode` property
  - [ ] Update caller to pass `system_manager`

### Medium Priority (Config Reference)

- [ ] **All Threads** - Consider removing `self.session_config` storage
  - Extract needed values during `__init__`
  - Access remaining values via `self._system_manager.session_config`
  - Reduces coupling and ensures consistency

### Low Priority (Documentation)

- [ ] Update all docstrings to reflect single source of truth
- [ ] Add architecture documentation about singleton access patterns
- [ ] Update examples and tutorials

---

## 📐 Access Patterns (Best Practices)

### ✅ CORRECT Pattern

```python
class MyThread(threading.Thread):
    def __init__(self, system_manager):
        self._system_manager = system_manager
        # Extract immutable config values during init (optional)
        self._derived_intervals = system_manager.session_config.session_data_config.data_upkeep.derived_intervals
    
    @property
    def mode(self) -> OperationMode:
        """Get mode from SystemManager (single source)."""
        return self._system_manager.mode
    
    @property
    def time_manager(self):
        """Get TimeManager from SystemManager."""
        return self._system_manager.get_time_manager()
    
    def run(self):
        # Use properties
        if self.mode == OperationMode.BACKTEST:
            current = self.time_manager.get_current_time()
```

### ❌ WRONG Pattern

```python
class MyThread(threading.Thread):
    def __init__(self, system_manager, session_config, mode):
        self._system_manager = system_manager
        self.session_config = session_config  # ❌ Storing reference
        self.mode = mode  # ❌ Duplicate storage
        self.timezone = system_manager.timezone  # ❌ Duplicate storage
    
    def run(self):
        # Reading from duplicates
        if self.mode == "backtest":  # ❌ Could be stale
            # ...
```

---

## 🎯 Architecture Principle

### Single Source of Truth Hierarchy

```
Config Files (static)
    ↓ (read ONCE during init)
SystemManager (runtime state)
    ├─ mode (property → session_config.mode)
    ├─ state (own attribute)
    ├─ timezone (own attribute, from DB)
    ├─ session_config (owns reference)
    ├─ TimeManager (manages time/calendar)
    ├─ DataManager (manages market data)
    └─ SessionData (manages current session data)
    ↓ (accessed via system_manager)
All Threads & Managers
    ├─ SessionCoordinator
    ├─ DataProcessor
    ├─ DataQualityManager
    ├─ AnalysisEngine
    └─ ExecutionManager
```

### Rules

1. **Never duplicate state** - If SystemManager has it, don't store it elsewhere
2. **Properties over storage** - Use properties that delegate to source
3. **Pass system_manager** - Not individual config values or mode
4. **Extract immutables** - OK to extract immutable config values during init
5. **Query dynamics** - Always query dynamic values (time, state, mode)

---

## 📊 Impact Analysis

### Files to Modify

1. `app/managers/system_manager/api.py` - Thread creation calls (remove mode parameter)
2. `app/threads/session_coordinator.py` - Remove mode storage, add property
3. `app/threads/data_processor.py` - Remove mode storage, add property
4. `app/threads/data_quality_manager.py` - Remove mode storage, add property
5. `app/threads/analysis_engine.py` - Remove mode/speed storage, add properties
6. `app/managers/execution_manager/api.py` - Remove mode parameter/storage, add property
7. `app/threads/quality/stream_requirements_coordinator.py` - Change to use system_manager

### Test Impact

- All thread initialization tests need updating
- Mock objects need to provide `mode` property
- Integration tests should verify single source access

### Risk Level

- **Medium Risk** - Widespread changes to thread initialization
- **Mitigation** - Properties maintain backward compatibility for reads
- **Validation** - Run full test suite + manual backtest verification

---

## ✅ Success Criteria

After refactoring:

1. ✅ `mode` stored in exactly 1 place: `SessionConfig.mode`
2. ✅ `mode` accessed via `SystemManager.mode` property everywhere
3. ✅ All threads access via `self._system_manager.mode`
4. ✅ No thread stores `self.mode` except as property
5. ✅ No thread stores `self.session_config` (access via system_manager)
6. ✅ All tests pass
7. ✅ Backtest runs successfully
8. ✅ Live mode works correctly

---

## 🔍 Verification Commands

After refactoring, run these checks:

```bash
# Find any remaining self.mode assignments (should be 0 outside SystemManager)
grep -r "self.mode =" backend/app/threads/
grep -r "self.mode =" backend/app/managers/ --exclude-dir=system_manager

# Find session_config stored as attribute (should remove these)
grep -r "self.session_config = session_config" backend/app/threads/

# Verify mode property exists in all threads
grep -r "def mode(self)" backend/app/threads/
```

Expected: No storage, only property definitions.

---

## 📝 Notes

- `StreamSubscription._mode` is NOT a violation - it stores subscription mode (data-driven/clock-driven/live), not system mode
- TradingSession.timezone is NOT a violation - it's data from database, not system timezone
- MarketHours.timezone is NOT a violation - it's configuration data from database

These are distinct from `SystemManager.mode` and `SystemManager.timezone`.
