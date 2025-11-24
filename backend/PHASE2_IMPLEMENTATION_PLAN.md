# Phase 2: Data-Upkeep Thread - Implementation Plan

## Objective

Implement a background thread that maintains data quality and completeness by detecting gaps, filling missing bars, and computing derived bars.

---

## Timeline

**Duration**: 3 weeks  
**Start**: After Phase 1 completion ✅  
**Complexity**: Medium-High (thread coordination)

**Week 1**: Core thread + gap detection  
**Week 2**: Gap filling + retry mechanism  
**Week 3**: Derived bars + testing

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│              BacktestStreamCoordinator                       │
│                                                              │
│  ┌────────────────────┐      ┌─────────────────────────┐   │
│  │ Main Coordinator   │      │ Data-Upkeep Thread      │   │
│  │ Thread             │      │ (NEW)                   │   │
│  │                    │      │                         │   │
│  │ • Stream data      │      │ • Check gaps            │   │
│  │ • Advance time     │      │ • Fill missing bars     │   │
│  │ • Write to         │◄────►│ • Compute derived       │   │
│  │   session_data     │      │ • Update bar_quality    │   │
│  │                    │      │ • Write to session_data │   │
│  └────────────────────┘      └─────────────────────────┘   │
│           │                              │                  │
│           └──────────┬───────────────────┘                  │
│                      │                                      │
│                      ▼                                      │
│              session_data                                   │
│              (Thread-safe)                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Components to Implement

### 1. DataUpkeepThread Class

**File**: `app/managers/data_manager/data_upkeep_thread.py`

**Responsibilities**:
1. Run in background thread
2. Check data quality every minute
3. Coordinate with session_data
4. Handle shutdown gracefully

**Key Methods**:
```python
class DataUpkeepThread:
    def __init__(self, session_data, system_manager, data_repository)
    def start() -> None
    def stop() -> None
    def _upkeep_worker() -> None  # Main thread loop
    async def _check_bar_completeness(symbol) -> float
    async def _fill_missing_bars(symbol, gaps) -> int
    async def _compute_derived_bars(symbol) -> None
```

**Configuration**:
```python
# In settings.py
DATA_UPKEEP_CHECK_INTERVAL_SECONDS = 60
DATA_UPKEEP_RETRY_MISSING_BARS = True
DATA_UPKEEP_MAX_RETRIES = 5
DATA_UPKEEP_ENABLED = True
```

---

### 2. Gap Detection Logic

**File**: `app/managers/data_manager/gap_detection.py`

**Functionality**:
- Identify missing 1-minute bars
- Calculate expected bar count
- Return list of missing timestamps

**Algorithm**:
```python
def detect_gaps(
    symbol: str,
    session_start: datetime,
    current_time: datetime,
    existing_bars: List[BarData]
) -> List[GapInfo]:
    """
    Detect gaps in 1-minute bars.
    
    Returns:
        List of gaps with start/end timestamps
    """
    # 1. Generate expected timestamps (every minute)
    expected_timestamps = generate_minute_timestamps(
        session_start, 
        current_time
    )
    
    # 2. Get actual timestamps from existing bars
    actual_timestamps = {bar.timestamp for bar in existing_bars}
    
    # 3. Find missing timestamps
    missing = expected_timestamps - actual_timestamps
    
    # 4. Group into consecutive gaps
    gaps = group_consecutive_timestamps(missing)
    
    return gaps
```

**Data Structure**:
```python
@dataclass
class GapInfo:
    symbol: str
    start_time: datetime
    end_time: datetime
    bar_count: int  # Number of missing bars
    retry_count: int = 0
```

---

### 3. Bar Quality Metric

**Calculation**:
```python
def calculate_bar_quality(
    session_start: datetime,
    current_time: datetime,
    actual_bar_count: int
) -> float:
    """
    Calculate bar quality as percentage of expected bars present.
    
    Returns:
        Quality percentage (0-100)
    """
    # Expected number of 1-minute bars
    expected_count = (current_time - session_start).total_seconds() / 60
    
    if expected_count == 0:
        return 100.0
    
    # Quality percentage
    quality = (actual_bar_count / expected_count) * 100
    
    return min(quality, 100.0)
```

