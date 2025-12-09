# Test Plan: Synchronization, Pause, and Performance Tracking

## Overview

Comprehensive test plan covering:
1. **Thread Synchronization** - Data-driven backpressure and clock-driven async behavior
2. **Pause Feature** - Both data-driven and clock-driven backtest modes
3. **Performance Counters** - Tracking and JSON output verification

## Test Hierarchy

```
Unit Tests
  ├── StreamSubscription behavior
  ├── Individual component waits
  └── State transitions

Integration Tests
  ├── Coordinator → Processor sync
  ├── Processor → Analysis sync
  └── Pause in both modes

E2E Tests
  ├── Full synchronization chain
  ├── Pause/resume workflows
  └── Performance counter accuracy
```

---

## 1. Unit Tests

### 1.1 StreamSubscription Tests

**File:** `tests/unit/test_stream_subscription.py`

#### Test: Data-Driven Mode Blocks Indefinitely
```python
def test_data_driven_blocks_indefinitely():
    """Verify data-driven mode blocks until signaled."""
    subscription = StreamSubscription(mode="data-driven", stream_id="test")
    
    # Start waiting in thread
    waited = threading.Event()
    def waiter():
        subscription.wait_until_ready()
        waited.set()
    
    thread = threading.Thread(target=waiter)
    thread.start()
    
    # Should still be waiting after 1 second
    time.sleep(1.0)
    assert not waited.is_set()
    
    # Signal ready
    subscription.signal_ready()
    
    # Should complete immediately
    thread.join(timeout=0.5)
    assert waited.is_set()
```

#### Test: Clock-Driven Mode Times Out
```python
def test_clock_driven_times_out():
    """Verify clock-driven mode respects timeout."""
    subscription = StreamSubscription(mode="clock-driven", stream_id="test")
    
    start = time.perf_counter()
    result = subscription.wait_until_ready(timeout=0.5)
    duration = time.perf_counter() - start
    
    assert result is False  # Timed out
    assert 0.4 < duration < 0.6  # Approximately 0.5s
```

#### Test: Overrun Detection
```python
def test_overrun_detection_clock_driven():
    """Verify overrun is detected when signal_ready called before reset."""
    subscription = StreamSubscription(mode="clock-driven", stream_id="test")
    
    # First signal
    subscription.signal_ready()
    assert subscription.get_overrun_count() == 0
    
    # Second signal before reset - should detect overrun
    subscription.signal_ready()
    assert subscription.get_overrun_count() == 1
    
    # Reset and signal again - no overrun
    subscription.reset()
    subscription.signal_ready()
    assert subscription.get_overrun_count() == 1  # Still 1, not incremented
```

#### Test: One-Shot Pattern
```python
def test_one_shot_pattern():
    """Verify signal→wait→reset cycle works correctly."""
    subscription = StreamSubscription(mode="data-driven", stream_id="test")
    
    # First cycle
    subscription.signal_ready()
    assert subscription.wait_until_ready() is True
    subscription.reset()
    
    # Should block again after reset
    result = subscription.wait_until_ready(timeout=0.1)
    # In data-driven, this blocks forever, so can't test timeout
    # But we can test that is_ready is False after reset
    assert not subscription.is_ready()
```

### 1.2 Pause/Resume Tests

**File:** `tests/unit/test_backtest_pause.py`

#### Test: Pause Event Mechanism
```python
def test_pause_event_blocks_streaming():
    """Verify _stream_paused event blocks streaming loop."""
    coordinator = SessionCoordinator(...)
    
    # Initially not paused
    assert not coordinator.is_paused()
    
    # Pause
    coordinator.pause_backtest()
    assert coordinator.is_paused()
    
    # Resume
    coordinator.resume_backtest()
    assert not coordinator.is_paused()
```

#### Test: SystemManager State Transitions
```python
def test_system_state_transitions():
    """Verify state transitions during pause/resume."""
    system_mgr = SystemManager()
    system_mgr.start("config.json")
    
    assert system_mgr.get_state() == SystemState.RUNNING
    
    # Pause
    system_mgr.pause()
    assert system_mgr.get_state() == SystemState.PAUSED
    assert system_mgr.is_paused()
    assert not system_mgr.is_running()
    
    # Resume
    system_mgr.resume()
    assert system_mgr.get_state() == SystemState.RUNNING
    assert not system_mgr.is_paused()
    assert system_mgr.is_running()
```

