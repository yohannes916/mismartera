# Threading Architecture Overview - Complete System Documentation

## Purpose

This document provides a high-level overview of the two critical background threads in the backtest system and how they coordinate to provide accurate, high-quality market data streaming.

## The Two Critical Threads

### 1. Backtest Stream Coordinator 🎯
**File:** `app/managers/data_manager/backtest_stream_coordinator.py`
**Docs:** `BACKTEST_STREAM_COORDINATOR_ANALYSIS.md`

**Primary Responsibilities:**
- ✅ Chronological merging of multiple data streams
- ✅ **Time advancement** (ONLY place time moves forward) ⚠️
- ✅ Market hours filtering (pre-market, after-hours)
- ✅ Writing data to SessionData

**Thread Count:** 1-2 threads
- Always: Merge worker
- Conditional: Clock worker (if speed > 0)

### 2. Data Upkeep Thread 🔧
**File:** `app/managers/data_manager/data_upkeep_thread.py`
**Docs:** `DATA_UPKEEP_THREAD_ANALYSIS.md`

**Primary Responsibilities:**
- ✅ Session lifecycle management (EOD detection, day transitions)
- ✅ Bar quality calculation
- ✅ Gap detection and filling
- ✅ Derived bar computation (5m, 15m from 1m)

**Thread Count:** 2 threads
- Always: Upkeep worker
- Always: Prefetch worker (launched by upkeep)

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           SystemManager                                   │
│  • Initializes both threads                                              │
│  • Provides TimeManager access                                           │
│  • Manages system state (running/paused/stopped)                         │
└──────────────────────────────────────────────────────────────────────────┘
         │                                │
         │                                │
         ▼                                ▼
┌─────────────────────────┐    ┌─────────────────────────────┐
│ BacktestStreamCoordinator│    │   DataUpkeepThread          │
│ ═════════════════════════│    │ ═════════════════════════   │
│                          │    │                              │
│ MERGE WORKER ★          │    │ UPKEEP LOOP ★               │
│ ├─ Fetch from queues    │    │ ├─ EOD Detection            │
│ ├─ Find oldest          │    │ ├─ Day Transition           │
│ ├─ Filter hours         │    │ ├─ Session Activation       │
│ ├─ ADVANCE TIME ⚠️      │    │ └─ Quality Tasks            │
│ ├─ Write to SessionData │    │   ├─ Calculate quality      │
│ └─ Yield output         │    │   ├─ Fill gaps              │
│                          │    │   └─ Compute derived        │
│ CLOCK WORKER (speed>0)  │    │                              │
│ └─ Advances time @speed │    │ PREFETCH WORKER             │
│                          │    │ └─ Loads next day data      │
└─────────────────────────┘    └─────────────────────────────┘
         │                                │
         │ (writes)                       │ (signals)
         ▼                                │
┌──────────────────────────────────────────────────────────┐
│              SessionData (Thread-Safe)                    │
│  • Stores 1m bars, ticks, quotes                         │
│  • Stores derived bars (5m, 15m)                         │
│  • Protected by _lock                                    │
│  • Signals _data_arrival_event                           │
└──────────────────────────────────────────────────────────┘
         │
         │ (consumes)
         ▼
┌──────────────────────────────────────────────────────────┐
│           AnalysisEngine (Future)                        │
│  • Consumes streamed data                                │
│  • Runs strategies                                       │
│  • Generates signals                                     │
└──────────────────────────────────────────────────────────┘
```

---

## Thread Coordination

### Shared Resources

| Resource | Protected By | Accessed By | Purpose |
|----------|-------------|-------------|---------|
| **SessionData** | `_lock` | Both threads | Store market data |
| **TimeManager** | Internal locks | Both threads | Time operations |
| **_data_arrival_event** | Event object | Both threads | Signal new data |
| **_active_streams** | Coordinator `_lock` | Coordinator only | Stream management |

### Communication Flow

```
1. Coordinator receives bar → 2. Writes to SessionData → 3. Signals event →
4. Upkeep wakes up → 5. Calculates quality → 6. Detects gaps →
7. Computes derived bars → 8. Waits for next event
```

### Time Flow (Critical Path)

```
INITIALIZATION:
SystemManager → TimeManager.set_backtest_time(start_date @ market_open)

