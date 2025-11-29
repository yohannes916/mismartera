# Implementation Details - Component Specifications

**Reference**: `SESSION_ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`

---

## Component 1: SessionData

### Purpose
Unified data store for ALL session-relevant data (historical + current).

### Data Structures
```python
from collections import defaultdict, deque
from typing import Any, Dict, Optional

class SessionData:
    def __init__(self):
        # Bars: {symbol: {interval: deque([bar1, bar2, ...])}}
        self._bars: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
        
        # Historical indicators: {name: indexed_data}
        # indexed_data allows O(1) lookup by time index
        self._historical_indicators: Dict[str, Any] = {}
        
        # Real-time indicators: {symbol: {name: value}}
        self._realtime_indicators: Dict[str, Dict[str, Any]] = defaultdict(dict)
        
        # Quality metrics: {symbol: {data_type: percentage}}
        # Example: {"AAPL": {"1m": 98.5, "5m": 98.5}}
        self._quality_metrics: Dict[str, Dict[str, float]] = defaultdict(dict)
```

### Critical Implementation Notes
1. **Zero-Copy**: Return deque reference, NOT `list(deque)`
2. **Thread-Safety**: Consider if locking needed (coordinator writes, others read)
3. **Memory Management**: Clear method must fully release memory

### Testing Checklist
- [ ] Verify same object reference returned (zero-copy)
- [ ] Test with 100k+ bars (memory usage)
- [ ] Benchmark append: target <1μs
- [ ] Benchmark access: target <1μs

---

## Component 2: StreamSubscription

### Purpose
Event-based one-shot synchronization between threads.

### Implementation
```python
import threading
import logging
from typing import Optional

class StreamSubscription:
    def __init__(self, mode: str, stream_id: str):
        self._ready_event = threading.Event()
        self._mode = mode  # 'data-driven', 'clock-driven', 'live'
        self._stream_id = stream_id
        self._overrun_count = 0
        
    def signal_ready(self) -> None:
        if self._ready_event.is_set() and self._mode == 'clock-driven':
            self._overrun_count += 1
            logging.warning(f"Overrun on {self._stream_id}: {self._overrun_count}")
        self._ready_event.set()
    
    def wait_until_ready(self, timeout: Optional[float] = None) -> bool:
        if self._mode == 'data-driven':
            self._ready_event.wait()  # Block indefinitely
            return True
        else:
            return self._ready_event.wait(timeout=timeout)
    
    def reset(self) -> None:
        self._ready_event.clear()
```

### Usage Pattern
```python
# Producer (coordinator):
subscription.signal_ready()

# Consumer (data_processor):
start = time.perf_counter()
subscription.wait_until_ready(timeout=1.0)
duration = time.perf_counter() - start
subscription.reset()  # Prepare for next cycle
```

### Testing Checklist
- [ ] Test signal before wait
- [ ] Test wait before signal
- [ ] Test overrun detection (clock-driven)
- [ ] Test reset behavior

---

## Component 3: TimeManager Caching

### Caching Strategy
```python
from functools import lru_cache
from typing import Optional
from datetime import date

class TimeManager:
    def __init__(self):
        # Last-query cache (most common: repeated same query)
        self._last_query_cache = {
            'key': None,
            'result': None
        }
        
    @lru_cache(maxsize=100)
    def _get_trading_session_cached(self, date_str: str, exchange: str):
        """LRU cached query (convert date to string for hashability)"""
        # Query database
        return result
    
    def get_trading_session(self, session, date, exchange):
        # Check last-query cache first
        cache_key = (date, exchange)
        if self._last_query_cache['key'] == cache_key:
            return self._last_query_cache['result']
        
        # Query with LRU cache
        result = self._get_trading_session_cached(date.isoformat(), exchange)
        
        # Update last-query cache
        self._last_query_cache = {'key': cache_key, 'result': result}
        return result
    
    def invalidate_cache(self):
        """Called at session start"""
        self._last_query_cache = {'key': None, 'result': None}
        self._get_trading_session_cached.cache_clear()
    
    def get_first_trading_date(self, session, from_date, exchange="NYSE"):
        """NEW - Inclusive date finding"""
        if self.is_trading_day(session, from_date, exchange):
            return from_date
        return self.get_next_trading_date(session, from_date, n=1, exchange=exchange)
```

### Testing Checklist
- [ ] Measure cache hit rate (should be >90%)
- [ ] Verify `get_first_trading_date` returns from_date if it's a trading day
- [ ] Benchmark performance improvement

---

## Component 4: Session Coordinator - Core Loop

### Main Loop Structure
```python
class SessionCoordinator(threading.Thread):
    def run(self):
        """Main loop: Initialization → Streaming → End → Repeat"""
        try:
            while not self._should_stop:
                # === INITIALIZATION PHASE ===
                if not self._initialize_session():
                    break  # No more trading days (backtest complete)
                
                # === STREAMING PHASE ===
                self._stream_session()
                
                # === END-OF-SESSION PHASE ===
                self._end_session()
        
        except Exception as e:
            logging.critical(f"SessionCoordinator crashed: {e}", exc_info=True)
        finally:
            # === TERMINATION PHASE ===
            self._terminate()
```

