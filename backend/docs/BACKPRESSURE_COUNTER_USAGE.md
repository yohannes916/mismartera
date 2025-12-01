# Backpressure Counter Usage Guide

## Overview

Two 64-bit counters track pipeline bottlenecks by measuring when producers are ready but consumers haven't signaled readiness yet.

## Counter 1: Coordinator → DataProcessor Backpressure

**Location**: `app/threads/session_coordinator.py` or `app/managers/data_manager/backtest_stream_coordinator.py`

**When to Increment**: Before delivering data, check if DataProcessor is ready. If not ready, increment counter (data still flows in clock-driven mode).

```python
# In BacktestStreamCoordinator (or SessionCoordinator)
def _stream_data(self):
    """Stream data to DataProcessor with backpressure tracking."""
    
    # ... get next bar/tick/quote from queue ...
    
    # Check if DataProcessor is ready (non-blocking check)
    if not self._processor_subscription.is_ready():
        # DataProcessor hasn't signaled ready yet - backpressure detected!
        self.metrics.increment_backpressure_coordinator_to_processor()
        
        # Log warning if backpressure is high
        bp_count = self.metrics.get_backpressure_coordinator_to_processor()
        if bp_count % 1000 == 0:  # Log every 1000 events
            logger.warning(
                f"[BACKPRESSURE] Coordinator→Processor: {bp_count:,} events "
                f"(DataProcessor falling behind)"
            )
    
    # In clock-driven mode: deliver data anyway (time waits for no one)
    # In data-driven mode: would block until ready (handled by subscription)
    
    # Deliver data to session_data
    session_data.add_bar(symbol, bar)
    
    # Signal DataProcessor that data is available
    self._processor_subscription.signal_ready()
```

**Interpretation**:
- **0 events**: Perfect synchronization - DataProcessor keeps up
- **Low (<5% of bars)**: Acceptable - occasional catching up
- **Medium (5-20%)**: Warning - DataProcessor is slower than coordinator
- **High (>20%)**: Critical - DataProcessor is bottleneck, consider optimization

---

## Counter 2: DataProcessor → AnalysisEngine Backpressure

**Location**: `app/threads/data_processor.py`

**When to Increment**: After computing derived bars, check if AnalysisEngine is ready before notifying. If not ready, increment counter.

```python
# In DataProcessor
def _process_derived_bars(self, symbol: str):
    """Compute derived bars and notify AnalysisEngine with backpressure tracking."""
    
    # ... compute derived bars ...
    
    # Check if AnalysisEngine is ready for this symbol (non-blocking check)
    if not self._analysis_subscription.is_ready():
        # AnalysisEngine hasn't signaled ready yet - backpressure detected!
        self.metrics.increment_backpressure_processor_to_analysis()
        
        # Log warning if backpressure is high
        bp_count = self.metrics.get_backpressure_processor_to_analysis()
        if bp_count % 500 == 0:  # Log every 500 events
            logger.warning(
                f"[BACKPRESSURE] Processor→Analysis: {bp_count:,} events "
                f"(AnalysisEngine falling behind)"
            )
    
    # In clock-driven mode: send notification anyway (time-sensitive)
    # In data-driven mode: would block until ready (handled by subscription)
    
    # Notify AnalysisEngine that derived bars are available
    self._notification_queue.put((symbol, interval, 'bar'))
```

**Interpretation**:
- **0 events**: Perfect - AnalysisEngine keeps up with all updates
- **Low (<10% of updates)**: Good - strategies processing efficiently
- **Medium (10-30%)**: Warning - AnalysisEngine slower than data arrival
- **High (>30%)**: Critical - Strategy computation is bottleneck

---

## Integration Points

### 1. BacktestStreamCoordinator

```python
# app/managers/data_manager/backtest_stream_coordinator.py

async def _stream_bars(self):
    """Stream bars chronologically."""
    for bar in self._get_next_bars():
        # Check backpressure before delivery
        if not self._processor_subscription.is_ready():
            self.metrics.increment_backpressure_coordinator_to_processor()
        
        # Deliver bar
        self.session_data.add_bar(bar.symbol, bar)
        
        # Signal processor
        self._processor_subscription.signal_ready()
```

### 2. DataProcessor

```python
# app/threads/data_processor.py

def _notify_analysis_engine(self, symbol: str, interval: str):
    """Notify AnalysisEngine with backpressure tracking."""
    # Check backpressure before notification
    if not self._analysis_subscription.is_ready():
        self.metrics.increment_backpressure_processor_to_analysis()
    
    # Send notification
    self._notification_queue.put((symbol, interval, 'bar'))
```

