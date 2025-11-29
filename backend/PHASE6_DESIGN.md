# Phase 6: Integration & Testing - Design Document

**Status**: 🚧 In Progress  
**Start Date**: November 28, 2025  
**Estimated Duration**: 1-2 days  

---

## 🎯 Objective

Integrate the newly created DataProcessor and DataQualityManager into the system, removing the old DataUpkeepThread, and perform end-to-end testing.

---

## 📋 Current State

### What We Have ✅
- ✅ Phase 1: SessionData, StreamSubscription, PerformanceMetrics
- ✅ Phase 2: SessionConfig, TimeManager
- ✅ Phase 3: SessionCoordinator (complete event-driven orchestrator)
- ✅ Phase 4: DataProcessor (derived bars + real-time indicators)
- ✅ Phase 5: DataQualityManager (quality measurement + gap filling)

### What Needs Integration
- ⏳ SystemManager: Still using old DataUpkeepThread
- ⏳ SessionCoordinator: Doesn't notify new threads yet
- ⏳ Old DataUpkeepThread: Still in codebase

---

## 🔗 Integration Points

### 1. SystemManager Integration

**Current State** (lines 508-524):
```python
from app.managers.data_manager.data_upkeep_thread import DataUpkeepThread

if settings.DATA_UPKEEP_ENABLED:
    upkeep_thread = DataUpkeepThread(
        session_data=session_data,
        system_manager=self,
        data_manager=data_manager,
        data_repository=None
    )
    upkeep_thread.start()
    self._upkeep_thread = upkeep_thread
```

**Target State**:
```python
from app.threads.data_processor import DataProcessor
from app.threads.data_quality_manager import DataQualityManager

# Create DataProcessor
processor = DataProcessor(
    session_data=session_data,
    system_manager=self,
    session_config=self._session_config,
    metrics=self._performance_metrics
)

# Create DataQualityManager
quality_manager = DataQualityManager(
    session_data=session_data,
    system_manager=self,
    session_config=self._session_config,
    metrics=self._performance_metrics,
    data_manager=data_manager
)

# Set up subscriptions
processor_subscription = StreamSubscription()
processor.set_coordinator_subscription(processor_subscription)

# Set up analysis engine queue (when implemented)
# analysis_queue = queue.Queue()
# processor.set_analysis_engine_queue(analysis_queue)

# Start threads
processor.start()
quality_manager.start()

# Store references
self._data_processor = processor
self._quality_manager = quality_manager
self._processor_subscription = processor_subscription
```

### 2. SessionCoordinator Integration

**Current State**: 
- No notifications to processor/quality manager

**Target State**:
```python
# In SessionCoordinator.__init__():
self.data_processor: Optional['DataProcessor'] = None
self.quality_manager: Optional['DataQualityManager'] = None
self._processor_subscription: Optional[StreamSubscription] = None

# Setters (called by SystemManager):
def set_data_processor(self, processor, subscription):
    self.data_processor = processor
    self._processor_subscription = subscription

def set_quality_manager(self, quality_manager):
    self.quality_manager = quality_manager

# In _handle_bar() after adding to SessionData:
# Notify processor and quality manager
if self.data_processor:
    self.data_processor.notify_data_available(symbol, interval, bar.timestamp)
    
    # Wait for processor in data-driven mode
    if self.mode == "backtest" and self.speed == 0:
        self._processor_subscription.wait_until_ready()

if self.quality_manager:
    self.quality_manager.notify_data_available(symbol, interval, bar.timestamp)
    # No waiting - quality manager is non-blocking
```

### 3. Remove Old DataUpkeepThread

**Files to Update**:
- `app/managers/system_manager.py` - Remove import and usage
- Verify no other references exist

**Files to Keep** (for reference):
- `app/managers/data_manager/_backup/data_upkeep_thread.py.bak` - Backup

---

## 📝 Implementation Tasks

### Task 6.1: Update SystemManager ✅
- [ ] Update imports (DataProcessor, DataQualityManager)
- [ ] Remove DataUpkeepThread import
- [ ] Create DataProcessor instance
- [ ] Create DataQualityManager instance
- [ ] Set up StreamSubscription for processor
- [ ] Start both threads
- [ ] Store references in SystemManager
- [ ] Update cleanup logic in stop()

### Task 6.2: Update SessionCoordinator ✅
- [ ] Add processor and quality manager references
- [ ] Add setter methods
- [ ] Notify processor when bars arrive
- [ ] Notify quality manager when bars arrive
- [ ] Wait for processor in data-driven mode
- [ ] Handle OverrunError in clock-driven mode
- [ ] Update thread lifecycle (cleanup)