#### Test: Pause Only in Backtest Mode
```python
def test_pause_ignored_in_live_mode():
    """Verify pause is ignored in live mode."""
    system_mgr = SystemManager()
    system_mgr.start("live_config.json")  # Live mode
    
    assert system_mgr.mode == OperationMode.LIVE
    
    # Pause should return False and log warning
    result = system_mgr.pause()
    assert result is False
    assert system_mgr.get_state() == SystemState.RUNNING
```

---

## 2. Integration Tests

### 2.1 Coordinator → Processor Synchronization

**File:** `tests/integration/test_coordinator_processor_sync.py`

#### Test: Data-Driven Coordinator Waits for Processor
```python
@pytest.mark.asyncio
async def test_data_driven_coordinator_waits():
    """Verify coordinator blocks until processor signals ready."""
    # Setup system in data-driven mode (speed=0)
    system_mgr = create_test_system(speed_multiplier=0)
    
    # Track timing
    events = []
    
    # Mock processor that takes time
    original_process = system_mgr._data_processor._processing_loop
    def slow_processor():
        events.append(("processor_start", time.time()))
        time.sleep(0.5)  # Simulate processing
        events.append(("processor_signal", time.time()))
        original_process()
    
    system_mgr._data_processor._processing_loop = slow_processor
    
    # Start system and process one bar
    system_mgr.start()
    
    # Coordinator should wait for processor
    # Verify via events timeline
    assert events[0][0] == "processor_start"
    assert events[1][0] == "processor_signal"
    
    # Time between coordinator iterations should be >= processor time
    # (coordinator blocks waiting)
```

#### Test: Clock-Driven Coordinator Doesn't Wait
```python
@pytest.mark.asyncio
async def test_clock_driven_coordinator_async():
    """Verify coordinator doesn't wait in clock-driven mode."""
    # Setup system in clock-driven mode (speed>0)
    system_mgr = create_test_system(speed_multiplier=1.0)
    
    # Track if coordinator continues without waiting
    coordinator_iterations = []
    
    # Mock to track iterations
    original_advance = system_mgr._coordinator._streaming_phase
    def track_iterations():
        coordinator_iterations.append(time.time())
        original_advance()
    
    system_mgr._coordinator._streaming_phase = track_iterations
    
    # Start system
    system_mgr.start()
    time.sleep(2.0)  # Let it run
    
    # Should have multiple iterations without blocking
    # (at least 2 in 2 seconds with 1-minute simulation)
    assert len(coordinator_iterations) >= 2
```

#### Test: Processor → Analysis Synchronization
```python
@pytest.mark.asyncio
async def test_processor_waits_for_analysis():
    """Verify processor waits for analysis in data-driven mode."""
    system_mgr = create_test_system(speed_multiplier=0)
    
    # Track analysis timing
    analysis_times = []
    
    # Mock analysis that records timing
    original_analysis = system_mgr._analysis_engine._signal_ready_to_processor
    def track_analysis():
        analysis_times.append(time.time())
        original_analysis()
    
    system_mgr._analysis_engine._signal_ready_to_processor = track_analysis
    
    # Process multiple bars
    system_mgr.start()
    
    # Verify analysis completes before processor signals coordinator
    # Check logs or timing sequence
```

### 2.2 Pause in Both Modes

**File:** `tests/integration/test_pause_both_modes.py`

#### Test: Data-Driven Pause Stops Bar Processing
```python
@pytest.mark.asyncio
async def test_data_driven_pause_stops_bars():
    """Verify pause stops bar timestamp advancement."""
    system_mgr = create_test_system(speed_multiplier=0)
    system_mgr.start()
    
    time_mgr = system_mgr.get_time_manager()
    
    # Let it run a bit
    time.sleep(0.5)
    initial_time = time_mgr.get_current_time()
    
    # Pause
    system_mgr.pause()
    assert system_mgr.is_paused()
    
    # Wait and verify time doesn't advance
    time.sleep(1.0)
    paused_time = time_mgr.get_current_time()
    assert paused_time == initial_time  # No advancement
    
    # Resume
    system_mgr.resume()
    time.sleep(0.5)
    resumed_time = time_mgr.get_current_time()
    assert resumed_time > paused_time  # Advancement resumed
```