**Update in session_data**:
```python
# In SymbolSessionData
symbol_data.bar_quality = calculate_bar_quality(
    session_start,
    current_time,
    len(symbol_data.bars_1m)
)
```

---

### 4. Gap Filling Mechanism

**Process**:
1. Detect gaps
2. Query database for missing bars
3. Insert into session_data
4. Update bar_quality
5. Retry if unsuccessful

**Implementation**:
```python
async def fill_missing_bars(
    symbol: str,
    gap: GapInfo,
    data_repository,
    session_data
) -> int:
    """
    Fill a gap by fetching bars from database.
    
    Returns:
        Number of bars filled
    """
    # 1. Query database
    try:
        bars = await data_repository.get_bars(
            symbol=symbol,
            start=gap.start_time,
            end=gap.end_time,
            interval=1  # 1-minute bars
        )
    except Exception as e:
        logger.error(f"Failed to fetch bars: {e}")
        return 0
    
    if not bars:
        logger.warning(f"No bars found for gap: {gap}")
        return 0
    
    # 2. Insert into session_data
    await session_data.add_bars_batch(symbol, bars)
    
    logger.info(
        f"Filled {len(bars)} bars for {symbol} "
        f"from {gap.start_time} to {gap.end_time}"
    )
    
    return len(bars)
```

**Retry Logic**:
```python
# Track failed gaps for retry
failed_gaps: Dict[str, List[GapInfo]] = defaultdict(list)

# In upkeep loop
for symbol in active_symbols:
    gaps = detect_gaps(symbol, ...)
    
    for gap in gaps:
        if gap.retry_count >= MAX_RETRIES:
            logger.error(f"Max retries reached for gap: {gap}")
            continue
        
        filled_count = await fill_missing_bars(symbol, gap, ...)
        
        if filled_count < gap.bar_count:
            # Partial fill or failure - retry later
            gap.retry_count += 1
            failed_gaps[symbol].append(gap)
```

---

### 5. Derived Bars Computation

**File**: `app/managers/data_manager/derived_bars.py`

**Functionality**:
- Compute 5m, 15m, 30m, 1h bars from 1m bars
- OHLCV aggregation
- Store in session_data.bars_derived

**Algorithm**:
```python
def compute_derived_bars(
    bars_1m: List[BarData],
    interval: int
) -> List[BarData]:
    """
    Compute derived bars from 1-minute bars.
    
    Args:
        bars_1m: List of 1-minute bars
        interval: Interval in minutes (5, 15, 30, 60)
    
    Returns:
        List of derived bars
    """
    derived = []
    
    # Group 1m bars into N-minute chunks
    for i in range(0, len(bars_1m), interval):
        chunk = bars_1m[i:i+interval]
        
        if len(chunk) < interval:
            # Incomplete bar - skip
            continue
        
        # Aggregate OHLCV
        derived_bar = BarData(
            symbol=chunk[0].symbol,
            timestamp=chunk[0].timestamp,  # Start of interval
            open=chunk[0].open,
            high=max(b.high for b in chunk),
            low=min(b.low for b in chunk),
            close=chunk[-1].close,
            volume=sum(b.volume for b in chunk)
        )
        
        derived.append(derived_bar)
    
    return derived
```

**Auto-Computation Trigger**:
```python
# In DataUpkeepThread
async def _update_derived_bars(self, symbol: str):
    """Recompute derived bars when 1m bars updated."""
    
    symbol_data = await self.session_data.get_symbol_data(symbol)
    
    if not symbol_data or not symbol_data.bars_updated:
        return
    
    # Get 1m bars
    bars_1m = list(symbol_data.bars_1m)
    
    # Compute for configured intervals
    for interval in self.derived_intervals:
        derived = compute_derived_bars(bars_1m, interval)
        
        # Store in session_data
        async with self.session_data._lock:
            symbol_data.bars_derived[interval] = derived
    
    # Reset update flag
    symbol_data.bars_updated = False
    
    logger.debug(
        f"Updated derived bars for {symbol}: "
        f"intervals={self.derived_intervals}"
    )
```