### Task 6.3: Wire Coordinator to Threads ✅
- [ ] SystemManager calls coordinator setters
- [ ] Pass processor reference
- [ ] Pass quality manager reference
- [ ] Pass processor subscription
- [ ] Verify initialization order

### Task 6.4: Remove Old Code ✅
- [ ] Verify no DataUpkeepThread references (except backup)
- [ ] Update any remaining imports
- [ ] Clean up unused code

### Task 6.5: Testing ✅
- [ ] Unit test: DataProcessor initialization
- [ ] Unit test: DataQualityManager initialization
- [ ] Integration test: Coordinator → Processor flow
- [ ] Integration test: Coordinator → Quality Manager flow
- [ ] End-to-end test: Full session lifecycle
- [ ] Performance test: Verify non-blocking behavior

### Task 6.6: Documentation ✅
- [ ] Update PROGRESS.md
- [ ] Create PHASE6_COMPLETE.md
- [ ] Update integration notes
- [ ] Document any issues/workarounds

---

## 🎨 Architecture After Integration

```
SystemManager
    │
    ├─ Creates SessionCoordinator
    ├─ Creates DataProcessor
    ├─ Creates DataQualityManager
    ├─ Creates StreamSubscription (processor ↔ coordinator)
    │
    └─ Wires Everything:
         coordinator.set_data_processor(processor, subscription)
         coordinator.set_quality_manager(quality_manager)

Session Flow:
    SessionCoordinator
         │
         ├─ Receives bar from stream
         ├─ Adds to SessionData
         │
         ├─ Notifies DataProcessor
         │   └─ Generate derived bars
         │   └─ Calculate real-time indicators
         │   └─ Signal ready
         │
         ├─ Notifies DataQualityManager (non-blocking)
         │   └─ Calculate quality %
         │   └─ Fill gaps (LIVE mode)
         │   └─ Propagate quality to derived
         │
         └─ Continue with next bar
```

---

## 🔧 Configuration Requirements

**SessionConfig**: Already has everything needed
- `data_upkeep.derived_intervals` - For DataProcessor
- `data_upkeep.auto_compute_derived` - Enable/disable derived bars
- `gap_filler.enable_session_quality` - For DataQualityManager
- `gap_filler.max_retries` - Gap fill retries
- `gap_filler.retry_interval_seconds` - Retry timing

**No config changes needed!**

---

## 🎯 Success Criteria

1. ✅ DataProcessor integrated and receiving notifications
2. ✅ DataQualityManager integrated and receiving notifications
3. ✅ StreamSubscription working (coordinator ↔ processor)
4. ✅ Data-driven mode blocks correctly
5. ✅ Clock-driven mode non-blocking
6. ✅ Quality manager non-blocking in all modes
7. ✅ Old DataUpkeepThread completely removed
8. ✅ All tests passing
9. ✅ No backward compatibility code
10. ✅ Documentation complete

---

## ⚠️ Critical Decisions

### 1. Initialization Order
**Decision**: SessionCoordinator → DataProcessor → DataQualityManager  
**Reason**: Coordinator must exist before setting up thread references  
**Implementation**: SystemManager creates in order, then wires together

### 2. StreamSubscription Lifecycle
**Decision**: One StreamSubscription per processor instance  
**Reason**: Each session needs independent coordination  
**Implementation**: Created in SystemManager, passed to both coordinator and processor

### 3. Analysis Engine Queue
**Decision**: Defer to Phase 7  
**Reason**: Analysis Engine not implemented yet  
**Implementation**: Placeholder in processor, will wire in Phase 7

### 4. Cleanup Order
**Decision**: Stop coordinator first, then processor/quality manager  
**Reason**: Coordinator feeds threads, stop source first  
**Implementation**: SystemManager.stop() stops in reverse order

---

## 🚀 Testing Strategy

### Unit Tests
- DataProcessor initialization and configuration
- DataQualityManager initialization and configuration
- StreamSubscription signal/wait behavior

### Integration Tests
- SystemManager creates all components correctly
- SessionCoordinator notifies threads
- StreamSubscription coordinates correctly
- Quality manager non-blocking behavior

### End-to-End Tests
- Full backtest session (data-driven mode)
- Full backtest session (clock-driven mode)
- Verify derived bars generated
- Verify quality calculated
- Verify gap filling (if applicable)

### Performance Tests
- Coordinator not blocked by quality manager
- Processor blocks coordinator only in data-driven mode
- Overall throughput maintained

---

## 📚 Reference

- **SESSION_ARCHITECTURE.md**: Architecture specification
- **PHASE4_COMPLETE.md**: DataProcessor design
- **PHASE5_COMPLETE.md**: DataQualityManager design
- **app/threads/session_coordinator.py**: Coordinator implementation
- **app/managers/system_manager.py**: System orchestration

---

**Next**: Begin implementation with Task 6.1!