#### Test: Clock-Driven Pause Stops Time Intervals
```python
@pytest.mark.asyncio
async def test_clock_driven_pause_stops_intervals():
    """Verify pause stops 1-minute interval advancement."""
    system_mgr = create_test_system(speed_multiplier=360)  # Fast
    system_mgr.start()
    
    time_mgr = system_mgr.get_time_manager()
    
    # Let it advance a few minutes
    initial_time = time_mgr.get_current_time()
    time.sleep(1.0)  # Should advance several minutes
    before_pause = time_mgr.get_current_time()
    assert before_pause > initial_time
    
    # Pause
    system_mgr.pause()
    
    # Verify no advancement
    time.sleep(1.0)
    during_pause = time_mgr.get_current_time()
    assert during_pause == before_pause
    
    # Resume
    system_mgr.resume()
    time.sleep(1.0)
    after_resume = time_mgr.get_current_time()
    assert after_resume > during_pause
```

#### Test: Pause Blocks All Threads
```python
@pytest.mark.asyncio
async def test_pause_blocks_entire_pipeline():
    """Verify pause blocks coordinator, processor, and analysis."""
    system_mgr = create_test_system(speed_multiplier=0)
    
    # Track events in all threads
    events = {
        "coordinator": [],
        "processor": [],
        "analysis": []
    }
    
    # Instrument threads
    # ... add tracking to each component ...
    
    system_mgr.start()
    time.sleep(0.5)
    
    # Pause
    system_mgr.pause()
    pause_time = time.time()
    
    # Wait
    time.sleep(1.0)
    
    # Verify no events after pause_time
    for component, component_events in events.items():
        post_pause = [e for e in component_events if e['time'] > pause_time]
        assert len(post_pause) == 0, f"{component} continued after pause"
```

---

## 3. E2E Tests

### 3.1 Full Synchronization Chain

**File:** `tests/e2e/test_full_synchronization.py`

#### Test: Complete Backpressure Flow
```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_backpressure():
    """
    Verify complete synchronization chain:
    Coordinator → Processor → Analysis → Back to Coordinator
    """
    # Setup with real data
    system_mgr = SystemManager()
    system_mgr.start("tests/configs/data_driven_backtest.json")
    
    # Track full cycle
    cycle_times = []
    
    # Instrument to track one complete cycle
    original_advance = system_mgr._coordinator._streaming_phase
    def track_cycle():
        start = time.perf_counter()
        original_advance()
        duration = time.perf_counter() - start
        cycle_times.append(duration)
    
    system_mgr._coordinator._streaming_phase = track_cycle
    
    # Let system run for 10 cycles
    while len(cycle_times) < 10:
        time.sleep(0.1)
    
    # Verify cycles complete (backpressure working)
    assert len(cycle_times) == 10
    
    # Verify reasonable timing (not too fast, not stuck)
    avg_cycle = sum(cycle_times) / len(cycle_times)
    assert 0.001 < avg_cycle < 1.0  # Between 1ms and 1s
```

#### Test: No Data Loss Under Backpressure
```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_no_data_loss():
    """Verify all bars processed correctly under backpressure."""
    system_mgr = SystemManager()
    system_mgr.start("tests/configs/data_driven_backtest.json")
    
    # Track bars at each stage
    bars_sent = 0
    bars_processed = 0
    bars_analyzed = 0
    
    # Instrument pipeline
    # ... track bars through each stage ...
    
    # Run until complete
    # ...
    
    # Verify no loss
    assert bars_sent == bars_processed == bars_analyzed
```

### 3.2 Pause/Resume Workflows

**File:** `tests/e2e/test_pause_resume_workflows.py`

#### Test: Mid-Session Pause and Resume
```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mid_session_pause_resume():
    """Test pause/resume in middle of backtest session."""
    system_mgr = SystemManager()
    system_mgr.start("tests/configs/full_day_backtest.json")
    
    time_mgr = system_mgr.get_time_manager()
    
    # Run until 11:00 AM
    while time_mgr.get_current_time().time() < time(11, 0):
        time.sleep(0.1)
    
    # Pause
    pause_time = time_mgr.get_current_time()
    system_mgr.pause()
    
    # Verify state frozen
    time.sleep(2.0)
    assert time_mgr.get_current_time() == pause_time
    
    # Check all state preserved
    session_data = system_mgr.get_session_data()
    paused_bars = len(session_data.get_symbol_data("AAPL").bars["1m"].data)
    
    # Resume
    system_mgr.resume()
    
    # Run to 2:00 PM
    while time_mgr.get_current_time().time() < time(14, 0):
        time.sleep(0.1)
    
    # Verify continued correctly
    resumed_bars = len(session_data.get_symbol_data("AAPL").bars["1m"].data)
    assert resumed_bars > paused_bars
```

