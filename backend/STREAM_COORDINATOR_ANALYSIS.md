# Stream Coordinator Architecture Analysis

## Executive Summary

The current implementation has **most of the foundational pieces** in place but needs significant architectural changes to implement the proposed `session_data` singleton and two-thread model. The main gaps are:

1. **Missing session_data singleton** - Need centralized per-symbol data storage
2. **Single thread instead of two** - Need separate main coordinator and data-upkeep threads
3. **No session boundary management** - Need configurable session start/end times
4. **No bar completeness checking** - Need gap detection and filling
5. **No historical bars trailing days** - Need automatic historical data management
6. **No prefetch mechanism** - Need next-session data prefetching for backtesting

---

## Current Architecture

### Components Present

#### 1. **BacktestStreamCoordinator** (`backtest_stream_coordinator.py`)
- ✅ Chronological merging of multiple streams
- ✅ Single worker thread for stream processing
- ✅ Priority queue (min-heap) for timestamp ordering
- ✅ Time advancement via TimeProvider
- ✅ State-aware processing (checks SystemManager.is_running())
- ✅ Thread-safe queue-based communication
- ✅ Backtest speed control

**Current Thread Model:**
```
Single Worker Thread (_merge_worker):
  - Reads from multiple input queues
  - Merges chronologically via heap
  - Advances backtest time
  - Outputs to single queue
```

#### 2. **TimeProvider** (`time_provider.py`)
- ✅ Singleton pattern
- ✅ SystemManager integration
- ✅ Live/backtest mode switching
- ✅ Backtest time state management

#### 3. **SessionTracker** (`session_tracker.py`)
- ✅ Tracks session metrics (volume, high/low)
- ✅ Per-symbol, per-date tracking
- ✅ Thread-safe with asyncio locks
- ✅ Cache management (5-minute TTL)

**Current Session Tracking:**
```python
SessionMetrics:
  - session_volume: int
  - session_high: float
  - session_low: float
  - last_update: datetime
```

#### 4. **DataManager** (`api.py`)
- ✅ SystemManager integration
- ✅ Backtest window management
- ✅ Stream registration/cancellation
- ✅ Time management APIs
- ✅ Database repository integration

#### 5. **SystemManager** (`system_manager.py`)
- ✅ Singleton pattern
- ✅ Operation mode management (live/backtest)
- ✅ System state management (running/paused/stopped)
- ✅ Manager lifecycle coordination

---

## Proposed Architecture

### New Components Required

#### 1. **session_data Singleton**
A global object that holds all market data for the current trading session:

```python
class SessionData:
    """Singleton managing current session market data."""
    
    # Session configuration
    start_time: time  # default: 09:30
    end_time: time    # default: 16:00
    historical_bars_trailing_days: int  # default: 0
    historical_bars_types: List[int]    # default: []
    
    # Session state
    session_ended: bool
    current_session_date: date
    
    # Per-symbol data structures
    symbols: Dict[str, SymbolSessionData]
```

```python
class SymbolSessionData:
    """Per-symbol data for current session."""
    
    # Required bars
    bars_1m: List[BarData]  # Always required if any derived bars requested
    bars_derived: Dict[int, List[BarData]]  # e.g., {5: [...], 15: [...]}
    
    # Quality metrics
    bar_quality: float  # 0-100% completeness
    
    # Other data types
    quotes: List[QuoteData]
    ticks: List[TickData]
    
    # Session metrics (real-time)
    session_volume: int
    session_high: float
    session_low: float
    
    # Update flags (set by main thread)
    bars_updated: bool
    quotes_updated: bool
    ticks_updated: bool
    
    # Historical bars (for trailing days)
    historical_bars: Dict[int, Dict[date, List[BarData]]]
    # e.g., {1: {date1: [...], date2: [...]}, 5: {date1: [...], date2: [...]}}
```

**Location:** `app/managers/data_manager/session_data.py`

---

#### 2. **Two-Thread Model**

##### **Thread 1: Main Coordinator Thread**
Current `_merge_worker` needs to be extended:

```python
class MainCoordinatorThread:
    """Main thread for chronological data delivery and session management."""
    
    Responsibilities:
    1. Chronological Data Delivery
       - Stream data into session_data in time order
       - Enforce backtest speed (if configured)
       - Fast-forward stale data
    
    2. Session Completion Detection
       - Live: current_time > end_time
       - Backtest: 
         * Within 1min of end_time + no more data, OR
         * All data streamed + 60s timeout with no data
         * Set stream_coordinator_timer_expired on timeout
    
    3. Advance to Next Session (Backtest Only)
       - Signal session_ended flag
       - Advance time to next session open
       - Wait for data-upkeep-thread to load data
```

**Key Changes:**
- Add session boundary detection
- Add timeout handling for session end
- Add next-session advancement logic
- Update `session_data` instead of just yielding

---

##### **Thread 2: Data-Upkeep Thread** (NEW)
Completely new component:

```python
class DataUpkeepThread:
    """Background thread for data integrity and prefetching."""
    
    Responsibilities:
    1. Bar Completeness (1-minute bars)
       - Check gaps from session_start to current_time
       - Fetch missing bars from database
       - Insert into session_data
       - Update bar_quality metric
       - Retry every minute until complete
       - Recompute derived bars after 1m bars complete
    
    2. Historical Bars for Trailing Days
       - Verify historical_bars_trailing_days requirement
       - Fetch missing historical data
       - Populate session_data.historical_bars
    
    3. Backtesting Data Prefetch
       - Look ahead to next session
       - Prefetch all required data for next session
       - Prepare derived bars
       - Update historical bars (remove oldest, add current)
    
    4. Refilling Stream Queues
       - Detect session_ended flag
       - Load prefetched data into coordinator queues
       - Reset session_ended flag
```

**Location:** `app/managers/data_manager/data_upkeep_thread.py`

---

## Gap Analysis

### What's Missing

#### 1. **session_data Singleton** ❌
**Current:** SessionTracker only tracks metrics, not actual data
**Need:** Full data structure holding bars, quotes, ticks, and historical data

**Implementation Required:**
- New `SessionData` class
- Integration with SystemManager
- Thread-safe access patterns
- Per-symbol data containers

---

#### 2. **Session Boundary Configuration** ❌
**Current:** Hardcoded market hours in multiple places
**Need:** Configurable session boundaries

**Current Code:**
```python
# DataManager.__init__
self.opening_time: time = time(6, 30)   # PST
self.closing_time: time = time(13, 0)   # PST
```

**Need:**
```python
# session_data configuration
session_data.start_time = time(9, 30)  # ET
session_data.end_time = time(16, 0)     # ET
session_data.historical_bars_trailing_days = 5
session_data.historical_bars_types = [1, 5]
```

---

#### 3. **Bar Completeness Checking** ❌
**Current:** No gap detection or filling mechanism
**Need:** 
- Detect gaps in 1-minute bars
- Fetch missing data from database
- Update bar_quality metric
- Retry mechanism

**Implementation:**
```python
async def check_bar_completeness(symbol: str, session_date: date):
    """Check for gaps in 1-minute bars from session start to current time."""
    start = datetime.combine(session_date, session_data.start_time)
    end = time_provider.get_current_time()
    
    # Expected bar count
    expected_count = (end - start).total_seconds() / 60
    
    # Actual bar count
    actual_count = len(session_data.symbols[symbol].bars_1m)
    
    # Calculate quality
    quality = (actual_count / expected_count) * 100
    session_data.symbols[symbol].bar_quality = quality
    
    if quality < 100:
        # Fetch missing bars
        await fill_missing_bars(symbol, start, end)
```

---

#### 4. **Historical Bars Management** ❌
**Current:** No automatic historical data loading
**Need:** 
- Fetch trailing days of historical bars
- Store in session_data
- Update on session roll

**Implementation:**
```python
async def ensure_historical_bars(symbol: str):
    """Ensure historical bars for trailing days are loaded."""
    if session_data.historical_bars_trailing_days == 0:
        return
    
    for interval in session_data.historical_bars_types:
        # Calculate date range
        end_date = session_data.current_session_date - timedelta(days=1)
        start_date = end_date - timedelta(days=session_data.historical_bars_trailing_days)
        
        # Fetch bars
        bars = await fetch_bars_for_range(symbol, start_date, end_date, interval)
        
        # Store in session_data
        session_data.symbols[symbol].historical_bars[interval] = bars
```

---

#### 5. **Prefetch Mechanism** ❌
**Current:** No lookahead or prefetch
**Need:**
- Detect next session
- Prefetch all data before session starts
- Load into coordinator when needed