---

## Thread Coordination

### Synchronization

Both threads access `session_data`:
- **Main thread**: Writes bars as they stream
- **Upkeep thread**: Fills gaps, computes derived

**Solution**: `asyncio.Lock` in session_data ensures atomicity

```python
# In session_data
async with self._lock:
    # Only one thread can modify data at a time
    symbol_data.bars_1m.append(bar)
```

### Communication

**Flags**:
```python
# In SymbolSessionData
bars_updated: bool = False  # Set by main thread
bars_checked: bool = False  # Set by upkeep thread
```

**Usage**:
```python
# Main thread
await session_data.add_bar(symbol, bar)
# Automatically sets bars_updated = True

# Upkeep thread
if symbol_data.bars_updated:
    # Recompute derived bars
    await _update_derived_bars(symbol)
```

---

## Configuration

### New Settings

Add to `app/config/settings.py`:

```python
# Data Upkeep Thread Configuration
DATA_UPKEEP_ENABLED: bool = True
DATA_UPKEEP_CHECK_INTERVAL_SECONDS: int = 60
DATA_UPKEEP_RETRY_MISSING_BARS: bool = True
DATA_UPKEEP_MAX_RETRIES: int = 5

# Derived Bars Configuration
DATA_UPKEEP_DERIVED_INTERVALS: List[int] = [5, 15]  # Minutes
DATA_UPKEEP_AUTO_COMPUTE_DERIVED: bool = True
```

---

## Integration with BacktestStreamCoordinator

### Initialization

```python
# In BacktestStreamCoordinator.__init__
from app.managers.data_manager.data_upkeep_thread import DataUpkeepThread

self._upkeep_thread = DataUpkeepThread(
    session_data=self._session_data,
    system_manager=self._system_manager,
    data_repository=self._data_repository  # Pass repository
)
```

### Lifecycle

```python
# In start_worker
def start_worker(self):
    # Start main coordinator thread
    self._worker_thread = threading.Thread(
        target=self._merge_worker,
        daemon=True
    )
    self._worker_thread.start()
    
    # Start upkeep thread
    if settings.DATA_UPKEEP_ENABLED:
        self._upkeep_thread.start()
        logger.info("Data-upkeep thread started")

# In shutdown
def shutdown(self):
    # Stop upkeep thread first
    if self._upkeep_thread:
        self._upkeep_thread.stop()
    
    # Stop main thread
    self._shutdown.set()
    if self._worker_thread:
        self._worker_thread.join(timeout=5.0)
```

---

## Testing Strategy

### Unit Tests

**File**: `app/managers/data_manager/tests/test_data_upkeep.py`

```python
@pytest.mark.asyncio
async def test_gap_detection():
    """Test gap detection identifies missing bars."""
    # Create bars with gaps
    bars = [
        BarData(timestamp=datetime(2025, 1, 1, 9, 30), ...),
        # Missing 9:31
        BarData(timestamp=datetime(2025, 1, 1, 9, 32), ...),
    ]
    
    gaps = detect_gaps(
        "AAPL",
        datetime(2025, 1, 1, 9, 30),
        datetime(2025, 1, 1, 9, 33),
        bars
    )
    
    assert len(gaps) == 1
    assert gaps[0].bar_count == 1


@pytest.mark.asyncio
async def test_bar_quality_calculation():
    """Test bar quality metric calculation."""
    quality = calculate_bar_quality(
        session_start=datetime(2025, 1, 1, 9, 30),
        current_time=datetime(2025, 1, 1, 10, 30),  # 60 minutes
        actual_bar_count=58  # 2 missing
    )
    
    assert quality == pytest.approx(96.67, rel=0.1)


@pytest.mark.asyncio
async def test_derived_bars_computation():
    """Test 5-minute bars computed from 1-minute bars."""
    # Create 10 1-minute bars
    bars_1m = [
        BarData(
            timestamp=datetime(2025, 1, 1, 9, 30 + i),
            open=100 + i,
            high=101 + i,
            low=99 + i,
            close=100.5 + i,
            volume=1000
        )
        for i in range(10)
    ]
    
    # Compute 5-minute bars
    bars_5m = compute_derived_bars(bars_1m, interval=5)
    
    assert len(bars_5m) == 2
    assert bars_5m[0].open == 100
    assert bars_5m[0].close == 104.5
    assert bars_5m[0].volume == 5000
```

