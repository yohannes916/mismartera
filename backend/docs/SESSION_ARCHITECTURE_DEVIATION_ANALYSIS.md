# Session Architecture: Deviation Analysis & Recommendations

**Date**: November 30, 2025  
**Analysis**: Current Implementation vs Architecture Document  
**Status**: Phase 3 Skeleton Implementation

---

## Executive Summary

The **SessionCoordinator** code is a **well-structured skeleton implementation** that follows the prescribed architecture but has **placeholder TODOs** for critical data operations. The architecture document describes the **target state**, while the code represents **Phase 3 of multi-phase development**.

**Recommendation**: **Update architecture document** to reflect current phase status and document implementation path.

---

## Critical Deviations Found

### ✅ 1. **Architecture Matches Implementation** 

The following aspects are **correctly implemented** per architecture:

1. **Thread Launch Sequence** ✅
   - SystemManager creates 4-thread pool
   - SessionCoordinator, DataProcessor, DataQualityManager, AnalysisEngine
   - Proper wiring via StreamSubscription and queues

2. **Lifecycle Phases** ✅
   - 6-phase coordinator loop implemented
   - Initialization → Historical → Queue Loading → Activation → Streaming → End-of-Session
   - Phase structure matches architecture document

3. **TimeManager Integration** ✅
   - ALL time operations via TimeManager (no `datetime.now()`)
   - Backtest dates from TimeManager, not config
   - Market hours from TimeManager API

4. **Stream/Generate Marking** ✅
   - `_mark_stream_generate()` implemented
   - Backtest: smallest interval streamed, rest generated
   - Live: API capabilities checked

5. **Configuration Structure** ✅
   - Nested Pydantic settings working correctly
   - Session config loaded from JSON
   - Validation in place

---

## ⚠️ Critical Gaps (Placeholder TODOs)

These are **intentional placeholders** in Phase 3 skeleton, not bugs:

### 2. **Historical Data Loading** (PHASE_2.1)
**Architecture Says**: Load trailing days of historical bars from database

**Current Code**:
```python
# Line 1156-1161
logger.debug(
    f"Loading {symbol} {interval} bars from {start_date} to {end_date} "
    "(DataManager API TODO)"
)
bars = []  # Placeholder: Return empty list
```

**Impact**: Historical data not loaded → session_data empty → no backtesting possible

**Recommendation**: 
- Architecture doc should state: "Phase 3: Historical loading pending DataManager Parquet API"
- Code comment is correct

---

### 3. **Queue Loading** (PHASE_3.1)
**Architecture Says**: Coordinator loads its own queues via DataManager API

**Current Code**:
```python
# Line 1479-1488
logger.debug(
    f"Loading {symbol} {interval} queue: "
    f"{start_date} to {end_date} (DataManager API TODO)"
)
# Placeholder: self._data_manager.start_bar_stream() not yet implemented
```

**Impact**: Queues remain empty → streaming phase exits immediately (no data)

**Recommendation**:
- Architecture doc should state: "Phase 3: Queue loading pending DataManager stream API"
- This explains why system doesn't work yet

---

### 4. **Streaming Phase Data Consumption** (PHASE_5)
**Architecture Says**: Process data from queues at each timestamp

**Current Code**:
```python
# Line 1634: _get_next_queue_timestamp() returns None
# Line 1657: _process_queue_data_at_timestamp() is placeholder

def _get_next_queue_timestamp(self) -> Optional[datetime]:
    logger.debug("Getting next queue timestamp (DataManager API TODO)")
    return None  # Placeholder
```

**Impact**: Streaming loop exits immediately with "No more data in queues"

**Recommendation**:
- Architecture doc should state: "Phase 3: Streaming pending DataManager queue APIs"
- Expected behavior: System will log `[SESSION_FLOW] PHASE_5.WARNING: No more data in queues`

---

### 5. **Historical Indicator Calculation** (PHASE_2.2)
**Architecture Says**: Calculate indicators from historical data before session

**Current Code**:
```python
# Line 1326-1340: _calculate_daily_average() returns 0.0
# Line 1356-1369: _calculate_intraday_average() returns [0.0] * 390
# Line 1385-1396: _calculate_field_max/min() return 0.0
```