**Implementation:**
```python
async def prefetch_next_session():
    """Prefetch data for next session (backtest only)."""
    if not system_manager.is_backtest_mode():
        return
    
    current_date = session_data.current_session_date
    next_date = find_next_trading_day(current_date)
    
    if next_date > backtest_end_date:
        return  # No more sessions
    
    # Prefetch all required data for all active symbols
    for symbol in session_data.symbols.keys():
        # Fetch bars
        start = datetime.combine(next_date, session_data.start_time)
        end = datetime.combine(next_date, session_data.end_time)
        
        bars = await fetch_bars(symbol, start, end)
        
        # Store in prefetch buffer
        prefetch_buffer[symbol] = bars
```

---

#### 6. **Session End Detection** ⚠️ Partially Present
**Current:** Basic time comparison in BacktestStreamCoordinator
**Need:** 
- Proper session boundary detection
- Timeout handling
- Error flagging

**Current Code:**
```python
# In _merge_worker - no explicit session end detection
```

**Need:**
```python
def detect_session_end():
    """Detect if current session has ended."""
    current_time = time_provider.get_current_time()
    
    if system_manager.is_live_mode():
        # Session ends when current time > end_time
        if current_time.time() > session_data.end_time:
            return True
    else:
        # Backtest mode
        session_end_dt = datetime.combine(
            session_data.current_session_date,
            session_data.end_time
        )
        
        # Within 1 minute of end + no more data
        if abs((current_time - session_end_dt).total_seconds()) < 60:
            if not has_more_data():
                return True
        
        # All data streamed + 60s timeout
        if all_streams_exhausted():
            if time_since_last_data() > 60:
                system_manager.stream_coordinator_timer_expired = True
                return True
    
    return False
```

---

#### 7. **Derived Bar Computation** ❌
**Current:** No automatic derived bar computation
**Need:** Compute 5m, 15m, etc. bars from 1m bars

**Implementation:**
```python
def compute_derived_bars(symbol: str, interval: int):
    """Compute derived bars from 1-minute bars."""
    bars_1m = session_data.symbols[symbol].bars_1m
    derived_bars = []
    
    # Group 1m bars into N-minute bars
    for i in range(0, len(bars_1m), interval):
        chunk = bars_1m[i:i+interval]
        if len(chunk) < interval:
            continue  # Incomplete bar
        
        derived_bar = BarData(
            symbol=symbol,
            timestamp=chunk[0].timestamp,
            open=chunk[0].open,
            high=max(b.high for b in chunk),
            low=min(b.low for b in chunk),
            close=chunk[-1].close,
            volume=sum(b.volume for b in chunk)
        )
        derived_bars.append(derived_bar)
    
    session_data.symbols[symbol].bars_derived[interval] = derived_bars
```

---

## Migration Path

### Phase 1: Create session_data Foundation
1. Create `SessionData` and `SymbolSessionData` classes
2. Integrate with SystemManager
3. Migrate SessionTracker functionality into session_data
4. Update BacktestStreamCoordinator to write to session_data

### Phase 2: Implement Data-Upkeep Thread
1. Create `DataUpkeepThread` class
2. Implement bar completeness checking
3. Implement gap filling mechanism
4. Add bar_quality tracking

### Phase 3: Add Historical Bars Support
1. Implement historical_bars_trailing_days configuration
2. Add historical data loading
3. Implement session roll logic

### Phase 4: Add Prefetch Mechanism
1. Implement next-session detection
2. Add prefetch logic for backtest mode
3. Implement queue refilling on session boundary

### Phase 5: Update Main Coordinator
1. Add session boundary detection
2. Add timeout handling
3. Implement next-session advancement
4. Add session_ended flag management

### Phase 6: Add Derived Bars
1. Implement derived bar computation
2. Ensure 1m bars always active when derived requested
3. Auto-recompute on 1m bar updates

---

## Implementation Recommendations

### 1. **Start Small**
Implement in phases, testing each phase thoroughly before moving to the next.

### 2. **Backward Compatibility**
Maintain current APIs during migration:
```python
# Keep existing stream_bars() working
async def stream_bars(...):
    # Internally uses session_data but external API unchanged
    async for bar in coordinator.get_merged_stream():
        yield bar
```