---

## Performance Considerations

### Upkeep Thread Impact

**Concern**: Background checking may slow down main thread

**Solution**:
- Lock is held for very short duration
- Main thread priority (upkeep yields)
- Configurable check interval (default: 60s)

### Memory Usage

**Concern**: Derived bars increase memory

**Solution**:
- Only compute configured intervals
- Limit to active symbols
- Clear on session roll

### Database Queries

**Concern**: Frequent gap filling queries

**Solution**:
- Batch queries where possible
- Cache failed queries (don't retry immediately)
- Limit concurrent queries

---

## Error Handling

### Gap Filling Failures

```python
try:
    filled = await fill_missing_bars(symbol, gap, ...)
except DatabaseError as e:
    logger.error(f"Database error filling gap: {e}")
    gap.retry_count += 1
except Exception as e:
    logger.exception(f"Unexpected error filling gap: {e}")
    # Don't retry unexpected errors
```

### Thread Failures

```python
# In _upkeep_worker
try:
    while not self._shutdown.is_set():
        # ... upkeep loop ...
except Exception as e:
    logger.critical(f"Upkeep thread crashed: {e}", exc_info=True)
    # Thread will exit - coordinator should detect and restart
```

---

## Success Criteria

- [ ] DataUpkeepThread runs independently
- [ ] Gaps detected within 1 minute of occurrence
- [ ] Missing bars filled automatically
- [ ] bar_quality metric accurate (±1%)
- [ ] Derived bars computed correctly
- [ ] No impact on main thread performance
- [ ] All unit tests passing (>95% coverage)
- [ ] Memory usage acceptable (<10% increase)

---

## Week-by-Week Breakdown

### Week 1: Core + Gap Detection
**Days 1-2**:
- Create DataUpkeepThread class
- Implement thread lifecycle (start/stop)
- Basic loop structure

**Days 3-4**:
- Implement gap_detection.py
- Implement bar_quality calculation
- Unit tests for gap detection

**Day 5**:
- Integration with session_data
- Testing and debugging

### Week 2: Gap Filling
**Days 1-2**:
- Implement gap filling logic
- Database query integration
- Error handling

**Days 3-4**:
- Implement retry mechanism
- Failed gap tracking
- Unit tests for gap filling

**Day 5**:
- Performance testing
- Optimization

### Week 3: Derived Bars + Testing
**Days 1-2**:
- Implement derived_bars.py
- OHLCV aggregation logic
- Auto-computation trigger

**Days 3-4**:
- Comprehensive integration testing
- Thread coordination testing
- Performance benchmarking

**Day 5**:
- Documentation
- Code review
- Final testing

---

## Migration Notes

### Backward Compatibility

Phase 2 is **additive** - no breaking changes:
- Phase 1 code continues to work
- Upkeep thread can be disabled via config
- Existing tests still pass

### Configuration

```python
# Disable upkeep thread if needed
DATA_UPKEEP_ENABLED = False  # Reverts to Phase 1 behavior
```

---

## Next: Phase 3

After Phase 2, Phase 3 will add:
- Historical bars for trailing days
- Session roll logic
- Historical data management

---

**Status**: 📋 Ready to implement  
**Prerequisites**: Phase 1 complete ✅  
**Timeline**: 3 weeks  
**Complexity**: Medium-High