### Initialization Phase
```python
def _initialize_session(self) -> bool:
    """Returns True if session initialized, False if backtest complete"""
    
    # 1. Determine next trading day
    if self._current_date is None:
        # First session: Use backtest start_date
        self._current_date = self._time_manager.get_first_trading_date(
            self._db_session,
            self._config.backtest_config.start_date,
            self._config.exchange_group
        )
    else:
        # Subsequent sessions: Advance to next trading day
        self._current_date = self._time_manager.get_next_trading_date(
            self._db_session,
            self._current_date,
            n=1,
            exchange=self._config.exchange_group
        )
    
    # 2. Check if backtest complete
    if self._current_date > self._config.backtest_config.end_date:
        logging.info("Backtest complete")
        return False
    
    logging.info(f"Initializing session for {self._current_date}")
    
    # 3. Update historical data (EVERY SESSION)
    self._update_historical_data()
    
    # 4. Calculate historical indicators (EVERY SESSION)
    self._calculate_historical_indicators()
    
    # 5. Assign historical quality (EVERY SESSION)
    self._assign_historical_quality()
    
    # 6. Load queues
    self._load_queues()
    
    # 7. Activate session
    self._activate_session()
    
    return True
```

### Historical Data Update
```python
def _update_historical_data(self) -> None:
    """Load/update historical bars for current session"""
    timer = self._metrics.start_timer()
    
    # Simple approach: Clear and reload
    # (Alternative: Drop old + add new for optimization)
    
    for hist_config in self._config.session_data_config.historical.data:
        symbols = self._resolve_symbols(hist_config.apply_to)
        
        for symbol in symbols:
            for interval in hist_config.intervals:
                # Calculate date range
                end_date = self._current_date - timedelta(days=1)
                start_date = self._time_manager.count_back_trading_days(
                    self._db_session,
                    end_date,
                    hist_config.trailing_days,
                    self._config.exchange_group
                )
                
                # Fetch from database
                bars = self._data_manager.get_bars(
                    symbol=symbol,
                    interval=interval,
                    start_date=start_date,
                    end_date=end_date
                )
                
                # Append to session_data (zero-copy)
                for bar in bars:
                    self._session_data.append_bar(symbol, interval, bar)
    
    # Record timing
    if self._first_session:
        self._metrics.record_initial_load(self._metrics.start_timer() - timer)
    else:
        self._metrics.record_subsequent_load(timer)
```

### Streaming Phase - Time Advancement
```python
def _stream_session(self) -> None:
    """Main streaming loop with time advancement"""
    
    while True:
        # Get next data timestamp from queues
        next_timestamp = self._peek_next_timestamp()
        
        if next_timestamp is None:
            # Data exhausted: Advance to market close
            self._current_time = self._market_close_time
        elif next_timestamp > self._market_close_time:
            # Next data past close: Advance to market close
            self._current_time = self._market_close_time
        else:
            # Normal: Advance to next data timestamp
            self._current_time = next_timestamp
        
        # CRITICAL: Ensure time within trading hours
        if self._current_time > self._market_close_time:
            logging.critical(
                f"CRITICAL ERROR: Time {self._current_time} exceeds "
                f"market close {self._market_close_time}"
            )
            raise RuntimeError("Time advancement error")
        
        # Check for end-of-session
        if self._current_time >= self._market_close_time:
            logging.info(f"End of session: {self._current_time}")
            break
        
        # Process data at current time
        self._process_current_data()
```

---

## Component 5: Data Processor - Event-Driven

### Core Structure
```python
class DataProcessor(threading.Thread):
    def __init__(self, session_data, subscriptions):
        super().__init__(name="data_processor")
        self._session_data = session_data
        self._notification_queue = queue.Queue()
        self._coordinator_subscription = subscriptions['coordinator']
        self._analysis_subscriptions = subscriptions['analysis']
    
    def run(self):
        while not self._should_stop:
            try:
                # Wait for notification from coordinator
                notification = self._notification_queue.get(timeout=1.0)
                
                # Read data from session_data (zero-copy)
                symbol, interval = notification
                bars = self._session_data.get_bars(symbol, interval)
                
                # Generate derivatives (if needed)
                self._generate_derivatives(symbol, interval, bars)
                
                # Calculate real-time indicators
                self._calculate_realtime_indicators(symbol, interval)
                
                # Signal ready to coordinator
                self._coordinator_subscription.signal_ready()
                
                # Notify analysis engine
                self._notify_analysis_engine(symbol, interval)
                
            except queue.Empty:
                continue
```

### Key Differences from Old Code
- **Event-driven**: Waits on notification queue (no polling)
- **Zero-copy**: Reads from session_data by reference
- **No quality**: Quality logic removed (moved to data_quality_manager)
- **Bidirectional sync**: Signals ready to coordinator, notifies analysis engine

---

## Component 6: Data Quality Manager

### Core Structure
```python
class DataQualityManager(threading.Thread):
    def __init__(self, config, session_data, mode):
        super().__init__(name="data_quality_manager")
        self._config = config
        self._session_data = session_data
        self._mode = mode  # 'backtest' or 'live'
        self._enable_session_quality = config.gap_filler.enable_session_quality
        
        # Internal gap analysis
        self._gap_tracker = {}
    
    def run(self):
        """Non-blocking background operation"""
        while not self._should_stop:
            # Wait for data arrival event
            # (Coordinator notifies when new data arrives)
            
            if not self._enable_session_quality:
                # Quality disabled: Assign 100% to all new bars
                self._assign_default_quality()
                continue
            
            # Calculate quality for streamed bars
            quality = self._calculate_quality()
            
            # Update session_data (non-blocking)
            self._session_data.set_quality_metric(symbol, interval, quality)
            
            # Copy quality to derived bars
            self._copy_quality_to_derived(symbol, interval, quality)
            
            # Gap filling (LIVE MODE ONLY)
            if self._mode == 'live':
                self._attempt_gap_fill()
```

### Key Features
- **Non-blocking**: Does NOT signal ready to anyone
- **Mode-aware**: Gap filling only in live mode
- **Configurable**: Respects `enable_session_quality` flag
- **Background**: Best-effort quality updates

---

## Next Steps

1. Review this detailed specification
2. Start implementation with SessionData (Component 1)
3. Add tests for each component before moving to next