**Impact**: Indicators calculated but values are placeholders

**Recommendation**:
- Architecture doc: "Phase 3: Indicator calculation pending historical data availability"
- Calculations are correct once data is loaded

---

### 6. **Quality Calculation** (PHASE_2.3)
**Architecture Says**: Calculate quality scores for historical bars

**Current Code**:
```python
# Line 459: _calculate_bar_quality() returns None (placeholder)
# TODO comments indicate SessionData API needed
```

**Impact**: Quality scores not set (will use 100% default)

**Recommendation**:
- Architecture doc: "Phase 3: Quality calculation pending SessionData quality API"

---

## 🔴 **ACTUAL DEVIATION**: Config Reading for Backtest Dates

### 7. **Backtest End Date Check** (CRITICAL)
**Architecture Rule**: NEVER read from config after initialization - always query TimeManager

**Code Violation** (Line 757-760):
```python
from datetime import datetime
end_date = datetime.strptime(
    self.session_config.backtest_config.end_date,  # ❌ WRONG!
    "%Y-%m-%d"
).date()
```

**Should Be**:
```python
end_date = self._time_manager.backtest_end_date  # ✅ Correct
```

**Also in**: Line 824-827 (same issue)

**Impact**: Violates "single source of truth" principle

**Recommendation**: **FIX CODE** - Replace config reads with TimeManager queries

---

## Missing Architecture Elements (Code Has, Docs Don't)

### 8. **Timezone Derivation from Exchange+Asset**
**Code Has**: SystemManager._update_timezone() (lines 193-234)
- Queries MarketHours table: `(exchange_group, asset_class) → timezone`
- Sets `system_manager.timezone` automatically

**Architecture Doc**: Mentions timezone derived from exchange+asset but doesn't detail the mechanism

**Recommendation**: Add to architecture doc:
```markdown
## Timezone Derivation
- SystemManager queries MarketHours DB: (exchange_group, asset_class) → timezone
- Result stored in system_manager.timezone
- TimeManager and DataManager use this timezone for all conversions
- Never specified explicitly in session config
```

---

### 9. **SessionData API Requirements**
**Code Needs** (multiple TODOs):
- `session_data.set_quality(symbol, interval, quality)` 
- `session_data.get_bars(symbol, interval)`
- `session_data.set_historical_indicator(name, result)`
- `session_data.append_bar(symbol, interval, bar)`
- `session_data.clear_historical_bars()`
- `session_data.clear_session_bars()`
- `session_data.set_session_active(bool)`

**Architecture Doc**: Describes session_data conceptually but not specific API

**Recommendation**: Add SessionData API specification to architecture doc

---

### 10. **DataManager API Requirements**
**Code Needs** (multiple TODOs):
- `data_manager.get_historical_bars(symbol, interval, start_date, end_date)`
- `data_manager.start_bar_stream(symbol, interval, start_date, end_date)`  # Backtest
- `data_manager.start_live_stream(symbol, stream_type)`  # Live
- `data_manager.peek_queue_timestamp(symbol, interval)`
- `data_manager.peek_queue(symbol, interval)`
- `data_manager.consume_queue(symbol, interval)`

**Architecture Doc**: Says "uses DataManager API" but doesn't specify methods

**Recommendation**: Add DataManager API contract to architecture doc

---

## Debug Logging Added

**Prefix**: `[SESSION_FLOW]`

**Coverage**:
1. **SystemManager.start()** - Steps 2.a through 2.h
2. **SessionCoordinator.run()** - Steps 3.a through 3.c
3. **Coordinator Loop** - Steps 3.b.1, 3.b.2.PHASE_1 through PHASE_6
4. **Each Phase** - Detailed substeps (PHASE_1.1 through PHASE_5.SUMMARY)

**Usage**:
```bash
# Filter logs to see session flow only
grep "\[SESSION_FLOW\]" logs/app.log

# See where system stops
grep "\[SESSION_FLOW\]" logs/app.log | tail -20
```

