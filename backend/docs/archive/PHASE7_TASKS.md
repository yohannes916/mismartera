# Phase 7: Analysis Engine - Complete Task List

**Status**: 📋 Planning  
**Start Date**: November 28, 2025  
**Estimated Duration**: 3-5 days  

---

## 🎯 Objective

Create the Analysis Engine thread that consumes processed data from SessionData, executes trading strategies, generates signals, and makes trading decisions.

---

## 📋 Complete Task Breakdown

### **Task 7.1: Analysis Engine Architecture Design** ⏳
**Estimated Time**: 1-2 hours

**Subtasks**:
- [ ] Review SESSION_ARCHITECTURE.md Analysis Engine specification (lines 1435-1483)
- [ ] Design event-driven processing loop
- [ ] Design notification queue integration with DataProcessor
- [ ] Design StreamSubscription pattern (analysis engine signals ready to processor)
- [ ] Design strategy loading mechanism
- [ ] Design signal generation framework
- [ ] Document data access patterns (all from SessionData)
- [ ] Create PHASE7_DESIGN.md document

**Deliverables**:
- Complete architecture document
- Class structure diagram
- Data flow diagram
- Integration points documented

---

### **Task 7.2: Create AnalysisEngine Thread Skeleton** ⏳
**Estimated Time**: 1-2 hours

**Subtasks**:
- [ ] Create `app/threads/analysis_engine.py` file
- [ ] Define `AnalysisEngine` class (extends threading.Thread)
- [ ] Add constructor with dependencies:
  - `session_data: SessionData`
  - `system_manager: SystemManager`
  - `session_config: SessionConfig`
  - `metrics: PerformanceMetrics`
- [ ] Add thread lifecycle methods:
  - `run()` - Main entry point
  - `stop()` - Graceful shutdown
  - `join()` - Wait for completion
- [ ] Add notification queue for processor notifications
- [ ] Add StreamSubscription for signaling ready to processor
- [ ] Add configuration loading
- [ ] Add logging infrastructure

**Deliverables**:
- AnalysisEngine class skeleton (~200-300 lines)
- Thread control infrastructure
- Notification queue setup
- Configuration framework

---

### **Task 7.3: Implement Event-Driven Processing Loop** ⏳
**Estimated Time**: 2-3 hours

**Subtasks**:
- [ ] Implement `_processing_loop()` method
- [ ] Wait on notification queue (blocking with timeout)
- [ ] Parse notification tuples: `(symbol, interval, data_type)`
- [ ] Implement graceful shutdown logic
- [ ] Add mode detection (backtest vs live)
- [ ] Add speed multiplier awareness (data-driven vs clock-driven)
- [ ] Add error handling and recovery
- [ ] Add performance metrics recording
- [ ] Add debug logging throughout

**Processing Loop Flow**:
```python
while not self._stop_event.is_set():
    # 1. Wait for notification from processor
    notification = self._notification_queue.get(timeout=1.0)
    
    # 2. Process notification
    symbol, interval, data_type = notification
    
    # 3. Read data from SessionData (zero-copy)
    bars = self.session_data.get_bars(symbol, interval)
    quality = self.session_data.get_quality_metric(symbol, interval)
    
    # 4. Execute strategy
    signals = self._execute_strategy(symbol, interval, bars, quality)
    
    # 5. Signal ready to processor
    self._signal_ready_to_processor()
    
    # 6. Record metrics
    self.metrics.record_analysis_engine(start_time)
```

**Deliverables**:
- Complete event-driven loop
- Notification handling
- Mode-aware behavior
- Performance tracking

---

### **Task 7.4: Implement SessionData Access Layer** ⏳
**Estimated Time**: 1-2 hours

**Subtasks**:
- [ ] Implement `_read_bars()` - Read bars from SessionData (zero-copy)
- [ ] Implement `_read_historical_bars()` - Read trailing days
- [ ] Implement `_read_indicators()` - Read real-time indicators
- [ ] Implement `_read_historical_indicators()` - Read pre-calculated indicators
- [ ] Implement `_read_quality()` - Read quality metrics
- [ ] Add data validation (check if data exists)
- [ ] Add error handling for missing data
- [ ] Add caching for frequently accessed data (optional)

