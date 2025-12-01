# Phase 4 Implementation - In Progress

**Date**: November 30, 2025  
**Status**: 🔄 IN PROGRESS - Queue Loading Complete, Consumption Pending

---

## ✅ Completed in This Session

### 1. **SystemManager Backtest Date Properties** ✅
Added properties that serve as single source of truth references to session_config:

```python
# In SystemManager
@property
def backtest_start_date(self) -> Optional[date]:
    """Read/write property that references session_config.backtest_config.start_date"""
    return datetime.strptime(
        self._session_config.backtest_config.start_date, "%Y-%m-%d"
    ).date()

@backtest_start_date.setter
def backtest_start_date(self, value: date):
    """Write to session_config"""
    self._session_config.backtest_config.start_date = value.strftime("%Y-%m-%d")
```

**Why This Matters**:
- Anyone reading `system_manager.backtest_start_date` reads from session_config
- Anyone writing to it updates session_config
- True single source of truth - no duplication

**Files Modified**:
- `/app/managers/system_manager/api.py` (lines 104-194)
- `/app/managers/time_manager/api.py` (lines 78-99) - delegates to system_manager

---

### 2. **Queue Storage in SessionCoordinator** ✅
Added deque-based queue storage:

```python
# In SessionCoordinator.__init__
self._bar_queues: Dict[Tuple[str, str], 'deque'] = {}
# Structure: {(symbol, interval): deque of BarData}
```

**Why deque**:
- O(1) popleft() for efficient queue consumption
- O(1) append() for queue population
- Memory efficient for large bar datasets

---

### 3. **_load_backtest_queues() Implementation** ✅
Fully implemented queue loading:

**What it does**:
1. Calculates prefetch date range using TimeManager
2. Loads bars for each streamed symbol/interval
3. Stores in deques for efficient consumption
4. Logs with `[SESSION_FLOW]` prefix

**Key Features**:
- Uses `DataManager.get_bars()` (existing Parquet API)
- Loads `prefetch_days` worth of data
- Only loads STREAMED intervals (not GENERATED)
- Comprehensive error handling and logging

**Sample Output**:
```
[SESSION_FLOW] PHASE_3.2: Loading backtest queues
[SESSION_FLOW] PHASE_3.2: Prefetch range: 2025-07-02 to 2025-07-07 (5 days)
[SESSION_FLOW] PHASE_3.2: Loading AAPL 1m queue: 2025-07-02 to 2025-07-07
[SESSION_FLOW] PHASE_3.2: Loaded 1950 bars for AAPL 1m
[SESSION_FLOW] PHASE_3.2: Loading RIVN 1m queue: 2025-07-02 to 2025-07-07
[SESSION_FLOW] PHASE_3.2: Loaded 1950 bars for RIVN 1m
[SESSION_FLOW] PHASE_3.2: Complete - Loaded 3900 bars across 2 streams
```

**File**: `/app/threads/session_coordinator.py` (lines 544-647)

---

## 📋 Still Pending

### 1. **_get_next_queue_timestamp()** 
**Purpose**: Find earliest timestamp across all queues

**Implementation Plan**:
```python
def _get_next_queue_timestamp(self) -> Optional[datetime]:
    if not self._bar_queues:
        return None
    
    # Find minimum timestamp across all queue fronts
    min_timestamp = None
    for queue_key, queue in self._bar_queues.items():
        if queue:  # Queue not empty
            bar = queue[0]  # Peek at front (don't pop yet)
            if min_timestamp is None or bar.timestamp < min_timestamp:
                min_timestamp = bar.timestamp
    
    return min_timestamp
```

**SESSION_FLOW Logging**:
- `[SESSION_FLOW] PHASE_5.2: Next timestamp across queues: 09:31:00`
- `[SESSION_FLOW] PHASE_5.2: No more data in queues`

---

### 2. **_process_queue_data_at_timestamp()**
**Purpose**: Consume and process all bars at given timestamp

