# Stream Coordinator Architecture Comparison

## Current Architecture (2025-11)

```
┌─────────────────────────────────────────────────────────────────┐
│                         SystemManager                            │
│  (Mode: live/backtest, State: running/paused/stopped)           │
└────────┬────────────────────────────────────────────────────────┘
         │
         ├──► DataManager
         │      │
         │      ├──► TimeProvider (singleton)
         │      │      └──► backtest_time state
         │      │
         │      ├──► BacktestStreamCoordinator (singleton)
         │      │      │
         │      │      └──► Single Worker Thread
         │      │             │
         │      │             ├──► Input Queues (per stream)
         │      │             │      │
         │      │             │      ├──► AAPL bars queue
         │      │             │      ├──► GOOGL bars queue
         │      │             │      └──► MSFT bars queue
         │      │             │
         │      │             ├──► Priority Heap (chronological merge)
         │      │             │
         │      │             ├──► Advance backtest_time
         │      │             │
         │      │             └──► Output Queue
         │      │                    └──► Yields to DataManager
         │      │
         │      └──► SessionTracker (singleton)
         │             │
         │             └──► Per-symbol metrics
         │                    ├──► session_volume
         │                    ├──► session_high
         │                    └──► session_low
         │
         └──► ExecutionManager (placeholder)
```

### Current Data Flow

```
Database Query
    │
    ├──► Bars for AAPL ──┐
    ├──► Bars for GOOGL ─┤
    └──► Bars for MSFT ──┘
                          │
                          ▼
              ┌───────────────────────┐
              │   Input Queues        │
              │  (Thread-safe)        │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │  Single Worker Thread │
              │  - Merge via heap     │
              │  - Advance time       │
              │  - Apply speed        │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   Output Queue        │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   Yield to Caller     │
              │  (async iterator)     │
              └───────────────────────┘
```

### Current Limitations

❌ **No centralized data storage** - Data flows through, not stored
❌ **Single thread** - One thread does everything
❌ **No gap detection** - Missing bars not detected or filled
❌ **No historical bars** - Can't maintain trailing days
❌ **No session boundaries** - No explicit session start/end
❌ **No prefetch** - Next session data fetched on-demand
❌ **No derived bars** - Must query database for 5m, 15m bars

---

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         SystemManager                            │
│    (Mode, State, stream_coordinator_timer_expired flag)          │
└────────┬────────────────────────────────────────────────────────┘
         │
         ├──► session_data (singleton) ◄─── NEW!
         │      │
         │      ├──► Configuration
         │      │      ├──► start_time: 09:30 ET
         │      │      ├──► end_time: 16:00 ET
         │      │      ├──► historical_bars_trailing_days: 5
         │      │      └──► historical_bars_types: [1, 5]
         │      │
         │      ├──► Session State
         │      │      ├──► current_session_date
         │      │      └──► session_ended: bool
         │      │
         │      └──► Per-Symbol Data (SymbolSessionData)
         │             │
         │             ├──► bars_1m: List[BarData]
         │             ├──► bars_derived: {5: [...], 15: [...]}
         │             ├──► bar_quality: 98.5%
         │             ├──► quotes: List[QuoteData]
         │             ├──► ticks: List[TickData]
         │             ├──► session_volume: 1,234,567
         │             ├──► session_high: 150.50
         │             ├──► session_low: 148.20
         │             ├──► update flags: {bars, quotes, ticks}
         │             └──► historical_bars: {1: {date: [...]}, 5: {...}}
         │
         ├──► DataManager
         │      │
         │      ├──► TimeProvider (singleton)
         │      │
         │      └──► BacktestStreamCoordinator (singleton)
         │             │
         │             ├──► Thread 1: Main Coordinator ◄─── MODIFIED
         │             │      │
         │             │      ├──► Chronological Delivery
         │             │      │      ├──► Merge via heap
         │             │      │      ├──► Write to session_data
         │             │      │      └──► Advance backtest_time
         │             │      │
         │             │      ├──► Session Completion Detection
         │             │      │      ├──► Check time vs end_time
         │             │      │      ├──► Check for more data
         │             │      │      └──► Set timeout flags
         │             │      │
         │             │      └──► Advance to Next Session
         │             │             ├──► Set session_ended flag
         │             │             ├──► Advance to next open
         │             │             └──► Wait for data-upkeep
         │             │
         │             └──► Thread 2: Data-Upkeep ◄─── NEW!
         │                    │
         │                    ├──► Bar Completeness
         │                    │      ├──► Check gaps (session_start → now)
         │                    │      ├──► Fetch missing bars
         │                    │      ├──► Update bar_quality
         │                    │      └──► Retry every minute
         │                    │
         │                    ├──► Historical Bars
         │                    │      ├──► Load trailing days
         │                    │      └──► Update on session roll
         │                    │
         │                    ├──► Prefetch (Backtest)
         │                    │      ├──► Detect next session
         │                    │      ├──► Fetch all data
         │                    │      ├──► Compute derived bars
         │                    │      └──► Store in buffer
         │                    │
         │                    └──► Refill Queues
         │                           ├──► Detect session_ended
         │                           ├──► Load prefetch → queues
         │                           └──► Reset session_ended
         │
         └──► ExecutionManager
