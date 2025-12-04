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
from typing import Dict, List, Optional, Set, Deque, Union, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
import asyncio
import threading

from app.models.trading import BarData, TickData
from app.logger import logger


# Import GapInfo for gap storage
try:
    from app.threads.quality.gap_detection import GapInfo
except ImportError:
    # Fallback if not yet available
    GapInfo = Any


@dataclass
class BarIntervalData:
    """Self-describing bar interval with all metadata.
    
    Each interval knows if it's derived, what it's derived from,
    its quality, and gap details. No separate tracking needed.
    
    This is the refined structure that eliminates duplicate tracking:
    - No need for separate derived_intervals list
    - No need for separate bar_quality dict
    - No need for separate bar_gaps dict
    - Everything about an interval is in one place!
    """
    derived: bool               # Is this computed from another interval?
    base: Optional[str]         # Source interval (None if streamed)
    data: Union[Deque[BarData], List[BarData]]  # Actual bars (Deque for base, List for derived)
    quality: float = 0.0        # Quality percentage (0-100)
    gaps: List[Any] = field(default_factory=list)  # GapInfo objects
    updated: bool = False       # New data since last check


@dataclass
class SessionMetrics:
    """Basic session metrics (OHLCV aggregations).
    
    Always present, computed from session data.
    Distinct from indicators (optional computed analytics).
    """
    volume: int = 0
    high: Optional[float] = None
    low: Optional[float] = None
    last_update: Optional[datetime] = None


@dataclass
class DateRange:
    """Date range for historical data."""
    start: date
    end: date


@dataclass
class HistoricalBarIntervalData:
    """Historical bars for one interval across multiple dates.
    
    Stores bars organized by date with quality metrics.
    """
    data_by_date: Dict[date, List[BarData]] = field(default_factory=dict)
    quality: float = 0.0
    gaps: List[Any] = field(default_factory=list)  # GapInfo objects
    date_range: Optional[DateRange] = None