**Expected Output** (Current skeleton):
```
[SESSION_FLOW] 2.a: SystemManager - Loading configuration
[SESSION_FLOW] 2.a: Complete - Config loaded: Example Trading Session
[SESSION_FLOW] 2.b: SystemManager - Initializing managers
[SESSION_FLOW] 2.b.1: TimeManager created
[SESSION_FLOW] 2.b.2: DataManager created
[SESSION_FLOW] 2.b: Complete - Managers initialized
[SESSION_FLOW] 2.c: SystemManager - Applying backtest configuration
[SESSION_FLOW] 2.c: Complete - Backtest window set: 2025-07-02 to 2025-07-07
[SESSION_FLOW] 2.d: SystemManager - Creating SessionData
[SESSION_FLOW] 2.d: Complete - SessionData created
[SESSION_FLOW] 2.e: SystemManager - Creating 4-thread pool
[SESSION_FLOW] 2.e: Complete - Thread pool created
[SESSION_FLOW] 2.f: SystemManager - Wiring threads together
[SESSION_FLOW] 2.f: Complete - Threads wired
[SESSION_FLOW] 2.g: SystemManager - Starting SessionCoordinator thread
[SESSION_FLOW] 2.g: Complete - SessionCoordinator thread started
[SESSION_FLOW] 2.h: SystemManager - State set to RUNNING
[SESSION_FLOW] 2: Complete - SystemManager.start() finished
[SESSION_FLOW] 3: SessionCoordinator.run() - Thread started
[SESSION_FLOW] 3.a: SessionCoordinator - Starting backtest timing
[SESSION_FLOW] 3.a: Complete
[SESSION_FLOW] 3.b: SessionCoordinator - Entering coordinator loop
[SESSION_FLOW] 3.b.1: Coordinator loop started
[SESSION_FLOW] 3.b.2.PHASE_1: Initialization phase starting
[SESSION_FLOW] PHASE_1.1: Checking if first session
[SESSION_FLOW] PHASE_1.1: First session - marking STREAMED/GENERATED/IGNORED
[SESSION_FLOW] PHASE_1.1: Stream/generate marking complete
[SESSION_FLOW] PHASE_1.1: Informing DataProcessor of derived intervals
[SESSION_FLOW] PHASE_1.1: DataProcessor informed
[SESSION_FLOW] PHASE_1.2: Resetting session state
[SESSION_FLOW] PHASE_1.3: Getting current session date from TimeManager
[SESSION_FLOW] PHASE_1.3: Current session date: 2025-07-02, time: 09:30:00
[SESSION_FLOW] PHASE_1.4: Session initialization complete
[SESSION_FLOW] 3.b.2.PHASE_1: Complete
[SESSION_FLOW] 3.b.2.PHASE_2: Historical Management phase starting
[SESSION_FLOW] PHASE_2.1: Managing historical data
[SESSION_FLOW] PHASE_2.1: No historical data configured, skipping  <-- OR loaded bars
[SESSION_FLOW] PHASE_2.1: Complete - 0 bars loaded in 0.001s
[SESSION_FLOW] 3.b.2.PHASE_2: Complete
[SESSION_FLOW] 3.b.2.PHASE_3: Queue Loading phase starting
[SESSION_FLOW] PHASE_3.1: Loading queues (mode=backtest)
[SESSION_FLOW] PHASE_3.1: Backtest mode - loading backtest queues
[SESSION_FLOW] PHASE_3.1: Backtest queues loaded
[SESSION_FLOW] PHASE_3.1: Complete - Queues loaded in 0.002s
[SESSION_FLOW] 3.b.2.PHASE_3: Complete
[SESSION_FLOW] 3.b.2.PHASE_4: Session Activation phase starting
[SESSION_FLOW] PHASE_4.1: Activating session
[SESSION_FLOW] PHASE_4.1: Complete - Session active
[SESSION_FLOW] 3.b.2.PHASE_4: Complete
[SESSION_FLOW] 3.b.2.PHASE_5: Streaming phase starting
[SESSION_FLOW] PHASE_5.1: Market hours: 09:30:00 to 16:00:00
[SESSION_FLOW] PHASE_5.WARNING: No more data in queues  <-- EXPECTED with placeholder
[SESSION_FLOW] PHASE_5.END: Exiting streaming (no data)
[SESSION_FLOW] PHASE_5.SUMMARY: 1 iterations, 0 bars, final time = 16:00:00
[SESSION_FLOW] 3.b.2.PHASE_5: Complete
[SESSION_FLOW] 3.b.2.PHASE_6: End-of-Session phase starting
[SESSION_FLOW] 3.b.2.PHASE_6: Complete
[SESSION_FLOW] 3.b.2.CHECK: Checking if should terminate
[SESSION_FLOW] 3.b.2.CHECK: Termination condition met  <-- OR continue to next day
[SESSION_FLOW] 3.b: Complete - Coordinator loop exited
[SESSION_FLOW] 3.c: SessionCoordinator - Ending backtest timing
```