**Data Access Pattern**:
```python
# ALL data from SessionData - zero-copy
bars_1m = self.session_data.get_bars(symbol, "1m")
bars_5m = self.session_data.get_bars(symbol, "5m")
quality = self.session_data.get_quality_metric(symbol, "5m")
indicator = self.session_data.get_realtime_indicator(symbol, "rsi")
```

**Deliverables**:
- Complete data access methods
- Zero-copy reads
- Validation and error handling
- Performance optimization

---

### **Task 7.5: Implement Strategy Loading Framework** ⏳
**Estimated Time**: 3-4 hours

**Subtasks**:
- [ ] Design strategy interface/base class
- [ ] Create `BaseStrategy` abstract class:
  - `on_bar(symbol, interval, bar)` - Called when new bar arrives
  - `on_bars(symbol, interval, bars)` - Called with multiple bars
  - `generate_signals()` - Generate trading signals
  - `on_quality_update(symbol, interval, quality)` - Quality changes
- [ ] Implement strategy registration system
- [ ] Implement strategy configuration loading
- [ ] Add strategy lifecycle management (init, start, stop)
- [ ] Create example strategy (SimpleMovingAverage or similar)
- [ ] Add strategy validation
- [ ] Add error isolation (one strategy failure doesn't crash engine)

**Strategy Interface**:
```python
class BaseStrategy(ABC):
    @abstractmethod
    def on_bar(self, symbol: str, interval: str, bar: BarData):
        """Called when new bar arrives."""
        pass
    
    @abstractmethod
    def generate_signals(self) -> List[Signal]:
        """Generate trading signals."""
        pass
```

**Deliverables**:
- BaseStrategy abstract class
- Strategy loading mechanism
- Example strategy implementation
- Strategy lifecycle management

---

### **Task 7.6: Implement Signal Generation** ⏳
**Estimated Time**: 2-3 hours

**Subtasks**:
- [ ] Define `Signal` dataclass:
  - `symbol: str`
  - `action: str` (BUY, SELL, HOLD)
  - `quantity: int`
  - `price: float`
  - `timestamp: datetime`
  - `strategy_name: str`
  - `confidence: float` (0.0 to 1.0)
  - `metadata: Dict[str, Any]`
- [ ] Implement `_generate_signals()` method
- [ ] Add signal validation (check for valid symbols, quantities, etc.)
- [ ] Add signal aggregation (multiple strategies → combined signals)
- [ ] Add signal prioritization
- [ ] Add signal logging
- [ ] Store signals in SessionData or separate structure

**Signal Generation Flow**:
```python
def _generate_signals(self, symbol: str, interval: str):
    signals = []
    
    # Execute all active strategies
    for strategy in self._active_strategies:
        strategy_signals = strategy.generate_signals()
        signals.extend(strategy_signals)
    
    # Validate and filter
    valid_signals = self._validate_signals(signals)
    
    # Aggregate if needed
    final_signals = self._aggregate_signals(valid_signals)
    
    return final_signals
```

**Deliverables**:
- Signal dataclass
- Signal generation logic
- Signal validation
- Signal aggregation

---

### **Task 7.7: Implement Decision Making** ⏳
**Estimated Time**: 2-3 hours

**Subtasks**:
- [ ] Implement `_make_trading_decision()` method
- [ ] Add risk management checks:
  - Position size limits
  - Buying power validation
  - Max positions per symbol
  - Portfolio exposure limits
- [ ] Add quality filtering (e.g., only trade if quality >= threshold)
- [ ] Add decision logging
- [ ] Create `Decision` dataclass:
  - `signal: Signal`
  - `approved: bool`
  - `reason: str`
  - `timestamp: datetime`
- [ ] Implement decision history tracking

**Decision Making Flow**:
```python
def _make_trading_decision(self, signal: Signal) -> Decision:
    # 1. Check quality
    quality = self.session_data.get_quality_metric(signal.symbol, "5m")
    if quality < self.min_quality_threshold:
        return Decision(signal, approved=False, reason="Low quality")
    
    # 2. Check risk limits
    if not self._check_risk_limits(signal):
        return Decision(signal, approved=False, reason="Risk limits exceeded")
    
    # 3. Approve
    return Decision(signal, approved=True, reason="All checks passed")
```

**Deliverables**:
- Decision making logic
- Risk management checks
- Quality filtering
- Decision tracking

---

### **Task 7.8: Implement StreamSubscription Integration** ⏳
**Estimated Time**: 1 hour

**Subtasks**:
- [ ] Add `set_processor_subscription()` method (called by SystemManager)
- [ ] Implement `_signal_ready_to_processor()` method
- [ ] Add mode-aware ready signaling:
  - Data-driven: Always signal ready (blocks processor)
  - Clock-driven: Check if ready, raise OverrunError if not
- [ ] Add subscription to notification queue
- [ ] Test bidirectional sync with DataProcessor

**Integration Code**:
```python
def _signal_ready_to_processor(self):
    if not self._processor_subscription:
        return
    
    try:
        self._processor_subscription.signal_ready()
        logger.debug("Signaled ready to data processor")
    except Exception as e:
        logger.error(f"Error signaling ready: {e}", exc_info=True)
```

**Deliverables**:
- StreamSubscription integration
- Ready signaling logic
- Mode-aware behavior
- Error handling

---

### **Task 7.9: Wire into SystemManager** ⏳
**Estimated Time**: 1 hour

**Subtasks**:
- [ ] Update `app/managers/system_manager.py`:
  - Import AnalysisEngine
  - Create AnalysisEngine instance
  - Create notification queue
  - Create StreamSubscription for analysis-processor sync
  - Wire notification queue to DataProcessor
  - Wire subscription to AnalysisEngine and DataProcessor
  - Start AnalysisEngine thread
  - Update stop() method for cleanup
- [ ] Test initialization order
- [ ] Verify all wiring

**Integration in SystemManager**:
```python
# Create analysis engine
analysis_engine = AnalysisEngine(
    session_data=session_data,
    system_manager=self,
    session_config=self._session_config,
    metrics=self._performance_metrics
)

# Create queue and subscription
analysis_queue = queue.Queue()
analysis_subscription = StreamSubscription()

# Wire to processor
processor.set_analysis_engine_queue(analysis_queue)
processor.set_analysis_subscription(analysis_subscription)

# Wire to analysis engine
analysis_engine.set_notification_queue(analysis_queue)
analysis_engine.set_processor_subscription(analysis_subscription)

# Start
analysis_engine.start()
```

**Deliverables**:
- SystemManager integration
- Complete thread wiring
- Lifecycle management

---

### **Task 7.10: Update DataProcessor Integration** ⏳
**Estimated Time**: 30 minutes

**Subtasks**:
- [ ] Update `app/threads/data_processor.py`:
  - Add `set_analysis_subscription()` method
  - Add `_processor_subscription` reference
  - Update notification logic to wait for analysis engine in data-driven mode
  - Add OverrunError handling for clock-driven mode
- [ ] Test processor-analysis bidirectional sync
- [ ] Verify blocking behavior in data-driven mode
- [ ] Verify non-blocking in clock-driven mode

**Deliverables**:
- DataProcessor updates
- Bidirectional sync working
- Mode-aware behavior verified

---

### **Task 7.11: Implement Performance Metrics** ⏳
**Estimated Time**: 1 hour

**Subtasks**:
- [ ] Add `record_analysis_engine()` to PerformanceMetrics
- [ ] Track processing times
- [ ] Track signal generation count
- [ ] Track decision count
- [ ] Track approved vs rejected decisions
- [ ] Add metrics reporting
- [ ] Add statistics collection

**Metrics to Track**:
- Processing time per notification
- Signals generated per strategy
- Decisions made (approved/rejected)
- Quality-based rejections
- Risk limit rejections
- Average confidence scores

**Deliverables**:
- Complete metrics integration
- Statistics collection
- Reporting capabilities

---

### **Task 7.12: Create Example Strategies** ⏳
**Estimated Time**: 2-3 hours

**Subtasks**:
- [ ] Create `app/strategies/` directory
- [ ] Implement `SimpleMovingAverageStrategy`:
  - 5-period and 20-period SMA
  - Buy when 5 crosses above 20
  - Sell when 5 crosses below 20
- [ ] Implement `RSIStrategy`:
  - Buy when RSI < 30 (oversold)
  - Sell when RSI > 70 (overbought)
- [ ] Create strategy configuration format
- [ ] Add strategy testing utilities
- [ ] Document strategy creation guide

**Deliverables**:
- 2+ example strategies
- Strategy configuration
- Testing utilities
- Documentation

---

### **Task 7.13: Testing & Validation** ⏳
**Estimated Time**: 2-3 hours

**Subtasks**:
- [ ] Unit tests for AnalysisEngine
- [ ] Unit tests for strategies
- [ ] Integration tests (full pipeline):
  - Coordinator → Processor → Analysis Engine
- [ ] Test data-driven mode (blocking)
- [ ] Test clock-driven mode (non-blocking, OverrunError)
- [ ] Test signal generation
- [ ] Test decision making
- [ ] Test quality filtering
- [ ] Test risk management
- [ ] Performance benchmarking

**Test Scenarios**:
1. Single strategy, single symbol
2. Multiple strategies, single symbol
3. Multiple strategies, multiple symbols
4. Low quality data (signals rejected)
5. Risk limits exceeded (decisions rejected)
6. Data-driven mode blocking
7. Clock-driven mode OverrunError

**Deliverables**:
- Complete test suite
- Integration tests
- Performance benchmarks
- Test documentation

---

### **Task 7.14: Documentation** ⏳
**Estimated Time**: 1-2 hours

**Subtasks**:
- [ ] Create PHASE7_COMPLETE.md
- [ ] Update PROGRESS.md
- [ ] Document strategy creation process
- [ ] Document signal generation
- [ ] Document decision making
- [ ] Document integration points
- [ ] Create usage examples
- [ ] Update SESSION_ARCHITECTURE.md if needed

**Deliverables**:
- Complete documentation
- Usage examples
- Integration guide
- Strategy creation guide

---

## 📊 Task Summary

### By Category

**Architecture & Design** (2 tasks):
- Task 7.1: Architecture design
- Task 7.14: Documentation

**Core Implementation** (6 tasks):
- Task 7.2: Thread skeleton
- Task 7.3: Processing loop
- Task 7.4: Data access
- Task 7.5: Strategy framework
- Task 7.6: Signal generation
- Task 7.7: Decision making

**Integration** (3 tasks):
- Task 7.8: StreamSubscription
- Task 7.9: SystemManager wiring
- Task 7.10: DataProcessor updates

**Features & Testing** (3 tasks):
- Task 7.11: Performance metrics
- Task 7.12: Example strategies
- Task 7.13: Testing

**Total**: 14 tasks

---

## ⏱️ Time Estimates

| Phase | Estimated Time |
|-------|---------------|
| Design & Architecture | 1-2 hours |
| Core Implementation | 12-16 hours |
| Integration | 2-3 hours |
| Features & Testing | 5-8 hours |
| Documentation | 1-2 hours |
| **TOTAL** | **21-31 hours** |

**Estimated Duration**: 3-5 days (at 6-8 hours per day)

---

## 🎯 Success Criteria

1. ✅ AnalysisEngine thread running and receiving notifications
2. ✅ Strategy framework working (BaseStrategy, loading, execution)
3. ✅ Signal generation working
4. ✅ Decision making with risk management working
5. ✅ Quality filtering integrated
6. ✅ StreamSubscription bidirectional sync working
7. ✅ Data-driven mode blocks processor correctly
8. ✅ Clock-driven mode non-blocking with OverrunError
9. ✅ At least 2 example strategies implemented
10. ✅ Complete test suite passing
11. ✅ Full integration with SystemManager
12. ✅ Performance metrics tracking
13. ✅ Documentation complete
14. ✅ End-to-end pipeline working: Coordinator → Processor → Analysis Engine

---

## 🚀 Recommended Implementation Order

**Day 1** (6-8 hours):
- Task 7.1: Design
- Task 7.2: Skeleton
- Task 7.3: Processing loop
- Task 7.4: Data access

**Day 2** (6-8 hours):
- Task 7.5: Strategy framework
- Task 7.6: Signal generation
- Task 7.7: Decision making

**Day 3** (6-8 hours):
- Task 7.8: StreamSubscription
- Task 7.9: SystemManager wiring
- Task 7.10: DataProcessor updates
- Task 7.11: Performance metrics

**Day 4** (6-8 hours):
- Task 7.12: Example strategies
- Task 7.13: Testing (part 1)

**Day 5** (if needed, 4-6 hours):
- Task 7.13: Testing (part 2)
- Task 7.14: Documentation
- Final polish and cleanup

---

## 📚 Reference

- **SESSION_ARCHITECTURE.md**: Lines 1435-1483 (Analysis Engine specification)
- **Phase 4 Complete**: DataProcessor (source of notifications)
- **Phase 5 Complete**: DataQualityManager (quality scores)
- **Phase 6 Complete**: Integration patterns

---

**Status**: 📋 Ready to begin implementation!