### 3. **Thread Safety**
Use proper locking for session_data access:
```python
class SessionData:
    def __init__(self):
        self._lock = asyncio.Lock()
    
    async def update_bars(self, symbol: str, bars: List[BarData]):
        async with self._lock:
            self.symbols[symbol].bars_1m.extend(bars)
```

### 4. **Configuration**
Add new settings to `app/config/settings.py`:
```python
# Session configuration
SESSION_START_TIME = "09:30"  # ET
SESSION_END_TIME = "16:00"    # ET
SESSION_HISTORICAL_TRAILING_DAYS = 5
SESSION_HISTORICAL_BAR_TYPES = [1, 5]

# Data upkeep configuration
DATA_UPKEEP_CHECK_INTERVAL_SECONDS = 60
DATA_UPKEEP_RETRY_MISSING_BARS = True
```

### 5. **Testing Strategy**
- Unit tests for session_data operations
- Integration tests for two-thread coordination
- Backtest replay tests for session boundaries
- Gap-filling tests with incomplete data

---

## File Structure Changes

### New Files Required:
```
app/managers/data_manager/
├── session_data.py              # NEW: SessionData singleton
├── data_upkeep_thread.py        # NEW: Data-upkeep thread
├── derived_bars.py              # NEW: Derived bar computation
├── gap_detection.py             # NEW: Gap detection & filling
└── prefetch_manager.py          # NEW: Prefetch logic
```

### Modified Files:
```
app/managers/data_manager/
├── backtest_stream_coordinator.py  # MODIFY: Add session detection
├── api.py                          # MODIFY: Use session_data
├── config.py                       # MODIFY: Add session config
└── session_tracker.py              # MODIFY: Integrate with session_data
```

---

## Complexity Assessment

### High Complexity Areas:
1. **Thread Coordination** - Two threads accessing shared session_data
2. **Session Boundary Logic** - Complex timeout and detection rules
3. **Prefetch Timing** - When to prefetch vs when to load
4. **Gap Filling** - Handling missing data during active session

### Medium Complexity Areas:
1. **Derived Bars** - Computation logic straightforward
2. **Historical Bars** - Data fetching and storage
3. **session_data Structure** - Class design

### Low Complexity Areas:
1. **Configuration** - Adding new settings
2. **bar_quality Metric** - Simple calculation
3. **Update Flags** - Boolean state tracking

---

## Estimated Effort

### Development Time (assuming 1 developer):
- **Phase 1 (Foundation)**: 1-2 weeks
- **Phase 2 (Data-Upkeep)**: 2-3 weeks
- **Phase 3 (Historical Bars)**: 1-2 weeks
- **Phase 4 (Prefetch)**: 2-3 weeks
- **Phase 5 (Main Coordinator)**: 1-2 weeks
- **Phase 6 (Derived Bars)**: 1 week

**Total: 8-13 weeks** (2-3 months)

### Testing Time:
- Unit tests: 2-3 weeks
- Integration tests: 2-3 weeks
- System tests: 1-2 weeks

**Total: 5-8 weeks**

### Grand Total: **13-21 weeks (3-5 months)**

---

## Risk Analysis

### High Risk:
1. **Thread synchronization bugs** - Can cause data corruption or deadlocks
2. **Session boundary edge cases** - Missing data at session transitions
3. **Memory usage** - Storing historical bars for multiple symbols

### Medium Risk:
1. **Performance degradation** - Gap filling may slow down streaming
2. **Prefetch timing issues** - Data not ready when needed
3. **Configuration complexity** - Too many knobs to tune

### Low Risk:
1. **API breaking changes** - Can maintain backward compatibility
2. **Testing coverage** - Good existing test infrastructure
3. **Code organization** - Clear module boundaries

---

## Conclusion

The current implementation provides a solid foundation with the core threading, time management, and coordinator patterns in place. However, the proposed architecture requires significant new components and substantial modifications to existing code.

**Key Takeaways:**
1. ✅ Core infrastructure (TimeProvider, SystemManager, Coordinator) is solid
2. ❌ Missing session_data singleton and two-thread model
3. ❌ No bar completeness, gap filling, or historical bars support
4. ⚠️ Significant development effort required (3-5 months)
5. 🎯 Recommended approach: Phased migration with backward compatibility

**Next Steps:**
1. Review and approve this analysis
2. Prioritize phases based on business value
3. Create detailed technical specs for Phase 1
4. Begin implementation with session_data foundation
