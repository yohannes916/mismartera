# Phase 3: Session Coordinator Rewrite - Implementation Plan

**Estimated Time**: 5-7 days  
**Complexity**: High (Core system component)  
**Status**: 🚧 Ready to start

---

## Overview

The Session Coordinator is the central orchestrator for the entire session lifecycle. It manages:
- Historical data loading and updating
- Historical indicator calculation
- Queue loading (backtest/live)
- Session activation and streaming
- Time advancement (backtest mode)
- End-of-session logic

**Critical Dependencies**:
- ✅ SessionData (Phase 1.1) - Unified data store
- ✅ StreamSubscription (Phase 1.2) - Thread synchronization
- ✅ PerformanceMetrics (Phase 1.3) - Monitoring
- ✅ SessionConfig (Phase 2.1) - Configuration
- ✅ TimeManager (Phase 2.2) - Time/calendar with caching

---

## Implementation Breakdown

### Task 3.1: Project Setup & Backup (1-2 hours)

**Actions**:
1. ✅ Back up existing coordinator file
2. Create new session_coordinator.py structure
3. Set up imports and class skeleton
4. Create basic __init__ method with dependencies

**Files**:
- Backup: `app/threads/_backup/session_coordinator.py.bak`
- New: `app/threads/session_coordinator.py`

**Dependencies Needed**:
```python
from app.data.session_data import SessionData
from app.threads.sync.stream_subscription import StreamSubscription
from app.monitoring.performance_metrics import PerformanceMetrics
from app.models.session_config import SessionConfig
# ... TimeManager, DataManager, etc.
```

---

### Task 3.2: Basic Lifecycle Loop (4-6 hours)

**Implement**:
```python
class SessionCoordinator:
    def __init__(self, system_manager, data_manager, session_config):
        # Initialize dependencies
        self.session_data = SessionData()
        self.metrics = PerformanceMetrics()
        self.subscriptions = {}  # StreamSubscription instances
        
    async def run(self):
        """Main coordinator loop"""
        while not self._stop_event.is_set():
            # Phase 1: Initialization
            await self._initialize_session()
            
            # Phase 2: Historical Management
            await self._manage_historical_data()
            
            # Phase 3: Queue Loading
            await self._load_queues()
            
            # Phase 4: Session Activation
            self._activate_session()
            
            # Phase 5: Streaming Phase
            await self._streaming_phase()
            
            # Phase 6: End-of-Session
            await self._end_session()
            
            # Check termination
            if self._should_terminate():
                break
```

**Methods to Implement**:
- `_initialize_session()` - Setup for new session
- `_should_terminate()` - Check if backtest complete
- `_cleanup()` - Resource cleanup

**Tests**:
- Lifecycle state transitions
- Stop event handling
- Error recovery

---

### Task 3.3: Historical Data Management (6-8 hours)

**Reference**: SESSION_ARCHITECTURE.md lines 1626-1636

**Implement**:
```python
async def _manage_historical_data(self):
    """Update historical data before EVERY session"""
    
    # 1. Determine date range
    current_date = self._time_manager.get_current_time().date()
    
    # 2. For each historical data config
    for hist_config in self.session_config.session_data_config.historical.data:
        trailing_days = hist_config.trailing_days
        intervals = hist_config.intervals
        symbols = self._resolve_symbols(hist_config.apply_to)
        
        # 3. Calculate start_date (inclusive) using TimeManager
        end_date = current_date - timedelta(days=1)  # Yesterday
        start_date = await self._get_start_date_for_trailing_days(
            end_date, trailing_days
        )
        
        # 4. Load historical bars for each symbol/interval
        for symbol in symbols:
            for interval in intervals:
                bars = await self._load_historical_bars(
                    symbol, interval, start_date, end_date
                )
                # Store in session_data
                for bar in bars:
                    self.session_data.append_bar(symbol, interval, bar)
    
    # 5. Calculate quality scores
    if self.session_config.session_data_config.historical.enable_quality:
        self._calculate_historical_quality()
    else:
        self._assign_default_quality()
```