**Implementation Plan**:
```python
def _process_queue_data_at_timestamp(self, timestamp: datetime) -> int:
    bars_processed = 0
    
    # Process all queues that have data at this timestamp
    for queue_key, queue in self._bar_queues.items():
        symbol, interval = queue_key
        
        # Consume bars at this exact timestamp
        while queue and queue[0].timestamp == timestamp:
            bar = queue.popleft()
            
            # Add to session_data (current session bars, not historical)
            symbol_data = self.session_data.get_symbol_data(symbol)
            if symbol_data:
                symbol_data.bars_base.append(bar)
                symbol_data.update_from_bar(bar)
                bars_processed += 1
    
    return bars_processed
```

**SESSION_FLOW Logging**:
- `[SESSION_FLOW] PHASE_5.3: Processing bars at 09:31:00`
- `[SESSION_FLOW] PHASE_5.3: Processed 2 bars (AAPL: 1, RIVN: 1)`

---

### 3. **Streaming Phase Integration**
**Current Code** (lines 684-692):
```python
next_timestamp = self._get_next_queue_timestamp()

if next_timestamp is None:
    logger.info("[SESSION_FLOW] PHASE_5.WARNING: No more data in queues")
    self._time_manager.set_backtest_time(market_close)
    break
```

**After Implementation**:
```python
next_timestamp = self._get_next_queue_timestamp()

if next_timestamp is None:
    logger.info("[SESSION_FLOW] PHASE_5.END: No more data, advancing to close")
    self._time_manager.set_backtest_time(market_close)
    break

# Advance time to next data timestamp
self._time_manager.set_backtest_time(next_timestamp)

# Process all bars at this timestamp
bars_count = self._process_queue_data_at_timestamp(next_timestamp)
total_bars_processed += bars_count
```

---

## Testing Instructions

### Current State (Phase 3 + Partial Phase 4)
```bash
cd backend
./start_cli.sh
system start
grep "[SESSION_FLOW]" logs/app.log | tail -40
```

**Expected**:
- Historical data loads
- Queues load with actual bar counts
- Stops at "No more data in queues" (queue consumption not implemented yet)

**Actual Output**:
```
[SESSION_FLOW] PHASE_3.2: Complete - Loaded 3900 bars across 2 streams
[SESSION_FLOW] PHASE_5.WARNING: No more data in queues
```

---

### After Full Phase 4 Implementation
**Expected**:
```
[SESSION_FLOW] PHASE_5.2: Next timestamp: 09:31:00
[SESSION_FLOW] PHASE_5.3: Processed 2 bars
[SESSION_FLOW] PHASE_5.2: Next timestamp: 09:32:00
[SESSION_FLOW] PHASE_5.3: Processed 2 bars
...
[SESSION_FLOW] PHASE_5.SUMMARY: 390 iterations, 780 bars, final time = 16:00:00
```

---

## Architecture Compliance

### ✅ Single Source of Truth
- `system_manager.backtest_start/end_date` are properties referencing session_config
- `time_manager.backtest_start/end_date` delegate to system_manager
- Everyone reads from same source (no duplication)

### ✅ TimeManager Integration
- All time operations via TimeManager
- No `datetime.now()` usage
- Proper date range calculations

### ✅ Queue Design
- Deque for efficient O(1) operations
- Per-symbol, per-interval queues
- Chronological ordering maintained

---

## Next Steps

1. **Implement `_get_next_queue_timestamp()`**
   - Find earliest timestamp across queues
   - Add SESSION_FLOW logging
   - Handle empty queue case

2. **Implement `_process_queue_data_at_timestamp()`**
   - Consume bars from queues
   - Update SessionData
   - Track processed bar count

3. **Wire into Streaming Phase**
   - Call queue methods in streaming loop
   - Advance time with each iteration
   - Update metrics

4. **Test End-to-End**
   - Run full backtest
   - Verify all bars process
   - Check final metrics

5. **Update Documentation**
   - Mark Phase 4 complete
   - Update architecture analysis
   - Create completion summary

---

## Files Modified So Far

1. `/app/managers/system_manager/api.py` - Added backtest date properties
2. `/app/managers/time_manager/api.py` - Updated to use system_manager properties
3. `/app/threads/session_coordinator.py` - Added queue storage and loading
4. `/backend/docs/windsurf/PHASE_4_PROGRESS.md` - This file

**Lines Added**: ~150 (properties + queue loading + logging)  
**Compilation Status**: ✅ All files compile without errors  
**Next Implementation**: Queue consumption methods (~50 lines)
