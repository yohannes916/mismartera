# Start/Stop Refactoring - Clean State Guarantee

## Summary

Refactored `system_manager.start()` to always call `stop()` first, ensuring clean state and eliminating duplicate stream stopping logic.

## Changes Made

### 1. `start()` Now Calls `stop()` First

**Before:**
```python
async def start(config_file_path: str):
    # Check current state
    if self._state == SystemState.RUNNING:
        logger.warning("System already running")
        return False
    
    if self._state == SystemState.PAUSED:
        logger.warning("System is paused. Use resume() to continue.")
        return False
    
    # ... continue with start
    
    # STOP ALL EXISTING STREAMS (duplicate logic!)
    logger.info("Stopping all existing streams...")
    await data_manager.stop_all_streams()
    logger.success("✓ All existing streams stopped")
```

**After:**
```python
async def start(config_file_path: str):
    # Stop system first to ensure clean state
    if self._state != SystemState.STOPPED:
        logger.info(f"System in {self._state.value} state, stopping first...")
        await self.stop()
    
    # ... continue with start
    
    # No more duplicate stream stopping - handled by stop()!
```

### 2. Made `stop()` Idempotent

**Before:**
```python
async def stop(self) -> bool:
    if self._state == SystemState.STOPPED:
        logger.warning("System already stopped")
        return False  # ❌ Treated as error
    
    # ... stop logic
```

**After:**
```python
async def stop(self) -> bool:
    if self._state == SystemState.STOPPED:
        logger.debug("System already stopped")
        return True  # ✅ Idempotent - already in desired state
    
    # ... stop logic
```

## Benefits

### 1. Clean State Guarantee ✅

**Before:** Could have lingering state from previous runs
```python
# User runs: system start
# System: RUNNING
# User runs: system start (again)
# System: Returns "already running", but doesn't clean up
# Streams might be in inconsistent state
```

**After:** Always starts from clean state
```python
# User runs: system start
# System: RUNNING
# User runs: system start (again)
# System: Stops first, cleans everything, then starts fresh ✓
```

### 2. No Duplicate Logic ✅

**Before:** Stream stopping in TWO places
- `stop()` - stops all streams
- `start()` - ALSO stops all streams (duplicate!)

**After:** Stream stopping in ONE place
- `stop()` - stops all streams (single source of truth)
- `start()` - calls `stop()` (reuses existing logic)

### 3. Handles All States ✅

**Before:** Special cases for RUNNING and PAUSED
```python
if self._state == SystemState.RUNNING:
    return False  # Can't start when running
if self._state == SystemState.PAUSED:
    return False  # Can't start when paused
```

**After:** Unified handling via `stop()`
```python
if self._state != SystemState.STOPPED:
    await self.stop()  # Handles RUNNING, PAUSED, or any state
```

### 4. Idempotent Operations ✅

Both `start()` and `stop()` are now idempotent:

```python
# Can safely call multiple times
await system_manager.stop()
await system_manager.stop()  # Returns True, no error
await system_manager.stop()  # Returns True, no error

await system_manager.start(config)
await system_manager.start(config)  # Stops first, then starts
await system_manager.start(config)  # Stops first, then starts
```

## State Transition Flow

### Old Flow (Before)

```
State: RUNNING
↓
User: system start
↓
Check: state == RUNNING?
↓
Result: ❌ "System already running" (error, returns False)
```

```
State: PAUSED
↓
User: system start
↓
Check: state == PAUSED?
↓
Result: ❌ "System is paused" (error, returns False)
```

### New Flow (After)

```
State: RUNNING
↓
User: system start
↓
Check: state != STOPPED?
↓
Call: await self.stop()
  → Stop all streams
  → Clear session config
  → State = STOPPED
↓
Continue: Load new config, start streams
↓
Result: ✅ System restarted cleanly
```

```
State: PAUSED
↓
User: system start
↓
Check: state != STOPPED?
↓
Call: await self.stop()
  → Stop all streams
  → Clear session config
  → State = STOPPED
↓
Continue: Load new config, start streams
↓
Result: ✅ System started cleanly
```

