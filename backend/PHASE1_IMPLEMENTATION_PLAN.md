# Phase 1: session_data Foundation - Implementation Plan

## Objective
Create the `session_data` singleton and integrate it with existing components without breaking current functionality.

---

## Phase 1 Deliverables

### 1. **SessionData Class** (`session_data.py`)
### 2. **SymbolSessionData Class** (same file)
### 3. **SystemManager Integration**
### 4. **Migration of SessionTracker**
### 5. **Update BacktestStreamCoordinator**

---

## Detailed Implementation

### File 1: `app/managers/data_manager/session_data.py`

```python
"""Session Data - Singleton managing current session market data.

This module provides centralized storage for all market data during a trading session.
It replaces and extends the functionality of SessionTracker with a comprehensive
data structure that holds bars, quotes, ticks, and historical data for all symbols.

PERFORMANCE OPTIMIZATIONS:
- Uses deque for O(1) append and recent access
- Cached latest bar for O(1) access
- Efficient last-N lookups
- Designed for high-frequency reads by AnalysisEngine and other modules
"""
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional, Set, Deque
from dataclasses import dataclass, field
from collections import defaultdict, deque
import asyncio

from app.models.trading import BarData, TickData
from app.logger import logger


@dataclass
class SymbolSessionData:
    """Per-symbol data for current trading session.
    
    Optimized for fast reads by AnalysisEngine and other consumers:
    - Latest bar cached for O(1) access
    - Deque for efficient append and recent-N access
    - Timestamp index for fast lookups
    """
    
    symbol: str
    
    # 1-minute bars (deque for O(1) append and efficient last-N access)
    bars_1m: Deque[BarData] = field(default_factory=deque)
    
    # Cache for O(1) access to latest bar
    _latest_bar: Optional[BarData] = None
    
    # Derived bars (e.g., {5: [...], 15: [...]})
    bars_derived: Dict[int, List[BarData]] = field(default_factory=dict)
    
    # Bar quality metric (0-100%)
    bar_quality: float = 0.0
    
    # Other data types
    quotes: List = field(default_factory=list)  # QuoteData when implemented
    ticks: List[TickData] = field(default_factory=list)
    
    # Session metrics (real-time tracking)
    session_volume: int = 0
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    last_update: Optional[datetime] = None
    
    # Update flags (set by main thread when new data inserted)
    bars_updated: bool = False
    quotes_updated: bool = False
    ticks_updated: bool = False
    
    # Historical bars for trailing days
    # Structure: {interval: {date: [bars]}}
    # Example: {1: {date1: [...], date2: [...]}, 5: {date1: [...], date2: [...]}}
    historical_bars: Dict[int, Dict[date, List[BarData]]] = field(
        default_factory=lambda: defaultdict(dict)
    )
    
    def update_from_bar(self, bar: BarData) -> None:
        """Update session metrics from a new bar.
        
        Args:
            bar: New bar data
        """
        # Update volume
        self.session_volume += bar.volume
        
        # Update high
        if self.session_high is None or bar.high > self.session_high:
            self.session_high = bar.high
        
        # Update low
        if self.session_low is None or bar.low < self.session_low:
            self.session_low = bar.low
        
        self.last_update = bar.timestamp
        self.bars_updated = True
        
        # Update latest bar cache
        self._latest_bar = bar
    
    def get_latest_bar(self, interval: int = 1) -> Optional[BarData]:
        """Get the most recent bar (O(1) operation).
        
        Args:
            interval: Bar interval in minutes (1, 5, 15, etc.)
            
        Returns:
            Most recent bar or None
        """
        if interval == 1:
            return self._latest_bar
        else:
            bars = self.bars_derived.get(interval, [])
            return bars[-1] if bars else None
    
    def get_last_n_bars(self, n: int, interval: int = 1) -> List[BarData]:
        """Get the last N bars efficiently.
        
        For 1-minute bars, uses deque for O(N) access.
        For derived bars, uses list slicing.
        
        Args:
            n: Number of bars to retrieve
            interval: Bar interval in minutes
            
        Returns:
            List of last N bars (oldest to newest)
        """
        if interval == 1:
            # Efficient: only iterate over last n items
            if len(self.bars_1m) <= n:
                return list(self.bars_1m)
            else:
                # Get last n items from deque
                return list(self.bars_1m)[-n:]
        else:
            bars = self.bars_derived.get(interval, [])
            return bars[-n:] if bars else []
    
    def get_bars_since(self, timestamp: datetime, interval: int = 1) -> List[BarData]:
        """Get all bars since a specific timestamp.
        
        Args:
            timestamp: Start timestamp
            interval: Bar interval in minutes
            
        Returns:
            List of bars after timestamp
        """
        if interval == 1:
            # Efficient: iterate backward from newest until we hit timestamp
            result = []
            for bar in reversed(self.bars_1m):
                if bar.timestamp < timestamp:
                    break
                result.append(bar)
            return list(reversed(result))
        else:
            bars = self.bars_derived.get(interval, [])
            return [b for b in bars if b.timestamp >= timestamp]
    
    def get_bar_count(self, interval: int = 1) -> int:
        """Get count of bars for an interval (O(1) operation).
        
        Args:
            interval: Bar interval in minutes
            
        Returns:
            Number of bars available
        """
        if interval == 1:
            return len(self.bars_1m)
        else:
            bars = self.bars_derived.get(interval)
            return len(bars) if bars else 0
    
    def reset_session_metrics(self) -> None:
        """Reset session metrics for a new session."""
        self.session_volume = 0
        self.session_high = None
        self.session_low = None
        self.last_update = None
        self.bar_quality = 0.0
        self.bars_updated = False
        self.quotes_updated = False
        self.ticks_updated = False
        self._latest_bar = None


class SessionData:
    """Singleton managing current session market data.
    
    Provides centralized storage and management for all market data during
    a trading session. Integrates with SystemManager and replaces SessionTracker.
    
    Thread-safe for concurrent access from main coordinator and data-upkeep threads.
    """
    
    def __init__(self):
        """Initialize SessionData.
        
        WARNING: Do not call directly. Use get_session_data() instead.
        """
        # Session configuration (defaults, can be overridden)
        self.start_time: time = time(9, 30)  # ET
        self.end_time: time = time(16, 0)    # ET
        self.historical_bars_trailing_days: int = 0
        self.historical_bars_types: List[int] = []
        
        # Session state
        self.session_ended: bool = False
        self.current_session_date: Optional[date] = None
        
        # Per-symbol data structures
        self._symbols: Dict[str, SymbolSessionData] = {}
        
        # Active symbols set (for quick lookup)
        self._active_symbols: Set[str] = set()
        
        # Thread-safe lock for concurrent access
        self._lock = asyncio.Lock()
        
        logger.info("SessionData initialized")
    
    async def register_symbol(self, symbol: str) -> SymbolSessionData:
        """Register a new symbol for tracking.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            SymbolSessionData for the symbol
        """
        symbol = symbol.upper()
        
        async with self._lock:
            if symbol not in self._symbols:
                self._symbols[symbol] = SymbolSessionData(symbol=symbol)
                self._active_symbols.add(symbol)
                logger.info(f"Registered symbol: {symbol}")
            
            return self._symbols[symbol]
    
    async def get_symbol_data(self, symbol: str) -> Optional[SymbolSessionData]:
        """Get data for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            SymbolSessionData if symbol is registered, None otherwise
        """
        symbol = symbol.upper()
        async with self._lock:
            return self._symbols.get(symbol)
    
    async def add_bar(self, symbol: str, bar: BarData) -> None:
        """Add a 1-minute bar to session data.
        
        Args:
            symbol: Stock symbol
            bar: Bar data to add
        """
        symbol = symbol.upper()
        
        # Auto-register symbol if not already registered
        if symbol not in self._active_symbols:
            await self.register_symbol(symbol)
        
        async with self._lock:
            symbol_data = self._symbols[symbol]
            symbol_data.bars_1m.append(bar)
            symbol_data.update_from_bar(bar)
    
    async def add_bars_batch(self, symbol: str, bars: List[BarData]) -> None:
        """Add multiple bars in batch (more efficient).
        
        Args:
            symbol: Stock symbol
            bars: List of bars to add
        """
        symbol = symbol.upper()
        
        if symbol not in self._active_symbols:
            await self.register_symbol(symbol)
        
        async with self._lock:
            symbol_data = self._symbols[symbol]
            symbol_data.bars_1m.extend(bars)
            
            # Update metrics from all bars
            for bar in bars:
                symbol_data.update_from_bar(bar)
    
    # ==================== FAST ACCESS METHODS ====================
    # These methods are optimized for AnalysisEngine and other high-frequency readers
    
    async def get_latest_bar(self, symbol: str, interval: int = 1) -> Optional[BarData]:
        """Get the most recent bar for a symbol (O(1) operation).
        
        Optimized for high-frequency access by AnalysisEngine.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval in minutes (1, 5, 15, etc.)
            
        Returns:
            Most recent bar or None
        """
        symbol = symbol.upper()
        async with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return None
            return symbol_data.get_latest_bar(interval)
    
    async def get_last_n_bars(
        self,
        symbol: str,
        n: int,
        interval: int = 1
    ) -> List[BarData]:
        """Get the last N bars for a symbol (efficient O(N) operation).
        
        Optimized for technical indicator calculations.
        
        Args:
            symbol: Stock symbol
            n: Number of bars to retrieve
            interval: Bar interval in minutes
            
        Returns:
            List of last N bars (oldest to newest)
        """
        symbol = symbol.upper()
        async with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return []
            return symbol_data.get_last_n_bars(n, interval)
    
    async def get_bars_since(
        self,
        symbol: str,
        timestamp: datetime,
        interval: int = 1
    ) -> List[BarData]:
        """Get all bars since a specific timestamp (efficient backward search).
        
        Args:
            symbol: Stock symbol
            timestamp: Start timestamp
            interval: Bar interval in minutes
            
        Returns:
            List of bars after timestamp
        """
        symbol = symbol.upper()
        async with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return []
            return symbol_data.get_bars_since(timestamp, interval)
    
    async def get_bar_count(self, symbol: str, interval: int = 1) -> int:
        """Get count of available bars (O(1) operation).
        
        Args:
            symbol: Stock symbol
            interval: Bar interval in minutes
            
        Returns:
            Number of bars available
        """
        symbol = symbol.upper()
        async with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return 0
            return symbol_data.get_bar_count(interval)
    
    async def get_latest_bars_multi(
        self,
        symbols: List[str],
        interval: int = 1
    ) -> Dict[str, Optional[BarData]]:
        """Get latest bars for multiple symbols in one call (batch operation).
        
        More efficient than calling get_latest_bar multiple times.
        
        Args:
            symbols: List of stock symbols
            interval: Bar interval in minutes
            
        Returns:
            Dictionary mapping symbol to latest bar
        """
        result = {}
        async with self._lock:
            for symbol in symbols:
                symbol = symbol.upper()
                symbol_data = self._symbols.get(symbol)
                if symbol_data:
                    result[symbol] = symbol_data.get_latest_bar(interval)
                else:
                    result[symbol] = None
        return result
    
    async def get_bars(
        self,
        symbol: str,
        interval: int = 1,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> List[BarData]:
        """Get bars for a symbol.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval in minutes (1, 5, 15, etc.)
            start: Optional start time filter
            end: Optional end time filter
            
        Returns:
            List of bars matching criteria
        """
        symbol = symbol.upper()
        
        async with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return []
            
            # Get bars based on interval
            if interval == 1:
                bars = symbol_data.bars_1m
            else:
                bars = symbol_data.bars_derived.get(interval, [])
            
            # Apply time filters if specified
            if start is not None or end is not None:
                filtered = []
                for bar in bars:
                    if start and bar.timestamp < start:
                        continue
                    if end and bar.timestamp > end:
                        continue
                    filtered.append(bar)
                return filtered
            
            return bars.copy()
    
    async def get_session_metrics(self, symbol: str) -> Dict[str, any]:
        """Get current session metrics for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with session metrics
        """
        symbol = symbol.upper()
        
        async with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return {}
            
            return {
                "symbol": symbol,
                "session_volume": symbol_data.session_volume,
                "session_high": symbol_data.session_high,
                "session_low": symbol_data.session_low,
                "last_update": symbol_data.last_update,
                "bar_quality": symbol_data.bar_quality,
                "bar_count": len(symbol_data.bars_1m),
            }
    
    async def start_new_session(self, session_date: date) -> None:
        """Start a new trading session.
        
        Clears all session-specific data but keeps configuration.
        
        Args:
            session_date: Date of the new session
        """
        async with self._lock:
            self.current_session_date = session_date
            self.session_ended = False
            
            # Reset all symbol data
            for symbol_data in self._symbols.values():
                symbol_data.bars_1m.clear()
                symbol_data.bars_derived.clear()
                symbol_data.quotes.clear()
                symbol_data.ticks.clear()
                symbol_data.reset_session_metrics()
            
            logger.info(f"Started new session for date: {session_date}")
    
    async def end_session(self) -> None:
        """Mark current session as ended."""
        async with self._lock:
            self.session_ended = True
            logger.info(f"Session ended for date: {self.current_session_date}")
    
    async def clear_all(self) -> None:
        """Clear all session data (for testing/reset)."""
        async with self._lock:
            self._symbols.clear()
            self._active_symbols.clear()
            self.current_session_date = None
            self.session_ended = False
            logger.info("All session data cleared")
    
    def get_active_symbols(self) -> Set[str]:
        """Get set of active symbols (thread-safe read)."""
        return self._active_symbols.copy()


# Global singleton instance
_session_data_instance: Optional[SessionData] = None


def get_session_data() -> SessionData:
    """Get or create the global SessionData singleton instance.
    
    Returns:
        The singleton SessionData instance
    """
    global _session_data_instance
    if _session_data_instance is None:
        _session_data_instance = SessionData()
        logger.info("SessionData singleton instance created")
    return _session_data_instance


def reset_session_data() -> None:
    """Reset the global SessionData singleton (useful for testing)."""
    global _session_data_instance
    _session_data_instance = None
    logger.info("SessionData singleton instance reset")
```

