# Phase 4: Prefetch Mechanism - Implementation Plan

## Objective

Implement intelligent prefetching of market data to eliminate session startup delays and enable seamless transitions between trading sessions.

---

## Timeline

**Duration**: 3 weeks  
**Complexity**: High  
**Dependencies**: Phases 1, 2, 3 ✅

---

## Overview

Phase 4 adds a prefetch mechanism that anticipates the next trading session and pre-loads required data before the session starts, enabling zero-delay session transitions and improved user experience.

### Problem Statement

**Current**: When a new session starts:
1. Historical bars must be loaded (1-2 second delay)
2. Symbols must be registered
3. Data structures initialized
4. User waits during initialization

**Solution**: Prefetch mechanism:
1. Detect next session in advance
2. Pre-load historical data
3. Pre-register symbols
4. Seamless transition when session starts

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────┐
│           Prefetch Manager (NEW)                     │
│                                                      │
│  ┌──────────────────┐      ┌──────────────────┐   │
│  │ Session Detector │      │ Prefetch Engine  │   │
│  │                  │      │                  │   │
│  │ • Next session   │─────►│ • Load historical│   │
│  │ • Business days  │      │ • Register       │   │
│  │ • Holidays       │      │ • Pre-warm       │   │
│  └──────────────────┘      └──────────────────┘   │
│           │                         │               │
│           └─────────┬───────────────┘               │
│                     ▼                               │
│              session_data                           │
└─────────────────────────────────────────────────────┘
```

### Data Flow

```
Before Session (T-60 minutes)
        │
        ├─► Detect Next Session
        │   └─► Query trading calendar
        │       └─► Calculate next business day
        │
        ├─► Prefetch Historical Data
        │   ├─► Query database for trailing days
        │   ├─► Load into prefetch cache
        │   └─► Validate completeness
        │
        └─► Session Start (T=0)
            ├─► Swap prefetch → session_data
            ├─► Start streaming
            └─► Zero delay! ✅
```

---

## Features to Implement

### 1. Session Detection

**File**: `session_detector.py` (NEW)

```python
class SessionDetector:
    """Detect next trading session based on calendar and time."""
    
    def __init__(self, trading_calendar=None):
        self.calendar = trading_calendar or get_default_calendar()
    
    def get_next_session(self, from_date: date) -> Optional[date]:
        """Get next trading session after given date.
        
        Args:
            from_date: Reference date
            
        Returns:
            Next trading session date, or None if not found
        """
        # Check next 30 days for valid trading day
        for days_ahead in range(1, 31):
            candidate = from_date + timedelta(days=days_ahead)
            if self.is_trading_day(candidate):
                return candidate
        return None
    
    def is_trading_day(self, check_date: date) -> bool:
        """Check if date is a valid trading day."""
        # Skip weekends
        if check_date.weekday() >= 5:  # Sat=5, Sun=6
            return False
        
        # Skip holidays
        if self.calendar.is_holiday(check_date):
            return False
        
        return True
    
    def should_prefetch(
        self,
        current_time: datetime,
        next_session: date
    ) -> bool:
        """Determine if prefetch should start.
        
        Prefetch window: 60 minutes before session start
        """
        session_start = datetime.combine(
            next_session,
            time(9, 30)  # Market open time
        )
        
        time_until_session = (session_start - current_time).total_seconds()
        
        # Prefetch 60 minutes before session
        return 0 < time_until_session <= 3600