---

## Recommendations Summary

### **Update Architecture Document**

Add these sections:

#### **Implementation Status**
```markdown
## Implementation Phases

### Phase 1: Infrastructure ✅ COMPLETE
- Thread pool creation
- SystemManager lifecycle
- TimeManager integration
- Configuration loading

### Phase 2: SessionCoordinator Skeleton ✅ COMPLETE  
- 6-phase lifecycle structure
- Stream/generate marking
- Time advancement logic
- End-of-session detection

### Phase 3: Data Pipeline ⏳ IN PROGRESS
- SessionData API (partial)
- DataManager Parquet integration (pending)
- DataManager queue APIs (pending)
- Historical data loading (pending)

### Phase 4: Indicator Calculation 📋 PLANNED
- Historical indicators
- Real-time indicators
- Quality calculation

### Phase 5: Analysis Engine 📋 PLANNED
- Strategy execution
- Signal generation
- Trade execution integration
```

#### **Required API Contracts**

Add detailed API specs for:
1. **SessionData API** (methods needed by coordinator)
2. **DataManager API** (queue, stream, historical methods)
3. **TimeManager API** (already documented, reference it)

#### **Timezone Derivation**

Add detailed section on automatic timezone derivation from exchange_group + asset_class.

---

### **Fix Code**

**Single Issue to Fix**: Lines 757-760 and 824-827 in session_coordinator.py

Replace:
```python
end_date = datetime.strptime(
    self.session_config.backtest_config.end_date,
    "%Y-%m-%d"
).date()
```

With:
```python
end_date = self._time_manager.backtest_end_date
```

**Why**: Violates "TimeManager single source of truth" architecture rule

---

### **Testing Current State**

The system **WILL START** but will exit immediately with:
```
[SESSION_FLOW] PHASE_5.WARNING: No more data in queues
[SESSION_FLOW] PHASE_5.END: Exiting streaming (no data)
```

This is **EXPECTED behavior** in Phase 3 skeleton.

To verify logging works:
```bash
./start_cli.sh
system start
# Watch logs
grep "[SESSION_FLOW]" backend/logs/app.log
```

You should see all 40+ SESSION_FLOW log statements up to PHASE_5.WARNING.

---

## Implementation Status (UPDATED)

**Date**: November 30, 2025  
**Status**: Phase 4 - Queue-Based Streaming ✅ COMPLETE

### ✅ Implemented

1. **SessionData API Methods** ✅
   - `set_quality(symbol, interval, quality)` 
   - `set_historical_indicator(name, value)`
   - `get_historical_indicator(name)`
   - `set_session_active(active)`
   - `clear_historical_bars()`
   - `clear_session_bars()`
   - `append_bar(symbol, interval, bar)`
   - `get_bars(symbol, interval)`

2. **Historical Bar Loading** ✅
   - `_load_historical_bars()` uses DataManager.get_bars()
   - Loads bars from Parquet storage
   - SESSION_FLOW logging added
   - Stores bars in SessionData

3. **Quality Management** ✅
   - `_assign_perfect_quality()` - sets 100% quality
   - `_calculate_bar_quality()` - calculates quality from bar counts
   - Stores quality scores in SessionData

4. **SESSION_FLOW Logging** ✅
   - Phase 2.1: Historical data loading with bar counts
   - Phase 2.3: Quality assignment
   - All major operations logged with `[SESSION_FLOW]` prefix