@dataclass
class HistoricalData:
    """Historical data for trailing days.
    
    Structure mirrors session data for consistency.
    Groups bars and indicators together.
    """
    bars: Dict[str, HistoricalBarIntervalData] = field(default_factory=dict)
    indicators: Dict[str, Any] = field(default_factory=dict)  # Historical aggregations


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
    
    # === NEW REFINED STRUCTURE (Phase 1: Non-Breaking Addition) ===
    # Self-describing bar structure - each interval contains all its metadata
    # Structure: {interval: BarIntervalData(derived, base, data, quality, gaps, updated)}
    # Example: {"1m": BarIntervalData(derived=False, base=None, data=deque([...])),
    #           "5m": BarIntervalData(derived=True, base="1m", data=[...])}
    bars: Dict[str, BarIntervalData] = field(default_factory=dict)
    
    # Grouped session metrics (volume, high, low)
    metrics: SessionMetrics = field(default_factory=SessionMetrics)
    
    # Session indicators (computed analytics like RSI, VWAP)
    # Distinct from metrics (basic aggregations)
    indicators: Dict[str, Any] = field(default_factory=dict)
    
    # Grouped historical data (bars + indicators)
    historical: HistoricalData = field(default_factory=HistoricalData)
    
    # === OLD STRUCTURE (Kept for Backward Compatibility - Phase 2: Will Remove) ===
    # Base bars (1s or 1m depending on base_interval)
    bars_base: Deque[BarData] = field(default_factory=deque)
    
    # Cache for O(1) access to latest bar
    _latest_bar: Optional[BarData] = None
    
    # Derived bars (e.g., {"1m": [...], "5m": [...], "15m": [...]})
    bars_derived: Dict[str, List[BarData]] = field(default_factory=dict)
    
    # Bar quality metrics per interval (0-100%)
    # Structure: {interval: quality_percentage}
    # Example: {"1m": 100.0, "5m": 98.5, "1d": 100.0}
    bar_quality: Dict[str, float] = field(default_factory=dict)
    
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
    
    # Historical indicators for this symbol
    # Structure: {indicator_key: value}
    # Example: {"avg_volume_2d": 12345678.9, "max_price_5d": 150.25}
    historical_indicators: Dict[str, Any] = field(default_factory=dict)
    
    # Delta export tracking: track last exported indices (for delta mode)
    _last_export_indices: Dict[str, Any] = field(
        default_factory=lambda: {
            "ticks": 0,
            "quotes": 0,
            "bars_base": 0,
            "bars_derived": {},  # {interval: index}
            "last_export_time": None  # Timestamp of last export
        },
        repr=False  # Don't show in repr
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
        # Update OLD structure (backward compatibility)
        self.session_volume += bar.volume
        
        if self.session_high is None or bar.high > self.session_high:
            self.session_high = bar.high
        
        if self.session_low is None or bar.low < self.session_low:
            self.session_low = bar.low
        
        self.last_update = bar.timestamp
        self.bars_updated = True
        
        # Update latest bar cache
        self._latest_bar = bar
        
        # Update NEW structure (dual-write for Phase 1)
        self.metrics.volume += bar.volume
        
        if self.metrics.high is None or bar.high > self.metrics.high:
            self.metrics.high = bar.high
        
        if self.metrics.low is None or bar.low < self.metrics.low:
            self.metrics.low = bar.low
        
        self.metrics.last_update = bar.timestamp
    
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
        # Reset OLD structure
        self.session_volume = 0
        self.session_high = None
        self.session_low = None
        self.last_update = None
        self.bar_quality = {}
        self.bars_updated = False
        self.quotes_updated = False
        self.ticks_updated = False
        self._latest_bar = None
        
        # Reset NEW structure (Phase 1: Dual-write)
        self.metrics = SessionMetrics()
        self.indicators = {}
        # Note: bars and historical are typically cleared separately via clear_session_bars()
    
    def to_json(self, complete: bool = True) -> dict:
        """Export symbol session data to JSON format.
        
        Args:
            complete: If True, return full data including historical.
                     If False, return delta (new data only, excludes historical).
        
        Returns:
            Dictionary matching SYSTEM_JSON_EXAMPLE.json format for symbol data
            
        Delta Mode Strategy:
            - Session metrics: Always included (small, frequently changing)
            - Ticks/Quotes: Only new data since last export (index-based slice)
            - Base/Derived bars: Only new bars since last export (index-based slice)
            - Historical: EXCLUDED (never changes after load, can be massive)
            
        Performance:
            - Complete: ~17K lines (includes historical)
            - Delta: ~10-50 lines per export (only new session data)
            - Memory: O(1) per symbol (just storing indices)
            - Speed: O(n) where n = new data only (not total data)
        """
        result = {
            "session": {
                "volume": self.session_volume,
                "high": self.session_high,
                "low": self.session_low,
                "data": {}
            },
            "historical": {}  # Will be populated below
        }
        
        # Determine slice indices for delta mode
        if complete:
            # Full export: all data from beginning
            ticks_start_idx = 0
            quotes_start_idx = 0
            bars_base_start_idx = 0
        else:
            # Delta export: only new data since last export
            ticks_start_idx = self._last_export_indices["ticks"]
            quotes_start_idx = self._last_export_indices["quotes"]
            bars_base_start_idx = self._last_export_indices["bars_base"]
        
        # Ticks (count + data)
        if self.ticks and len(self.ticks) > ticks_start_idx:
            new_ticks = self.ticks[ticks_start_idx:]
            if new_ticks:  # Only include if there's new data
                latest_tick = new_ticks[-1]
                result["session"]["data"]["ticks"] = {
                    "count": len(new_ticks),
                    "total_count": len(self.ticks),  # Total for reference
                    "latest": {
                        "timestamp": latest_tick.timestamp.isoformat(),
                        "price": latest_tick.price,
                        "size": latest_tick.size,
                        "exchange": latest_tick.exchange
                    }
                }
                # Update tracking index
                self._last_export_indices["ticks"] = len(self.ticks)
        
        # Quotes (count + data)
        if self.quotes and len(self.quotes) > quotes_start_idx:
            new_quotes = self.quotes[quotes_start_idx:]
            if new_quotes:  # Only include if there's new data
                latest_quote = new_quotes[-1]
                result["session"]["data"]["quotes"] = {
                    "count": len(new_quotes),
                    "total_count": len(self.quotes),  # Total for reference
                    "latest": {
                        "timestamp": latest_quote.timestamp.isoformat(),
                        "bid": latest_quote.bid,
                        "ask": latest_quote.ask,
                        "bid_size": latest_quote.bid_size,
                        "ask_size": latest_quote.ask_size
                    }
                }
                # Update tracking index
                self._last_export_indices["quotes"] = len(self.quotes)
        
        # Base bars (1m or 1s)
        if len(self.bars_base) > bars_base_start_idx:
            new_bars_base = list(self.bars_base)[bars_base_start_idx:]
            if new_bars_base:  # Only include if there's new data
                base_data = {
                    "count": len(new_bars_base),
                    "total_count": len(self.bars_base),  # Total for reference
                    "generated": False,  # Base bars are streamed, not generated
                    "columns": ["timestamp", "open", "high", "low", "close", "volume"],
                    "data": [
                        [
                            bar.timestamp.time().isoformat(),
                            bar.open,
                            bar.high,
                            bar.low,
                            bar.close,
                            bar.volume
                        ]
                        for bar in new_bars_base
                    ]
                }
                
                # Add quality metric if available for this interval
                if self.base_interval in self.bar_quality:
                    base_data["quality"] = self.bar_quality[self.base_interval]
                
                result["session"]["data"][self.base_interval] = base_data
                
                # Update tracking index
                self._last_export_indices["bars_base"] = len(self.bars_base)
        
        # Derived bars (5m, 15m, etc.)
        for interval, bars in self.bars_derived.items():
            if bars:
                # Get last exported index for this interval
                if complete:
                    derived_start_idx = 0
                else:
                    derived_start_idx = self._last_export_indices["bars_derived"].get(interval, 0)
                
                # Only export new bars
                if len(bars) > derived_start_idx:
                    new_bars_derived = bars[derived_start_idx:]
                    if new_bars_derived:  # Only include if there's new data
                        derived_data = {
                            "count": len(new_bars_derived),
                            "total_count": len(bars),  # Total for reference
                            "generated": True,  # Derived bars are computed
                            "columns": ["timestamp", "open", "high", "low", "close", "volume"],
                            "data": [
                                [
                                    bar.timestamp.time().isoformat(),
                                    bar.open,
                                    bar.high,
                                    bar.low,
                                    bar.close,
                                    bar.volume
                                ]
                                for bar in new_bars_derived
                            ]
                        }
                        
                        # Add quality metric if available for this interval
                        if interval in self.bar_quality:
                            derived_data["quality"] = self.bar_quality[interval]
                        
                        result["session"]["data"][interval] = derived_data
                        
                        # Update tracking index for this interval
                        self._last_export_indices["bars_derived"][interval] = len(bars)
        
        # Historical bars - ONLY in complete mode (massive data, never changes)
        if complete and self.historical_bars:
            # Debug: Log what intervals we have
            logger.debug(
                f"[EXPORT] Historical bars intervals for {self.symbol}: "
                f"{list(self.historical_bars.keys())}"
            )
            
            result["historical"]["loaded"] = True
            result["historical"]["data"] = {}
            
            # Add historical indicators nested under historical section
            if self.historical_indicators:
                for indicator_name, indicator_value in self.historical_indicators.items():
                    result["historical"][indicator_name] = indicator_value
            
            for interval, dates_dict in self.historical_bars.items():
                if dates_dict:
                    all_bars = []
                    dates_list = sorted(dates_dict.keys())
                    
                    # Collect all bars across dates
                    for dt in dates_list:
                        all_bars.extend(dates_dict[dt])
                    
                    if all_bars:
                        # Normalize interval key to string format
                        if isinstance(interval, int):
                            interval_key = f"{interval}m"
                        elif isinstance(interval, str):
                            # Already a string, use as-is (e.g., "1m", "5m", "1d")
                            interval_key = interval
                        else:
                            interval_key = str(interval)
                        
                        # Determine column format based on interval
                        is_daily = interval_key == "1d"
                        
                        # Calculate date range for THIS interval
                        date_range = {
                            "start_date": dates_list[0].isoformat(),
                            "end_date": dates_list[-1].isoformat(),
                            "days": len(dates_list)
                        }
                        
                        historical_interval_data = {
                            "count": len(all_bars),
                            "date_range": date_range,
                            "dates": [dt.isoformat() for dt in dates_list],
                            "columns": ["date", "open", "high", "low", "close", "volume"] if is_daily 
                                      else ["timestamp", "open", "high", "low", "close", "volume"],
                            "data": [
                                [
                                    bar.timestamp.date().isoformat() if is_daily else bar.timestamp.isoformat(),
                                    bar.open,
                                    bar.high,
                                    bar.low,
                                    bar.close,
                                    bar.volume
                                ]
                                for bar in all_bars
                            ]
                        }
                        
                        # Add quality for this interval if available
                        if interval_key in self.bar_quality:
                            historical_interval_data["quality"] = self.bar_quality[interval_key]
                        
                        result["historical"]["data"][interval_key] = historical_interval_data
        elif not complete and self.historical_bars:
            # Delta mode: Just indicate historical is loaded, include per-interval date ranges but not data
            result["historical"]["loaded"] = True
            result["historical"]["intervals"] = {}  # Per-interval date ranges
            
            # Include date range for each interval
            for interval, dates_dict in self.historical_bars.items():
                if dates_dict:
                    dates_list = sorted(dates_dict.keys())
                    
                    # Normalize interval key
                    if isinstance(interval, int):
                        interval_key = f"{interval}m"
                    elif isinstance(interval, str):
                        interval_key = interval
                    else:
                        interval_key = str(interval)
                    
                    interval_info = {
                        "date_range": {
                            "start_date": dates_list[0].isoformat(),
                            "end_date": dates_list[-1].isoformat(),
                            "days": len(dates_list)
                        }
                    }
                    
                    # Add quality for this interval if available
                    if interval_key in self.bar_quality:
                        interval_info["quality"] = self.bar_quality[interval_key]
                    
                    result["historical"]["intervals"][interval_key] = interval_info
        
        return result


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
        self._session_active: bool = False  # Managed by coordinator thread
        
        # Per-symbol data structures
        self._symbols: Dict[str, SymbolSessionData] = {}
        
        # Active symbols set (for quick lookup)
        self._active_symbols: Set[str] = set()
        
        # Active streams tracking: {(symbol, stream_type): True}
        # stream_type: "bars", "ticks", "quotes"
        self._active_streams: Dict[Tuple[str, str], bool] = {}
        # Event to signal upkeep thread when new data arrives
        self._data_arrival_event = threading.Event()
        
        # Delta export tracking: timestamp of last export
        self._last_export_time: Optional[datetime] = None
        
        # Thread lock for concurrent access
        self._lock = threading.RLock()
        
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
        
        # # Data upkeep configuration
        # if config.data_upkeep:
        #     settings.DATA_UPKEEP_ENABLED = config.data_upkeep.enabled
        #     settings.DATA_UPKEEP_CHECK_INTERVAL_SECONDS = config.data_upkeep.check_interval_seconds
        #     settings.DATA_UPKEEP_RETRY_MISSING_BARS = config.data_upkeep.retry_missing_bars
        #     settings.DATA_UPKEEP_MAX_RETRIES = config.data_upkeep.max_retries
        #     settings.DATA_UPKEEP_DERIVED_INTERVALS = config.data_upkeep.derived_intervals
        #     settings.DATA_UPKEEP_AUTO_COMPUTE_DERIVED = config.data_upkeep.auto_compute_derived
        #     logger.info(f"  ✓ Data upkeep: check every {config.data_upkeep.check_interval_seconds}s, derived intervals {config.data_upkeep.derived_intervals}")
        
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
    
    def _check_session_active(self) -> bool:
        """
        Check if session is active before allowing data access.
        
        Used by read methods to block access during catchup (dynamic symbol addition).
        
        Returns:
            True if active (allow access), False if deactivated (block access)
        
        Note:
            This is used for dynamic symbol management (Phase 2).
            During catchup, session is deactivated to prevent AnalysisEngine
            from seeing intermediate state.
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
    
    def get_symbol_data(self, symbol: str, internal: bool = False) -> Optional[SymbolSessionData]:
        """Get data for a symbol.
        
        Args:
            symbol: Stock symbol
            internal: If True, bypass session_active check (for internal threads)
            
        Returns:
            SymbolSessionData or None if not found (None if session deactivated and not internal)
        """
        # Block external access when session inactive (internal threads can still read)
        if not internal and not self._session_active:
            return None
        
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
    
    def get_latest_bar(self, symbol: str, interval: int = 1, internal: bool = False) -> Optional[BarData]:
        """Get the most recent bar for a symbol (O(1) operation).
        
        Optimized for high-frequency access by AnalysisEngine.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval in minutes (1, 5, 15, etc.)
            internal: If True, bypass session_active check.
                     Use True for internal threads (DataProcessor, DataQualityManager).
                     Use False (default) for external subscribers (AnalysisEngine).
            
        Returns:
            Most recent bar or None if no data (or session deactivated for external callers)
        """
        # Block external callers during deactivation
        if not internal and not self._session_active:
            return None
        
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
        interval: int = 1,
        internal: bool = False
    ) -> List[BarData]:
        """Get the last N bars for a symbol (efficient O(N) operation).
        
        Optimized for technical indicator calculations.
        
        Args:
            symbol: Stock symbol
            n: Number of bars to retrieve
            interval: Bar interval in minutes
            internal: If True, bypass session_active check.
            
        Returns:
            List of last N bars (may be fewer if not enough data, or None if session deactivated)
        """
        # Block external callers during deactivation
        if not internal and not self._session_active:
            return None
        
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
        interval: int = 1,
        internal: bool = False
    ) -> List[BarData]:
        """Get all bars since a specific timestamp (efficient backward search).
        
        Args:
            symbol: Stock symbol
            timestamp: Start timestamp
            interval: Bar interval in minutes
            internal: If True, bypass session_active check.
            
        Returns:
            List of bars after timestamp (empty list if session deactivated)
        """
        # Block external callers during deactivation
        if not internal and not self._session_active:
            return []
        
        symbol = symbol.upper()
        
        with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return []
            return symbol_data.get_bars_since(timestamp, interval)
    
    def get_bar_count(self, symbol: str, interval: int = 1, internal: bool = False) -> int:
        """Get count of available bars (O(1) operation).
        
        Args:
            symbol: Stock symbol
            interval: Bar interval in minutes
            internal: If True, bypass session_active check.
            
        Returns:
            Number of bars available (0 if session deactivated)
        """
        # Block external callers during deactivation
        if not internal and not self._session_active:
            return 0
        
        symbol = symbol.upper()
        
        with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return 0
            return symbol_data.get_bar_count(interval)
    
    def get_latest_bars_multi(
        self,
        symbols: List[str],
        interval: int = 1,
        internal: bool = False
    ) -> Dict[str, Optional[BarData]]:
        """Get latest bars for multiple symbols in one call (batch operation).
        
        More efficient than calling get_latest_bar multiple times.
        
        Args:
            symbols: List of stock symbols
            interval: Bar interval in minutes
            internal: If True, bypass session_active check.
            
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
        interval: int = 1,
        internal: bool = False
    ) -> Union[Deque[BarData], List[BarData], None]:
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
            internal: If True, bypass session_active check.
            
        Returns:
            Direct reference to bars deque (1m) or list (derived)
            Empty container if symbol/interval not found
        """
        # Block external callers during deactivation
        if not internal and not self._session_active:
            return None
        
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
        end: Optional[datetime] = None,
        internal: bool = False
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
            internal: If True, bypass session_active check.
            
        Returns:
            List of bars matching criteria (copy created)
        """
        # Block external callers during deactivation
        if not internal and not self._session_active:
            return []
        
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
    
    def get_session_metrics(self, symbol: str, internal: bool = False) -> Dict[str, any]:
        """Get current session metrics for a symbol.
        
        Args:
            symbol: Stock symbol
            internal: If True, bypass session_active check.
            
        Returns:
            Dictionary with session metrics
        """
        # Block external callers during deactivation
        if not internal and not self._session_active:
            return {}
        
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
        interval: int = 1,
        internal: bool = False
    ) -> Dict[date, List[BarData]]:
        """Get historical bars for past N days.
        
        Args:
            symbol: Stock symbol
            days_back: Number of days to retrieve (0 = all)
            interval: Bar interval
            internal: If True, bypass session_active check.
            
        Returns:
            Dictionary mapping date to bars for that date
        """
        # Block external callers during deactivation
        if not internal and not self._session_active:
            return {}
        
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
        interval: int = 1,
        internal: bool = False
    ) -> List[BarData]:
        """Get all bars including historical and current session.
        
        Chronologically ordered from oldest to newest.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval
            internal: If True, bypass session_active check.
            
        Returns:
            All bars chronologically ordered
        """
        # Block external callers during deactivation
        if not internal and not self._session_active:
            return []
        
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
    
    def remove_symbol(self, symbol: str) -> bool:
        """Remove symbol and all its data (thread-safe).
        
        Called by SessionCoordinator when a symbol is removed from the session.
        
        Args:
            symbol: Symbol to remove
        
        Returns:
            True if removed, False if not found
        """
        symbol = symbol.upper()
        
        with self._lock:
            if symbol not in self._symbols:
                return False
            
            # Remove SymbolSessionData
            del self._symbols[symbol]
            
            # Remove from active symbols
            self._active_symbols.discard(symbol)
            
            # Remove from active streams
            streams_to_remove = [
                key for key in self._active_streams.keys() 
                if key[0] == symbol
            ]
            for key in streams_to_remove:
                del self._active_streams[key]
            
            logger.info(
                f"[SESSION_DATA] Removed {symbol} "
                f"({len(self._symbols)} symbols remaining)"
            )
            
            return True
    
    def get_active_symbols(self) -> Set[str]:
        """Get set of active symbols (thread-safe read).
        
        Returns:
            Set of active symbols (empty set if session deactivated)
        """
        # Block access during catchup (Phase 2: Dynamic symbol management)
        if not self._check_session_active():
            return set()
        
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
            
            # Debug logging for 1d bars
            if interval == "1d" or interval_int == "1d":
                logger.info(
                    f"[HISTORICAL_LOAD] Appended 1d bar for {symbol} on {bar_date}: "
                    f"close=${bar.close}, volume={bar.volume}"
                )
    
    def set_quality(self, symbol: str, interval: str, quality: float) -> None:
        """Set quality score for a symbol/interval.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval (e.g., "1m", "5m", "1d")
            quality: Quality percentage (0-100)
        """
        symbol = symbol.upper()
        
        # Normalize interval to string format
        if isinstance(interval, int):
            interval_key = f"{interval}m"
        else:
            interval_key = str(interval)
        
        with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                symbol_data = self.register_symbol(symbol)
            
            symbol_data.bar_quality[interval_key] = quality
            logger.debug(f"Set quality for {symbol} {interval_key}: {quality:.1f}%")
    
    def get_quality_metric(self, symbol: str, interval: str) -> Optional[float]:
        """Get quality score for a symbol/interval.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval (e.g., "1m", "5m", "1d")
            
        Returns:
            Quality percentage (0-100) or None if not set
        """
        symbol = symbol.upper()
        
        # Normalize interval to string format
        if isinstance(interval, int):
            interval_key = f"{interval}m"
        else:
            interval_key = str(interval)
        
        with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data is None:
                return None
            return symbol_data.bar_quality.get(interval_key)
    
    def set_historical_indicator(self, symbol: str, name: str, value: any) -> None:
        """Store a historical indicator value for a symbol.
        
        Args:
            symbol: Stock symbol
            name: Indicator name (e.g., "avg_volume_2d")
            value: Indicator value (can be scalar, list, dict, etc.)
        """
        symbol = symbol.upper()
        with self._lock:
            symbol_data = self.get_symbol_data(symbol)
            if symbol_data is None:
                symbol_data = self.register_symbol(symbol)
            symbol_data.historical_indicators[name] = value
            logger.debug(f"Set historical indicator for {symbol}: {name} = {value}")
    
    def get_historical_indicator(self, symbol: str, name: str) -> Optional[any]:
        """Get a historical indicator value by name for a symbol.
        
        Indicator names include the period for clarity:
        - "avg_volume_2d" - 2-day average volume
        - "avg_volume_10d" - 10-day average volume
        - "max_price_5d" - 5-day max price
        
        This allows multiple indicators with same base but different periods.
        
        Args:
            symbol: Stock symbol
            name: Full indicator name (e.g., "avg_volume_2d")
            
        Returns:
            Indicator value or None if not found
            
        Example:
            # In analysis engine
            avg_vol = session_data.get_historical_indicator("AAPL", "avg_volume_2d")
            max_price = session_data.get_historical_indicator("AAPL", "max_price_5d")
        """
        symbol = symbol.upper()
        with self._lock:
            symbol_data = self.get_symbol_data(symbol)
            if symbol_data is None:
                return None
            return symbol_data.historical_indicators.get(name)
    
    def get_all_historical_indicators(self, symbol: str) -> Dict[str, any]:
        """Get all historical indicators for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary of indicator_name -> value
            
        Example:
            indicators = session_data.get_all_historical_indicators("AAPL")
            # {'avg_volume_2d': 12345678.9, 'max_price_5d': 150.25}
        """
        symbol = symbol.upper()
        with self._lock:
            symbol_data = self.get_symbol_data(symbol)
            if symbol_data is None:
                return {}
            return symbol_data.historical_indicators.copy()
    
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
    
    def get_bars(self, symbol: str, interval: str, internal: bool = False) -> Optional[List[BarData]]:
        """Get all bars (historical + current session) for a symbol/interval.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval (e.g., "1m", "5m")
            internal: If True, bypass session_active check.
            
        Returns:
            List of bars in chronological order, or None if session deactivated
        """
        # Block external callers during deactivation
        if not internal and not self._session_active:
            return None
        
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
    
    def to_json(self, complete: bool = True) -> Tuple[dict, Optional[datetime]]:
        """Export session data to JSON format.
        
        Args:
            complete: If True, return full data including historical.
                     If False, return delta (new data only, excludes historical).
        
        Returns:
            Tuple of (result_dict, last_export_time):
            - result_dict: Session data in JSON format
            - last_export_time: Timestamp of previous export (for delta metadata)
        """
        # Get last export time before updating it
        last_export_time = self._last_export_time
        
        result = {
            "_session_active": self._session_active,
            "_active_symbols": sorted(list(self._active_symbols)),
            "symbols": {}
        }
        
        # Export each symbol's data
        with self._lock:
            for symbol, symbol_data in self._symbols.items():
                result["symbols"][symbol] = symbol_data.to_json(complete=complete)
            
            # Update last export time for next delta
            self._last_export_time = datetime.now()
        
        return result, last_export_time


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
