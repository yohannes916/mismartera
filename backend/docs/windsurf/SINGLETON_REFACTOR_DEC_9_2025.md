# Singleton Pattern Refactoring - December 9, 2025

## Summary

Refactored indicator auto-provisioning to use SystemManager singleton pattern instead of passing TimeManager and session objects around. This aligns with the architecture where all components are accessible through SystemManager.

## Problem

The initial implementation passed TimeManager and database session as parameters:

```python
# ❌ OLD WAY - Passing components around
def analyze_indicator_requirements(
    indicator_config,
    time_manager,      # Passed explicitly
    session,           # Passed explicitly
    warmup_multiplier=2.0
):
    # ...
```

**Issues:**
- Verbose API with multiple parameters
- Violates singleton pattern used throughout codebase
- Caller must manage getting TimeManager
- Caller must manage database session lifecycle

## Solution

Use SystemManager singleton to access components as needed:

```python
# ✅ NEW WAY - Using singleton pattern
def analyze_indicator_requirements(
    indicator_config,
    system_manager,    # Single entry point
    warmup_multiplier=2.0
):
    # Get TimeManager from SystemManager
    time_manager = system_manager.get_time_manager()
    
    # Create database session internally
    with SessionLocal() as session:
        # Use TimeManager with session
        start_date = time_manager.get_previous_trading_date(
            session, from_date, n=trading_days
        )
```

## Architecture Pattern

### SystemManager is Single Source

**All components available through SystemManager:**
- TimeManager: `system_manager.get_time_manager()`
- DataManager: `system_manager.get_data_manager()`
- etc.

**Database sessions created as needed:**
- `from app.models.database import SessionLocal`
- `with SessionLocal() as session:` (synchronous)

**No need to pass components around:**
- Components are singletons
- Access through SystemManager when needed
- Session lifecycle managed locally

## Changes Made

### 1. Updated Function Signature

**Before:**
```python
def analyze_indicator_requirements(
    indicator_config,
    time_manager,      # ❌ Explicit parameter
    session,           # ❌ Explicit parameter
    warmup_multiplier=2.0,
    from_date=None,
    exchange="NYSE"
):
```

**After:**
```python
def analyze_indicator_requirements(
    indicator_config,
    system_manager,    # ✅ Single parameter
    warmup_multiplier=2.0,
    from_date=None,
    exchange="NYSE"
):
```

### 2. Updated Implementation

**Get TimeManager internally:**
```python
# Get TimeManager from SystemManager
time_manager = system_manager.get_time_manager()
```

**Create database session internally:**
```python
# Create session for TimeManager queries
with SessionLocal() as session:
    # Use TimeManager APIs
    start_date = time_manager.get_previous_trading_date(...)
    trading_session = time_manager.get_trading_session(...)
```

### 3. Updated Caller (SessionData)

**Before:**
```python
# ❌ Complex setup
time_manager = self._session_coordinator._time_manager
system_manager = self._session_coordinator._system_manager

async with AsyncSessionLocal() as db_session:
    requirements = analyze_indicator_requirements(
        indicator_config,
        time_manager,      # Passed explicitly
        db_session,        # Passed explicitly
        warmup_multiplier=2.0
    )
```

**After:**
```python
# ✅ Simple call
system_manager = self._session_coordinator._system_manager

requirements = analyze_indicator_requirements(
    indicator_config,
    system_manager,    # Single parameter
    warmup_multiplier=2.0
)
```

### 4. Updated Tests

**Mock SystemManager instead of individual components:**

```python
def analyze_with_mocks(config, warmup_multiplier=2.0):
    # Create mock TimeManager
    time_manager = Mock()
    time_manager.get_current_time.return_value = Mock(...)
    time_manager.get_previous_trading_date = Mock(...)
    time_manager.get_trading_session = Mock(...)
    
    # Create mock SystemManager that provides TimeManager
    system_manager = Mock()
    system_manager.get_time_manager.return_value = time_manager
    
    # Call with SystemManager
    return analyze_indicator_requirements(
        config,
        system_manager,    # ✅ Single mock
        warmup_multiplier
    )
```

## Benefits

### 1. Simpler API
✅ Single parameter instead of multiple
✅ Caller doesn't manage component access
✅ Caller doesn't manage session lifecycle

### 2. Architecture Compliance
✅ Follows singleton pattern
✅ SystemManager is single entry point
✅ Components accessed through established patterns

### 3. Maintainability
✅ Less coupling between components
✅ Easier to test (mock SystemManager)
✅ Consistent with rest of codebase

### 4. Flexibility
✅ Function manages its own dependencies
✅ Can easily add more component access
✅ Session lifecycle scoped appropriately

## Synchronous vs Async Sessions

**Key Discovery:** TimeManager uses synchronous `Session`, not async:

```python
# TimeManager signature
def get_previous_trading_date(
    self,
    session: Session,  # Synchronous!
    from_date: date,
    n: int = 1
) -> Optional[date]:
```

**Solution:** Use synchronous `SessionLocal()`:

```python
from app.models.database import SessionLocal  # Synchronous

with SessionLocal() as session:
    # Use with TimeManager
    time_manager.get_previous_trading_date(session, ...)
```

**No need for async/await!**

## Test Results

| Test Suite | Tests | Status |
|------------|-------|--------|
| `test_indicator_auto_provisioning.py` | 17 | ✅ ALL PASS |
| `test_scanner_integration.py` | 8 | ✅ ALL PASS |
| **TOTAL** | **25** | **✅ ALL PASS** |

## Files Modified

1. **`/app/threads/quality/requirement_analyzer.py`**
   - Updated `analyze_indicator_requirements()` signature
   - Gets TimeManager from SystemManager internally
   - Creates database session internally
   - Uses synchronous `SessionLocal()`

2. **`/app/managers/data_manager/session_data.py`**
   - Simplified call to `analyze_indicator_requirements()`
   - Passes SystemManager only
   - Removed async wrapper

3. **`/tests/unit/test_indicator_auto_provisioning.py`**
   - Updated mock helper to mock SystemManager
   - SystemManager provides mocked TimeManager
   - Simpler test setup

## Comparison

### Before (Verbose)

```python
# Caller code
time_manager = self._session_coordinator._time_manager
system_manager = self._session_coordinator._system_manager

async with AsyncSessionLocal() as db_session:
    requirements = analyze_indicator_requirements(
        indicator_config,
        time_manager,      # Parameter 1
        db_session,        # Parameter 2
        warmup_multiplier=2.0,
        from_date=None,
        exchange="NYSE"
    )
```

### After (Clean)

```python
# Caller code
system_manager = self._session_coordinator._system_manager

requirements = analyze_indicator_requirements(
    indicator_config,
    system_manager,    # Single parameter
    warmup_multiplier=2.0,
    from_date=None,
    exchange="NYSE"
)
```

## Pattern to Follow

When writing new functions that need TimeManager:

**✅ DO:**
```python
def my_function(system_manager, ...):
    time_manager = system_manager.get_time_manager()
    with SessionLocal() as session:
        # Use TimeManager with session
```

**❌ DON'T:**
```python
def my_function(time_manager, session, ...):
    # Don't pass components explicitly
```

## Conclusion

The refactoring successfully applies the singleton pattern, making the API cleaner and more consistent with the rest of the codebase. All tests pass and the code is more maintainable.

**Status:** ✅ Complete and Production-Ready

---

**End of Singleton Refactoring Documentation**