**Helper Methods**:
- `_resolve_symbols()` - Handle "all" vs specific symbols
- `_get_start_date_for_trailing_days()` - Use TimeManager to count back trading days
- `_load_historical_bars()` - Query database via DataManager
- `_calculate_historical_quality()` - Gap detection for historical data
- `_assign_default_quality()` - Set 100% quality

**Tests**:
- Trailing window calculation
- Symbol resolution ("all" vs list)
- Quality calculation vs default
- Multiple historical configs

---

### Task 3.4: Historical Indicator Calculation (6-8 hours)

**Reference**: SESSION_ARCHITECTURE.md lines 380-440

**Implement**:
```python
async def _calculate_historical_indicators(self):
    """Calculate all historical indicators before EVERY session"""
    
    indicators = self.session_config.session_data_config.historical.indicators
    
    for indicator_name, indicator_config in indicators.items():
        indicator_type = indicator_config['type']
        
        if indicator_type == 'trailing_average':
            result = await self._calculate_trailing_average(
                indicator_name, indicator_config
            )
        elif indicator_type == 'trailing_max':
            result = await self._calculate_trailing_max(
                indicator_name, indicator_config
            )
        elif indicator_type == 'trailing_min':
            result = await self._calculate_trailing_min(
                indicator_name, indicator_config
            )
        else:
            raise ValueError(f"Unknown indicator type: {indicator_type}")
        
        # Store in session_data with indexed access
        self.session_data.set_historical_indicator(indicator_name, result)
```

**Indicator Types**:
1. **Trailing Average (Daily)**:
   - Calculate average over N trading days
   - Result: Single value per day
   - Example: avg_volume over 10 days

2. **Trailing Average (Intraday)**:
   - Calculate average for each minute of trading day
   - Result: Array of 390 values (one per minute)
   - Example: avg_volume_intraday over 10 days

3. **Trailing Max/Min**:
   - Find max/min over period
   - Example: high_52w, low_52w

**Helper Methods**:
- `_calculate_trailing_average()` - With daily/intraday granularity
- `_calculate_trailing_max()` - Track maximum
- `_calculate_trailing_min()` - Track minimum
- `_get_trading_minutes_array()` - Generate 390 time points
- `_query_bars_for_indicator()` - Fetch required historical data

**Tests**:
- Each indicator type
- Daily vs intraday granularity
- Period parsing (10d, 52w, etc.)
- Edge cases (insufficient data)

---

### Task 3.5: Queue Loading (4-6 hours)

**Reference**: SESSION_ARCHITECTURE.md lines 1651-1654

**Implement**:
```python
async def _load_queues(self):
    """Load queues with data for streaming phase"""
    
    if self._system_manager.mode == "backtest":
        await self._load_backtest_queues()
    else:  # live mode
        await self._start_live_streams()

async def _load_backtest_queues(self):
    """Load prefetch_days of data into queues"""
    
    prefetch_days = self.session_config.backtest_config.prefetch_days
    current_date = self._time_manager.get_current_time().date()
    
    # Determine date range
    start_date = current_date
    end_date = await self._get_date_plus_trading_days(
        start_date, prefetch_days - 1
    )
    
    # For each symbol
    for symbol in self.session_config.session_data_config.symbols:
        # Only load STREAMED intervals (determined by mode)
        streamed_intervals = self._get_streamed_intervals(symbol)
        
        for interval in streamed_intervals:
            # Load bars into queue
            await self._data_manager.start_bar_stream(
                symbol, interval, start_date, end_date
            )

async def _start_live_streams(self):
    """Start API streams for live mode"""
    for symbol in self.session_config.session_data_config.symbols:
        streamed_types = self._get_streamed_types(symbol)
        
        for stream_type in streamed_types:
            await self._data_manager.start_live_stream(symbol, stream_type)
```

**Helper Methods**:
- `_get_streamed_intervals()` - Determine what to stream vs generate
- `_get_date_plus_trading_days()` - Use TimeManager for calendar navigation
- Stream/Generate marking logic (backtest: smallest interval; live: what API provides)

