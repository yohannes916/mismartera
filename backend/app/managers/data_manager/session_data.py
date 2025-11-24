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
        # Session configuration
        # NOTE: Do NOT store start_time/end_time here!
        # Get trading hours from data_manager.get_trading_hours() instead.
        # Single source of truth: data_manager queries trading calendar for
        # accurate hours (accounts for holidays, early closes, etc.)
        self.historical_bars_trailing_days: int = 0
        self.historical_bars_intervals: List[int] = []
        
        # Session state
        self.session_ended: bool = False
        
        # Per-symbol data structures
        self._symbols: Dict[str, SymbolSessionData] = {}
        
        # Active symbols set (for quick lookup)
        self._active_symbols: Set[str] = set()
        
        # Active streams tracking: {(symbol, stream_type): True}
        # stream_type: "bars", "ticks", "quotes"
        self._active_streams: Dict[Tuple[str, str], bool] = {}
        
        # Thread-safe lock for concurrent access
        self._lock = asyncio.Lock()
        
        logger.info("SessionData initialized")
    
    def apply_config(self, config: 'SessionDataConfig') -> None:
        """Apply session data configuration from SessionConfig.
        
        This updates session_data settings and global settings that control
        background threads (DataUpkeepThread, PrefetchManager, etc.).
        
        Args:
            config: SessionDataConfig from session config file
        """
        from app.config import settings
        
        if config is None:
            logger.info("No session_data_config provided, using defaults")
            return
        
        logger.info("Applying session_data configuration...")
        
        # Historical bars configuration
        if config.historical_bars:
            self.historical_bars_trailing_days = config.historical_bars.trailing_days
            self.historical_bars_intervals = config.historical_bars.intervals
            settings.HISTORICAL_BARS_ENABLED = config.historical_bars.enabled
            settings.HISTORICAL_BARS_TRAILING_DAYS = config.historical_bars.trailing_days
            settings.HISTORICAL_BARS_INTERVALS = config.historical_bars.intervals
            settings.HISTORICAL_BARS_AUTO_LOAD = config.historical_bars.auto_load
            logger.info(f"  ✓ Historical bars: {config.historical_bars.trailing_days} days, intervals {config.historical_bars.intervals}")
        
        # Data upkeep configuration
        if config.data_upkeep:
            settings.DATA_UPKEEP_ENABLED = config.data_upkeep.enabled
            settings.DATA_UPKEEP_CHECK_INTERVAL_SECONDS = config.data_upkeep.check_interval_seconds
            settings.DATA_UPKEEP_RETRY_MISSING_BARS = config.data_upkeep.retry_missing_bars
            settings.DATA_UPKEEP_MAX_RETRIES = config.data_upkeep.max_retries
            settings.DATA_UPKEEP_DERIVED_INTERVALS = config.data_upkeep.derived_intervals
            settings.DATA_UPKEEP_AUTO_COMPUTE_DERIVED = config.data_upkeep.auto_compute_derived
            logger.info(f"  ✓ Data upkeep: check every {config.data_upkeep.check_interval_seconds}s, derived intervals {config.data_upkeep.derived_intervals}")
        
        # Prefetch configuration
        if config.prefetch:
            settings.PREFETCH_ENABLED = config.prefetch.enabled
            settings.PREFETCH_WINDOW_MINUTES = config.prefetch.window_minutes
            settings.PREFETCH_CHECK_INTERVAL_MINUTES = config.prefetch.check_interval_minutes
            settings.PREFETCH_AUTO_ACTIVATE = config.prefetch.auto_activate
            logger.info(f"  ✓ Prefetch: window {config.prefetch.window_minutes} min before session")
        
        # Session boundary configuration
        if config.session_boundary:
            settings.SESSION_AUTO_ROLL = config.session_boundary.auto_roll
            # Also update historical_bars_trailing_days for consistency
            if config.session_boundary.preserve_historical_days != self.historical_bars_trailing_days:
                self.historical_bars_trailing_days = config.session_boundary.preserve_historical_days
                logger.info(f"  ✓ Session boundary: auto-roll enabled, preserve {config.session_boundary.preserve_historical_days} days")
        
        logger.success("Session data configuration applied")
    
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
                logger.info(f"✓ Registered symbol: {symbol} (total active: {len(self._active_symbols)})")
            else:
                logger.debug(f"Symbol already registered: {symbol}")
            
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
    
    def is_stream_active(self, symbol: str, stream_type: str) -> bool:
        """Check if a stream is currently active for a symbol.
        
        Args:
            symbol: Stock symbol
            stream_type: "bars", "ticks", or "quotes"
            
        Returns:
            True if stream is active, False otherwise
        """
        symbol = symbol.upper()
        stream_key = (symbol, stream_type.lower())
        return stream_key in self._active_streams
    
    async def mark_stream_active(self, symbol: str, stream_type: str) -> None:
        """Mark a stream as active for a symbol.
        
        Args:
            symbol: Stock symbol
            stream_type: "bars", "ticks", or "quotes"
        """
        symbol = symbol.upper()
        stream_type = stream_type.lower()
        
        async with self._lock:
            stream_key = (symbol, stream_type)
            self._active_streams[stream_key] = True
            logger.info(f"Marked {stream_type} stream active for {symbol}")
    
    async def mark_stream_inactive(self, symbol: str, stream_type: str) -> None:
        """Mark a stream as inactive for a symbol.
        
        Args:
            symbol: Stock symbol
            stream_type: "bars", "ticks", or "quotes"
        """
        symbol = symbol.upper()
        stream_type = stream_type.lower()
        
        async with self._lock:
            stream_key = (symbol, stream_type)
            if stream_key in self._active_streams:
                del self._active_streams[stream_key]
                logger.info(f"Marked {stream_type} stream inactive for {symbol}")
    
    async def add_bar(self, symbol: str, bar: BarData) -> None:
        """Add a 1-minute bar to session data.
        
        Automatically determines if bar belongs to current session or historical data
        based on the bar's date vs current session date.
        
        Args:
            symbol: Stock symbol
            bar: Bar data to add
        """
        symbol = symbol.upper()
        
        # Auto-register symbol if not already registered
        if symbol not in self._active_symbols:
            await self.register_symbol(symbol)
        
        # Get current session date to determine where to store the bar
        current_session_date = self.get_current_session_date()
        bar_date = bar.timestamp.date()
        
        async with self._lock:
            symbol_data = self._symbols[symbol]
            
            # Check if bar belongs to current session or historical data
            if current_session_date is not None and bar_date == current_session_date:
                # Current session bar - add to bars_1m and update metrics
                symbol_data.bars_1m.append(bar)
                symbol_data.update_from_bar(bar)
            else:
                # Historical bar - add to historical_bars storage
                if 1 not in symbol_data.historical_bars:
                    symbol_data.historical_bars[1] = {}
                if bar_date not in symbol_data.historical_bars[1]:
                    symbol_data.historical_bars[1][bar_date] = []
                symbol_data.historical_bars[1][bar_date].append(bar)
    
    async def add_bars_batch(
        self, 
        symbol: str, 
        bars: List[BarData],
        insert_mode: str = "auto"
    ) -> None:
        """Add multiple bars in batch (more efficient).
        
        Args:
            symbol: Stock symbol
            bars: List of bars to add
            insert_mode: How to insert bars:
                - "auto": Date-based routing (current session vs historical)
                - "stream": Append to current session (assumes chronological)
                - "gap_fill": Insert into current session maintaining sort order
                - "historical": Force to historical_bars storage
        """
        symbol = symbol.upper()
        
        if symbol not in self._active_symbols:
            await self.register_symbol(symbol)
        
        async with self._lock:
            symbol_data = self._symbols[symbol]
            
            if insert_mode == "historical":
                # Force all bars to historical storage
                if 1 not in symbol_data.historical_bars:
                    symbol_data.historical_bars[1] = {}
                for bar in bars:
                    bar_date = bar.timestamp.date()
                    if bar_date not in symbol_data.historical_bars[1]:
                        symbol_data.historical_bars[1][bar_date] = []
                    symbol_data.historical_bars[1][bar_date].append(bar)
                return
            
            if insert_mode == "stream":
                # Fast path: assume bars are chronological, just append
                symbol_data.bars_1m.extend(bars)
                for bar in bars:
                    symbol_data.update_from_bar(bar)
                return
            
            if insert_mode == "gap_fill":
                # Sorted insertion to maintain chronological order
                import bisect
                bars_list = list(symbol_data.bars_1m)
                for bar in bars:
                    # Find insertion point to maintain sorted order
                    idx = bisect.bisect_left([b.timestamp for b in bars_list], bar.timestamp)
                    bars_list.insert(idx, bar)
                    symbol_data.update_from_bar(bar)
                # Replace deque with updated sorted list
                from collections import deque
                symbol_data.bars_1m = deque(bars_list)
                return
            
            # Default "auto" mode: date-based routing
            current_session_date = self.get_current_session_date()
            current_session_bars = []
            historical_bars_by_date = {}
            
            for bar in bars:
                bar_date = bar.timestamp.date()
                if current_session_date is not None and bar_date == current_session_date:
                    current_session_bars.append(bar)
                else:
                    if bar_date not in historical_bars_by_date:
                        historical_bars_by_date[bar_date] = []
                    historical_bars_by_date[bar_date].append(bar)
            
            # Add current session bars with sorted insertion
            if current_session_bars:
                import bisect
                bars_list = list(symbol_data.bars_1m)
                for bar in current_session_bars:
                    idx = bisect.bisect_left([b.timestamp for b in bars_list], bar.timestamp)
                    bars_list.insert(idx, bar)
                    symbol_data.update_from_bar(bar)
                from collections import deque
                symbol_data.bars_1m = deque(bars_list)
            
            # Add historical bars
            if historical_bars_by_date:
                if 1 not in symbol_data.historical_bars:
                    symbol_data.historical_bars[1] = {}
                for bar_date, date_bars in historical_bars_by_date.items():
                    if bar_date not in symbol_data.historical_bars[1]:
                        symbol_data.historical_bars[1][bar_date] = []
                    symbol_data.historical_bars[1][bar_date].extend(date_bars)
    
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
                bars = list(symbol_data.bars_1m)
            else:
                bars = symbol_data.bars_derived.get(interval, []).copy()
            
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
            
            return bars
    
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
    
    # ==================== HISTORICAL BARS METHODS (Phase 3) ====================
    
    def get_current_session_date(self) -> Optional[date]:
        """Get current session date from TimeProvider (single source of truth).
        
        Returns:
            Current session date from TimeProvider, or None if not available
        """
        try:
            from app.managers.data_manager.time_provider import get_time_provider
            time_provider = get_time_provider()
            current_time = time_provider.get_current_time()
            return current_time.date()
        except Exception as e:
            logger.warning(f"Could not get current date from TimeProvider: {e}")
            return None
    
    def is_session_active(self) -> bool:
        """Check if a session is currently active.
        
        A session is considered active when ALL of the following are true:
        1. System is in RUNNING state (from system_manager)
        2. Market is currently open (from data_manager)
        3. Session has not been explicitly ended (from self.session_ended flag)
        
        Note: Does NOT require active symbols. A session can be active even
        with no symbols streaming, as long as system is running and market is open.
        
        Returns:
            True if session is active, False otherwise
        """
        # 1. Check if session explicitly ended (self)
        if self.session_ended:
            logger.debug("Session not active: session_ended=True")
            return False
        
        # 2 & 3. Check system state and market status via system_manager
        try:
            from app.managers.system_manager import get_system_manager
            system_manager = get_system_manager()
            
            # Check system is running
            if not system_manager.is_running():
                logger.debug("Session not active: system not running")
                return False
            
            # Check market is open via data_manager
            data_manager = system_manager.get_data_manager()
            market_open = data_manager.check_market_open()
            
            if not market_open:
                logger.debug("Session not active: market closed")
            else:
                logger.debug("Session active: all checks passed")
            
            return market_open
            
        except Exception as e:
            logger.warning(f"Session not active: error checking status: {e}")
            import traceback
            logger.warning(f"Traceback: {traceback.format_exc()}")
            # If we can't determine status, assume not active
            return False
    
    async def load_historical_bars(
        self,
        symbol: str,
        trailing_days: int,
        intervals: List[int],
        data_repository
    ) -> int:
        """Load historical bars for trailing days from database.
        
        Args:
            symbol: Stock symbol
            trailing_days: Number of days to load
            intervals: List of intervals (1, 5, 15, etc.)
            data_repository: Database access (session or repository)
            
        Returns:
            Total number of bars loaded
        """
        if data_repository is None:
            logger.warning(f"No data_repository available for loading historical bars")
            return 0
        
        symbol = symbol.upper()
        
        if symbol not in self._active_symbols:
            await self.register_symbol(symbol)
        
        current_session_date = self.get_current_session_date()
        if current_session_date is None:
            logger.warning("No current session date available, cannot load historical bars")
            return 0
        
        # Calculate date range
        end_date = current_session_date - timedelta(days=1)  # Day before current session
        start_date = end_date - timedelta(days=trailing_days)
        
        total_loaded = 0
        
        async with self._lock:
            symbol_data = self._symbols[symbol]
            
            for interval in intervals:
                try:
                    # Query database using same interface detection as gap filling
                    bars_db = await self._query_historical_bars(
                        data_repository,
                        symbol,
                        start_date,
                        end_date,
                        interval
                    )
                    
                    if not bars_db:
                        continue
                    
                    # Group by date
                    from collections import defaultdict
                    bars_by_date = defaultdict(list)
                    for bar in bars_db:
                        bar_date = bar.timestamp.date()
                        bars_by_date[bar_date].append(bar)
                    
                    # Store in historical_bars
                    if interval not in symbol_data.historical_bars:
                        symbol_data.historical_bars[interval] = {}
                    
                    symbol_data.historical_bars[interval].update(dict(bars_by_date))
                    total_loaded += len(bars_db)
                    
                    logger.debug(
                        f"Loaded {len(bars_db)} historical {interval}m bars for {symbol}"
                    )
                
                except Exception as e:
                    logger.error(f"Error loading historical bars for {symbol}: {e}")
                    continue
        
        logger.info(
            f"Loaded {total_loaded} historical bars for {symbol} "
            f"({trailing_days} days, intervals: {intervals})"
        )
        
        return total_loaded
    
    async def _query_historical_bars(
        self,
        data_repository,
        symbol: str,
        start_date: date,
        end_date: date,
        interval: int
    ) -> List:
        """Query historical bars from database (internal helper).
        
        Supports same interfaces as gap filling.
        """
        from datetime import datetime as dt_class
        
        # Convert dates to datetime
        start_dt = dt_class.combine(start_date, datetime.min.time())
        end_dt = dt_class.combine(end_date, datetime.max.time())
        
        bars_db = None
        
        # Method 1: Database session (AsyncSession)
        if hasattr(data_repository, 'execute'):
            from app.repositories.market_data_repository import MarketDataRepository
            bars_db = await MarketDataRepository.get_bars_by_symbol(
                session=data_repository,
                symbol=symbol,
                start_date=start_dt,
                end_date=end_dt,
                interval=f"{interval}m"
            )
        
        # Method 2: Repository with get_bars_by_symbol
        elif hasattr(data_repository, 'get_bars_by_symbol'):
            bars_db = await data_repository.get_bars_by_symbol(
                symbol=symbol,
                start_date=start_dt,
                end_date=end_dt,
                interval=f"{interval}m"
            )
        
        # Method 3: Generic get_bars
        elif hasattr(data_repository, 'get_bars'):
            bars_db = await data_repository.get_bars(
                symbol=symbol,
                start=start_dt,
                end=end_dt,
                interval=interval
            )
        
        return bars_db or []
    
    async def get_historical_bars(
        self,
        symbol: str,
        days_back: int = 0,
        interval: int = 1
    ) -> Dict[date, List[BarData]]:
        """Get historical bars for past N days.
        
        Args:
            symbol: Stock symbol
            days_back: Number of days to retrieve (0 = all)
            interval: Bar interval
            
        Returns:
            Dictionary mapping date to bars for that date
        """
        symbol = symbol.upper()
        
        async with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return {}
            
            historical = symbol_data.historical_bars.get(interval, {})
            
            if days_back <= 0:
                return dict(historical)
            
            # Get last N days
            dates = sorted(historical.keys(), reverse=True)[:days_back]
            return {d: historical[d] for d in dates}
    
    async def get_all_bars_including_historical(
        self,
        symbol: str,
        interval: int = 1
    ) -> List[BarData]:
        """Get all bars including historical and current session.
        
        Chronologically ordered from oldest to newest.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval
            
        Returns:
            All bars chronologically ordered
        """
        symbol = symbol.upper()
        
        async with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return []
            
            all_bars = []
            
            # Add historical bars (sorted by date)
            historical = symbol_data.historical_bars.get(interval, {})
            for bar_date in sorted(historical.keys()):
                all_bars.extend(historical[bar_date])
            
            # Add current session bars
            if interval == 1:
                all_bars.extend(list(symbol_data.bars_1m))
            else:
                derived = symbol_data.bars_derived.get(interval, [])
                all_bars.extend(derived)
            
            return all_bars
    
    async def roll_session(
        self,
        new_session_date: date
    ) -> None:
        """Roll to a new session, moving current data to historical.
        
        Moves current session bars to historical storage and clears
        current session for new data. Maintains trailing days window.
        
        Note: This method is for manual session rolling. The current
        session date comes from TimeProvider as the single source of truth.
        
        Args:
            new_session_date: Date of the new session (informational only,
                TimeProvider should be updated separately)
        """
        old_date = self.get_current_session_date()
        if old_date is None:
            # No previous session data to roll
            logger.info(f"Starting first session for date: {new_session_date}")
            return
        
        async with self._lock:
            
            # For each symbol, move current session to historical
            for symbol_data in self._symbols.values():
                # Move current 1m bars to historical
                if len(symbol_data.bars_1m) > 0:
                    historical_bars = list(symbol_data.bars_1m)
                    if 1 not in symbol_data.historical_bars:
                        symbol_data.historical_bars[1] = {}
                    symbol_data.historical_bars[1][old_date] = historical_bars
                
                # Move derived bars to historical
                for interval, bars in symbol_data.bars_derived.items():
                    if len(bars) > 0:
                        if interval not in symbol_data.historical_bars:
                            symbol_data.historical_bars[interval] = {}
                        symbol_data.historical_bars[interval][old_date] = bars.copy()
                
                # Remove oldest day if exceeding trailing days
                max_days = self.historical_bars_trailing_days
                if max_days > 0:
                    for interval in list(symbol_data.historical_bars.keys()):
                        dates = sorted(symbol_data.historical_bars[interval].keys())
                        while len(dates) > max_days:
                            oldest = dates.pop(0)
                            del symbol_data.historical_bars[interval][oldest]
                            logger.debug(
                                f"Removed oldest historical day: {oldest} for interval {interval}m"
                            )
                
                # Clear current session data
                symbol_data.bars_1m.clear()
                symbol_data.bars_derived.clear()
                symbol_data.quotes.clear()
                symbol_data.ticks.clear()
                symbol_data.reset_session_metrics()
            
            # Reset session state
            self.session_ended = False
        
        logger.info(
            f"Rolled session from {old_date} to {new_session_date}. "
            f"Note: TimeProvider should be updated to {new_session_date} separately."
        )
    
    async def reset_session(self) -> None:
        """Reset current session data.
        
        Clears all session-specific data but keeps configuration and symbol registrations.
        The current session date comes from TimeProvider (single source of truth).
        
        Note: This does NOT change the TimeProvider date. Call this when starting
        a new session after TimeProvider has been updated.
        """
        async with self._lock:
            self.session_ended = False
            
            # Reset all symbol data
            for symbol_data in self._symbols.values():
                symbol_data.bars_1m.clear()
                symbol_data.bars_derived.clear()
                symbol_data.quotes.clear()
                symbol_data.ticks.clear()
                symbol_data.reset_session_metrics()
            
            current_date = self.get_current_session_date()
            logger.info(f"Reset session data for date: {current_date}")
    
    async def end_session(self) -> None:
        """Mark current session as ended."""
        async with self._lock:
            self.session_ended = True
            current_date = self.get_current_session_date()
            logger.info(f"Session ended for date: {current_date}")
    
    async def clear(self) -> None:
        """Clear all session data including symbols, bars, and session state.
        
        This method:
        - Clears all symbol data (bars, ticks, quotes, metrics)
        - Removes all registered symbols
        - Resets session ended flag
        
        Use this when stopping the system or starting a fresh session.
        Note: Current date comes from TimeProvider, not stored here.
        """
        async with self._lock:
            num_symbols = len(self._active_symbols)
            num_streams = len(self._active_streams)
            self._symbols.clear()
            self._active_symbols.clear()
            self._active_streams.clear()  # Clear active streams tracking
            self.session_ended = False
            logger.warning(f"⚠ Session data cleared! Removed {num_symbols} symbols, {num_streams} active streams")
            import traceback
            logger.debug(f"Clear called from:\n{''.join(traceback.format_stack()[-5:-1])}")
    
    async def clear_all(self) -> None:
        """Clear all session data (alias for clear(), kept for backwards compatibility)."""
        await self.clear()
    
    def get_active_symbols(self) -> Set[str]:
        """Get set of active symbols (thread-safe read)."""
        symbols = self._active_symbols.copy()
        logger.debug(f"get_active_symbols() returning {len(symbols)} symbols: {symbols}")
        return symbols


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