---

### File 2: Update `app/managers/system_manager.py`

Add session_data property:

```python
# Add to SystemManager class

@property
def session_data(self):
    """Get the global session_data singleton.
    
    Returns:
        SessionData instance
    """
    from app.managers.data_manager.session_data import get_session_data
    return get_session_data()
```

---

### File 3: Update `app/managers/data_manager/backtest_stream_coordinator.py`

Add session_data integration to _merge_worker:

```python
# In BacktestStreamCoordinator.__init__, add:
from app.managers.data_manager.session_data import get_session_data
self._session_data = get_session_data()

# In _merge_worker, after yielding data, add:
if oldest_item is not None and oldest_key is not None:
    # ... existing time advancement code ...
    
    # NEW: Write data to session_data
    symbol = oldest_key[0]
    stream_type = oldest_key[1]
    
    if stream_type == StreamType.BAR:
        await asyncio.to_thread(
            self._write_bar_to_session,
            symbol,
            oldest_item.data
        )
    
    self._output_queue.put(oldest_item.data)
    pending_items[oldest_key] = None

# Add new method:
def _write_bar_to_session(self, symbol: str, bar_data):
    """Write bar data to session_data (called from thread)."""
    # Use asyncio.run_coroutine_threadsafe if needed
    # For now, simple direct call
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(self._session_data.add_bar(symbol, bar_data))
    loop.close()
```

