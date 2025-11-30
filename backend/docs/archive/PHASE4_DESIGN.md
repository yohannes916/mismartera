# Phase 4: Data Processor Rewrite - Design Document

**Status**: 🚧 In Planning  
**Start Date**: November 28, 2025  
**Estimated Duration**: 4-6 days  

---

## 🎯 Objective

Transform `DataUpkeepThread` into a focused `DataProcessor` that:
1. **Generates derivative bars** (5m, 15m, 30m from 1m)
2. **Calculates real-time indicators** (NOT historical - coordinator does those)
3. **Implements bidirectional thread synchronization** with SessionCoordinator
4. **Event-driven architecture** with subscriber notifications
5. **Zero-copy data access** from SessionData
6. **NO quality management** (moves to Phase 5: Data Quality Manager)

---

## 📋 Architecture Reference

**SESSION_ARCHITECTURE.md**: Lines 1330-1360 (Data Processor Thread)

### Key Architectural Rules

1. **Scope Focus**: Purely computation and transformation
2. **No Quality Management**: Remove all gap detection, quality calculation, gap filling
3. **No Historical Indicators**: SessionCoordinator calculates those before session start
4. **Event-Driven**: Wait on notification queue, process, signal ready
5. **Bidirectional Sync**: 
   - **FROM Coordinator**: Notification queue + subscriptions
   - **TO Coordinator**: Ready signals (one-shot)
   - **TO Analysis Engine**: Data available notifications
6. **Mode-Aware**: 
   - Data-driven (speed=0): Blocks coordinator when not ready
   - Clock-driven (speed>0): Raises OverrunError if not ready

---

## 🏗️ Current State Analysis

### What DataUpkeepThread Currently Does (1,319 lines)

**Keep (Core Functionality)**:
- ✅ Derived bar computation (5m, 15m, 30m from 1m)
- ✅ Progressive computation (compute as soon as enough bars available)
- ✅ Thread lifecycle management
- ✅ Configuration-aware (derived_intervals, auto_compute_derived)

**Remove (Out of Scope)**:
- ❌ Session lifecycle management (EOD detection, deactivation, activation)
  - Lines 10-14, 33-36: Session coordinator now handles this
- ❌ Prefetch coordination
  - Lines 44, 167-171: PrefetchWorker logic moves elsewhere or removed
- ❌ Quality measurement and gap detection
  - Lines 17-19, 78-86: Moves to Data Quality Manager (Phase 5)
- ❌ Gap filling from Parquet
  - Lines 19: Moves to Data Quality Manager (Phase 5)
- ❌ Stream exhaustion detection
  - Line 35: Coordinator handles this
- ❌ Initial session activation logic
  - Lines 34, 176-177: Coordinator handles this

**Refactor (Change Architecture)**:
- 🔄 Main loop: From periodic polling → Event-driven with notification queue
- 🔄 No subscriptions TO coordinator (currently absent)
- 🔄 No ready signals TO coordinator (currently absent)
- 🔄 No notifications TO analysis engine (currently absent)

---

## 🎨 New DataProcessor Architecture

### Responsibilities

**Primary**:
1. **Derive bars**: Generate 5m, 15m, 30m, 1h, 1d bars from 1m bars
2. **Real-time indicators**: Calculate indicators as new data arrives
3. **Subscriber notifications**: Notify analysis engine when data ready

**Secondary**:
- Thread lifecycle (start, stop, cleanup)
- Configuration awareness
- Performance metrics tracking
- Error handling and logging

### Thread Synchronization Design

```python
┌─────────────────────────┐
│  Session Coordinator    │
│  (Main orchestrator)    │
└───────────┬─────────────┘
            │
            │ (1) Notify: ("AAPL", "1m", timestamp)
            ▼
    ┌──────────────────┐
    │ Notification     │
    │ Queue (tuples)   │
    └────────┬─────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│         Data Processor                  │
│  1. Wait on notification queue          │
│  2. Read 1m bars from session_data      │
│  3. Generate derived bars (5m, 15m...)  │
│  4. Calculate real-time indicators      │
│  5. Signal ready to coordinator ────────┼──> StreamSubscription.signal_ready()
│  6. Notify analysis engine              │
└─────────────┬───────────────────────────┘
              │
              │ (6) Notify: ("AAPL", "5m", "bars")
              ▼
    ┌───────────────────────┐
    │  Analysis Engine      │
    │  Notification Queue   │
    └───────────────────────┘
```

### Notification Queue Structure

**FROM Coordinator**:
```python
notification_queue.put(("symbol", "interval", timestamp))
# Example: ("AAPL", "1m", datetime(2024, 1, 15, 9, 31, 0))
```

**TO Analysis Engine**:
```python
analysis_engine_queue.put(("symbol", "interval", "bars"))
analysis_engine_queue.put(("symbol", "indicator_name", "indicator"))
# Examples:
# ("AAPL", "5m", "bars")
# ("AAPL", "rsi_14", "indicator")
```

### Event-Driven Processing Loop

```python
def _processing_loop(self):
    """Main event-driven processing loop."""
    while not self._stop_event.is_set():
        try:
            # 1. Wait for notification (blocking with timeout)
            notification = self._notification_queue.get(timeout=1.0)
            
            if notification is None:
                continue
            
            symbol, interval, timestamp = notification
            
            # 2. Read data from session_data (zero-copy)
            bars = self.session_data.get_bars(symbol, interval)
            
            # 3. Generate derivatives
            if interval == "1m":
                self._generate_derived_bars(symbol, bars)
            
            # 4. Calculate real-time indicators
            self._calculate_realtime_indicators(symbol, interval)
            
            # 5. Signal ready to coordinator
            if self._coordinator_subscription:
                self._coordinator_subscription.signal_ready()
            
            # 6. Notify analysis engine
            self._notify_analysis_engine(symbol, interval)
            
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Error in processing loop: {e}", exc_info=True)
```

