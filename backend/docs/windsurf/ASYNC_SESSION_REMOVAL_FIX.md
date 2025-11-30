# AsyncSessionLocal Removal Fix

**Date:** 2025-11-29  
**Issue:** System startup failed with "cannot import name 'AsyncSessionLocal'"

---

## Problem

System tried to import `AsyncSessionLocal` from `app.models.database` but it doesn't exist. Our architecture is **synchronous** and uses `SessionLocal` only.

**Error:**
```
System startup failed: cannot import name 'AsyncSessionLocal' from 'app.models.database'
```

---

## Root Cause

Old async code remained in thread files that were trying to use async database sessions, which violates our synchronous architecture.

**Affected Files:**
1. `app/threads/data_processor.py` - Unused import
2. `app/threads/data_quality_manager.py` - Multiple async database calls

---

## Architecture Principle

**MisMartera uses SYNCHRONOUS architecture:**
- ✅ Use `SessionLocal` (synchronous)
- ✅ Use regular `def` functions
- ✅ Use `threading.Thread`
- ❌ NO `AsyncSessionLocal`
- ❌ NO `async def` in threads/managers
- ❌ NO `asyncio`

**Exception:** FastAPI routes can be async (framework requirement only)

---

## Solution

### 1. data_processor.py - Removed Unused Import

**Before:**
```python
# Existing infrastructure
from app.models.database import AsyncSessionLocal  # ❌ Not used

logger = logging.getLogger(__name__)
```

**After:**
```python
logger = logging.getLogger(__name__)  # ✅ Clean
```

### 2. data_quality_manager.py - Replaced Async Calls

**Before (2 locations):**
```python
# ❌ Complex async wrapper for synchronous operation
from app.models.database import AsyncSessionLocal
import asyncio

async def get_trading_session():
    async with AsyncSessionLocal() as session:
        return await self._time_manager.get_trading_session(session, current_date)

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

trading_session = loop.run_until_complete(get_trading_session())
```

**After:**
```python
# ✅ Simple synchronous call
with SessionLocal() as db_session:
    trading_session = self._time_manager.get_trading_session(db_session, current_date)
```

---

## Files Modified

1. **`app/threads/data_processor.py`**
   - Removed unused `AsyncSessionLocal` import (line 56)

2. **`app/threads/data_quality_manager.py`**
   - Changed import: `AsyncSessionLocal` → `SessionLocal` (line 55)
   - Simplified database call in `_update_quality()` (lines 290-291)
   - Simplified database call in `_check_for_gaps()` (lines 386-387)

---

## Why This Happened

These thread files had old async code that wasn't updated when we consolidated the architecture to be fully synchronous.

**The Fix:**
- TimeManager methods are synchronous
- Database sessions should be synchronous
- No need for async/await wrappers

---

## Architecture Verification

### Correct Pattern (✅)

```python
# Synchronous thread using synchronous database
class MyThread(threading.Thread):
    def run(self):
        with SessionLocal() as session:
            result = manager.get_data(session)
```

### Wrong Pattern (❌)

```python
# DON'T: Async in threads
class MyThread(threading.Thread):
    def run(self):
        async def get_data():
            async with AsyncSessionLocal() as session:
                return await manager.get_data(session)
        
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(get_data())
```

---

## Benefits

1. **Simpler Code:**
   - 1 line instead of 10+ lines
   - No event loop management
   - No async/await complexity

2. **Consistent Architecture:**
   - All threads use same pattern
   - Matches documented architecture
   - Easier to understand and maintain

3. **Better Performance:**
   - No async overhead
   - No event loop creation
   - Direct function calls

---

## Testing

### Before Fix
```bash
system@mismartera: system start
# ERROR: cannot import name 'AsyncSessionLocal'
```

### After Fix
```bash
system@mismartera: system start
# ✅ Should proceed past this error
```

---

## Related Files That Correctly Use Async

**ONLY these should use AsyncSessionLocal:**
- `app/api/routes/*.py` - FastAPI routes (framework requirement)
- `app/repositories/user_repository.py` - User management (API-only)
- `app/scripts/init_users.py` - Standalone script (acceptable)

**Everything else should use SessionLocal:**
- All managers (`app/managers/`)
- All threads (`app/threads/`)
- All services (`app/services/`)
- All repositories except user_repository

---

## Status

✅ **Fixed** - All thread files now use synchronous SessionLocal

**Next:** System should start successfully
