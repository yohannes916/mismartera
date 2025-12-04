# session_config.mode Access Analysis

## Question
Is `session_config.mode` directly accessed by anyone outside of setting `system_manager.mode`?

## Answer
**YES** - `session_config.mode` is accessed directly in **6 places** within `SystemManager` itself, plus **1 external class**.

---

## Direct Accesses in SystemManager (`system_manager/api.py`)

### 1. **Line 193** - First `mode` property (DUPLICATE)
```python
@property
def mode(self) -> str:
    if self._session_config:
        return self._session_config.mode  # ✅ Direct access
    return "backtest"
```

### 2. **Line 386** - Backtest config check
```python
if self._session_config.mode == "backtest" and self._session_config.backtest_config:
    logger.info("[SESSION_FLOW] 2.c: SystemManager - Applying backtest configuration")
```
**Should use:** `if self.mode == OperationMode.BACKTEST:`

### 3. **Line 491** - SessionCoordinator creation
```python
self._coordinator = SessionCoordinator(
    system_manager=self,
    data_manager=data_manager,
    session_config=self._session_config,
    mode=self._session_config.mode  # ✅ Direct access
)
```
**Should use:** `mode=self.mode.value`

### 4. **Line 537** - Subscription mode logic
```python
if self._session_config.mode == "live":
    subscription_mode = "live"
```
**Should use:** `if self.mode == OperationMode.LIVE:`

### 5. **Line 723** - Backtest window validation
```python
if self._session_config.mode != "backtest":
    raise RuntimeError("System must be in backtest mode to set backtest window")
```
**Should use:** `if self.mode != OperationMode.BACKTEST:`

### 6. **Line 767** - Second `mode` property (KEEPS - enum version)
```python
@property
def mode(self) -> OperationMode:
    if self._session_config is None:
        raise RuntimeError("Session config not loaded")
    return OperationMode(self._session_config.mode)  # ✅ Direct access (CORRECT)
```
**This is the CORRECT single source of truth access**

---

## External Direct Access

### 7. **StreamRequirementsCoordinator** (`threads/quality/stream_requirements_coordinator.py:89`)

```python
def __init__(self, session_config, time_manager):
    self.session_config = session_config
    self.time_manager = time_manager
    
    # Extract config values
    self.symbols = session_config.session_data_config.symbols
    self.streams = session_config.session_data_config.streams
    self.mode = session_config.mode  # ✅ Direct access - stores as string
```

**Issue:** This class stores `mode` as a string attribute.

**Should be:** Either:
1. Pass `system_manager` reference and use `system_manager.mode`
2. Or pass `mode` as a parameter (already extracted by SystemManager)

---

## Recommendation: Refactor to Single Source

### Current State (Violations)
```python
# ❌ Multiple direct accesses throughout SystemManager
if self._session_config.mode == "backtest":  # Line 386
mode=self._session_config.mode               # Line 491
if self._session_config.mode == "live":      # Line 537
if self._session_config.mode != "backtest":  # Line 723
```

### Refactored (Single Source)
```python
# ✅ All access through self.mode property
if self.mode == OperationMode.BACKTEST:           # Line 386
mode=self.mode.value                              # Line 491
if self.mode == OperationMode.LIVE:               # Line 537
if self.mode != OperationMode.BACKTEST:           # Line 723
```

---

## Action Items

### High Priority

1. **Remove duplicate `mode` property** (lines 186-194)
   - Keep only the enum version (lines 762-767)

2. **Refactor SystemManager internal uses**
   - Replace 4 direct `_session_config.mode` accesses with `self.mode`
   - Lines: 386, 491, 537, 723

3. **Fix StreamRequirementsCoordinator**
   - Option A: Pass `system_manager` reference
   - Option B: Pass `mode` as parameter (already computed by SystemManager)

### Implementation

#### SystemManager Refactor

```python
# Line 386 - BEFORE
if self._session_config.mode == "backtest" and self._session_config.backtest_config:

# Line 386 - AFTER
if self.mode == OperationMode.BACKTEST and self._session_config.backtest_config:

# Line 491 - BEFORE
mode=self._session_config.mode

# Line 491 - AFTER
mode=self.mode.value  # Convert enum to string for SessionCoordinator

# Line 537 - BEFORE
if self._session_config.mode == "live":

# Line 537 - AFTER
if self.mode == OperationMode.LIVE:

# Line 723 - BEFORE
if self._session_config.mode != "backtest":

# Line 723 - AFTER
if self.mode != OperationMode.BACKTEST:
```

#### StreamRequirementsCoordinator Refactor

**Option A (Recommended):**
```python
class StreamRequirementsCoordinator:
    def __init__(
        self,
        session_config: SessionConfig,
        time_manager: TimeManager,
        system_manager: SystemManager  # ✅ ADD
    ):
        self.session_config = session_config
        self.time_manager = time_manager
        self.system_manager = system_manager  # ✅ ADD
        
        # Extract config values
        self.symbols = session_config.session_data_config.symbols
        self.streams = session_config.session_data_config.streams
        # ✅ Access via system_manager
        # (no need to store, access dynamically)
    
    def some_method(self):
        if self.system_manager.mode == OperationMode.BACKTEST:
            # ...
```

**Option B (Alternative):**
```python
class StreamRequirementsCoordinator:
    def __init__(
        self,
        session_config: SessionConfig,
        time_manager: TimeManager,
        mode: OperationMode  # ✅ Pass as parameter
    ):
        self.session_config = session_config
        self.time_manager = time_manager
        self.mode = mode  # ✅ Already computed by SystemManager
```

---

## Summary

### Current State
- **7 direct accesses** to `session_config.mode`
- **1** is in the correct property definition (line 767)
- **5** are in SystemManager methods (should use `self.mode`)
- **1** is in external class (should use SystemManager reference)

### Target State
- **1 direct access** - Only in the `mode` property definition
- **All other code** uses `system_manager.mode` property
- **Single source of truth** maintained

### Benefits
1. **Type safety** - Enum instead of string comparisons
2. **Consistency** - All code uses same accessor
3. **Maintainability** - One place to change behavior
4. **Testability** - Can mock `mode` property easily

---

## Files to Modify

1. **`app/managers/system_manager/api.py`**
   - Remove duplicate `mode` property (lines 186-194)
   - Refactor 4 internal uses (lines 386, 491, 537, 723)

2. **`app/threads/quality/stream_requirements_coordinator.py`**
   - Add `system_manager` parameter (or `mode` parameter)
   - Remove direct `session_config.mode` access (line 89)
   - Update all references to use SystemManager.mode

3. **Update all callers of StreamRequirementsCoordinator**
   - Pass SystemManager reference or mode parameter