```

### 2. Trading Calendar

**File**: `trading_calendar.py` (NEW)

```python
class TradingCalendar:
    """US stock market trading calendar."""
    
    def __init__(self):
        self._holidays = self._load_holidays()
    
    def _load_holidays(self) -> Set[date]:
        """Load US market holidays."""
        # 2025 US Market Holidays
        holidays = {
            date(2025, 1, 1),   # New Year's Day
            date(2025, 1, 20),  # MLK Day
            date(2025, 2, 17),  # Presidents Day
            date(2025, 4, 18),  # Good Friday
            date(2025, 5, 26),  # Memorial Day
            date(2025, 6, 19),  # Juneteenth
            date(2025, 7, 4),   # Independence Day
            date(2025, 9, 1),   # Labor Day
            date(2025, 11, 27), # Thanksgiving
            date(2025, 12, 25), # Christmas
        }
        return holidays
    
    def is_holiday(self, check_date: date) -> bool:
        """Check if date is a market holiday."""
        return check_date in self._holidays
    
    def get_next_trading_day(
        self,
        from_date: date,
        days_ahead: int = 1
    ) -> date:
        """Get next trading day N days ahead."""
        current = from_date
        found = 0
        
        while found < days_ahead:
            current += timedelta(days=1)
            if self.is_trading_day(current):
                found += 1
        
        return current
    
    def is_trading_day(self, check_date: date) -> bool:
        """Check if date is a trading day."""
        if check_date.weekday() >= 5:  # Weekend
            return False
        if check_date in self._holidays:
            return False
        return True
```

### 3. Prefetch Manager

**File**: `prefetch_manager.py` (NEW)

```python
class PrefetchManager:
    """Manage prefetching of market data for next session."""
    
    def __init__(
        self,
        session_data: SessionData,
        data_repository,
        session_detector: SessionDetector
    ):
        self._session_data = session_data
        self._data_repository = data_repository
        self._detector = session_detector
        
        # Prefetch cache
        self._prefetch_cache: Dict[str, SymbolPrefetchData] = {}
        self._prefetch_session_date: Optional[date] = None
        self._prefetch_complete = False
        
        # Background thread
        self._thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
        self._running = False
    
    def start(self) -> None:
        """Start prefetch monitoring thread."""
        if self._running:
            return
        
        self._shutdown.clear()
        self._running = True
        
        self._thread = threading.Thread(
            target=self._prefetch_worker,
            name="PrefetchThread",
            daemon=True
        )
        self._thread.start()
        logger.info("PrefetchManager started")
    
    def stop(self) -> None:
        """Stop prefetch thread."""
        if not self._running:
            return
        
        self._shutdown.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        self._running = False
        logger.info("PrefetchManager stopped")
    
    def _prefetch_worker(self) -> None:
        """Background worker that monitors and prefetches."""
        while not self._shutdown.is_set():
            try:
                # Check every 5 minutes
                self._check_and_prefetch()
                self._shutdown.wait(300)  # 5 minutes
            
            except Exception as e:
                logger.error(f"Error in prefetch worker: {e}")
                self._shutdown.wait(60)
    
    async def _check_and_prefetch(self) -> None:
        """Check if prefetch needed and execute."""
        current_date = self._session_data.current_session_date
        if current_date is None:
            return
        
        # Get next session
        next_session = self._detector.get_next_session(current_date)
        if next_session is None:
            return
        
        # Already prefetched?
        if (self._prefetch_complete and 
            self._prefetch_session_date == next_session):
            return
        
        # Should prefetch now?
        now = datetime.now()
        if not self._detector.should_prefetch(now, next_session):
            return
        
        # Execute prefetch
        logger.info(f"Starting prefetch for session: {next_session}")
        await self._execute_prefetch(next_session)
    
    async def _execute_prefetch(self, session_date: date) -> None:
        """Execute prefetch for given session."""
        # Get active symbols
        symbols = self._session_data.get_active_symbols()
        if not symbols:
            logger.warning("No active symbols to prefetch")
            return
        
        # Clear old cache
        self._prefetch_cache.clear()
        self._prefetch_session_date = session_date
        
        # Load for each symbol
        for symbol in symbols:
            try:
                await self._prefetch_symbol(symbol, session_date)
            except Exception as e:
                logger.error(f"Error prefetching {symbol}: {e}")
        
        self._prefetch_complete = True
        logger.info(
            f"Prefetch complete for {len(self._prefetch_cache)} symbols"
        )
    
    async def _prefetch_symbol(
        self,
        symbol: str,
        session_date: date
    ) -> None:
        """Prefetch data for single symbol."""
        # Query historical bars
        bars = await self._load_historical_bars(
            symbol,
            session_date,
            trailing_days=settings.HISTORICAL_BARS_TRAILING_DAYS,
            intervals=settings.HISTORICAL_BARS_INTERVALS
        )
        
        # Store in cache
        self._prefetch_cache[symbol] = SymbolPrefetchData(
            symbol=symbol,
            session_date=session_date,
            historical_bars=bars,
            prefetch_time=datetime.now()
        )
        
        logger.debug(f"Prefetched {len(bars)} bars for {symbol}")
    
    async def activate_prefetch(self) -> bool:
        """Activate prefetched data for current session.
        
        Called when session starts to swap cache → session_data.
        
        Returns:
            True if prefetch was activated
        """
        if not self._prefetch_complete:
            logger.warning("No prefetch available to activate")
            return False
        
        current = self._session_data.current_session_date
        if current != self._prefetch_session_date:
            logger.warning(
                f"Prefetch mismatch: current={current}, "
                f"prefetched={self._prefetch_session_date}"
            )
            return False
        
        # Swap cache into session_data
        for symbol, prefetch_data in self._prefetch_cache.items():
            await self._session_data.load_prefetched_data(
                symbol,
                prefetch_data.historical_bars
            )
        
        logger.info(f"Activated prefetch for {len(self._prefetch_cache)} symbols")
        
        # Clear cache
        self._prefetch_cache.clear()
        self._prefetch_complete = False
        
        return True