```

### Proposed Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Start of Session                              │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────┐
              │  Data-Upkeep Thread      │
              │  - Load historical bars  │
              │  - Prefetch session data │
              └─────────────┬────────────┘
                            │
                            ▼
              ┌──────────────────────────┐
              │  Main Coordinator Thread │
              │  - Read from queues      │
              │  - Merge chronologically │
              │  - Write to session_data │
              │  - Advance time          │
              └─────────────┬────────────┘
                            │
                            ▼
              ┌──────────────────────────┐
              │     session_data         │
              │  - Store bars            │
              │  - Update metrics        │
              │  - Set update flags      │
              └─────────────┬────────────┘
                            │
                            ├──► Yield to Caller
                            │
                            └──► Data-Upkeep Thread
                                    │
                                    ├──► Check gaps
                                    ├──► Fill missing bars
                                    ├──► Compute derived bars
                                    └──► Update bar_quality
                                            │
                                            ▼
                            ┌──────────────────────────┐
                            │   End of Session         │
                            │  - Set session_ended     │
                            │  - Prefetch next session │
                            │  - Advance time          │
                            │  - Load into queues      │
                            └──────────────────────────┘
```

### Proposed Benefits

✅ **Centralized storage** - All data in session_data
✅ **Two-thread model** - Separation of concerns
✅ **Gap detection** - Automatic bar completeness checking
✅ **Historical bars** - Trailing days maintained automatically
✅ **Session boundaries** - Explicit start/end management
✅ **Prefetch** - Next session ready before needed
✅ **Derived bars** - Computed from 1m bars automatically
✅ **Bar quality metric** - Know data completeness
✅ **Update flags** - Know what data changed

---

## Side-by-Side Comparison

| Feature | Current | Proposed | Status |
|---------|---------|----------|--------|
| **Data Storage** | Flows through | Stored in session_data | ❌ Missing |
| **Thread Model** | 1 thread | 2 threads | ❌ Missing |
| **Bar Completeness** | Not checked | Automatic gaps detection | ❌ Missing |
| **Gap Filling** | No | Automatic retry | ❌ Missing |
| **Historical Bars** | No | Trailing days support | ❌ Missing |
| **Derived Bars** | From DB | Computed from 1m | ❌ Missing |
| **Session Boundaries** | Implicit | Explicit start/end | ❌ Missing |
| **Session End Detection** | Basic | Sophisticated with timeout | ⚠️ Partial |
| **Prefetch** | No | Next session prefetch | ❌ Missing |
| **Quality Metrics** | No | bar_quality % | ❌ Missing |
| **Update Flags** | No | Per data type | ❌ Missing |
| **Time Management** | ✅ TimeProvider | ✅ Same | ✅ Present |
| **Mode Management** | ✅ SystemManager | ✅ Same | ✅ Present |
| **State Management** | ✅ SystemManager | ✅ Same | ✅ Present |
| **Thread Safety** | ✅ Queues & locks | ✅ asyncio locks | ✅ Present |
| **Backtest Speed** | ✅ Configurable | ✅ Same | ✅ Present |
| **Chronological Merge** | ✅ Min-heap | ✅ Same | ✅ Present |