---

## Viewing Backpressure Metrics

### CLI Command
```bash
system@mismartera: system status
```

### Performance Report Output
```
Performance Metrics Summary:
==================================================
...

Pipeline Backpressure (Bottlenecks):
  - Coordinator→Processor: 1,234 events
    (DataProcessor slower than Coordinator)
  - Processor→Analysis: 567 events
    (AnalysisEngine slower than DataProcessor)

==================================================
```

---

## Optimization Actions Based on Counters

### If Coordinator→Processor is High:
1. **DataProcessor too slow**:
   - Profile `compute_derived_bars()` function
   - Reduce derived intervals (less computation)
   - Optimize bar computation algorithms
   - Consider batch processing

2. **Too many symbols/intervals**:
   - Reduce number of active symbols
   - Reduce derived interval count
   - Prioritize important intervals

### If Processor→Analysis is High:
1. **AnalysisEngine too slow**:
   - Profile strategy computation
   - Simplify strategy logic
   - Reduce indicator calculations
   - Optimize hot path (zero-copy access)

2. **Too many strategies**:
   - Reduce active strategy count
   - Disable expensive strategies
   - Run strategies on fewer intervals

### If Both are High:
- **System overload**: Reduce data volume or computational complexity
- **Clock-driven speed too fast**: Lower backtest speed multiplier
- **Hardware limitation**: Upgrade CPU or optimize critical paths

---

## Zero-Copy Optimization Impact

With the zero-copy implementation, backpressure should **decrease significantly**:

**Before Zero-Copy** (with list copying):
- `Coordinator→Processor`: ~5-15% of bars (moderate backpressure)
- `Processor→Analysis`: ~20-40% of updates (high backpressure)

**After Zero-Copy** (direct references):
- `Coordinator→Processor`: <2% of bars (minimal backpressure)
- `Processor→Analysis`: <5% of updates (low backpressure)

**Expected Improvement**: 3-8x reduction in backpressure events

---

## Technical Notes

1. **Counter Type**: 64-bit integer (`int` in Python)
   - Max value: 9,223,372,036,854,775,807
   - Overflow impossible for realistic workloads
   - Thread-safe via Python GIL

2. **Performance Overhead**: Negligible
   - Simple integer increment (~1-2 CPU cycles)
   - Non-blocking `is_ready()` check (~10-20 CPU cycles)
   - Total overhead: <50 nanoseconds per check

3. **Clock-Driven vs Data-Driven**:
   - **Clock-driven**: Counter increments, data flows anyway
   - **Data-driven**: Would block instead (counter not incremented)
   - Counter only meaningful in clock-driven/live modes

4. **Difference from Overrun**:
   - **Backpressure**: Producer checks consumer readiness BEFORE delivery
   - **Overrun**: Producer signals BEFORE previous data consumed
   - Both indicate consumer slowness, measured at different points

---

## Example: Healthy Pipeline

```
Performance Metrics Summary:
==================================================
Analysis Engine:
  - Cycles: 10,000
  - Min: 0.50 ms | Max: 2.00 ms | Avg: 0.75 ms

Data Processor:
  - Items: 50,000
  - Min: 0.10 ms | Max: 0.50 ms | Avg: 0.20 ms

Pipeline Backpressure (Bottlenecks):
  - Coordinator→Processor: 123 events  (0.25% of 50,000 bars)
  - Processor→Analysis: 45 events      (0.45% of 10,000 cycles)

==================================================
```
✅ **Interpretation**: Excellent performance, negligible backpressure

---

## Example: Bottlenecked Pipeline

```
Performance Metrics Summary:
==================================================
Analysis Engine:
  - Cycles: 10,000
  - Min: 5.00 ms | Max: 50.00 ms | Avg: 15.00 ms  ⚠️ SLOW!

Data Processor:
  - Items: 50,000
  - Min: 0.10 ms | Max: 0.50 ms | Avg: 0.20 ms

Pipeline Backpressure (Bottlenecks):
  - Coordinator→Processor: 234 events    (0.47% - OK)
  - Processor→Analysis: 8,500 events     (85% - CRITICAL!) ❌

==================================================
```
❌ **Interpretation**: AnalysisEngine is critical bottleneck, needs optimization

**Action**: Profile and optimize strategy computation or reduce strategy complexity