```

### 4. Session Boundary Detection

**Enhancement to `session_data.py`**:

```python
# Add to SessionData class

async def check_session_boundary(self) -> Optional[str]:
    """Check if at session boundary.
    
    Returns:
        "end" if session ended
        "start" if new session starting
        None if mid-session
    """
    if self.current_session_date is None:
        return "start"
    
    now = datetime.now()
    current_date = now.date()
    
    # Market hours: 9:30 AM - 4:00 PM ET
    market_open = time(9, 30)
    market_close = time(16, 0)
    
    # Before market open?
    if now.time() < market_open:
        # Different day?
        if current_date != self.current_session_date:
            return "start"
    
    # After market close?
    elif now.time() > market_close:
        # Still same day?
        if current_date == self.current_session_date:
            return "end"
    
    return None
```

---

## Configuration

### New Settings

```python
# In settings.py

# Prefetch Configuration (Phase 4)
PREFETCH_ENABLED: bool = True
PREFETCH_WINDOW_MINUTES: int = 60          # Start prefetch 60min before session
PREFETCH_CHECK_INTERVAL_MINUTES: int = 5   # Check every 5 minutes
PREFETCH_AUTO_ACTIVATE: bool = True        # Auto-activate on session start
```

---

## Integration Points

### 1. DataManager Integration

```python
class DataManager:
    def __init__(self):
        # ... existing init ...
        
        # Add prefetch manager (Phase 4)
        if settings.PREFETCH_ENABLED:
            from app.managers.data_manager.prefetch_manager import PrefetchManager
            from app.managers.data_manager.session_detector import SessionDetector
            
            detector = SessionDetector()
            self._prefetch_manager = PrefetchManager(
                session_data=self.session_data,
                data_repository=self.get_database_session(),
                session_detector=detector
            )
            self._prefetch_manager.start()
```

### 2. Session Start Integration

```python
async def start_session(self, session_date: date):
    """Start new trading session with prefetch support."""
    # Check if prefetch available
    if self._prefetch_manager:
        activated = await self._prefetch_manager.activate_prefetch()
        if activated:
            logger.info("Started session with prefetched data (zero delay!)")
            return
    
    # Fallback: Load normally
    await self._load_session_data(session_date)
```

---

## Testing Strategy

### Unit Tests

**File**: `test_prefetch.py`

```python
@pytest.mark.asyncio
async def test_session_detector_next_session():
    """Test detecting next trading session."""
    