---

## 📝 Implementation Tasks

### Task 4.1: Project Setup & Backup ✅
- [ ] Backup existing `data_upkeep_thread.py` to `_backup/`
- [ ] Create new `data_processor.py` skeleton
- [ ] Set up imports (Phase 1, 2, 3 dependencies)
- [ ] Create initial class structure

### Task 4.2: Core Thread Infrastructure ✅
- [ ] Thread lifecycle (start, stop, join)
- [ ] Notification queue setup
- [ ] Stop event and running flag
- [ ] Configuration loading from SessionConfig
- [ ] TimeManager integration

### Task 4.3: Bidirectional Synchronization ✅
- [ ] **FROM Coordinator**:
  - [ ] Notification queue receiver
  - [ ] Subscription to coordinator (receive ready signals)
- [ ] **TO Coordinator**:
  - [ ] Ready signal sender (one-shot per notification)
  - [ ] Mode-aware: block (data-driven) or OverrunError (clock-driven)
- [ ] **TO Analysis Engine**:
  - [ ] Notification queue setup
  - [ ] Data available notifications

### Task 4.4: Derived Bar Generation ✅
- [ ] Copy existing derived bar logic from DataUpkeepThread
- [ ] Progressive computation (5m as soon as 5 bars, 15m when 15 bars)
- [ ] Zero-copy read from session_data
- [ ] Write generated bars to session_data
- [ ] Configuration: `derived_intervals`, `auto_compute_derived`

### Task 4.5: Real-Time Indicator Calculation ✅
- [ ] Indicator calculation framework
- [ ] Support common indicators (RSI, SMA, EMA, MACD, etc.)
- [ ] Event-driven calculation (when new bar arrives)
- [ ] Store results in session_data
- [ ] Configuration: `realtime_indicators` (from config)

### Task 4.6: Event-Driven Processing Loop ✅
- [ ] Main loop with notification queue
- [ ] Timeout handling (1s for graceful shutdown)
- [ ] Error handling per notification
- [ ] Logging and metrics

### Task 4.7: Performance Metrics Integration ✅
- [ ] Start timer on notification receive
- [ ] Record processing duration
- [ ] Track: min, max, avg, count
- [ ] Integration with PerformanceMetrics

### Task 4.8: Cleanup & Testing ✅
- [ ] Remove all quality-related code
- [ ] Remove session lifecycle code
- [ ] Remove prefetch worker integration
- [ ] Verify zero backward compatibility
- [ ] Update PROGRESS.md

---

## 🗑️ Code to Remove

### Session Lifecycle Management
- `_run_upkeep_loop()` - EOD detection, activation, deactivation
- `_check_eod_and_advance()` - Market close detection
- `_deactivate_session()` - Session deactivation
- `_activate_session()` - Session activation
- `_activate_day_and_prefetch()` - Day activation + prefetch
- `_check_initial_activation()` - First-day activation
- `_handle_stream_exhaustion()` - Stream end detection
- `_session_activated_for_day` flag

### Quality & Gap Management
- `calculate_session_quality()` import and calls
- `detect_gaps()` import and calls
- `GapInfo`, `merge_overlapping_gaps` imports
- Gap detection logic throughout
- `_failed_gaps` tracking
- All quality metric updates

### Prefetch Coordination
- `PrefetchWorker` import and instantiation
- `self._prefetch_worker`
- All prefetch-related calls

### Other
- `_build_stream_inventory()` - Not needed for pure processing
- Speed multiplier scaling for check interval - No longer polling
- `_check_interval` - No longer periodic

---

## ✅ Code to Keep & Refactor

### Derived Bar Generation
- `compute_all_derived_intervals()` - Core logic
- Progressive computation logic
- Configuration reading (`derived_intervals`, `auto_compute_derived`)

### Thread Infrastructure
- Thread start/stop mechanics
- Configuration from SystemManager
- SessionData reference
- Error handling patterns

---

## 📊 Expected Outcome

### New DataProcessor
- **~400-600 lines** (down from 1,319)
- **Zero backward compatibility**
- **Event-driven architecture**
- **Bidirectional synchronization**
- **Clean separation of concerns**

### Integration Points
- ✅ SessionCoordinator sends notifications
- ✅ DataProcessor processes and signals ready
- ✅ Analysis Engine receives notifications
- ✅ SessionData stores all data (zero-copy access)

---

## 🚀 Success Criteria

1. ✅ DataProcessor only handles derived bars + real-time indicators
2. ✅ No quality management code
3. ✅ No session lifecycle code
4. ✅ Event-driven with notification queue
5. ✅ Bidirectional sync with coordinator
6. ✅ Notification system to analysis engine
7. ✅ Zero-copy data access
8. ✅ Mode-aware (data-driven vs clock-driven)
9. ✅ Performance metrics integrated
10. ✅ Clean, maintainable code

---

## 📚 Reference

- **SESSION_ARCHITECTURE.md**: Lines 1330-1360, 1670-1687
- **Phase 3 Complete**: Session Coordinator (1,691 lines)
- **Phase 1 Complete**: SessionData, StreamSubscription, PerformanceMetrics
- **Phase 2 Complete**: SessionConfig, TimeManager

---

**Next**: Begin implementation with Task 4.1!