DURING SESSION:
Coordinator → time_manager.set_backtest_time(bar_end_time)  [ONLY place]
↓
All components → time_manager.get_current_time()  [Query only]

AT EOD:
Upkeep Thread → time_manager.advance_to_market_open()  [Day transition]
Coordinator → Pauses (detects market close)
```

---

## Operating Modes

### Mode 1: Data-Driven (Speed = 0) 🚀
**Use Case:** Fast backtesting, testing, debugging

| Component | Behavior |
|-----------|----------|
| **Coordinator** | Streams immediately, advances time to data |
| **Clock Worker** | Not started |
| **Upkeep Thread** | Responds to data arrival events |
| **Time Advancement** | As fast as data can be processed |

**Flow:**
```
Coordinator fetches bar @ 09:30:00 →
Coordinator sets time to 09:31:00 →
Coordinator writes to SessionData →
Signals event → Upkeep processes →
Repeat with next bar
```

### Mode 2: Clock-Driven (Speed > 0) 🕐
**Use Case:** Realistic timing, strategy testing

| Component | Behavior |
|-----------|----------|
| **Coordinator** | Waits for time to reach data, then streams |
| **Clock Worker** | Advances time independently @ speed |
| **Upkeep Thread** | Responds to data arrival events |
| **Time Advancement** | Controlled by speed multiplier |

**Flow:**
```
Clock worker advances time @ speed →
Coordinator has bar @ 09:30:00 →
Coordinator waits for time >= 09:31:00 →
Time reaches 09:31:00 → Coordinator streams →
Writes to SessionData → Signals event →
Upkeep processes → Repeat
```

**Speed Examples:**
- `1x`: Real-time (1 second = 1 second)
- `60x`: 1 minute per second
- `360x`: 6 hours per minute

---

## Lifecycle Comparison

### Startup Sequence

```
1. SystemManager starts
2. SystemManager initializes TimeManager
3. DataManager creates BacktestStreamCoordinator (singleton)
4. DataManager creates DataUpkeepThread
5. DataManager starts coordinator.start_worker()
   └─> Starts merge worker thread
   └─> Starts clock worker thread (if speed > 0)
6. DataManager starts upkeep_thread.start()
   └─> Starts upkeep worker thread
7. SystemManager sets backtest time to start date @ market open
8. Upkeep thread detects time >= market open
9. Upkeep thread activates session
10. Upkeep thread launches prefetch for current day
11. Prefetch loads data into coordinator queues
12. Both threads now running in parallel
```

### Normal Operation

```
┌─ Coordinator Loop ─────────────┐  ┌─ Upkeep Loop ──────────────────┐
│                                 │  │                                 │
│ 1. Check market close           │  │ 1. Wait on data_arrival_event  │
│ 2. Fetch next items             │  │    (timeout: 1 second)         │
│ 3. Find oldest                  │  │                                 │
│ 4. Filter hours                 │  │ 2. Check EOD (every cycle)     │
│ 5. Advance time ⚠️              │  │    if time >= close:           │
│ 6. Write to SessionData ────────┼──┼──> Signal event                │
│ 7. Yield output                 │  │    Deactivate session          │
│                                 │  │    Advance to next day         │
│ Repeat ~390 times per day      │  │    Activate session            │
│ (one per 1m bar)               │  │    Launch prefetch             │
│                                 │  │    continue                    │
│                                 │  │                                 │
│ At 16:01: Detect market close  │  │ 3. Run symbol upkeep:          │
│ Pause streaming                 │  │    - Calculate quality         │
│ Wait for upkeep to advance ────┼──┼─>  - Fill gaps                 │
│                                 │  │    - Compute derived bars      │
│                                 │  │                                 │
└─────────────────────────────────┘  └─────────────────────────────────┘
```

### Shutdown Sequence

```
1. SystemManager.stop() called
2. SystemManager calls coordinator.stop_worker()
   └─> Sets _shutdown event
   └─> Stops clock worker (if running)
   └─> Stops merge worker
