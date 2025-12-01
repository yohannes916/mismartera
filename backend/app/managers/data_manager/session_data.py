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
from typing import Dict, List, Optional, Set, Deque, Union
from dataclasses import dataclass, field
from collections import defaultdict, deque
import asyncio
import threading

from app.models.trading import BarData, TickData
from app.logger import logger


@dataclass
class SymbolSessionData:
    """Per-symbol data for current trading session.
    
    Optimized for fast reads by AnalysisEngine and other consumers:
    - Latest bar cached for O(1) access
    - Deque for efficient append and recent-N access
    - Timestamp index for fast lookups
    - Dynamic base interval support (1s or 1m per symbol)
    """
    
    symbol: str
    
    # Base interval for this symbol ("1s" or "1m")
    base_interval: str = "1m"
    
    # Base bars (1s or 1m depending on base_interval)
    bars_base: Deque[BarData] = field(default_factory=deque)
    
    # Cache for O(1) access to latest bar
    _latest_bar: Optional[BarData] = None
    
    # Derived bars (e.g., {"1m": [...], "5m": [...], "15m": [...]})
    bars_derived: Dict[str, List[BarData]] = field(default_factory=dict)
    
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
    # Example: {"1m": {date1: [...], date2: [...]}, "5m": {date1: [...], date2: [...]}}
    historical_bars: Dict[str, Dict[date, List[BarData]]] = field(
        default_factory=lambda: defaultdict(dict)
    )
    
    @property
    def bars_1m(self) -> Deque[BarData]:
        """Backward compatibility: Access to bars (works for 1m base or derived 1m from 1s).
        
        Returns:
            Base bars if interval is 1m, otherwise derived 1m bars
        """
        if self.base_interval == "1m":
            return self.bars_base
        else:
            # Return derived 1m bars (if computed from 1s)
            return deque(self.bars_derived.get("1m", []))
    
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
    
    def get_latest_bar(self, interval = None) -> Optional[BarData]:
        """Get the most recent bar (O(1) operation).
        
        Args:
            interval: Bar interval (int minutes or string like "1s", "1m", "5m"). If None, uses base_interval.
            
        Returns:
            Most recent bar or None
        """
        # Normalize interval: convert int to string
        if isinstance(interval, int):
            interval = f"{interval}m"
        
        if interval is None or interval == self.base_interval:
            return self._latest_bar
        else:
            # Try string key first
            bars = self.bars_derived.get(interval, [])
            if not bars and isinstance(interval, str) and interval.endswith('m'):
                # Fallback: try integer key
                try:
                    interval_int = int(interval[:-1])
                    bars = self.bars_derived.get(interval_int, [])
                except (ValueError, IndexError):
                    pass
            return bars[-1] if bars else None
    
    def get_last_n_bars(self, n: int, interval = None) -> List[BarData]:
        """Get the last N bars efficiently.
        
        For base bars, uses deque for O(N) access.
        For derived bars, uses list slicing.
        
        Args:
            n: Number of bars to retrieve
            interval: Bar interval (int minutes or string like "1s", "1m", "5m"). If None, uses base_interval.
            
        Returns:
            List of last N bars (oldest to newest)
        """
        # Normalize interval: convert int to string
        if isinstance(interval, int):
            interval = f"{interval}m"
        
        if interval is None or interval == self.base_interval:
            # Efficient: only iterate over last n items from base bars
            if len(self.bars_base) <= n:
                return list(self.bars_base)
            else:
                # Get last n items from deque
                return list(self.bars_base)[-n:]
        else:
            # Try string key first
            bars = self.bars_derived.get(interval, [])
            if not bars and isinstance(interval, str) and interval.endswith('m'):
                # Fallback: try integer key
                try:
                    interval_int = int(interval[:-1])
                    bars = self.bars_derived.get(interval_int, [])
                except (ValueError, IndexError):
                    pass
            return bars[-n:] if bars else []
    
    def get_bars_since(self, timestamp: datetime, interval = None) -> List[BarData]:
        """Get all bars since a specific timestamp.
        
        Args:
            timestamp: Start timestamp
            interval: Bar interval (int minutes or string like "1s", "1m", "5m"). If None, uses base_interval.
            
        Returns:
            List of bars after timestamp
        """
        # Normalize interval: convert int to string
        if isinstance(interval, int):
            interval = f"{interval}m"
        
        if interval is None or interval == self.base_interval:
            # Efficient: iterate backward from newest until we hit timestamp
            result = []
            for bar in reversed(self.bars_base):
                if bar.timestamp < timestamp:
                    break
                result.append(bar)
            return list(reversed(result))
        else:
            # Try string key first
            bars = self.bars_derived.get(interval, [])
            if not bars and isinstance(interval, str) and interval.endswith('m'):
                # Fallback: try integer key
                try:
                    interval_int = int(interval[:-1])
                    bars = self.bars_derived.get(interval_int, [])
                except (ValueError, IndexError):
                    pass
            return [b for b in bars if b.timestamp >= timestamp] if bars else []
    
    def get_bar_count(self, interval = None) -> int:
        """Get count of bars for an interval (O(1) operation).
        
        Args:
            interval: Bar interval (int minutes, or string like "1s", "1m", "5m"). If None, uses base_interval.
            
        Returns:
            Number of bars available
        """
        # Normalize interval: convert int to string
        if isinstance(interval, int):
            interval = f"{interval}m"
        
        if interval is None or interval == self.base_interval:
            return len(self.bars_base)
        else:
            # Try string key first (e.g., "5m")
            bars = self.bars_derived.get(interval)
            if bars is None and isinstance(interval, str) and interval.endswith('m'):
                # Fallback: try integer key (e.g., 5)
                try:
                    interval_int = int(interval[:-1])
                    bars = self.bars_derived.get(interval_int)
                except (ValueError, IndexError):
                    pass
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
        self._session_active: bool = False  # Managed by upkeep thread
        
        # Per-symbol data structures
        self._symbols: Dict[str, SymbolSessionData] = {}
        
        # Active symbols set (for quick lookup)
        self._active_symbols: Set[str] = set()
        
        # Active streams tracking: {(symbol, stream_type): True}
        # stream_type: "bars", "ticks", "quotes"
        self._active_streams: Dict[Tuple[str, str], bool] = {}
        # Event to signal upkeep thread when new data arrives
        self._data_arrival_event = threading.Event()
        # Thread lock for concurrent access
        self._lock = threading.RLock()
        
        # Historical indicators storage: {indicator_name: value}
        self._historical_indicators: Dict[str, any] = {}
        
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
        
        # Prefetch configuration (logged only, not stored in settings)
        if config.prefetch:
            logger.info(f"  ✓ Prefetch: window {config.prefetch.window_minutes} min before session")
        
        logger.success("Session data configuration applied")
    
    def activate_session(self) -> None:
        """
        Activate the trading session.
        
        Called by upkeep thread when:
        1. System starts (initial activation)
        2. New trading day begins after EOD transition
        
        This signals to the stream coordinator that it can begin streaming data.
        """
        self._session_active = True
        logger.info("✓ Session activated")
    
    def deactivate_session(self) -> None:
        """
        Deactivate the trading session.
        
        Called by upkeep thread when market close time is reached.
        This signals to the stream coordinator to stop streaming.
        """
        self._session_active = False
        logger.info("✓ Session deactivated")
    
    def is_session_active(self) -> bool:
        """
        Check if session is currently active.
        
        Returns:
            True if session is active and streaming should occur
        
        Note: This is a simple boolean check (GIL-safe for reads)
        """
        return self._session_active
    
    def register_symbol(self, symbol: str) -> SymbolSessionData:
        """Register a new symbol for tracking.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            SymbolSessionData for the symbol
        """
        symbol = symbol.upper()
        
        with self._lock:
            if symbol not in self._symbols:
                self._symbols[symbol] = SymbolSessionData(symbol=symbol)
                self._active_symbols.add(symbol)
                logger.info(f"✓ Registered symbol: {symbol} (total active: {len(self._active_symbols)})")
            else:
                logger.debug(f"Symbol already registered: {symbol}")
            
            return self._symbols[symbol]
    
    def get_symbol_data(self, symbol: str) -> Optional[SymbolSessionData]:
        """Get data for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            SymbolSessionData if symbol is registered, None otherwise
        """
        symbol = symbol.upper()
        with self._lock:
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
    
    def mark_stream_active(self, symbol: str, stream_type: str) -> None:
        """Mark a stream as active for a symbol.
        
        Args:
            symbol: Stock symbol
            stream_type: "bars", "ticks", or "quotes"
        """
        symbol = symbol.upper()
        stream_type = stream_type.lower()
        
        with self._lock:
            stream_key = (symbol, stream_type)
            self._active_streams[stream_key] = True
            logger.info(f"Marked {stream_type} stream active for {symbol}")
    
    def mark_stream_inactive(self, symbol: str, stream_type: str) -> None:
        """Mark a stream as inactive for a symbol.
        
        Args:
            symbol: Stock symbol
            stream_type: "bars", "ticks", or "quotes"
        """
        symbol = symbol.upper()
        stream_type = stream_type.lower()
        
        with self._lock:
            stream_key = (symbol, stream_type)
            if stream_key in self._active_streams:
                del self._active_streams[stream_key]
                logger.info(f"Marked {stream_type} stream inactive for {symbol}")
    
    def add_bar(self, symbol: str, bar: BarData) -> None:
        """Add a bar to session data (base interval: 1s or 1m).
        
        Automatically determines if bar belongs to current session or historical data
        based on the bar's date vs current session date.
        Sets the base_interval from the first bar's interval.
        
        Args:
            symbol: Stock symbol
            bar: Bar data to add (with interval field)
        """
        symbol = symbol.upper()
        
        # Auto-register symbol if not already registered
        if symbol not in self._active_symbols:
            self.register_symbol(symbol)
        
        # Get current session date to determine where to store the bar
        current_session_date = self.get_current_session_date()
        bar_date = bar.timestamp.date()
        
        with self._lock:
            symbol_data = self._symbols[symbol]
            
            # Set base_interval from first bar if not already set
            if symbol_data.base_interval == "1m" and bar.interval in ["1s", "1m"]:
                symbol_data.base_interval = bar.interval
            
            # Check if bar belongs to current session or historical data
            if current_session_date is not None and bar_date == current_session_date:
                # DEPRECATED: Do NOT add to bars_base here!
                # SessionCoordinator (PHASE_5) is responsible for adding current session bars
                # This method is only for adding historical bars
                logger.warning(
                    f"add_bar() called with current session date - this should not happen! "
                    f"SessionCoordinator should add current session bars directly. "
                    f"Bar: {symbol} {bar.timestamp}"
                )
                # Do NOT add to bars_base to prevent duplicates!
                # symbol_data.bars_base.append(bar)  # REMOVED
                # symbol_data.update_from_bar(bar)   # REMOVED
            else:
                # Historical bar - add to historical_bars storage
                # Store by interval (string) and date
                interval_key = bar.interval
                if interval_key not in symbol_data.historical_bars:
                    symbol_data.historical_bars[interval_key] = {}
                if bar_date not in symbol_data.historical_bars[interval_key]:
                    symbol_data.historical_bars[interval_key][bar_date] = []
                symbol_data.historical_bars[interval_key][bar_date].append(bar)
    
    def add_bars_batch(
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
            self.register_symbol(symbol)
        
        with self._lock:
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
                # Signal upkeep thread that new data arrived
                self._data_arrival_event.set()
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
                # Signal upkeep thread that new data arrived
                self._data_arrival_event.set()
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
                # Signal upkeep thread that new data arrived
                self._data_arrival_event.set()
            
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
    
    def get_latest_bar(self, symbol: str, interval: int = 1) -> Optional[BarData]:
        """Get the most recent bar for a symbol (O(1) operation).
        
        Optimized for high-frequency access by AnalysisEngine.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval in minutes (1, 5, 15, etc.)
            
        Returns:
            Most recent bar or None
        """
        symbol = symbol.upper()
        with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return None
            return symbol_data.get_latest_bar(interval)
    
    def get_last_n_bars(
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
        with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return []
            return symbol_data.get_last_n_bars(n, interval)
    
    def get_bars_since(
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
        with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return []
            return symbol_data.get_bars_since(timestamp, interval)
    
    def get_bar_count(self, symbol: str, interval: int = 1) -> int:
        """Get count of available bars (O(1) operation).
        
        Args:
            symbol: Stock symbol
            interval: Bar interval in minutes
            
        Returns:
            Number of bars available
        """
        symbol = symbol.upper()
        with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return 0
            return symbol_data.get_bar_count(interval)
    
    def get_latest_bars_multi(
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
        with self._lock:
            for symbol in symbols:
                symbol = symbol.upper()
                symbol_data = self._symbols.get(symbol)
                if symbol_data:
                    result[symbol] = symbol_data.get_latest_bar(interval)
                else:
                    result[symbol] = None
        return result
    
    def get_bars_ref(
        self,
        symbol: str,
        interval: int = 1
    ) -> Union[Deque[BarData], List[BarData]]:
        """Get direct reference to bars container (ZERO-COPY, HIGH PERFORMANCE).
        
        ⚠️ WARNING: Returns mutable container reference.
        Caller must NOT modify the returned container.
        For read-only iteration and access only.
        
        Performance:
        - Zero memory allocation
        - Zero copying overhead
        - Direct container access
        - Ideal for AnalysisEngine hot path
        
        Args:
            symbol: Stock symbol
            interval: Bar interval in minutes (1, 5, 15, etc.)
            
        Returns:
            Direct reference to bars deque (1m) or list (derived)
            Empty container if symbol/interval not found
        
        Example:
            # Zero-copy iteration
            bars_ref = session_data.get_bars_ref("AAPL", 1)
            for bar in bars_ref:
                price = bar.close
            
            # Zero-copy slice (only sliced portion copied)
            last_20 = list(bars_ref)[-20:]
        """
        symbol = symbol.upper()
        
        with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return deque() if interval == 1 else []
            
            # Return direct reference (zero-copy)
            if interval == 1:
                return symbol_data.bars_1m
            else:
                return symbol_data.bars_derived.get(interval, [])
    
    def get_bars(
        self,
        symbol: str,
        interval: int = 1,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> List[BarData]:
        """Get bars for a symbol (CREATES COPY).
        
        ⚠️ PERFORMANCE NOTE: This method creates a copy of bars.
        For high-frequency access without filtering, use get_bars_ref() instead.
        
        Use this method when:
        - You need time-based filtering (start/end)
        - You need to modify the returned list
        - You need to store the list long-term
        
        For read-only iteration without filtering, prefer get_bars_ref().
        
        Args:
            symbol: Stock symbol
            interval: Bar interval in minutes (1, 5, 15, etc.)
            start: Optional start time filter
            end: Optional end time filter
            
        Returns:
            List of bars matching criteria (copy created)
        """
        symbol = symbol.upper()
        
        with self._lock:
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
    
    def get_session_metrics(self, symbol: str) -> Dict[str, any]:
        """Get current session metrics for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with session metrics
        """
        symbol = symbol.upper()
        
        with self._lock:
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
        """Get current session date from TimeManager (single source of truth).
        
        Returns:
            Current session date from TimeManager, or None if not available
        """
        try:
            from app.managers.system_manager import get_system_manager
            system_mgr = get_system_manager()
            time_mgr = system_mgr.get_time_manager()
            current_time = time_mgr.get_current_time()
            return current_time.date()
        except Exception as e:
            logger.warning(f"Could not get current date from TimeManager: {e}")
            return None
    
    def load_historical_bars(
        self,
        symbol: str,
        trailing_days: int,
        intervals: List,  # Can be int (for minutes) or str (e.g., '1m', '5m', '1d')
        data_repository
    ) -> int:
        """Load historical bars for trailing days from database.
        
        Args:
            symbol: Stock symbol
            trailing_days: Number of days to load
            intervals: List of intervals (1, 5, 15) or ('1m', '5m', '1d', etc.)
            data_repository: Database access (session or repository)
            
        Returns:
            Total number of bars loaded
        """
        if data_repository is None:
            logger.warning(f"No data_repository available for loading historical bars")
            return 0
        
        symbol = symbol.upper()
        
        if symbol not in self._active_symbols:
            self.register_symbol(symbol)
        
        current_session_date = self.get_current_session_date()
        if current_session_date is None:
            logger.warning("No current session date available, cannot load historical bars")
            return 0
        
        # Calculate date range
        end_date = current_session_date - timedelta(days=1)  # Day before current session
        start_date = end_date - timedelta(days=trailing_days)
        
        total_loaded = 0
        
        with self._lock:
            symbol_data = self._symbols[symbol]
            
            for interval in intervals:
                try:
                    # Query database using same interface detection as gap filling
                    bars_db = self._query_historical_bars(
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
                    
                    # Format interval for display
                    interval_str = f"{interval}m" if isinstance(interval, int) else interval
                    logger.debug(
                        f"Loaded {len(bars_db)} historical {interval_str} bars for {symbol}"
                    )
                
                except Exception as e:
                    logger.error(f"Error loading historical bars for {symbol}: {e}")
                    continue
        
        logger.info(
            f"Loaded {total_loaded} historical bars for {symbol} "
            f"({trailing_days} days, intervals: {intervals})"
        )
        
        return total_loaded
    
    def _query_historical_bars(
        self,
        data_repository,
        symbol: str,
        start_date: date,
        end_date: date,
        interval  # Can be int (for minutes) or str (e.g., '1m', '5m', '1d')
    ) -> List:
        """Query historical bars from database (internal helper).
        
        Supports same interfaces as gap filling.
        Handles both integer (minutes) and string (e.g., '1m', '1d') interval formats.
        """
        from datetime import datetime as dt_class
        
        # Convert dates to datetime
        start_dt = dt_class.combine(start_date, datetime.min.time())
        end_dt = dt_class.combine(end_date, datetime.max.time())
        
        # Convert interval to string format if it's an integer
        interval_str = f"{interval}m" if isinstance(interval, int) else interval
        
        # Load bars from Parquet (no database)
        from app.managers.data_manager.parquet_storage import parquet_storage
        
        df = parquet_storage.read_bars(
            interval_str,
            symbol,
            start_date=start_dt,
            end_date=end_dt
        )
        
        # Convert DataFrame to list of BarData objects
        bars_db = []
        if not df.empty:
            for _, row in df.iterrows():
                bars_db.append(BarData(
                    symbol=row['symbol'],
                    timestamp=row['timestamp'],
                    interval=row.get('interval', interval_str),
                    open=row['open'],
                    high=row['high'],
                    low=row['low'],
                    close=row['close'],
                    volume=row['volume']
                ))
        
        return bars_db
    
    def get_historical_bars(
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
        
        with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return {}
            
            historical = symbol_data.historical_bars.get(interval, {})
            
            if days_back <= 0:
                return dict(historical)
            
            # Get last N days
            dates = sorted(historical.keys(), reverse=True)[:days_back]
            return {d: historical[d] for d in dates}
    
    def get_all_bars_including_historical(
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
        
        with self._lock:
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
    
    def roll_session(
        self,
        new_session_date: date
    ) -> None:
        """Roll to a new session, moving current data to historical.
        
        Moves current session bars to historical storage and clears
        current session for new data. Maintains trailing days window.
        
        Note: This method is for manual session rolling. The current
        session date comes from TimeManager as the single source of truth.
        
        Args:
            new_session_date: Date of the new session (informational only,
                TimeManager should be updated separately)
        """
        old_date = self.get_current_session_date()
        if old_date is None:
            # No previous session data to roll
            logger.info(f"Starting first session for date: {new_session_date}")
            return
        
        with self._lock:
            
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
            
            # Session state managed by upkeep thread
        
        logger.info(
            f"Rolled session from {old_date} to {new_session_date}. "
            f"Note: TimeManager should be updated to {new_session_date} separately."
        )
    
    def reset_session(self) -> None:
        """Reset current session data.
        
        Clears all session-specific data but keeps configuration and symbol registrations.
        The current session date comes from TimeManager (single source of truth).
        
        Note: This does NOT change the TimeManager date. Call this when starting
        a new session after TimeManager has been updated.
        """
        with self._lock:
            # Reset all symbol data
            for symbol_data in self._symbols.values():
                symbol_data.bars_1m.clear()
                symbol_data.bars_derived.clear()
                symbol_data.quotes.clear()
                symbol_data.ticks.clear()
                symbol_data.reset_session_metrics()
            
            current_date = self.get_current_session_date()
            logger.info(f"Reset session data for date: {current_date}")
    
    def end_session(self) -> None:
        """Mark current session as ended."""
        with self._lock:
            self._session_active = False
            current_date = self.get_current_session_date()
            logger.info(f"Session ended for date: {current_date}")
    
    def clear(self) -> None:
        """Clear all session data including symbols, bars, and session state.
        
        This method:
        - Clears all symbol data (bars, ticks, quotes, metrics)
        - Removes all registered symbols
        - Resets session ended flag
        
        Use this when stopping the system or starting a fresh session.
        Note: Current date comes from TimeManager, not stored here.
        """
        with self._lock:
            num_symbols = len(self._active_symbols)
            num_streams = len(self._active_streams)
            self._symbols.clear()
            self._active_symbols.clear()
            self._active_streams.clear()  # Clear active streams tracking
            logger.warning(f"⚠ Session data cleared! Removed {num_symbols} symbols, {num_streams} active streams")
            import traceback
            logger.debug(f"Clear called from:\n{''.join(traceback.format_stack()[-5:-1])}")
    
    def clear_all(self) -> None:
        """Clear all session data (alias for clear(), kept for backwards compatibility)."""
        self.clear()
    
    def get_active_symbols(self) -> Set[str]:
        """Get set of active symbols (thread-safe read)."""
        symbols = self._active_symbols.copy()
        logger.debug(f"get_active_symbols() returning {len(symbols)} symbols: {symbols}")
        return symbols
    
    # ==================== SESSION COORDINATOR SUPPORT ====================
    
    def set_session_active(self, active: bool) -> None:
        """Set session active state.
        
        Args:
            active: True to activate session, False to deactivate
        """
        if active:
            self.activate_session()
        else:
            self.deactivate_session()
    
    def clear_historical_bars(self) -> None:
        """Clear all historical bars for all symbols."""
        with self._lock:
            for symbol_data in self._symbols.values():
                symbol_data.historical_bars.clear()
            logger.debug("Cleared all historical bars")
    
    def clear_session_bars(self) -> None:
        """Clear current session bars (not historical)."""
        with self._lock:
            symbols_cleared = []
            for symbol, symbol_data in self._symbols.items():
                bars_before = len(symbol_data.bars_base)
                symbol_data.bars_base.clear()
                symbol_data.bars_derived.clear()
                symbol_data._latest_bar = None
                symbols_cleared.append(f"{symbol}({bars_before}→0)")
            logger.info(f"Cleared current session bars for {len(self._symbols)} symbols: {', '.join(symbols_cleared)}")
    
    def append_bar(self, symbol: str, interval: str, bar: BarData) -> None:
        """Append a bar to historical storage.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval (e.g., "1m", "5m")
            bar: Bar data to append
        """
        symbol = symbol.upper()
        
        with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                symbol_data = self.register_symbol(symbol)
            
            # Store in historical bars by date
            bar_date = bar.timestamp.date()
            
            # Normalize interval to integer if it's a string like "1m"
            if isinstance(interval, str) and interval.endswith('m'):
                try:
                    interval_int = int(interval[:-1])
                except ValueError:
                    interval_int = interval
            else:
                interval_int = interval
            
            if interval_int not in symbol_data.historical_bars:
                symbol_data.historical_bars[interval_int] = {}
            
            if bar_date not in symbol_data.historical_bars[interval_int]:
                symbol_data.historical_bars[interval_int][bar_date] = []
            
            symbol_data.historical_bars[interval_int][bar_date].append(bar)
    
    def set_quality(self, symbol: str, interval: str, quality: float) -> None:
        """Set quality score for a symbol/interval.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval
            quality: Quality percentage (0-100)
        """
        symbol = symbol.upper()
        
        with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                symbol_data = self.register_symbol(symbol)
            
            symbol_data.bar_quality = quality
            logger.debug(f"Set quality for {symbol} {interval}: {quality:.1f}%")
    
    def get_quality_metric(self, symbol: str, interval: str) -> Optional[float]:
        """Get quality score for a symbol/interval.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval
            
        Returns:
            Quality percentage (0-100) or None if not set
        """
        symbol = symbol.upper()
        
        with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return None
            return symbol_data.bar_quality
    
    def set_historical_indicator(self, name: str, value: any) -> None:
        """Store a historical indicator value.
        
        Args:
            name: Indicator name
            value: Indicator value (can be scalar, list, dict, etc.)
        """
        with self._lock:
            self._historical_indicators[name] = value
            logger.debug(f"Set historical indicator: {name}")
    
    def get_historical_indicator(self, name: str) -> Optional[any]:
        """Get a historical indicator value.
        
        Args:
            name: Indicator name
            
        Returns:
            Indicator value or None if not found
        """
        with self._lock:
            return self._historical_indicators.get(name)
    
    def get_latest_quote(self, symbol: str) -> Optional['Quote']:
        """Get latest quote for symbol (backtest mode).
        
        Generates synthetic quote from most recent bar data.
        Uses closing price as both bid and ask (no spread).
        
        Priority:
        1. Most recent 1s bar (if base_interval is 1s)
        2. Most recent 1m bar (if base_interval is 1m or derived from 1s)
        3. Most recent 1d bar (if no intraday bars)
        4. None if no bars available
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Quote with bid=ask=close, or None if no data
        """
        from app.models.trading import Quote
        
        symbol = symbol.upper()
        
        with self._lock:
            symbol_data = self._symbols.get(symbol)
            if not symbol_data:
                return None
            
            # Try base bars first (1s or 1m depending on base_interval)
            if symbol_data.bars_base and len(symbol_data.bars_base) > 0:
                latest_bar = symbol_data.bars_base[-1]
                return Quote(
                    symbol=symbol,
                    timestamp=latest_bar.timestamp,
                    bid=latest_bar.close,
                    ask=latest_bar.close,
                    bid_size=0,
                    ask_size=0,
                    source="bar"
                )
            
            # Try derived 1m bars (if base is 1s but have generated 1m)
            if "1m" in symbol_data.bars_derived and symbol_data.bars_derived["1m"]:
                latest_bar = symbol_data.bars_derived["1m"][-1]
                return Quote(
                    symbol=symbol,
                    timestamp=latest_bar.timestamp,
                    bid=latest_bar.close,
                    ask=latest_bar.close,
                    bid_size=0,
                    ask_size=0,
                    source="bar"
                )
            
            # Try derived 1d bars
            if "1d" in symbol_data.bars_derived and symbol_data.bars_derived["1d"]:
                latest_bar = symbol_data.bars_derived["1d"][-1]
                return Quote(
                    symbol=symbol,
                    timestamp=latest_bar.timestamp,
                    bid=latest_bar.close,
                    ask=latest_bar.close,
                    bid_size=0,
                    ask_size=0,
                    source="bar"
                )
            
            # No data available
            return None
    
    def get_bars(self, symbol: str, interval: str) -> List[BarData]:
        """Get all bars (historical + current session) for a symbol/interval.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval (e.g., "1m", "5m")
            
        Returns:
            List of bars in chronological order
        """
        symbol = symbol.upper()
        
        # Normalize interval
        if isinstance(interval, str) and interval.endswith('m'):
            try:
                interval_int = int(interval[:-1])
            except ValueError:
                interval_int = interval
        else:
            interval_int = interval
        
        return self.get_all_bars_including_historical(symbol, interval_int)


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