#### Test: Multiple Pause/Resume Cycles
```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_multiple_pause_resume():
    """Test multiple pause/resume cycles in one session."""
    system_mgr = SystemManager()
    system_mgr.start("tests/configs/backtest.json")
    
    for i in range(5):
        # Run
        time.sleep(1.0)
        
        # Pause
        system_mgr.pause()
        time.sleep(0.5)
        
        # Resume
        system_mgr.resume()
    
    # Verify system still healthy
    assert system_mgr.is_running()
    # Check data integrity
```

### 3.3 Performance Counter Verification

**File:** `tests/e2e/test_performance_counters.py`

#### Test: Performance Metrics Accuracy
```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_performance_metrics_accuracy():
    """Verify performance counters track correctly."""
    system_mgr = SystemManager()
    system_mgr.start("tests/configs/backtest.json")
    
    # Run for known duration
    start = time.perf_counter()
    time.sleep(5.0)
    actual_duration = time.perf_counter() - start
    
    # Get metrics
    metrics = system_mgr.get_performance_metrics()
    
    # Verify timing metrics
    assert metrics.session_duration is not None
    assert abs(metrics.session_duration - actual_duration) < 0.1  # Within 100ms
    
    # Verify bar counts
    # ...
```

#### Test: JSON Output Contains All Metrics
```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_json_output_complete():
    """Verify JSON output contains all expected metrics."""
    system_mgr = SystemManager()
    system_mgr.start("tests/configs/backtest.json")
    
    # Run for a bit
    time.sleep(2.0)
    
    # Get JSON output
    json_output = system_mgr.to_json()
    data = json.loads(json_output)
    
    # Verify structure
    assert "system_manager" in data
    assert "_state" in data["system_manager"]
    assert "_mode" in data["system_manager"]
    
    # Verify performance metrics present
    assert "performance_metrics" in data
    metrics = data["performance_metrics"]
    
    # Check key metrics
    required_fields = [
        "session_duration",
        "bars_processed",
        "processor_timing",
        "analysis_timing"
    ]
    for field in required_fields:
        assert field in metrics or any(field in str(metrics.values()))
```

#### Test: Overrun Counter Tracking
```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_overrun_counter_tracking():
    """Verify overrun counters work in clock-driven mode."""
    # Setup FAST clock-driven (likely to overrun)
    system_mgr = SystemManager()
    config = load_config("tests/configs/backtest.json")
    config["backtest_config"]["speed_multiplier"] = 1000  # Very fast
    system_mgr.start_with_config(config)
    
    # Run for a bit
    time.sleep(5.0)
    
    # Check if overruns detected
    json_output = system_mgr.to_json()
    data = json.loads(json_output)
    
    # Should have subscription info with overrun counts
    # ... verify overrun counter accessible in JSON ...
```

---

## 4. Performance Tests

**File:** `tests/performance/test_synchronization_overhead.py`

### Test: Synchronization Overhead Measurement
```python
@pytest.mark.performance
@pytest.mark.asyncio
async def test_sync_overhead_data_driven():
    """Measure overhead of synchronization in data-driven mode."""
    # Run with sync
    system_mgr = create_test_system(speed_multiplier=0)
    start = time.perf_counter()
    process_n_bars(system_mgr, 1000)
    with_sync = time.perf_counter() - start
    
    # Run without sync (mock wait to always return immediately)
    system_mgr._processor_subscription.wait_until_ready = lambda: True
    start = time.perf_counter()
    process_n_bars(system_mgr, 1000)
    without_sync = time.perf_counter() - start
    
    # Calculate overhead
    overhead = (with_sync - without_sync) / with_sync * 100
    
    # Should be < 5% overhead
    assert overhead < 5.0, f"Sync overhead too high: {overhead:.2f}%"
```

### Test: Pause/Resume Performance
```python
@pytest.mark.performance
@pytest.mark.asyncio
async def test_pause_resume_latency():
    """Measure pause/resume latency."""
    system_mgr = create_test_system()
    system_mgr.start()
    
    # Measure pause latency
    start = time.perf_counter()
    system_mgr.pause()
    pause_latency = time.perf_counter() - start
    
    # Measure resume latency
    start = time.perf_counter()
    system_mgr.resume()
    resume_latency = time.perf_counter() - start
    
    # Should be < 1ms each
    assert pause_latency < 0.001
    assert resume_latency < 0.001
```