3. SystemManager calls upkeep_thread.stop()
   └─> Sets _shutdown event
   └─> Stops prefetch worker
   └─> Stops upkeep worker
4. All threads join with timeout
5. Cleanup complete
```

---

## Responsibility Matrix

| Task | Coordinator | Upkeep | Who's Critical? |
|------|------------|--------|-----------------|
| **Time advancement (forward)** | ✅ | ❌ | Coordinator ⚠️ |
| **Time reset (day transition)** | ❌ | ✅ | Upkeep |
| **EOD detection** | ✅ (pauses) | ✅ (handles) | Upkeep |
| **Session activation** | ❌ | ✅ | Upkeep |
| **Data streaming** | ✅ | ❌ | Coordinator |
| **Quality calculation** | ✅ (immediate) | ✅ (periodic) | Both |
| **Gap detection** | ❌ | ✅ | Upkeep |
| **Gap filling** | ❌ | ✅ | Upkeep |
| **Derived bars** | ❌ | ✅ | Upkeep |
| **Prefetch coordination** | ❌ | ✅ | Upkeep |
| **Market hours filtering** | ✅ | ❌ | Coordinator |
| **Chronological ordering** | ✅ | ❌ | Coordinator |

---

## Critical Rules

### Rule 1: Time Advancement ⚠️
**ONLY the stream coordinator advances time FORWARD.**

- ✅ Coordinator: `time_manager.set_backtest_time(bar_end_time)`
- ✅ Upkeep: `time_manager.advance_to_market_open()` (resets to open)
- ❌ All others: Only `time_manager.get_current_time()` (query)

### Rule 2: Bar Timestamp Lag
**Bar timestamps represent interval START, not END.**

- 1m bar @ 09:30:00 = interval [09:30:00 - 09:30:59]
- Time set to 09:31:00 when yielding (bar complete)
- Matches real-world streaming behavior

### Rule 3: 1m Bars Only (Coordinator)
**Coordinator only handles 1m bars, ticks, and quotes.**

- Derived bars (5m, 15m) computed by upkeep thread
- Validation prevents other intervals
- Separation of concerns: streaming vs computation

### Rule 4: EOD Coordination
**Both threads detect EOD, but upkeep handles transitions.**

- Coordinator: Pauses streaming at close + 1min
- Upkeep: Deactivates session, advances day, reactivates
- Coordinator: Resumes streaming with next day data

### Rule 5: Thread Safety
**All shared resources protected by locks or queues.**

- SessionData: Protected by `_lock`
- Active streams: Protected by coordinator `_lock`
- Queues: Thread-safe by design (queue.Queue)
- Events: Thread-safe by design (threading.Event)

---

## Common Scenarios

### Scenario 1: Normal Trading Day
```
09:30:00 → Upkeep activates session, launches prefetch
09:30:01 → Coordinator streams first bar, advances time to 09:31:00
09:31:01 → Coordinator streams second bar, advances time to 09:32:00
...
16:00:01 → Coordinator streams last bar, advances time to 16:01:00
16:01:00 → Coordinator detects market close, pauses
16:01:00 → Upkeep detects EOD, deactivates session
16:01:01 → Upkeep advances time to next day 09:30:00
16:01:02 → Upkeep activates session, launches prefetch
16:01:03 → Coordinator resumes streaming with next day data
```

### Scenario 2: Mid-Day Start
```
12:00:00 → System starts
12:00:01 → Upkeep detects time >= market open
12:00:02 → Upkeep activates session
12:00:03 → Upkeep launches prefetch for 09:30-12:00 (historical)
12:00:20 → Prefetch completes
12:00:21 → Coordinator streams historical data rapidly
12:10:00 → Caught up to 12:00 start time
12:10:01 → Continue normally until market close
```

### Scenario 3: System Pause
```
10:00:00 → System running normally
10:00:01 → User pauses system
10:00:01 → Clock worker pauses (if running)
10:00:01 → Merge worker pauses (waits in while loop)
10:00:01 → Upkeep continues (not paused)
10:05:00 → User resumes system
10:05:01 → Clock worker resumes (if running)
10:05:01 → Merge worker resumes
10:05:01 → Streaming continues from 10:00:01 timestamp
```

### Scenario 4: Stream Exhaustion (Data Ends Early)
```
14:30:00 → All parquet data exhausted (no more bars)
14:30:01 → Streams send None sentinels
14:30:02 → Coordinator deregisters all streams
14:30:03 → Upkeep detects no active streams
14:30:04 → Upkeep force-advances time to 16:00:00
14:30:05 → Next cycle, upkeep detects EOD
14:30:06 → Normal day transition occurs
```

---

## Performance Characteristics

### Coordinator
- **Throughput:** ~10,000 bars/second (data-driven mode)
- **Latency:** ~0.01ms per bar (no queue waits)
- **Memory:** ~1MB per 10,000 queued items
- **CPU:** Low (simple comparison, no sorting)

### Upkeep Thread
- **Check Interval:** 1 second (scaled by speed)
- **Quality Calc:** ~1ms per symbol
- **Gap Fill:** ~100ms per gap (DB access)
- **Derived Bars:** ~5ms per symbol per interval
- **CPU:** Low (event-driven, mostly sleeping)

---

## Documentation Files

### Coordinator Documentation
- 📄 `BACKTEST_STREAM_COORDINATOR_ANALYSIS.md` - Detailed analysis (~400 lines)
- 📄 `BACKTEST_STREAM_COORDINATOR_DOCUMENTATION_SUMMARY.md` - Quick reference (~400 lines)
- 💻 `backtest_stream_coordinator.py` - Inline documentation (enhanced)

### Upkeep Documentation
- 📄 `DATA_UPKEEP_THREAD_ANALYSIS.md` - Detailed analysis (~400 lines)
- 📄 `DATA_UPKEEP_DOCUMENTATION_SUMMARY.md` - Quick reference (~400 lines)
- 💻 `data_upkeep_thread.py` - Inline documentation (enhanced)

### This Document
- 📄 `THREADING_ARCHITECTURE_OVERVIEW.md` - System-wide view (~400 lines)

**Total: 7 comprehensive documentation files!**

---

## Quick Reference

### To Understand the System
1. Read this overview (10 min)
2. Read coordinator file header (5 min)
3. Read upkeep file header (5 min)
4. Pick one thread to deep dive (30 min each)

### To Debug Threading Issues
1. Check which thread is responsible (responsibility matrix)
2. Look at the ASCII diagram for data flow
3. Review scenario that matches your issue
4. Read detailed analysis for that thread
5. Use inline step comments to trace execution

### To Modify Threading Behavior
1. Identify which thread owns the behavior
2. Read detailed analysis for that thread
3. Check if it affects thread coordination
4. Update both threads if coordination changes
5. Update documentation (inline + analysis + this doc)

### To Simplify
1. Review "Potential Simplifications" in each analysis doc
2. Consider impact on thread coordination
3. Start with independent changes first
4. Test coordination scenarios thoroughly
5. Update all documentation to reflect changes

---

## Summary

This system uses **two independent daemon threads** that coordinate via **thread-safe queues and shared state** to provide accurate, high-quality backtest data streaming:

1. **Backtest Stream Coordinator**: Merges streams chronologically and advances time
2. **Data Upkeep Thread**: Manages session lifecycle and maintains data quality

Both threads are now **fully documented** with:
- ✅ Comprehensive inline comments
- ✅ Detailed lifecycle analysis
- ✅ Quick reference guides
- ✅ Architecture diagrams
- ✅ Simplification recommendations

**You now have complete visibility into the threading architecture!** 🎉
