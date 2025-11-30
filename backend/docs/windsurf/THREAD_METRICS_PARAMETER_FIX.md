# Thread Metrics Parameter Fix

**Date:** 2025-11-29  
**Issue:** DataProcessor.__init__() missing required 'metrics' argument

---

## Problem

System startup failed because threads were being created without the required `metrics` parameter.

**Error:**
```
System startup failed: DataProcessor.__init__() missing 1 required positional argument: 'metrics'
```

---

## Root Cause

Three threads require a `PerformanceMetrics` instance in their `__init__()` methods, but SystemManager wasn't passing it when creating the threads.

**Affected Threads:**
1. `DataProcessor` - Required `metrics` parameter
2. `DataQualityManager` - Required `metrics` parameter  
3. `AnalysisEngine` - Required `metrics` parameter

**Note:** SessionCoordinator does NOT require metrics.

---

## Solution

SystemManager already has `self._performance_metrics` created during initialization. The fix was to pass it to all three threads that need it.

### Thread Signatures

```python
# DataProcessor
def __init__(
    self,
    session_data: SessionData,
    system_manager,
    session_config: SessionConfig,
    metrics: PerformanceMetrics  # ✅ Required
):

# DataQualityManager  
def __init__(
    self,
    session_data: SessionData,
    system_manager,
    session_config: SessionConfig,
    metrics: PerformanceMetrics,  # ✅ Required
    data_manager=None
):

# AnalysisEngine
def __init__(
    self,
    session_data: SessionData,
    system_manager,
    session_config: SessionConfig,
    metrics: PerformanceMetrics  # ✅ Required
):

# SessionCoordinator (NO metrics needed)
def __init__(
    self,
    system_manager,
    data_manager,
    session_config: SessionConfig,
    mode: str = "backtest"
):
```

---

## Fix Applied

### DataProcessor

**Before:**
```python
self._data_processor = DataProcessor(
    session_data=session_data,
    system_manager=self,
    session_config=self._session_config
    # ❌ Missing metrics!
)
```

**After:**
```python
self._data_processor = DataProcessor(
    session_data=session_data,
    system_manager=self,
    session_config=self._session_config,
    metrics=self._performance_metrics  # ✅ Added
)
```

### DataQualityManager

**Before:**
```python
self._quality_manager = DataQualityManager(
    session_data=session_data,
    system_manager=self,
    session_config=self._session_config,
    data_manager=data_manager
    # ❌ Missing metrics!
)
```

**After:**
```python
self._quality_manager = DataQualityManager(
    session_data=session_data,
    system_manager=self,
    session_config=self._session_config,
    metrics=self._performance_metrics,  # ✅ Added
    data_manager=data_manager
)
```

### AnalysisEngine

**Before:**
```python
self._analysis_engine = AnalysisEngine(
    session_data=session_data,
    system_manager=self,
    session_config=self._session_config
    # ❌ Missing metrics!
)
```

**After:**
```python
self._analysis_engine = AnalysisEngine(
    session_data=session_data,
    system_manager=self,
    session_config=self._session_config,
    metrics=self._performance_metrics  # ✅ Added
)
```

---

## Why Metrics?

The `PerformanceMetrics` object is used by threads to:
- Track processing times
- Measure throughput
- Monitor queue depths
- Collect performance statistics
- Detect bottlenecks

Each thread reports its own metrics to the shared `PerformanceMetrics` instance, which aggregates system-wide performance data.

---

## Files Modified

**`app/managers/system_manager/api.py`**
- Added `metrics=self._performance_metrics` to DataProcessor creation (line 363)
- Added `metrics=self._performance_metrics` to DataQualityManager creation (line 372)
- Added `metrics=self._performance_metrics` to AnalysisEngine creation (line 382)

---

## Testing

### Before Fix
```bash
system@mismartera: system start
# ERROR: DataProcessor.__init__() missing 1 required positional argument: 'metrics'
```

### After Fix
```bash
system@mismartera: system start
# ✅ Should create all threads successfully
```

---

## Why This Happened

The thread __init__ signatures were updated to require metrics, but the SystemManager thread creation code wasn't updated to match.

**Lesson:** When updating function signatures, grep for all callers and update them.

---

## Verification

```python
# SystemManager has metrics available
self._performance_metrics = PerformanceMetrics()  # Line 82

# All threads now receive it
DataProcessor(..., metrics=self._performance_metrics)
DataQualityManager(..., metrics=self._performance_metrics, ...)
AnalysisEngine(..., metrics=self._performance_metrics)
```

---

## Status

✅ **Fixed** - All threads now receive required metrics parameter

**Next:** System should start successfully and create all 4 threads