---

## 5. Test Fixtures and Utilities

**File:** `tests/conftest.py`

```python
import pytest
from app.managers.system_manager import SystemManager
from app.models.session_config import SessionConfig

@pytest.fixture
def data_driven_system():
    """Create system in data-driven mode."""
    config = create_test_config(speed_multiplier=0)
    system_mgr = SystemManager()
    system_mgr.start_with_config(config)
    yield system_mgr
    system_mgr.stop()

@pytest.fixture
def clock_driven_system():
    """Create system in clock-driven mode."""
    config = create_test_config(speed_multiplier=360)
    system_mgr = SystemManager()
    system_mgr.start_with_config(config)
    yield system_mgr
    system_mgr.stop()

@pytest.fixture
def mock_subscription():
    """Create mock StreamSubscription for testing."""
    return StreamSubscription(mode="data-driven", stream_id="test")

def create_test_config(speed_multiplier: float) -> dict:
    """Create test configuration."""
    return {
        "session_name": "test_session",
        "mode": "backtest",
        "exchange_group": "US_EQUITY",
        "asset_class": "EQUITY",
        "backtest_config": {
            "start_date": "2025-01-01",
            "end_date": "2025-01-05",
            "speed_multiplier": speed_multiplier
        },
        "session_data_config": {
            "symbols": ["AAPL"],
            "streams": ["bars:AAPL:1m"]
        }
    }
```

---

## 6. Test Execution Plan

### Phase 1: Unit Tests (Week 1)
- [ ] StreamSubscription tests (all modes)
- [ ] Pause/resume state transitions
- [ ] Individual component behavior

### Phase 2: Integration Tests (Week 2)
- [ ] Coordinator-Processor sync
- [ ] Processor-Analysis sync  
- [ ] Pause in both modes
- [ ] Mid-session symbol addition

### Phase 3: E2E Tests (Week 3)
- [ ] Full synchronization chain
- [ ] Pause/resume workflows
- [ ] Performance counter validation
- [ ] JSON output verification

### Phase 4: Performance Tests (Week 4)
- [ ] Synchronization overhead
- [ ] Pause/resume latency
- [ ] Throughput under backpressure
- [ ] Memory usage during pause

### Phase 5: Regression Tests (Ongoing)
- [ ] Run full suite on every commit
- [ ] Benchmark against baseline
- [ ] Track metrics over time

---

## 7. Success Criteria

### Synchronization
- ✅ Data-driven mode: Coordinator blocks until processor ready
- ✅ Clock-driven mode: Coordinator continues async
- ✅ Overrun detection works in clock-driven
- ✅ No data loss under backpressure
- ✅ < 5% overhead for synchronization

### Pause Feature
- ✅ Pause blocks time advancement in both modes
- ✅ State transitions correctly (RUNNING ↔ PAUSED)
- ✅ Resume continues from exact same point
- ✅ Multiple pause/resume cycles work
- ✅ < 1ms latency for pause/resume

### Performance Counters
- ✅ All metrics tracked accurately
- ✅ JSON output contains complete data
- ✅ Overrun counters increment correctly
- ✅ Timing metrics within 5% of actual

---

## 8. CI/CD Integration

### GitHub Actions Workflow
```yaml
name: Synchronization Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run unit tests
        run: pytest tests/unit/test_stream_subscription.py -v
  
  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run integration tests
        run: pytest tests/integration/ -v --timeout=30
  
  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run E2E tests
        run: pytest tests/e2e/ -v --timeout=60
```

---

## 9. Monitoring and Debugging

### Test Instrumentation
- Add detailed logging to all tests
- Capture timing data for analysis
- Record state transitions
- Track memory usage

### Debugging Failed Tests
1. Check logs for timing issues
2. Verify state transitions
3. Check for race conditions
4. Review performance metrics

### Performance Benchmarking
- Establish baseline metrics
- Track over time
- Alert on regressions
- Compare modes (data vs clock)

---

## Summary

This test plan provides comprehensive coverage of:
- ✅ **Thread synchronization** (data-driven backpressure, clock-driven async)
- ✅ **Pause feature** (both backtest modes, state management)
- ✅ **Performance tracking** (counters, JSON output, accuracy)

**Estimated Effort:** 4 weeks for complete implementation
**Coverage Target:** >90% for all synchronization code
**Regression Prevention:** CI/CD integration with every commit
