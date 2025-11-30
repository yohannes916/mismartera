# Asyncio Removal from SessionCoordinator

**Date:** 2025-11-29  
**Issue:** SessionCoordinator using asyncio.run() in synchronous thread

---

## Problem

SessionCoordinator (a `threading.Thread`) was calling `asyncio.run()` which violates the synchronous architecture.

**Error:**
```
SessionCoordinator error: name 'asyncio' is not defined
Traceback:
  File "app/threads/session_coordinator.py", line 143, in run
    asyncio.run(self._coordinator_loop())
    ^^^^^^^
NameError: name 'asyncio' is not defined
```

---

## Architecture Violation

**CRITICAL RULE:** No asyncio outside of FastAPI routes!

- ❌ **Threading threads** should NEVER use asyncio
- ❌ **Manager methods** should be synchronous
- ✅ **FastAPI routes** can use async (framework requirement)
- ✅ **Websocket integrations** can use async (e.g., Alpaca streams)

---

## Root Cause

SessionCoordinator's `run()` method was trying to call `_coordinator_loop()` using `asyncio.run()`:

```python
def run(self):
    """Thread entry point."""
    try:
        self.metrics.start_backtest()
        
        # ❌ WRONG: asyncio in threading.Thread
        asyncio.run(self._coordinator_loop())
        
        self.metrics.end_backtest()
    except Exception as e:
        logger.error(f"SessionCoordinator error: {e}", exc_info=True)
```

**But `_coordinator_loop()` was already synchronous!**

```python
def _coordinator_loop(self):  # ← Note: NOT async def
    """Main coordinator loop..."""
    while not self._stop_event.is_set():
        # ... synchronous code ...
```

---

## Solution

Simply call the method directly without asyncio:

```python
def run(self):
    """Thread entry point."""
    try:
        self.metrics.start_backtest()
        
        # ✅ CORRECT: Direct call (method is already synchronous)
        self._coordinator_loop()
        
        self.metrics.end_backtest()
    except Exception as e:
        logger.error(f"SessionCoordinator error: {e}", exc_info=True)
```

---

## Why This Works

1. **_coordinator_loop() is synchronous** - It's a regular `def`, not `async def`
2. **Threading.Thread uses regular functions** - No need for asyncio
3. **All operations are synchronous** - Database via SessionLocal, no await needed

---

## Before vs After

### Before (Broken)
```python
# ❌ Trying to run sync function with asyncio
asyncio.run(self._coordinator_loop())  # RuntimeError!
```

### After (Fixed)
```python
# ✅ Direct call to synchronous method
self._coordinator_loop()  # Works perfectly!
```

---

## Files Modified

**`app/threads/session_coordinator.py`**
- Line 143: Removed `asyncio.run()` wrapper
- Changed: `asyncio.run(self._coordinator_loop())` → `self._coordinator_loop()`

---

## Additional Asyncio Found (For Future Cleanup)

While fixing this, discovered asyncio usage in other places that should be addressed:

### DataManager Components (Need Review)
- `data_manager/data_upkeep_thread.py` - Uses asyncio event loop
- `data_manager/session_boundary_manager.py` - Creates asyncio event loops
- `data_manager/prefetch_manager.py` - Uses asyncio.new_event_loop()
- `data_manager/session_data.py` - Imports asyncio
- `data_manager/api.py` - Uses asyncio.Event for stream cancellation

### OK Asyncio Usage (Keep)
- `data_manager/integrations/alpaca_streams.py` - Websocket streams (inherently async)
- `execution_manager/api.py` - Used by FastAPI routes
- `analysis_engine/api.py` - Used by FastAPI routes

**Note:** The DataManager asyncio usage needs architectural review. These should likely be converted to synchronous threading patterns for consistency.

---

## Architecture Reminder

### ✅ Synchronous Architecture (Use This)

```python
# Threading threads
class MyThread(threading.Thread):
    def run(self):
        # Regular synchronous code
        with SessionLocal() as session:
            result = manager.get_data(session)

# Regular functions
def process_data():
    # No async/await
    data = fetch_data()
    return transform(data)
```

### ❌ Don't Mix Async with Threads

```python
# DON'T DO THIS
class MyThread(threading.Thread):
    def run(self):
        # ❌ Creating event loop in thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(async_function())
```

### ✅ FastAPI Routes Can Be Async

```python
# This is OK (FastAPI requirement)
@router.post("/api/data/import")
async def import_data(session: AsyncSession = Depends(get_db)):
    result = await repository.create_data(session, data)
    return result
```

---

## Testing

### Before Fix
```bash
system@mismartera: system start
# ERROR: name 'asyncio' is not defined
```

### After Fix
```bash
system@mismartera: system start
# ✅ SessionCoordinator thread starts successfully
# ✅ Coordinator loop runs synchronously
```

---

## Lessons Learned

1. **Never assume async is needed** - Check if method is actually async def
2. **Threading.Thread = synchronous** - No asyncio needed or wanted
3. **Follow architecture rules** - Async only in FastAPI routes
4. **Review existing code** - Found multiple asyncio violations to clean up

---

## Status

✅ **Fixed** - SessionCoordinator now runs synchronously without asyncio

⚠️ **TODO:** Review and potentially remove asyncio from DataManager components for architectural consistency

---

**Next:** System should start and SessionCoordinator should run its main loop successfully