**Tests**:
- Backtest queue loading (1-3 days)
- Live stream startup
- Stream vs generate marking
- Multiple symbols

---

### Task 3.6: Session Activation (2-3 hours)

**Implement**:
```python
def _activate_session(self):
    """Signal session is active and ready for streaming"""
    
    # Mark session as active
    self.session_data.set_session_active(True)
    
    # Record session start time for metrics
    self._session_start_time = self.metrics.start_timer()
    
    # Log activation
    current_time = self._time_manager.get_current_time()
    logger.info(f"Session activated at {current_time}")
    
    # Notify subscribers (if any)
    self._notify_session_activated()
```

**Tests**:
- Activation flag set
- Metrics started
- Notification sent

---

### Task 3.7: Streaming Phase with Time Advancement (8-10 hours)

**Reference**: SESSION_ARCHITECTURE.md lines 1656-1662

**Most Complex Part - Handles Data-Driven and Clock-Driven Modes**

**Implement**:
```python
async def _streaming_phase(self):
    """Main streaming loop with time advancement"""
    
    trading_session = await self._get_current_trading_session()
    market_close = datetime.combine(
        trading_session.date,
        trading_session.regular_close
    )
    
    while True:
        current_time = self._time_manager.get_current_time()
        
        # Check end-of-session
        if current_time >= market_close:
            logger.info("Market close reached, ending session")
            break
        
        # Get next data timestamp from queues
        next_timestamp = self._get_next_queue_timestamp()
        
        if next_timestamp is None:
            # No more data - advance to market close
            self._time_manager.set_backtest_time(market_close)
            logger.info("No more data, advanced to market close")
            break
        
        # Check if next data is beyond market close
        if next_timestamp > market_close:
            # Advance to market close and end
            self._time_manager.set_backtest_time(market_close)
            logger.info("Next data beyond close, advanced to market close")
            break
        
        # Advance time to next data
        self._time_manager.set_backtest_time(next_timestamp)
        
        # Process data at this timestamp
        await self._process_queue_data(next_timestamp)
        
        # Notify subscribers
        self._notify_data_available()
        
        # Clock-driven delay if speed_multiplier > 0
        if self.session_config.backtest_config.speed_multiplier > 0:
            await self._apply_clock_driven_delay()
```

**Helper Methods**:
- `_get_next_queue_timestamp()` - Find earliest timestamp across all queues
- `_process_queue_data()` - Consume data from queues, add to session_data
- `_notify_data_available()` - Signal data_processor
- `_apply_clock_driven_delay()` - Sleep for clock-driven mode
- `_get_current_trading_session()` - Query TimeManager

**Critical Rules**:
1. **Time must stay within trading hours**: `open_time <= current_time <= close_time`
2. **Never exceed market close**: If `current_time > close_time`, it's an error
3. **Data exhaustion**: Advance to market close if no more data
4. **Support multiple modes**: data-driven (speed=0), clock-driven (speed>0), live

**Tests**:
- Data-driven mode (no delays)
- Clock-driven mode (with delays)
- End-of-session detection
- Data exhaustion handling
- Multiple symbols interleaved

---

### Task 3.8: End-of-Session Logic (3-4 hours)

**Implement**:
```python
async def _end_session(self):
    """End current session and prepare for next"""
    
    # 1. Deactivate session
    self.session_data.set_session_active(False)
    
    # 2. Record session duration
    self.metrics.record_session_duration(self._session_start_time)
    
    # 3. Clear session data
    self.session_data.clear_session_bars()  # Keep historical
    
    # 4. Advance to next trading day
    current_date = self._time_manager.get_current_time().date()
    next_trading_date = await self._time_manager.get_next_trading_date(
        session, current_date, n=1
    )
    
    if next_trading_date is None:
        logger.info("No more trading days, backtest complete")
        self._backtest_complete = True
        return
    
    # 5. Set time to market open of next day
    next_session = await self._time_manager.get_trading_session(
        session, next_trading_date
    )
    next_open = datetime.combine(
        next_trading_date,
        next_session.regular_open
    )
    self._time_manager.set_backtest_time(next_open)
    
    # 6. Record gap time
    gap_start = self.metrics.start_timer()
    # Historical update will happen next loop iteration
    self._gap_start_time = gap_start
    
    logger.info(f"Session ended, advancing to {next_trading_date}")
```

