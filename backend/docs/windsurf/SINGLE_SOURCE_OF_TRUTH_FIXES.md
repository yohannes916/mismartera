# Single Source of Truth - Architecture Fixes

## Issue Summary

Found violations of the "single source of truth" principle in the JSON serialization design and SystemManager code.

---

## 1. SystemManager `mode` Property - DUPLICATE DEFINITION ⚠️

**Location:** `/app/managers/system_manager/api.py`

### Problem

The `mode` property is defined **twice** in the same class:

```python
# Definition 1 (Line 186-194)
@property
def mode(self) -> str:
    """Get current system mode (live or backtest).
    
    Returns:
        'live' or 'backtest'
    """
    if self._session_config:
        return self._session_config.mode
    return "backtest"  # Default

# Definition 2 (Line 762-767)
@property
def mode(self) -> OperationMode:
    """Get current operation mode from session config."""
    if self._session_config is None:
        raise RuntimeError("Session config not loaded")
    return OperationMode(self._session_config.mode)
```

### Issues
1. **Duplicate code** - Same property defined twice
2. **Different return types** - First returns `str`, second returns `OperationMode` enum
3. **Different error handling** - First has default, second raises exception
4. **Python override** - Second definition (line 762) overrides first (line 186)

### Fix

**Keep only ONE definition** (recommend keeping the enum version for type safety):

```python
@property
def mode(self) -> OperationMode:
    """Get current operation mode from session config.
    
    Single source of truth: delegates to self._session_config.mode
    
    Returns:
        OperationMode enum (BACKTEST or LIVE)
        
    Raises:
        RuntimeError: If session config not loaded
    """
    if self._session_config is None:
        raise RuntimeError("Session config not loaded")
    return OperationMode(self._session_config.mode)
```

**Remove lines 186-194** (first definition).

### Why This Matters

- **Type safety**: Enum is better than string for mode
- **Consistency**: All code should see same type
- **Maintainability**: One definition = one place to update
- **Single source**: `_session_config.mode` is the source, property delegates to it

---

## 2. JSON Schema - Removed Duplicate `session_data.system` ✅

**Location:** `/backend/docs/windsurf/SYSTEM_JSON_EXAMPLE.json`

### Problem (FIXED)

Original JSON had duplicate system state/mode:

```json
{
  "system_manager": {
    "state": "running",
    "mode": "backtest"
  },
  "session_data": {
    "system": {
      "state": "running",    // ❌ DUPLICATE
      "mode": "backtest"     // ❌ DUPLICATE
    }
  }
}
```

### Fix Applied ✅

Removed `session_data.system` section:

```json
{
  "system_manager": {
    "state": "running",
    "mode": "backtest"
  },
  "session_data": {
    "session": {
      "date": "2024-11-15",
      ...
    }
  }
}
```

### Why This Is Correct

- **SystemManager owns system state** - Not SessionData's responsibility
- **SessionData is for market data** - Bars, quotes, ticks, symbols
- **Single source of truth** - One place for state/mode
- **No duplication** - Follows SOLID principles

---

## 3. Single Source of Truth Architecture

### Principle

**Each piece of information should have exactly ONE authoritative source.**

### Current Sources of Truth

| Information | Source of Truth | Access Pattern |
|-------------|----------------|----------------|
| **System State** | `SystemManager._state` | `system_manager.state` |
| **System Mode** | `SessionConfig.mode` | `system_manager.mode` (property) |
| **Timezone** | `SystemManager.timezone` | `system_manager.timezone` |
| **Current Time** | `TimeManager` | `time_manager.get_current_time()` |
| **Trading Hours** | `TimeManager` + DB | `time_manager.get_trading_session()` |
| **Session Date** | `SessionData._session_date` | `session_data._session_date` (will add) |
| **Session Active** | `SessionData._session_active` | `session_data.is_session_active()` |
| **Symbol Data** | `SymbolSessionData` | `session_data.get_symbol_data()` |

### Read/Write Pattern

When a value needs to be stored in config but accessed frequently:

**✅ CORRECT Pattern** (like `backtest_start_date`):

```python
class SystemManager:
    @property
    def backtest_start_date(self) -> Optional[date]:
        """Single source: reads from session_config."""
        if not self._session_config or not self._session_config.backtest_config:
            return None
        return datetime.strptime(
            self._session_config.backtest_config.start_date,
            "%Y-%m-%d"
        ).date()
    
    @backtest_start_date.setter
    def backtest_start_date(self, value: date) -> None:
        """Single source: writes to session_config."""
        if not self._session_config or not self._session_config.backtest_config:
            raise RuntimeError("Session config not loaded")
        self._session_config.backtest_config.start_date = value.strftime("%Y-%m-%d")
```

**Benefits:**
- Config is the source
- Property provides convenient access
- Read/write both go through config
- No duplication

**❌ WRONG Pattern**:

```python
class SystemManager:
    def __init__(self):
        self._mode = None  # ❌ Duplicate storage
    
    def load_config(self, config):
        self._mode = config.mode  # ❌ Copy from config
        
    @property
    def mode(self):
        return self._mode  # ❌ Serving stale copy
```

---

## 4. Implementation Guidance for JSON Serialization

### When Serializing SystemManager

```python
class SystemManager:
    def to_json(self, complete: bool = False, debug: bool = False) -> dict:
        # ✅ CORRECT - delegate to property
        data = {
            "state": self._state.value,  # Direct access OK (owned by this class)
            "mode": self.mode.value,     # Via property (delegates to config)
            "timezone": self.timezone    # Direct access OK (owned by this class)
        }
```

### When Serializing SessionData

```python
class SessionData:
    def to_json(self, complete: bool = False, debug: bool = False) -> dict:
        # ✅ CORRECT - no system state/mode
        data = {
            "session": {
                "date": self._session_date,
                "active": self._session_active,
                # ... symbol data ...
            }
        }
        # ❌ WRONG - don't include system state/mode here
        # data["system"] = {"state": ..., "mode": ...}
```

---

## 5. Action Items

### Immediate (Before Implementation)

- [x] Update JSON example to remove `session_data.system`
- [x] Update mapping documents to reflect single source
- [ ] **Remove duplicate `mode` property** from SystemManager (lines 186-194)

### During Implementation

- [ ] Ensure `to_json()` methods respect single source of truth
- [ ] SessionData should NOT serialize system state/mode
- [ ] All time operations via TimeManager (already enforced)
- [ ] All mode checks via `system_manager.mode` property

### Testing

- [ ] Verify JSON output has no duplicates
- [ ] Verify mode property works correctly after removing duplicate
- [ ] Verify SessionData.to_json() doesn't include system state

---

## 6. Summary

### What We Fixed ✅

1. **Removed duplicate `session_data.system`** from JSON schema
2. **Identified duplicate `mode` property** in SystemManager (needs code fix)
3. **Documented single source of truth** for all major data

### What We Avoided ❌

1. Storing mode in multiple places
2. Duplicating system state in SessionData
3. Creating parallel tracking of same information

### Key Principle

**"Don't store it twice. Store it once, access it everywhere."**

- Config is source → Property delegates to config
- SystemManager owns state → Others read from SystemManager
- TimeManager owns time → Others query TimeManager
- SessionData owns market data → Others query SessionData

This ensures consistency, eliminates sync bugs, and makes the code easier to maintain.
