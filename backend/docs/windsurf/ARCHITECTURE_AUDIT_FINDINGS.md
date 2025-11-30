# Architecture Audit - Obsolete Files Check

**Date:** 2025-11-29  
**Status:** REVIEW REQUIRED

---

## Summary

Audit of remaining files after session architecture cleanup found **1 major duplication** and **1 potentially obsolete manager**.

---

## Findings

### 1. ⚠️ SessionData Duplication (HIGH PRIORITY)

**Issue:** TWO SessionData implementations exist

#### Location 1: `app/core/session_data.py`
**Status:** ✅ ACTIVE - Used by new architecture
**Used By:**
- app/threads/session_coordinator.py
- app/threads/data_processor.py
- app/threads/data_quality_manager.py
- app/threads/analysis_engine.py
- app/managers/system_manager/api.py

**Structure:** Simple, clean SessionData class for Phase 1 architecture

#### Location 2: `app/managers/data_manager/session_data.py`
**Status:** ⚠️ ACTIVE BUT OBSOLETE - Used by old code
**Used By:**
- app/managers/data_manager/backtest_stream_coordinator.py
- app/managers/data_manager/api.py
- app/cli/session_data_display.py
- app/cli/system_status_impl.py

**Structure:** Complex, legacy SessionData with get_session_data() singleton

**Impact:**
- Confusing duplication
- Two sources of truth
- Potential inconsistencies
- More code to maintain

**Recommendation:**
- Migrate remaining usage to app/core/session_data.py
- Delete app/managers/data_manager/session_data.py
- Update all imports
- **Complexity:** HIGH (widely used in CLI and stream coordinator)

---

### 2. ⚠️ AnalysisEngine Manager (MEDIUM PRIORITY)

**Issue:** AnalysisEngine exists as BOTH a manager AND a thread

#### Location 1: `app/threads/analysis_engine.py`
**Status:** ✅ ACTIVE - Used by SystemManager
**Purpose:** Strategy execution thread (Phase 4)
**Created by:** SystemManager in 4-thread pool

#### Location 2: `app/managers/analysis_engine/`
**Status:** ❌ POTENTIALLY OBSOLETE
**Contents:**
- api.py (12KB)
- technical_indicators.py (12KB)
- integrations/
- repositories/

**Used By:**
- app/managers/__init__.py (imported but not used elsewhere)
- NO OTHER IMPORTS FOUND

**Recommendation:**
- Verify if technical_indicators.py is still needed
- If indicators are needed, move to threads/analysis_engine/
- Delete obsolete manager directory
- **Complexity:** MEDIUM (may contain useful indicator code)

---

## Files Confirmed ACTIVE (Keep)

### Data Manager (All Active)
✅ `api.py` - DataManager main class  
✅ `backtest_stream_coordinator.py` - Low-level stream coordination  
✅ `config.py` - Configuration  
✅ `derived_bars.py` - Bar computation (used by DataProcessor)  
✅ `gap_detection.py` - Gap analysis (used by DataQualityManager)  
✅ `parquet_storage.py` - Persistent storage  
✅ `symbol_exchange_mapping.py` - Utilities  
✅ `integrations/` - Data sources  
✅ `repositories/` - DB access  

### Threads (All Active)
✅ `session_coordinator.py` - High-level orchestrator  
✅ `data_processor.py` - Derived bars + indicators  
✅ `data_quality_manager.py` - Quality + gap filling  
✅ `analysis_engine.py` - Strategy execution  
✅ `sync/` - Thread synchronization  
✅ `quality/` - Quality utilities  

### Managers (All Active)
✅ `system_manager/` - Main orchestrator  
✅ `time_manager/` - All time operations  
✅ `data_manager/` - Data streaming  
✅ `execution_manager/` - Order execution  

---

## Files Already Deleted (Previous Cleanup)