@pytest.mark.asyncio
async def test_session_detector_skip_weekends():
    """Test that weekends are skipped."""
    
@pytest.mark.asyncio
async def test_session_detector_skip_holidays():
    """Test that holidays are skipped."""
    
@pytest.mark.asyncio
async def test_prefetch_manager_execute():
    """Test prefetch execution."""
    
@pytest.mark.asyncio
async def test_prefetch_manager_activate():
    """Test prefetch activation."""
    
@pytest.mark.asyncio
async def test_prefetch_window_timing():
    """Test prefetch window calculation."""
```

---

## Performance Goals

### Before Phase 4 (Current)
- Session start: 1-2 seconds (loading historical bars)
- User waits during initialization

### After Phase 4 (Target)
- Session start: <50ms (swap prefetch → session_data)
- **20-40x faster** session startup
- Zero perceived delay

---

## Use Cases

### 1. Overnight Trading Preparation

```python
# Evening: Detect next trading day
next_session = detector.get_next_session(date.today())
# → 2025-01-10 (next business day)

# T-60 minutes: Auto-prefetch starts
# Load historical bars for all symbols
# Cache ready

# T=0 (9:30 AM): Session starts
# Instant activation, zero delay!
```

### 2. Intraday Session Transition

```python
# End of day (4:00 PM)
await session_data.end_session()

# Auto-prefetch for tomorrow
# Load historical bars during off-hours

# Next morning (9:30 AM)
# Seamless transition
```

---

## Timeline Breakdown

### Week 1: Core Components
**Days 1-2**: Session detector and trading calendar
**Days 3-4**: Prefetch manager structure
**Day 5**: Unit tests for detection

### Week 2: Prefetch Execution
**Days 1-2**: Prefetch execution logic
**Days 3-4**: Cache management
**Day 5**: Integration with session_data

### Week 3: Integration & Testing
**Days 1-2**: DataManager integration
**Days 3-4**: End-to-end testing
**Day 5**: Documentation and polish

---

## Success Criteria

### Phase 4 Goals

- [ ] Session detector working (next session, holidays, weekends)
- [ ] Trading calendar implemented
- [ ] Prefetch manager complete
- [ ] Prefetch execution working
- [ ] Cache management working
- [ ] Activation mechanism working
- [ ] DataManager integration
- [ ] Unit tests comprehensive (>10 tests)
- [ ] Session startup <50ms
- [ ] Documentation complete

---

## Known Challenges

### 1. Timing Synchronization

**Challenge**: Prefetch must complete before session starts

**Solution**: Start 60 minutes early, monitor progress

### 2. Cache Invalidation

**Challenge**: Prefetch becomes stale if session changes

**Solution**: Validate session date on activation

### 3. Resource Usage

**Challenge**: Prefetch uses CPU/memory during off-hours

**Solution**: Configurable, can disable if needed

### 4. Multiple Symbols

**Challenge**: Prefetch 100+ symbols takes time

**Solution**: Parallel loading, async operations

---

## Future Enhancements (Phase 5+)

### Intelligent Prefetch

- Predict which symbols will be needed
- Prefetch only likely symbols
- Adaptive based on usage patterns

### Partial Prefetch

- Prefetch most recent days first
- Lazy load older history
- Progressive enhancement

### Background Refresh

- Keep historical bars up-to-date
- Continuous background sync
- Always ready

---

## Dependencies

### Phase 1 ✅
- SessionData singleton
- Fast access methods

### Phase 2 ✅
- Data quality management
- Background threads

### Phase 3 ✅
- Historical bars support
- Session roll logic

---

## Next: Phase 5

After Phase 4, Phase 5 will add:
- Explicit session boundary detection
- Automatic session roll
- Timeout handling
- Error flagging

---

**Status**: 📋 Ready to implement  
**Prerequisites**: Phases 1-3 complete ✅  
**Timeline**: 3 weeks  
**Complexity**: High