```
State: STOPPED
↓
User: system start
↓
Check: state != STOPPED? → No
↓
Skip: stop() not called (already stopped)
↓
Continue: Load config, start streams
↓
Result: ✅ System started
```

## Code Changes Detail

### system_manager.py

**Lines 249-254 (NEW):**
```python
# Stop system first to ensure clean state
# This handles RUNNING, PAUSED, or already STOPPED states
if self._state != SystemState.STOPPED:
    logger.info(f"System in {self._state.value} state, stopping first...")
    await self.stop()
```

**Lines 325-328 (REMOVED):**
```python
# REMOVED - No longer needed!
# STOP ALL EXISTING STREAMS
# logger.info("Stopping all existing streams...")
# await data_manager.stop_all_streams()
# logger.success("✓ All existing streams stopped")
```

**Lines 525-527 (MODIFIED):**
```python
if self._state == SystemState.STOPPED:
    logger.debug("System already stopped")  # Changed from warning to debug
    return True  # Changed from False to True (idempotent)
```

## User Experience Impact

### Before (Confusing)

```bash
system@mismartera: system start config.json
✓ System started

system@mismartera: system start config.json
⚠ System already running  # Error! User confused

system@mismartera: system stop
✓ System stopped

system@mismartera: system start config.json
✓ System started
```

### After (Intuitive)

```bash
system@mismartera: system start config.json
✓ System started

system@mismartera: system start config.json
ℹ System in RUNNING state, stopping first...
✓ All data streams stopped
✓ System stopped
✓ System started  # Cleanly restarted!

system@mismartera: system start config.json
ℹ System in RUNNING state, stopping first...
✓ All data streams stopped
✓ System stopped
✓ System started  # Can keep restarting!
```

## Testing Scenarios

### Scenario 1: Start from STOPPED
```python
# State: STOPPED
result = await system_manager.start("config.json")
# Expected: Starts normally
# State: RUNNING
```

### Scenario 2: Start from RUNNING
```python
# State: RUNNING
result = await system_manager.start("config.json")
# Expected: Stops first, then starts
# Logs: "System in RUNNING state, stopping first..."
# State: RUNNING (restarted)
```

### Scenario 3: Start from PAUSED
```python
# State: PAUSED
result = await system_manager.start("config.json")
# Expected: Stops first, then starts
# Logs: "System in PAUSED state, stopping first..."
# State: RUNNING
```

### Scenario 4: Multiple Stops
```python
# State: RUNNING
await system_manager.stop()  # Returns True
await system_manager.stop()  # Returns True (idempotent)
await system_manager.stop()  # Returns True (idempotent)
# State: STOPPED
```

### Scenario 5: Multiple Starts
```python
# State: STOPPED
await system_manager.start("config.json")  # Fresh start
await system_manager.start("config.json")  # Stops first, restarts
await system_manager.start("config.json")  # Stops first, restarts
# State: RUNNING (last config)
```

## Error Handling

### Clean Shutdown on Start Failure

```python
try:
    # ... start logic
    self._state = SystemState.RUNNING
except Exception as e:
    logger.error(f"System startup failed: {e}")
    self._state = SystemState.STOPPED  # Ensure STOPPED on failure
    raise
```

**Behavior:**
- If start fails at any point, system transitions to STOPPED
- Next `start()` attempt will be from clean STOPPED state
- No lingering RUNNING or PAUSED state on failure

## Summary

✅ **Always calls stop() first** - Ensures clean state
✅ **Idempotent operations** - Safe to call multiple times
✅ **No duplicate logic** - Stream stopping in one place
✅ **Better UX** - Can restart without explicit stop
✅ **Handles all states** - RUNNING, PAUSED, STOPPED
✅ **Cleaner code** - Less duplication, clearer intent

**Result:** Robust, user-friendly start/stop semantics! 🎯