---

### File 4: Update `app/managers/data_manager/api.py`

Expose session_data via DataManager:

```python
# Add to DataManager class

@property
def session_data(self):
    """Get the global session_data singleton.
    
    Returns:
        SessionData instance
    """
    from app.managers.data_manager.session_data import get_session_data
    return get_session_data()

async def get_session_metrics(self, symbol: str) -> Dict[str, any]:
    """Get current session metrics for a symbol.
    
    Convenience method that delegates to session_data.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Dictionary with session metrics
    """
    return await self.session_data.get_session_metrics(symbol)
```

---

### File 5: Deprecate (but keep) `session_tracker.py`

Add deprecation notice:

```python
# At top of file:
"""
DEPRECATED: This module is being replaced by session_data.py

SessionTracker functionality has been moved to the new SessionData singleton
which provides more comprehensive session management. This module is kept
for backward compatibility during the migration period.

See: app/managers/data_manager/session_data.py
"""

import warnings

warnings.warn(
    "SessionTracker is deprecated. Use session_data.get_session_data() instead.",
    DeprecationWarning,
    stacklevel=2
)
```

---

## Testing Plan

### Unit Tests

Create `tests/test_session_data.py`:

```python
import pytest
from datetime import datetime, date, time
from app.managers.data_manager.session_data import (
    SessionData,
    SymbolSessionData,
    get_session_data,
    reset_session_data
)
from app.models.trading import BarData


@pytest.fixture
def session_data():
    """Create a fresh SessionData instance for each test."""
    reset_session_data()
    return get_session_data()


@pytest.mark.asyncio
async def test_register_symbol(session_data):
    """Test symbol registration."""
    symbol_data = await session_data.register_symbol("AAPL")
    
    assert symbol_data.symbol == "AAPL"
    assert "AAPL" in session_data.get_active_symbols()
    assert len(symbol_data.bars_1m) == 0


@pytest.mark.asyncio
async def test_add_bar(session_data):
    """Test adding a single bar."""
    bar = BarData(
        symbol="AAPL",
        timestamp=datetime(2025, 1, 1, 9, 30),
        open=150.0,
        high=151.0,
        low=149.0,
        close=150.5,
        volume=1000
    )
    
    await session_data.add_bar("AAPL", bar)
    
    bars = await session_data.get_bars("AAPL")
    assert len(bars) == 1
    assert bars[0].close == 150.5
    
    metrics = await session_data.get_session_metrics("AAPL")
    assert metrics["session_volume"] == 1000
    assert metrics["session_high"] == 151.0
    assert metrics["session_low"] == 149.0


@pytest.mark.asyncio
async def test_add_bars_batch(session_data):
    """Test batch bar insertion."""
    bars = [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 1, 9, 30 + i),
            open=150.0 + i,
            high=151.0 + i,
            low=149.0 + i,
            close=150.5 + i,
            volume=1000 * (i + 1)
        )
        for i in range(10)
    ]
    
    await session_data.add_bars_batch("AAPL", bars)
    
    stored_bars = await session_data.get_bars("AAPL")
    assert len(stored_bars) == 10
    
    metrics = await session_data.get_session_metrics("AAPL")
    assert metrics["bar_count"] == 10
    assert metrics["session_volume"] == sum(b.volume for b in bars)


@pytest.mark.asyncio
async def test_session_lifecycle(session_data):
    """Test session start/end lifecycle."""
    session_date = date(2025, 1, 1)
    
    # Start session
    await session_data.start_new_session(session_date)
    assert session_data.current_session_date == session_date
    assert not session_data.session_ended
    
    # Add some data
    bar = BarData(
        symbol="AAPL",
        timestamp=datetime(2025, 1, 1, 9, 30),
        open=150.0,
        high=151.0,
        low=149.0,
        close=150.5,
        volume=1000
    )
    await session_data.add_bar("AAPL", bar)
    
    # End session
    await session_data.end_session()
    assert session_data.session_ended
    
    # Start new session - should clear data
    await session_data.start_new_session(date(2025, 1, 2))
    bars = await session_data.get_bars("AAPL")
    assert len(bars) == 0  # Data cleared


@pytest.mark.asyncio
async def test_get_bars_with_filters(session_data):
    """Test bar retrieval with time filters."""
    bars = [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 1, 9, 30 + i),
            open=150.0,
            high=151.0,
            low=149.0,
            close=150.5,
            volume=1000
        )
        for i in range(10)
    ]
    
    await session_data.add_bars_batch("AAPL", bars)
    
    # Filter by start time
    start = datetime(2025, 1, 1, 9, 35)
    filtered = await session_data.get_bars("AAPL", start=start)
    assert len(filtered) == 5  # bars 5-9
    
    # Filter by end time
    end = datetime(2025, 1, 1, 9, 35)
    filtered = await session_data.get_bars("AAPL", end=end)
    assert len(filtered) == 5  # bars 0-4
    
    # Filter by both
    start = datetime(2025, 1, 1, 9, 32)
    end = datetime(2025, 1, 1, 9, 37)
    filtered = await session_data.get_bars("AAPL", start=start, end=end)
    assert len(filtered) == 5  # bars 2-6


@pytest.mark.asyncio
async def test_thread_safety(session_data):
    """Test concurrent access from multiple tasks."""
    import asyncio
    
    async def add_bars_task(symbol, count):
        for i in range(count):
            bar = BarData(
                symbol=symbol,
                timestamp=datetime(2025, 1, 1, 9, 30, i),
                open=150.0,
                high=151.0,
                low=149.0,
                close=150.5,
                volume=1000
            )
            await session_data.add_bar(symbol, bar)
            await asyncio.sleep(0.001)  # Small delay
    
    # Run multiple tasks concurrently
    tasks = [
        add_bars_task("AAPL", 10),
        add_bars_task("GOOGL", 10),
        add_bars_task("MSFT", 10),
    ]
    
    await asyncio.gather(*tasks)
    
    # Verify all bars were added
    assert len(await session_data.get_bars("AAPL")) == 10
    assert len(await session_data.get_bars("GOOGL")) == 10
    assert len(await session_data.get_bars("MSFT")) == 10


@pytest.mark.asyncio
async def test_get_latest_bar(session_data):
    """Test O(1) access to latest bar."""
    bars = [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 1, 9, 30 + i),
            open=150.0 + i,
            high=151.0 + i,
            low=149.0 + i,
            close=150.5 + i,
            volume=1000
        )
        for i in range(100)
    ]
    
    await session_data.add_bars_batch("AAPL", bars)
    
    # Get latest bar (should be instant)
    latest = await session_data.get_latest_bar("AAPL")
    assert latest is not None
    assert latest.close == 150.5 + 99  # Last bar
    
    # Should be same as last in list
    all_bars = await session_data.get_bars("AAPL")
    assert latest == all_bars[-1]


@pytest.mark.asyncio
async def test_get_last_n_bars(session_data):
    """Test efficient last-N access."""
    bars = [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 1, 9, 30 + i),
            open=150.0 + i,
            high=151.0 + i,
            low=149.0 + i,
            close=150.5 + i,
            volume=1000
        )
        for i in range(100)
    ]
    
    await session_data.add_bars_batch("AAPL", bars)
    
    # Get last 20 bars
    last_20 = await session_data.get_last_n_bars("AAPL", 20)
    assert len(last_20) == 20
    assert last_20[0].close == 150.5 + 80  # 80th bar
    assert last_20[-1].close == 150.5 + 99  # 99th bar
    
    # Request more than available
    all_bars = await session_data.get_last_n_bars("AAPL", 200)
    assert len(all_bars) == 100  # Only 100 available


@pytest.mark.asyncio
async def test_get_bars_since(session_data):
    """Test efficient time-based filtering."""
    bars = [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 1, 9, 30 + i),
            open=150.0,
            high=151.0,
            low=149.0,
            close=150.5,
            volume=1000
        )
        for i in range(100)
    ]
    
    await session_data.add_bars_batch("AAPL", bars)
    
    # Get bars since 9:50
    since_time = datetime(2025, 1, 1, 9, 50)
    recent = await session_data.get_bars_since("AAPL", since_time)
    
    assert len(recent) == 80  # Bars 20-99
    assert all(b.timestamp >= since_time for b in recent)


@pytest.mark.asyncio
async def test_get_bar_count(session_data):
    """Test O(1) bar count."""
    bars = [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 1, 9, 30 + i),
            open=150.0,
            high=151.0,
            low=149.0,
            close=150.5,
            volume=1000
        )
        for i in range(100)
    ]
    
    await session_data.add_bars_batch("AAPL", bars)
    
    # Count should be instant
    count = await session_data.get_bar_count("AAPL")
    assert count == 100


@pytest.mark.asyncio
async def test_get_latest_bars_multi(session_data):
    """Test batch retrieval for multiple symbols."""
    # Add bars for multiple symbols
    for symbol in ["AAPL", "GOOGL", "MSFT"]:
        bars = [
            BarData(
                symbol=symbol,
                timestamp=datetime(2025, 1, 1, 9, 30 + i),
                open=150.0,
                high=151.0,
                low=149.0,
                close=150.5 + i,
                volume=1000
            )
            for i in range(10)
        ]
        await session_data.add_bars_batch(symbol, bars)
    
    # Get latest bars for all symbols in one call
    latest_bars = await session_data.get_latest_bars_multi(["AAPL", "GOOGL", "MSFT"])
    
    assert len(latest_bars) == 3
    assert latest_bars["AAPL"].close == 150.5 + 9
    assert latest_bars["GOOGL"].close == 150.5 + 9
    assert latest_bars["MSFT"].close == 150.5 + 9


@pytest.mark.asyncio
async def test_performance_latest_bar(session_data):
    """Benchmark latest bar access performance."""
    import time
    
    # Add many bars
    bars = [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 1, 9, 30, i),
            open=150.0,
            high=151.0,
            low=149.0,
            close=150.5,
            volume=1000
        )
        for i in range(1000)
    ]
    
    await session_data.add_bars_batch("AAPL", bars)
    
    # Benchmark 1000 latest bar accesses
    start = time.perf_counter()
    for _ in range(1000):
        await session_data.get_latest_bar("AAPL")
    elapsed = time.perf_counter() - start
    
    # Should be very fast (< 100ms for 1000 accesses)
    assert elapsed < 0.1
    print(f"1000 latest_bar accesses: {elapsed:.4f}s ({elapsed/1000*1000:.2f}µs per call)")
```