✅ data_upkeep_thread.py (55KB) - Replaced by DataQualityManager  
✅ session_boundary_manager.py (15KB) - Replaced by SessionCoordinator  
✅ session_detector.py (9KB) - Replaced by SessionCoordinator  
✅ session_state.py (5KB) - Replaced by SystemState enum  
✅ quality_checker.py (9KB) - Replaced by DataQualityManager  
✅ prefetch_manager.py (16KB) - Not used  
✅ prefetch_worker.py (8KB) - Not used  
✅ production_config.py (9KB) - Not used  

**Total Deleted:** 126KB across 8 files

---

## Recommended Actions

### Priority 1: SessionData Migration
**Action:** Migrate all usage to app/core/session_data.py

**Files to Update:**
1. app/managers/data_manager/backtest_stream_coordinator.py
2. app/managers/data_manager/api.py
3. app/cli/session_data_display.py
4. app/cli/system_status_impl.py

**Steps:**
1. Analyze differences between two SessionData classes
2. Ensure app/core version has all needed functionality
3. Update imports one file at a time
4. Test thoroughly (especially CLI commands)
5. Delete app/managers/data_manager/session_data.py

**Complexity:** HIGH  
**Risk:** MEDIUM (CLI extensively uses session_data)  
**Benefit:** Eliminates major duplication

---

### Priority 2: AnalysisEngine Manager Review
**Action:** Review and potentially remove obsolete manager

**Files to Check:**
1. app/managers/analysis_engine/technical_indicators.py
   - Contains: Indicator calculation functions
   - May be needed by thread version
   - Should move to threads/ if still needed

2. app/managers/analysis_engine/api.py
   - Check if any code is referenced
   - Likely obsolete

**Steps:**
1. Review technical_indicators.py for useful code
2. Move needed indicators to app/threads/analysis_engine/
3. Delete app/managers/analysis_engine/ directory
4. Update app/managers/__init__.py

**Complexity:** MEDIUM  
**Risk:** LOW (not actively used)  
**Benefit:** Cleaner architecture, less confusion

---

## Architecture Clarity After Cleanup

### Clear Separation
```
app/
├── core/
│   └── session_data.py         # ✅ Single SessionData
├── threads/
│   ├── session_coordinator.py  # High-level orchestrator
│   ├── data_processor.py       # Derived bars
│   ├── data_quality_manager.py # Quality
│   └── analysis_engine.py      # ✅ Single AnalysisEngine
└── managers/
    ├── system_manager/         # Main orchestrator
    ├── time_manager/           # All time ops
    ├── data_manager/           # Data streaming
    │   ├── api.py
    │   ├── backtest_stream_coordinator.py
    │   └── (no session_data.py) # ✅ Removed
    └── execution_manager/      # Orders
        (no analysis_engine/)   # ✅ Removed
```

---

## Impact Summary

### Current State
- ❌ SessionData exists in 2 places (confusion)
- ❌ AnalysisEngine exists in 2 places (confusion)
- ✅ 8 obsolete files already removed (126KB)

### After Full Cleanup
- ✅ Single SessionData in app/core/
- ✅ Single AnalysisEngine in app/threads/
- ✅ Clear architecture boundaries
- ✅ ~50KB more code removed
- ✅ Less maintenance burden

---

## Testing Requirements

After cleanup:
1. ✅ System startup works
2. ✅ Backtest runs without errors
3. ✅ CLI commands work (especially `data session`, `system status`)
4. ✅ All threads communicate properly
5. ✅ SessionData accessed correctly

---

## Status

**Current:** 2 issues identified  
**Priority 1:** SessionData duplication (HIGH)  
**Priority 2:** AnalysisEngine manager (MEDIUM)  
**Complexity:** HIGH for P1, MEDIUM for P2  
**Estimated Effort:** 2-3 hours for full cleanup

---

## Notes

- BacktestStreamCoordinator is NOT obsolete (low-level stream coordination)
- SessionCoordinator is NOT a replacement for BacktestStreamCoordinator
- Both serve different purposes in the architecture
- No backup files (.bak) found
- No other obsolete files detected

---

**Recommendation:** Defer SessionData migration to a dedicated session after current startup issues are resolved. Tag as technical debt.