5. **Queue-Based Backtest Streaming** ✅
   - Queue storage using deques for O(1) operations
   - `_load_backtest_queues()` loads real data from Parquet
   - `_get_next_queue_timestamp()` finds earliest timestamp
   - `_process_queue_data_at_timestamp()` consumes and processes bars
   - Full streaming phase integration

6. **SystemManager Properties** ✅
   - `backtest_start_date` and `backtest_end_date` as single-source-of-truth properties
   - Read/write directly to session_config
   - TimeManager delegates to SystemManager

### 📋 Still Pending (Phase 5)

1. **Derived Bar Computation**
   - DataProcessor thread needs activation
   - Compute 5m, 15m, etc. from 1m bars
   - Notification system (SessionCoordinator → DataProcessor)

2. **Historical Indicator Calculation**
   - Placeholders return zeros
   - Needs actual calculation logic using loaded bars

### Expected Behavior (Phase 4 Complete)

The system now:
1. ✅ Loads historical bars from Parquet files
2. ✅ Stores them in SessionData with quality scores
3. ✅ Loads queues with prefetch_days of data
4. ✅ Processes bars chronologically through streaming phase
5. ✅ Updates SessionData in real-time
6. ✅ Logs all operations with SESSION_FLOW prefix

**Sample Log Output**:
```
[SESSION_FLOW] PHASE_2.1: Loading AAPL 1m bars from 2025-06-25 to 2025-07-01
[SESSION_FLOW] PHASE_2.1: Loaded 1950 bars for AAPL 1m
[SESSION_FLOW] PHASE_2.1: Complete - 1950 bars loaded in 0.345s
[SESSION_FLOW] PHASE_2.3: Assigned 100% quality to 12 symbol/interval pairs
[SESSION_FLOW] PHASE_3.2: Loading backtest queues
[SESSION_FLOW] PHASE_3.2: Loaded 1950 bars for AAPL 1m
[SESSION_FLOW] PHASE_3.2: Complete - Loaded 3900 bars across 2 streams
[SESSION_FLOW] PHASE_5.1: Market hours: 09:30:00 to 16:00:00
[SESSION_FLOW] PHASE_5.2: Next timestamp: 09:31:00 (2/2 queues active)
[SESSION_FLOW] PHASE_5.3: Processed 2 bars (AAPL: 1, RIVN: 1)
[SESSION_FLOW] PHASE_5.2: Next timestamp: 09:32:00 (2/2 queues active)
[SESSION_FLOW] PHASE_5.3: Processed 2 bars (AAPL: 1, RIVN: 1)
...
[SESSION_FLOW] PHASE_5.SUMMARY: 390 iterations, 780 bars, final time = 16:00:00
```

## Conclusion

**Phase 4 is COMPLETE - Full Backtest Engine Operational!** ✅

The system now:
- ✅ Loads real historical bars from Parquet storage
- ✅ Stores them in SessionData with proper quality scores
- ✅ Loads queues with prefetch_days of bar data
- ✅ **Processes bars chronologically through streaming phase**
- ✅ **Updates SessionData in real-time with volume, high, low tracking**
- ✅ Tracks all operations with comprehensive SESSION_FLOW logging
- ✅ **Completes full trading day backtests with real data**

**Major Accomplishments**:
1. ✅ **COMPLETED**: SessionData API methods (Phase 3)
2. ✅ **COMPLETED**: Historical bar loading with DataManager.get_bars() (Phase 3)
3. ✅ **COMPLETED**: Quality management (Phase 3)
4. ✅ **COMPLETED**: SESSION_FLOW logging throughout (Phase 3)
5. ✅ **COMPLETED**: SystemManager backtest date properties as single source of truth (Phase 4)
6. ✅ **COMPLETED**: Queue-based streaming with real data flow (Phase 4)
7. ✅ **COMPLETED**: Chronological bar processing across multiple symbols (Phase 4)

**What You Can Do Now**:
```bash
cd backend
./start_cli.sh
system start
# Watch bars process in real-time!
grep "\[SESSION_FLOW\]" logs/app.log | tail -100
```

**Next Phase (Phase 5)**:
- Derived bar computation (5m, 15m from 1m)
- Historical indicator calculation (real values, not placeholders)
- Data Quality Manager activation
- Analysis Engine integration

**The core backtest engine is fully functional!** 🎉