**Tests**:
- Session deactivation
- Metrics recording
- Next day calculation
- Backtest completion detection

---

### Task 3.9: Performance Metrics Integration (2-3 hours)

**Instrument Key Operations**:
```python
# Session gap timing
gap_start = self.metrics.start_timer()
await self._manage_historical_data()
self.metrics.record_session_gap(gap_start)

# Data processor timing
proc_start = self.metrics.start_timer()
# ... notify data processor ...
# ... wait for ready signal ...
self.metrics.record_data_processor(proc_start)

# Session duration
session_start = self.metrics.start_timer()
# ... streaming phase ...
self.metrics.record_session_duration(session_start)

# Trading days counter
self.metrics.increment_trading_days()
```

**Tests**:
- Metrics recorded correctly
- Report generation
- Performance targets met

---

### Task 3.10: Quality Calculation Integration (3-4 hours)

**Implement**:
```python
def _calculate_historical_quality(self):
    """Calculate quality for historical bars"""
    
    for symbol in self.session_config.session_data_config.symbols:
        for interval in self._get_all_intervals():
            bars = self.session_data.get_bars(symbol, interval)
            
            # Detect gaps
            gaps = self._detect_gaps(bars, interval)
            
            # Calculate quality percentage
            expected_bars = self._calculate_expected_bars(...)
            actual_bars = len(bars)
            quality = (actual_bars / expected_bars) * 100 if expected_bars > 0 else 100.0
            
            # Store quality
            self.session_data.set_quality_metric(symbol, interval, quality)

def _detect_gaps(self, bars, interval):
    """Detect gaps in bar sequence"""
    gaps = []
    for i in range(len(bars) - 1):
        current_ts = bars[i].timestamp
        next_ts = bars[i + 1].timestamp
        expected_next = current_ts + timedelta(minutes=int(interval[:-1]))
        
        if next_ts > expected_next:
            gaps.append((current_ts, next_ts))
    
    return gaps
```

**Tests**:
- Gap detection
- Quality calculation
- Enable/disable flag behavior

---

## Testing Strategy

### Unit Tests
- Each helper method independently
- Indicator calculations
- Quality calculations
- Time advancement logic

### Integration Tests
- Full lifecycle (one session)
- Multiple sessions (backtest)
- Historical data updates
- Queue loading

### End-to-End Tests
- Complete backtest run (3-5 days)
- Verify all metrics
- Verify data quality
- Performance benchmarks

---

## Success Criteria

- [ ] **Lifecycle** completes without errors
- [ ] **Historical data** loaded and updated correctly
- [ ] **Historical indicators** calculated accurately
- [ ] **Queues** loaded with correct data
- [ ] **Time advancement** follows all rules
- [ ] **End-of-session** logic works
- [ ] **Performance metrics** recorded
- [ ] **Quality calculation** accurate
- [ ] **All tests** passing
- [ ] **Documentation** complete

---

## Estimated Timeline

| Task | Time | Status |
|------|------|--------|
| 3.1: Setup & Backup | 1-2 hours | 🚧 Next |
| 3.2: Basic Lifecycle | 4-6 hours | ⏳ |
| 3.3: Historical Data | 6-8 hours | ⏳ |
| 3.4: Indicators | 6-8 hours | ⏳ |
| 3.5: Queue Loading | 4-6 hours | ⏳ |
| 3.6: Activation | 2-3 hours | ⏳ |
| 3.7: Streaming | 8-10 hours | ⏳ |
| 3.8: End-of-Session | 3-4 hours | ⏳ |
| 3.9: Metrics | 2-3 hours | ⏳ |
| 3.10: Quality | 3-4 hours | ⏳ |
| **Testing** | 6-8 hours | ⏳ |
| **Total** | **45-62 hours** (5-7 days) | |

---

## Next Steps

Ready to start Task 3.1: Project Setup & Backup!
