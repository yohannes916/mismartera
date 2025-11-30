# Session Architecture Implementation Plan

**Reference**: `SESSION_ARCHITECTURE.md`  
**Strategy**: Fresh rewrites for core components  
**Created**: 2025-11-28

---

## File Organization

### Files to Backup (Move to `app/threads/_backup/`)
- `backtest_stream_coordinator.py` → `_backup/backtest_stream_coordinator.py.bak`
- `data_upkeep_thread.py` → `_backup/data_upkeep_thread.py.bak`
- `gap_filler.py` (if exists) → `_backup/gap_filler.py.bak`

### New Files to Create
```
app/data/session_data.py              # NEW - Unified data store
app/threads/sync/stream_subscription.py  # NEW - Thread sync
app/monitoring/performance_metrics.py     # NEW - Performance tracking
app/threads/session_coordinator.py        # REWRITE
app/threads/data_processor.py             # REWRITE
app/threads/data_quality_manager.py       # REWRITE
```

### Files to Update
```
app/managers/time_manager/api.py       # Add caching + get_first_trading_date()
app/config/session_config.py           # Update schema
app/managers/system_manager.py         # Remove queue preloading
```

---

## Implementation Phases

### Phase 0: Preparation (1 day)
- [ ] Create directory structure (`app/data/`, `app/threads/sync/`, `app/monitoring/`)
- [ ] Backup existing files to `_backup/`
- [ ] Create feature branch: `feature/session-architecture-rewrite`
- [ ] Document baseline behavior

### Phase 1: Core Infrastructure (3 days)

#### 1.1: SessionData (1 day)
**File**: `app/data/session_data.py`

**Key API**:
```python
class SessionData:
    def __init__(self):
        self._bars = defaultdict(lambda: defaultdict(deque))
        self._historical_indicators = {}
        self._realtime_indicators = defaultdict(dict)
        self._quality_metrics = defaultdict(dict)
    
    def append_bar(symbol, interval, bar) -> None
    def get_bars(symbol, interval) -> deque
    def set_quality_metric(symbol, data_type, percentage) -> None
    def get_quality_metric(symbol, data_type) -> float
    def clear() -> None
```

#### 1.2: StreamSubscription (1 day)
**File**: `app/threads/sync/stream_subscription.py`

**Key API**:
```python
class StreamSubscription:
    def __init__(self, mode: str, stream_id: str):
        self._ready_event = threading.Event()
        self._mode = mode
    
    def signal_ready() -> None
    def wait_until_ready(timeout=None) -> bool
    def reset() -> None
```

#### 1.3: PerformanceMetrics (1 day)
**File**: `app/monitoring/performance_metrics.py`

**Key API**:
```python
class PerformanceMetrics:
    def start_timer() -> float
    def record_analysis_engine(start_time) -> None
    def record_data_processor(start_time) -> None
    def format_report(report_type) -> str
```

### Phase 2: Configuration (1 day)

#### 2.1: Update SessionConfig
**File**: `app/config/session_config.py`

**Changes**:
- Add `historical.enable_quality: bool = True`
- Add `gap_filler.enable_session_quality: bool = True`
- Remove `gap_filler.quality_update_frequency`

#### 2.2: Update TimeManager
**File**: `app/managers/time_manager/api.py`

**Changes**:
- Add LRU caching decorator
- Add `get_first_trading_date()` method
- Add `invalidate_cache()` method

### Phase 3: Session Coordinator (5 days)

**File**: `app/threads/session_coordinator.py`

**Core Loop**:
```python
def run(self):
    while not self._should_stop:
        # INITIALIZATION PHASE
        self._update_historical_data()
        self._calculate_historical_indicators()
        self._assign_historical_quality()
        self._load_queues()
        self._activate_session()
        
        # STREAMING PHASE
        self._stream_session()
        
        # END-OF-SESSION PHASE
        self._end_session()
```

**Key Methods** (2 days each):
- Historical data/indicator management
- Queue loading (use existing APIs: `start_bars()`, etc.)
- Streaming with time advancement + end-of-session detection

### Phase 4: Data Processor (3 days)

**File**: `app/threads/data_processor.py`

**Key Changes**:
- Event-driven (notification queue from coordinator)
- Bidirectional sync (StreamSubscription)
- Zero-copy access from session_data
- Remove quality measurement logic

### Phase 5: Data Quality Manager (3 days)

**File**: `app/threads/data_quality_manager.py`

**Key Features**:
- Mode detection (backtest vs live)
- Gap filling ONLY in live mode
- Non-blocking background operation
- Quality calculation (configurable)

### Phase 6: Integration & Testing (3 days)

- [ ] Update system_manager (remove queue preloading)
- [ ] Update analysis_engine (session_data only access)
- [ ] End-to-end testing
- [ ] Performance validation
- [ ] Documentation updates

---

## Testing Strategy

### Unit Tests
- SessionData zero-copy behavior
- StreamSubscription thread-safety
- TimeManager caching
- Configuration validation

### Integration Tests
- Full session lifecycle
- Thread synchronization
- Performance metrics accuracy

### Performance Tests
- Backtest speed vs. baseline
- Memory usage
- Cache hit rates

---

## Success Criteria

✅ **Phase 1**: Infrastructure tests pass, zero overhead  
✅ **Phase 2**: Example config loads, caching works  
✅ **Phase 3**: Session coordinator completes full backtest  
✅ **Phase 4**: Data processor event-driven, no quality code  
✅ **Phase 5**: Quality manager non-blocking, mode-aware  
✅ **Phase 6**: Full system faster than baseline  

---

## Timeline

**Total**: ~18-20 days

- Phase 0: 1 day
- Phase 1: 3 days
- Phase 2: 1 day
- Phase 3: 5 days
- Phase 4: 3 days
- Phase 5: 3 days
- Phase 6: 3 days
- Buffer: 2 days

---

## Next Steps

1. Review this plan
2. Create directory structure
3. Start with Phase 1.1 (SessionData)