---

## Thread Interaction Diagrams

### Current: Single Thread

```
Time ──►

Main Coordinator Thread:
│
├──► Read Queue 1
├──► Read Queue 2
├──► Read Queue 3
├──► Merge (heap)
├──► Advance time
├──► Apply speed
├──► Output
│
└──► (repeat)
```

### Proposed: Two Threads

```
Time ──►

Main Coordinator Thread:                  Data-Upkeep Thread:
│                                         │
├──► Read queues                          ├──► Check time
├──► Merge (heap)                         ├──► Is session active?
├──► Write to session_data ◄──────────────┤      │
├──► Advance time                         │      └──► If yes:
├──► Apply speed                          │           ├──► Check gaps
├──► Check session end ◄──────────────────┤           ├──► Fetch missing
│    │                                    │           ├──► Write to session_data
│    └──► If yes:                         │           └──► Update bar_quality
│         ├──► Set session_ended ─────────┤
│         ├──► Advance to next            │      Is session ended?
│         └──► Wait                       │           │
│                                         │           └──► If yes:
├──► Output                               │                ├──► Prefetch next
│                                         │                ├──► Compute derived
└──► (repeat)                             │                ├──► Load queues
                                          │                └──► Reset flag
                                          │
                                          └──► (repeat)
```

---

## Concurrency & Synchronization

### session_data Access Pattern

```python
class SessionData:
    def __init__(self):
        self._lock = asyncio.Lock()
    
    # All public methods use lock:
    async def add_bar(self, ...):
        async with self._lock:  # ◄─── Thread-safe
            # ... modify data ...
    
    async def get_bars(self, ...):
        async with self._lock:  # ◄─── Thread-safe
            # ... read data ...
```

### Thread Coordination

```
Main Coordinator:                     Data-Upkeep:
                                      
Write bar ──────►┌────────────┐      Read bars
                 │ session_   │◄──── Check gaps
                 │   data     │
Update metrics ──►└────────────┘      Write bars
                       │
                       └──────────────► Compute derived
```

**Key Points:**
- Both threads access session_data concurrently
- asyncio.Lock ensures atomicity
- No deadlocks (single lock, always acquired/released)
- Update flags allow coordination without polling

---

## Configuration Comparison

### Current Configuration

```python
# In DataManager
self.backtest_days = 10  # Number of trading days
self.opening_time = time(6, 30)  # PST
self.closing_time = time(13, 0)  # PST

# In BacktestStreamCoordinator
# No configuration - hardcoded behavior
```

### Proposed Configuration

```python
# In session_data
session_data.start_time = time(9, 30)  # ET
session_data.end_time = time(16, 0)    # ET
session_data.historical_bars_trailing_days = 5
session_data.historical_bars_types = [1, 5]

# In settings.py (new)
SESSION_START_TIME = "09:30"
SESSION_END_TIME = "16:00"
SESSION_HISTORICAL_TRAILING_DAYS = 5
SESSION_HISTORICAL_BAR_TYPES = [1, 5]

DATA_UPKEEP_CHECK_INTERVAL_SECONDS = 60
DATA_UPKEEP_RETRY_MISSING_BARS = True
```

---

## Summary

### What Works Today ✅
- TimeProvider with backtest time management
- SystemManager with mode and state control
- BacktestStreamCoordinator with chronological merging
- SessionTracker with basic metrics
- Thread-safe queue communication

### What's Missing ❌
- session_data singleton for centralized storage
- Two-thread model (data-upkeep thread)
- Bar completeness checking and gap filling
- Historical bars management (trailing days)
- Derived bar computation
- Session boundary detection and handling
- Prefetch mechanism for next session
- Bar quality metrics
- Update flag system

### Migration Strategy 🎯
1. **Phase 1** (2 weeks): Add session_data foundation
2. **Phase 2** (3 weeks): Add data-upkeep thread
3. **Phase 3** (2 weeks): Add historical bars support
4. **Phase 4** (3 weeks): Add prefetch mechanism
5. **Phase 5** (2 weeks): Update main coordinator for session boundaries
6. **Phase 6** (1 week): Add derived bars computation

**Total: 13 weeks (3 months)**