---

## Migration Checklist

### Pre-Implementation
- [ ] Review and approve implementation plan
- [ ] Create feature branch: `feature/session-data-foundation`
- [ ] Set up test database for integration tests

### Implementation
- [ ] Create `session_data.py` with SessionData and SymbolSessionData classes
- [ ] Add unit tests for session_data
- [ ] Update SystemManager to expose session_data property
- [ ] Update BacktestStreamCoordinator to write to session_data
- [ ] Update DataManager API to expose session_data
- [ ] Add deprecation warnings to session_tracker.py
- [ ] Run all unit tests
- [ ] Run integration tests

### Verification
- [ ] Verify existing tests still pass
- [ ] Verify backward compatibility maintained
- [ ] Test with sample backtest run
- [ ] Code review
- [ ] Merge to main branch

### Documentation
- [ ] Update API documentation
- [ ] Add migration guide for users of SessionTracker
- [ ] Update architecture diagrams

---

## Success Criteria

1. ✅ SessionData singleton created and integrated with SystemManager
2. ✅ All new unit tests pass (>95% coverage)
3. ✅ All existing tests still pass (no regressions)
4. ✅ BacktestStreamCoordinator writes data to session_data
5. ✅ DataManager exposes session_data via property
6. ✅ SessionTracker marked as deprecated but still functional

---

## Timeline

**Week 1:**
- Days 1-2: Implement SessionData and SymbolSessionData classes
- Days 3-4: Write unit tests
- Day 5: Code review and fixes

**Week 2:**
- Days 1-2: SystemManager and BacktestStreamCoordinator integration
- Days 3-4: DataManager integration and testing
- Day 5: Documentation and merge

**Total: 2 weeks**

---

## Next Phase Preview

After Phase 1 is complete, Phase 2 will add the Data-Upkeep Thread:
- Bar completeness checking
- Gap detection and filling
- bar_quality metric updates
- Retry mechanism for missing data

This will be covered in a separate implementation plan document.
