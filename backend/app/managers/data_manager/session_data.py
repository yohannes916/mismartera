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
    - Integrated metadata for tracking symbol origin and loading status
    """
    
    symbol: str
    
    # Base interval for this symbol ("1s" or "1m")
    # Kept for performance - enables O(1) base interval lookup
    base_interval: str = "1m"
    
    # === METADATA (Integrated - tracks symbol origin and loading) ===
    # These flags determine how the symbol was added and what data is loaded
    meets_session_config_requirements: bool = False  # Full loading vs adhoc
    added_by: str = "config"  # "config", "strategy", "scanner", "adhoc"
    auto_provisioned: bool = False  # Was this auto-created for adhoc addition?
    added_at: Optional[datetime] = None  # When was this symbol added?
    upgraded_from_adhoc: bool = False  # Was this upgraded from adhoc to full?
    
    # === BARS (Self-Describing Structure) ===
    # Each interval contains all its metadata: derived flag, base source, data, quality, gaps
    # Structure: {interval: BarIntervalData(derived, base, data, quality, gaps, updated)}
    # Example: {"1m": BarIntervalData(derived=False, base=None, data=deque([...])),
    #           "5m": BarIntervalData(derived=True, base="1m", data=[...])}
    bars: Dict[str, BarIntervalData] = field(default_factory=dict)
    
    # === QUOTES ===
    quotes: List = field(default_factory=list)  # QuoteData when implemented
    quotes_updated: bool = False
    
    # === TICKS ===
    ticks: List[TickData] = field(default_factory=list)
    ticks_updated: bool = False
    
    # === SESSION METRICS (Basic OHLCV Aggregations) ===
    metrics: SessionMetrics = field(default_factory=SessionMetrics)
    
    # === SESSION INDICATORS (Computed Analytics) ===
    # Computed real-time indicators like RSI, VWAP, momentum, etc.
    # Distinct from metrics (which are basic aggregations)
    indicators: Dict[str, Any] = field(default_factory=dict)
    
    # === HISTORICAL DATA ===
    # Trailing days of bars and pre-calculated indicators
    historical: HistoricalData = field(default_factory=HistoricalData)
    
    # === INTERNAL (Caching & Export Tracking) ===
    # Cache for O(1) access to latest bar
    _latest_bar: Optional[BarData] = None
    
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
    def bars_1m(self) -> Union[Deque[BarData], List[BarData]]:
        """Get 1m bars (convenience property).
        
        Returns:
            1m bars if they exist, otherwise empty list
        """
        interval_data = self.bars.get("1m")
        if interval_data:
            return interval_data.data
        return []
    
    def update_from_bar(self, bar: BarData) -> None:
        """Update session metrics from a new bar.
        
        Args:
            bar: New bar data
        """
        # Update session metrics
        self.metrics.volume += bar.volume
        
        if self.metrics.high is None or bar.high > self.metrics.high:
            self.metrics.high = bar.high
        
        if self.metrics.low is None or bar.low < self.metrics.low:
            self.metrics.low = bar.low
        
        self.metrics.last_update = bar.timestamp
        
        # Update latest bar cache
        self._latest_bar = bar
    
    def get_latest_bar(self, interval = None) -> Optional[BarData]:
        """Get the most recent bar (O(1) operation).
        
        Args:
            interval: Bar interval (string like "1s", "1m", "5m"). If None, uses cached latest bar.
            
        Returns:
            Most recent bar or None
        """
        # If no interval specified, return cached latest bar
        if interval is None:
            return self._latest_bar
        
        # Normalize interval: convert int to string
        if isinstance(interval, int):
            interval = f"{interval}m"
        
        # Get interval data
        interval_data = self.bars.get(interval)
        if not interval_data or not interval_data.data:
            return None
        
        # Return last bar
        return interval_data.data[-1]
    
    def get_last_n_bars(self, n: int, interval = None) -> List[BarData]:
        """Get the last N bars efficiently.
        
        Args:
            n: Number of bars to retrieve
            interval: Bar interval (string like "1s", "1m", "5m"). If None, uses base_interval.
            
        Returns:
            List of last N bars (oldest to newest)
        """
        # Normalize interval: convert int to string
        if isinstance(interval, int):
            interval = f"{interval}m"
        
        # Default to base interval
        if interval is None:
            interval = self.base_interval
        
        # Get interval data
        interval_data = self.bars.get(interval)
        if not interval_data or not interval_data.data:
            return []
        
        # Return last n bars
        bars = interval_data.data
        if len(bars) <= n:
            return list(bars)
        else:
            return list(bars)[-n:]
    
    def get_bars_since(self, timestamp: datetime, interval = None) -> List[BarData]:
        """Get all bars since a specific timestamp.
        
        Args:
            timestamp: Start timestamp
            interval: Bar interval (string like "1s", "1m", "5m"). If None, uses base_interval.
            
        Returns:
            List of bars after timestamp
        """
        # Normalize interval: convert int to string
        if isinstance(interval, int):
            interval = f"{interval}m"
        
        # Default to base interval
        if interval is None:
            interval = self.base_interval
        
        # Get interval data
        interval_data = self.bars.get(interval)
        if not interval_data or not interval_data.data:
            return []
        
        # Filter bars by timestamp
        return [b for b in interval_data.data if b.timestamp >= timestamp]
    
    def get_bar_count(self, interval = None) -> int:
        """Get count of bars for an interval (O(1) operation).
        
        Args:
            interval: Bar interval (string like "1s", "1m", "5m"). If None, uses base_interval.
            
        Returns:
            Number of bars
        """
        # Normalize interval: convert int to string
        if isinstance(interval, int):
            interval = f"{interval}m"
        
        # Default to base interval
        if interval is None:
            interval = self.base_interval
        
        # Get interval data
        interval_data = self.bars.get(interval)
        if not interval_data or not interval_data.data:
            return 0
        
        return len(interval_data.data)
    
    def reset_session_metrics(self) -> None:
        """Reset session metrics for a new session.
        
        NOTE: This does NOT clear indicators! Indicators are configuration-driven
        and persist across sessions. Only their VALUES are reset (current_value, valid, etc.),
        not the IndicatorData structures themselves.
        """
        self.metrics = SessionMetrics()
        
        # Reset indicator VALUES but keep structures
        for ind_data in self.indicators.values():
            ind_data.current_value = None
            ind_data.last_updated = None
            ind_data.valid = False
            # Keep: config, state (for stateful indicators like EMA)
        
        self.quotes_updated = False
        self.ticks_updated = False
        self._latest_bar = None
        # Note: bars and historical are typically cleared separately via clear_session_bars()
    
    def _serialize_indicator_config(self, config) -> Optional[dict]:
        """Serialize IndicatorConfig to dict.
        
        Args:
            config: IndicatorConfig object
            
        Returns:
            Dict with config details or None
        """
        if config is None:
            return None
        
        try:
            return {
                "name": config.name,
                "type": config.type.value if hasattr(config.type, 'value') else str(config.type),
                "period": config.period,
                "interval": config.interval,
                "params": config.params if config.params else {},
                "warmup_bars": config.warmup_bars() if hasattr(config, 'warmup_bars') else config.period
            }
        except Exception as e:
            logger.warning(f"Failed to serialize indicator config: {e}")
            return None
    
    def _serialize_indicator_state(self, state) -> Optional[dict]:
        """Serialize IndicatorResult state to dict.
        
        Args:
            state: IndicatorResult object
            
        Returns:
            Dict with state details or None
        """
        if state is None:
            return None
        
        try:
            return {
                "timestamp": state.timestamp.isoformat() if state.timestamp else None,
                "value": state.value,
                "valid": state.valid
            }
        except Exception as e:
            logger.warning(f"Failed to serialize indicator state: {e}")
            return None
    
    def to_json(self, complete: bool = True) -> dict:
        """Export symbol session data to JSON format.
        
        Args:
            complete: If True, return full data including historical.
                     If False, return delta (new data only, excludes historical).
        
        Returns:
            Dictionary with structure:
            {
              "bars": {interval: {derived, base, quality, gaps, data}},
              "quotes": {count, data},
              "ticks": {count, data},
              "metrics": {volume, high, low, last_update},
              "indicators": {indicator_name: {name, type, interval, value, config, state, ...}},
              "historical": {bars, indicators}
            }
        """
        result = {
            "bars": {},
            "quotes": {},
            "ticks": {},
            "metrics": {
                "volume": self.metrics.volume,
                "high": self.metrics.high,
                "low": self.metrics.low,
                "last_update": self.metrics.last_update.isoformat() if self.metrics.last_update else None
            },
            "indicators": {},  # Will populate below
            "historical": {},
            "metadata": {  # NEW: Symbol metadata
                "meets_session_config_requirements": self.meets_session_config_requirements,
                "added_by": self.added_by,
                "auto_provisioned": self.auto_provisioned,
                "added_at": self.added_at.isoformat() if self.added_at else None,
                "upgraded_from_adhoc": self.upgraded_from_adhoc
            }
        }
        
        # DEBUG: Log indicator count for debugging
        indicator_count = len(self.indicators)
        if indicator_count > 0:
            logger.debug(f"{self.symbol}: Serializing {indicator_count} indicators")
        else:
            logger.warning(f"{self.symbol}: No indicators to serialize (indicators dict is empty)")
        
        # Serialize indicators (IndicatorData objects to dict)
        for key, indicator_data in self.indicators.items():
            # Check if it's an IndicatorData object or plain value
            if hasattr(indicator_data, 'current_value'):
                # IndicatorData object - serialize properly
                # Get indicator category from embedded config if available
                indicator_type = indicator_data.type
                if indicator_data.config and hasattr(indicator_data.config, 'type'):
                    # Use indicator category (trend, momentum, etc.) from config
                    indicator_type = indicator_data.config.type.value
                
                # Base fields (always present)
                indicator_export = {
                    "name": indicator_data.name,
                    "type": indicator_type,
                    "interval": indicator_data.interval,
                    "value": indicator_data.current_value,
                    "last_updated": indicator_data.last_updated.isoformat() if indicator_data.last_updated else None,
                    "valid": indicator_data.valid
                }
                
                # NEW: Add metadata fields (config, state, historical_values)
                if hasattr(indicator_data, 'config') and indicator_data.config:
                    indicator_export["config"] = self._serialize_indicator_config(indicator_data.config)
                
                if hasattr(indicator_data, 'state') and indicator_data.state:
                    indicator_export["state"] = self._serialize_indicator_state(indicator_data.state)
                
                if hasattr(indicator_data, 'historical_values') and indicator_data.historical_values:
                    # Only export historical values in complete mode (can be large)
                    if complete:
                        indicator_export["historical_values"] = indicator_data.historical_values
                    else:
                        indicator_export["historical_values_count"] = len(indicator_data.historical_values)
                
                result["indicators"][key] = indicator_export
            else:
                # Plain value (backward compatibility)
                result["indicators"][key] = indicator_data
        
        # === BARS (Self-Describing Structure) ===
        for interval, interval_data in self.bars.items():
            if not interval_data.data:
                continue
            
            # Determine start index for delta export
            if complete:
                start_idx = 0
            else:
                start_idx = self._last_export_indices.get("bars", {}).get(interval, 0)
            
            # Only export new bars
            bars_list = list(interval_data.data)
            if len(bars_list) > start_idx:
                new_bars = bars_list[start_idx:]
                
                interval_export = {
                    "derived": interval_data.derived,
                    "base": interval_data.base,
                    "quality": interval_data.quality,
                    "count": len(new_bars),
                    "total_count": len(bars_list),
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
                        for bar in new_bars
                    ]
                }
                
                # Add gaps if present
                if interval_data.gaps:
                    interval_export["gaps"] = {
                        "gap_count": len(interval_data.gaps),
                        "missing_bars": sum(g.bar_count for g in interval_data.gaps if hasattr(g, 'bar_count')),
                        "ranges": [
                            {
                                "start_time": g.start_time.time().isoformat() if hasattr(g, 'start_time') else None,
                                "end_time": g.end_time.time().isoformat() if hasattr(g, 'end_time') else None,
                                "bar_count": g.bar_count if hasattr(g, 'bar_count') else 0
                            }
                            for g in interval_data.gaps
                        ]
                    }
                
                result["bars"][interval] = interval_export
                
                # Update tracking index
                if not complete:
                    if "bars" not in self._last_export_indices:
                        self._last_export_indices["bars"] = {}
                    self._last_export_indices["bars"][interval] = len(bars_list)
        
        # === QUOTES ===
        if self.quotes:
            start_idx = 0 if complete else self._last_export_indices.get("quotes", 0)
            if len(self.quotes) > start_idx:
                new_quotes = self.quotes[start_idx:]
                if new_quotes:
                    latest_quote = new_quotes[-1]
                    result["quotes"] = {
                        "count": len(new_quotes),
                        "total_count": len(self.quotes),
                        "latest": {
                            "timestamp": latest_quote.timestamp.isoformat(),
                            "bid": latest_quote.bid,
                            "ask": latest_quote.ask,
                            "bid_size": latest_quote.bid_size,
                            "ask_size": latest_quote.ask_size
                        }
                    }
                    if not complete:
                        self._last_export_indices["quotes"] = len(self.quotes)
        
        # === TICKS ===
        if self.ticks:
            start_idx = 0 if complete else self._last_export_indices.get("ticks", 0)
            if len(self.ticks) > start_idx:
                new_ticks = self.ticks[start_idx:]
                if new_ticks:
                    latest_tick = new_ticks[-1]
                    result["ticks"] = {
                        "count": len(new_ticks),
                        "total_count": len(self.ticks),
                        "latest": {
                            "timestamp": latest_tick.timestamp.isoformat(),
                            "price": latest_tick.price,
                            "size": latest_tick.size,
                            "exchange": latest_tick.exchange
                        }
                    }
                    if not complete:
                        self._last_export_indices["ticks"] = len(self.ticks)
        
        # === HISTORICAL (Only in complete mode) ===
        if complete and self.historical.bars:
            result["historical"]["loaded"] = True
            result["historical"]["bars"] = {}
            
            # Export historical indicators (properly serialize IndicatorData objects)
            if self.historical.indicators:
                result["historical"]["indicators"] = {}
                for key, ind_data in self.historical.indicators.items():
                    # Check if it's an IndicatorData object
                    if hasattr(ind_data, 'current_value'):
                        indicator_type = ind_data.type
                        if ind_data.config and hasattr(ind_data.config, 'type'):
                            indicator_type = ind_data.config.type.value
                        
                        result["historical"]["indicators"][key] = {
                            "name": ind_data.name,
                            "type": indicator_type,
                            "interval": ind_data.interval,
                            "value": ind_data.current_value,
                            "last_updated": ind_data.last_updated.isoformat() if ind_data.last_updated else None,
                            "valid": ind_data.valid,
                            "config": self._serialize_indicator_config(ind_data.config) if hasattr(ind_data, 'config') else None,
                            "state": self._serialize_indicator_state(ind_data.state) if hasattr(ind_data, 'state') else None
                        }
                    else:
                        # Plain value
                        result["historical"]["indicators"][key] = ind_data
            
            # Export historical bars per interval
            for interval, hist_interval_data in self.historical.bars.items():
                if not hist_interval_data.data_by_date:
                    continue
                
                # Collect all bars across dates
                dates_list = sorted(hist_interval_data.data_by_date.keys())
                all_bars = []
                for dt in dates_list:
                    all_bars.extend(hist_interval_data.data_by_date[dt])
                
                if all_bars:
                    is_daily = interval == "1d"
                    
                    hist_export = {
                        "count": len(all_bars),
                        "quality": hist_interval_data.quality,
                        "date_range": {
                            "start_date": dates_list[0].isoformat(),
                            "end_date": dates_list[-1].isoformat(),
                            "days": len(dates_list)
                        },
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
                    
                    # Add gaps if present
                    if hist_interval_data.gaps:
                        hist_export["gaps"] = {
                            "gap_count": len(hist_interval_data.gaps),
                            "missing_bars": sum(g.bar_count for g in hist_interval_data.gaps if hasattr(g, 'bar_count')),
                            "ranges": [
                                {
                                    "start_time": g.start_time.time().isoformat() if hasattr(g, 'start_time') else None,
                                    "end_time": g.end_time.time().isoformat() if hasattr(g, 'end_time') else None,
                                    "bar_count": g.bar_count if hasattr(g, 'bar_count') else 0
                                }
                                for g in hist_interval_data.gaps
                            ]
                        }
                    
                    result["historical"]["bars"][interval] = hist_export
        elif not complete and self.historical.bars:
            # Delta mode: Just indicate historical is loaded
            result["historical"]["loaded"] = True
            result["historical"]["intervals"] = {}
            
            for interval, hist_interval_data in self.historical.bars.items():
                if hist_interval_data.data_by_date:
                    dates_list = sorted(hist_interval_data.data_by_date.keys())
                    result["historical"]["intervals"][interval] = {
                        "date_range": {
                            "start_date": dates_list[0].isoformat(),
                            "end_date": dates_list[-1].isoformat(),
                            "days": len(dates_list)
                        },
                        "quality": hist_interval_data.quality
                    }
        
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
        # Get trading hours from time manager instead.
        # Single source of truth: time manager queries trading calendar for
        # accurate hours (accounts for holidays, early closes, weekends, etc.)
        self.historical_bars_trailing_days: int = 0
        self.historical_bars_intervals: List[int] = []
        
        # Session state
        # Start active - lag detection will deactivate if needed
        self._session_active: bool = True
        
        # Per-symbol data structures
        self._symbols: Dict[str, SymbolSessionData] = {}
        
        # Event to signal upkeep thread when new data arrives
        self._data_arrival_event = threading.Event()
        
        # Delta export tracking: timestamp of last export
        self._last_export_time: Optional[datetime] = None
        
        # Thread lock for concurrent access
        self._lock = threading.RLock()
        
        # Scanner framework support
        self._config_symbols: Set[str] = set()  # Symbols from session_config
        self._symbol_locks: Dict[str, str] = {}  # {symbol: reason}
        self._indicator_manager: Optional[Any] = None  # Set by coordinator
        self._session_coordinator: Optional[Any] = None  # Set by coordinator
        
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
                logger.info(f"✓ Registered symbol: {symbol} (total active: {len(self._symbols)})")
            else:
                logger.debug(f"Symbol already registered: {symbol}")
            
            return self._symbols[symbol]
    
    def register_symbol_data(self, symbol_data: SymbolSessionData) -> None:
        """Register a fully-populated SymbolSessionData object.
        
        Used by SessionCoordinator to register symbols with pre-configured bar structure.
        The symbol_data should have bars dict populated with BarIntervalData objects.
        
        Args:
            symbol_data: Fully configured SymbolSessionData with bar structure
        """
        symbol = symbol_data.symbol.upper()
        with self._lock:
            self._symbols[symbol] = symbol_data
            bar_intervals = list(symbol_data.bars.keys())
            logger.info(
                f"✓ Registered symbol with structure: {symbol} "
                f"(intervals: {bar_intervals}, total symbols: {len(self._symbols)})"
            )
    
    def get_symbols_with_derived(self) -> Dict[str, List[str]]:
        """Get map of symbols to their derived intervals.
        
        Returns:
            Dict mapping symbol to list of derived interval names
            
        Example:
            {"AAPL": ["5m", "15m"], "RIVN": ["5m"]}
        """
        result = {}
        with self._lock:
            for symbol, symbol_data in self._symbols.items():
                derived = [
                    interval for interval, data in symbol_data.bars.items()
                    if data.derived
                ]
                if derived:
                    result[symbol] = derived
        return result
    
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
        
        Infers stream state from actual data structures - no separate tracker needed.
        A stream is active if the symbol exists and has data for that stream type.
        
        Args:
            symbol: Stock symbol
            stream_type: "bars", "ticks", or "quotes"
            
        Returns:
            True if stream is active (data structures exist), False otherwise
        """
        symbol = symbol.upper()
        stream_type = stream_type.lower()
        
        with self._lock:
            if symbol not in self._symbols:
                return False
            
            symbol_data = self._symbols[symbol]
            
            # Infer stream state from existence of data structures
            if stream_type == "bars":
                return len(symbol_data.bars) > 0
            elif stream_type == "quotes":
                return len(symbol_data.quotes) > 0
            elif stream_type == "ticks":
                return len(symbol_data.ticks) > 0
            
            return False
    
    # mark_stream_active() and mark_stream_inactive() removed
    # Stream state is now inferred from data structures automatically
    # When you add data → stream becomes active
    # When you remove symbol/interval → stream becomes inactive
    
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
        if symbol not in self._symbols:
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
                # Do NOT add to session bars to prevent duplicates!
                # (V2 structure uses symbol_data.bars[interval].data)
                # SessionCoordinator handles current session bar additions
            else:
                # Historical bar - add to historical.bars storage
                # Store by interval (string) and date
                interval_key = bar.interval
                if interval_key not in symbol_data.historical.bars:
                    symbol_data.historical.bars[interval_key] = HistoricalBarIntervalData()
                if bar_date not in symbol_data.historical.bars[interval_key].data_by_date:
                    symbol_data.historical.bars[interval_key].data_by_date[bar_date] = []
                symbol_data.historical.bars[interval_key].data_by_date[bar_date].append(bar)
    
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
        
        if symbol not in self._symbols:
            self.register_symbol(symbol)
        
        with self._lock:
            symbol_data = self._symbols[symbol]
            
            if insert_mode == "historical":
                # Force all bars to historical storage
                if "1m" not in symbol_data.historical.bars:
                    symbol_data.historical.bars["1m"] = HistoricalBarIntervalData()
                for bar in bars:
                    bar_date = bar.timestamp.date()
                    if bar_date not in symbol_data.historical.bars["1m"].data_by_date:
                        symbol_data.historical.bars["1m"].data_by_date[bar_date] = []
                    symbol_data.historical.bars["1m"].data_by_date[bar_date].append(bar)
                return
            
            if insert_mode == "stream":
                # Fast path: assume bars are chronological, just append
                interval_data = symbol_data.bars.get("1m")
                if interval_data:
                    interval_data.data.extend(bars)
                    for bar in bars:
                        symbol_data.update_from_bar(bar)
                    interval_data.updated = True
                # Signal upkeep thread that new data arrived
                self._data_arrival_event.set()
                return
            
            if insert_mode == "gap_fill":
                # Sorted insertion to maintain chronological order
                import bisect
                interval_data = symbol_data.bars.get("1m")
                if interval_data:
                    bars_list = list(interval_data.data)
                    for bar in bars:
                        # Find insertion point to maintain sorted order
                        idx = bisect.bisect_left([b.timestamp for b in bars_list], bar.timestamp)
                        bars_list.insert(idx, bar)
                        symbol_data.update_from_bar(bar)
                    # Replace deque with updated sorted list
                    from collections import deque
                    interval_data.data = deque(bars_list)
                    interval_data.updated = True
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
                interval_data = symbol_data.bars.get("1m")
                if interval_data:
                    bars_list = list(interval_data.data)
                    for bar in current_session_bars:
                        idx = bisect.bisect_left([b.timestamp for b in bars_list], bar.timestamp)
                        bars_list.insert(idx, bar)
                        symbol_data.update_from_bar(bar)
                    from collections import deque
                    interval_data.data = deque(bars_list)
                    interval_data.updated = True
                # Signal upkeep thread that new data arrived
                self._data_arrival_event.set()
            
            # Add historical bars
            if historical_bars_by_date:
                if "1m" not in symbol_data.historical.bars:
                    symbol_data.historical.bars["1m"] = HistoricalBarIntervalData()
                for bar_date, date_bars in historical_bars_by_date.items():
                    if bar_date not in symbol_data.historical.bars["1m"].data_by_date:
                        symbol_data.historical.bars["1m"].data_by_date[bar_date] = []
                    symbol_data.historical.bars["1m"].data_by_date[bar_date].extend(date_bars)
    
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
            
            # Normalize interval to string format
            if isinstance(interval, int):
                interval_key = f"{interval}m"
            else:
                interval_key = str(interval)
            
            # Get bar data from new structure (zero-copy)
            interval_data = symbol_data.bars.get(interval_key)
            if interval_data:
                return interval_data.data  # Direct reference to deque or list
            else:
                # Return empty container of appropriate type
                return deque() if interval == 1 else []
    
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
            
            # Normalize interval to string format
            if isinstance(interval, int):
                interval_key = f"{interval}m"
            else:
                interval_key = str(interval)
            
            # Get bars from new structure (creates copy)
            interval_data = symbol_data.bars.get(interval_key)
            if interval_data:
                bars = list(interval_data.data)  # Create copy
            else:
                return []
            
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
            
            # Get bar count from base interval
            base_interval_data = symbol_data.bars.get(symbol_data.base_interval)
            bar_count = len(base_interval_data.data) if base_interval_data else 0
            
            # Get quality from base interval
            quality = base_interval_data.quality if base_interval_data else 0.0
            
            return {
                "symbol": symbol,
                "session_volume": symbol_data.metrics.volume,
                "session_high": symbol_data.metrics.high,
                "session_low": symbol_data.metrics.low,
                "last_update": symbol_data.metrics.last_update,
                "bar_quality": quality,
                "bar_count": bar_count,
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
        
        if symbol not in self._symbols:
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
                    
                    # Store in historical.bars
                    interval_key = f"{interval}m" if isinstance(interval, int) else interval
                    if interval_key not in symbol_data.historical.bars:
                        symbol_data.historical.bars[interval_key] = HistoricalBarIntervalData()
                    
                    symbol_data.historical.bars[interval_key].data_by_date.update(dict(bars_by_date))
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
            
            interval_key = f"{interval}m" if isinstance(interval, int) else interval
            historical_data = symbol_data.historical.bars.get(interval_key)
            
            if not historical_data or not historical_data.data_by_date:
                return {}
            
            if days_back <= 0:
                return dict(historical_data.data_by_date)
            
            # Get last N days
            dates = sorted(historical_data.data_by_date.keys(), reverse=True)[:days_back]
            return {d: historical_data.data_by_date[d] for d in dates}
    
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
            interval_key = f"{interval}m" if isinstance(interval, int) else interval
            historical_data = symbol_data.historical.bars.get(interval_key)
            if historical_data and historical_data.data_by_date:
                for bar_date in sorted(historical_data.data_by_date.keys()):
                    all_bars.extend(historical_data.data_by_date[bar_date])
            
            # Add current session bars from new structure
            interval_key = f"{interval}m" if isinstance(interval, int) else str(interval)
            interval_data = symbol_data.bars.get(interval_key)
            if interval_data:
                all_bars.extend(list(interval_data.data))
            
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
                # Move all bars (base and derived) to historical
                for interval_key, interval_data in symbol_data.bars.items():
                    if len(interval_data.data) > 0:
                        # Store with same interval key format
                        if interval_key not in symbol_data.historical.bars:
                            symbol_data.historical.bars[interval_key] = HistoricalBarIntervalData()
                        
                        symbol_data.historical.bars[interval_key].data_by_date[old_date] = list(interval_data.data)
                
                # Remove oldest day if exceeding trailing days
                max_days = self.historical_bars_trailing_days
                if max_days > 0:
                    for interval_key in list(symbol_data.historical.bars.keys()):
                        interval_data = symbol_data.historical.bars[interval_key]
                        dates = sorted(interval_data.data_by_date.keys())
                        while len(dates) > max_days:
                            oldest = dates.pop(0)
                            del interval_data.data_by_date[oldest]
                            logger.debug(
                                f"Removed oldest historical day: {oldest} for interval {interval_key}"
                            )
                
                # Clear current session data from new structure
                for interval_data in symbol_data.bars.values():
                    interval_data.data.clear()
                    interval_data.updated = False
                
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
            # Reset all symbol data using new structure
            for symbol_data in self._symbols.values():
                # Clear all bar intervals
                for interval_data in symbol_data.bars.values():
                    interval_data.data.clear()
                    interval_data.updated = False
                
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
            num_symbols = len(self._symbols)
            self._symbols.clear()
            logger.warning(f"⚠ Session data cleared! Removed {num_symbols} symbols")
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
            
            logger.info(
                f"[SESSION_DATA] Removed {symbol} "
                f"({len(self._symbols)} symbols remaining)"
            )
            
            return True
    
    def get_active_symbols(self) -> Set[str]:
        """Get set of active symbols (thread-safe read).
        
        Returns:
            Set of active symbol names
        """
        # Block access when session inactive (catchup mode)
        if not self._check_session_active():
            return set()
        
        with self._lock:
            symbols = set(self._symbols.keys())
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
                symbol_data.historical.bars.clear()
            logger.debug("Cleared all historical bars")
    
    def clear_symbol_historical(self, symbol: str) -> None:
        """Clear historical bars for a specific symbol.
        
        Args:
            symbol: Symbol to clear historical data for
        """
        with self._lock:
            symbol_data = self._symbols.get(symbol)
            if symbol_data:
                symbol_data.historical.bars.clear()
                symbol_data.historical.indicators.clear()
                logger.debug(f"Cleared historical data for {symbol}")
            else:
                logger.warning(f"Cannot clear historical for {symbol} - symbol not found")
    
    def clear_session_bars(self) -> None:
        """Clear current session bars (not historical)."""
        with self._lock:
            symbols_cleared = []
            for symbol, symbol_data in self._symbols.items():
                # Get count from base interval before clearing
                base_interval_data = symbol_data.bars.get(symbol_data.base_interval)
                bars_before = len(base_interval_data.data) if base_interval_data else 0
                
                # Clear all bar intervals
                for interval_data in symbol_data.bars.values():
                    interval_data.data.clear()
                    interval_data.updated = False
                
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
            
            # Normalize interval to string key format (e.g., "1m", "5m", "1d")
            if isinstance(interval, int):
                interval_key = f"{interval}m"
            else:
                interval_key = interval
            
            if interval_key not in symbol_data.historical.bars:
                symbol_data.historical.bars[interval_key] = HistoricalBarIntervalData()
            
            if bar_date not in symbol_data.historical.bars[interval_key].data_by_date:
                symbol_data.historical.bars[interval_key].data_by_date[bar_date] = []
            
            symbol_data.historical.bars[interval_key].data_by_date[bar_date].append(bar)
            
            # Debug logging for 1d bars
            if interval == "1d" or interval_key == "1d":
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
            
            # Update quality in bar structure
            interval_data = symbol_data.bars.get(interval_key)
            if interval_data:
                interval_data.quality = quality
                logger.debug(f"Set quality for {symbol} {interval_key}: {quality:.1f}%")
            else:
                logger.warning(f"No interval data for {symbol} {interval_key}, cannot set quality")
    
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
            
            # Get quality from bar structure
            interval_data = symbol_data.bars.get(interval_key)
            return interval_data.quality if interval_data else None
    
    def set_gaps(self, symbol: str, interval: str, gaps: List) -> None:
        """Set gaps for a symbol/interval.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval (e.g., "1m", "5m", "1d")
            gaps: List of GapInfo objects
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
            
            # Update gaps in bar structure
            interval_data = symbol_data.bars.get(interval_key)
            if interval_data:
                interval_data.gaps = gaps
                logger.debug(f"Set {len(gaps)} gaps for {symbol} {interval_key}")
            else:
                logger.warning(f"No interval data for {symbol} {interval_key}, cannot set gaps")
    
    def get_gaps(self, symbol: str, interval: str) -> List:
        """Get gaps for a symbol/interval.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval (e.g., "1m", "5m", "1d")
            
        Returns:
            List of GapInfo objects or empty list if not set
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
                return []
            
            # Get gaps from bar structure
            interval_data = symbol_data.bars.get(interval_key)
            return interval_data.gaps if interval_data else []
    
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
            symbol_data.historical.indicators[name] = value
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
            return symbol_data.historical.indicators.get(name)
    
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
            return symbol_data.historical.indicators.copy()
    
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
            
            # Try base interval first
            base_interval_data = symbol_data.bars.get(symbol_data.base_interval)
            if base_interval_data and len(base_interval_data.data) > 0:
                latest_bar = base_interval_data.data[-1]
                return Quote(
                    symbol=symbol,
                    timestamp=latest_bar.timestamp,
                    bid=latest_bar.close,
                    ask=latest_bar.close,
                    bid_size=0,
                    ask_size=0,
                    source="bar"
                )
            
            # Try 1m bars (if different from base)
            if symbol_data.base_interval != "1m":
                interval_1m = symbol_data.bars.get("1m")
                if interval_1m and len(interval_1m.data) > 0:
                    latest_bar = interval_1m.data[-1]
                    return Quote(
                        symbol=symbol,
                        timestamp=latest_bar.timestamp,
                        bid=latest_bar.close,
                        ask=latest_bar.close,
                        bid_size=0,
                        ask_size=0,
                        source="bar"
                    )
            
            # Try 1d bars
            interval_1d = symbol_data.bars.get("1d")
            if interval_1d and len(interval_1d.data) > 0:
                latest_bar = interval_1d.data[-1]
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
    
    # ==================== SCANNER FRAMEWORK SUPPORT ====================
    
    def set_indicator_manager(self, indicator_manager: Any) -> None:
        """Set indicator manager reference (called by coordinator).
        
        Args:
            indicator_manager: IndicatorManager instance
        """
        self._indicator_manager = indicator_manager
        logger.debug("IndicatorManager reference set in SessionData")
    
    def set_session_coordinator(self, coordinator: Any) -> None:
        """Set session coordinator reference (called by coordinator).
        
        Args:
            coordinator: SessionCoordinator instance
        """
        self._session_coordinator = coordinator
        logger.debug("SessionCoordinator reference set in SessionData")
    
    def register_config_symbol(self, symbol: str) -> None:
        """Register a symbol from session_config (not adhoc).
        
        Args:
            symbol: Symbol from session_config
        """
        symbol = symbol.upper()
        with self._lock:
            self._config_symbols.add(symbol)
            logger.debug(f"Registered config symbol: {symbol}")
    
    def get_config_symbols(self) -> Set[str]:
        """Get set of symbols from session_config.
        
        Returns:
            Set of config symbol names
        """
        with self._lock:
            return self._config_symbols.copy()
    
    # ==================== ADHOC DATA APIS ====================
    
    def add_historical_bars(self, symbol: str, interval: str, days: int) -> bool:
        """Add historical bars for a symbol (adhoc, lightweight).
        
        Provisions historical bars only (no streaming).
        Used by scanners for lightweight data provisioning.
        
        Args:
            symbol: Symbol to add bars for
            interval: Bar interval (e.g., "1d", "5m")
            days: Number of historical days to load
        
        Returns:
            True if successful
        """
        symbol = symbol.upper()
        
        logger.info(f"[ADHOC] add_historical_bars({symbol}, {interval}, {days} days)")
        
        # Register symbol if not exists
        with self._lock:
            if symbol not in self._symbols:
                self.register_symbol(symbol)
        
        # Load historical bars via session coordinator
        if self._session_coordinator:
            # Coordinator will load historical bars
            logger.debug(f"Requesting historical bars for {symbol} {interval}")
            # TODO: Call coordinator method to load historical bars
            # self._session_coordinator.load_historical_bars(symbol, interval, days)
        else:
            logger.warning("SessionCoordinator not set, cannot load historical bars")
        
        return True
    
    def add_session_bars(self, symbol: str, interval: str) -> bool:
        """Add session bars for a symbol (adhoc, streaming only).
        
        Provisions live streaming bars only (no historical).
        Used by scanners for real-time data.
        
        Args:
            symbol: Symbol to add bars for
            interval: Bar interval (e.g., "1m", "5m")
        
        Returns:
            True if successful
        """
        symbol = symbol.upper()
        
        logger.info(f"[ADHOC] add_session_bars({symbol}, {interval})")
        
        # Register symbol if not exists
        with self._lock:
            if symbol not in self._symbols:
                self.register_symbol(symbol)
        
        # Start streaming via session coordinator
        if self._session_coordinator:
            logger.debug(f"Requesting session bars stream for {symbol} {interval}")
            # TODO: Call coordinator method to start streaming
            # self._session_coordinator.start_bar_stream(symbol, interval)
        else:
            logger.warning("SessionCoordinator not set, cannot start streaming")
        
        return True
    
    def add_indicator(
        self,
        symbol: str,
        indicator_type: str,
        config: dict
    ) -> bool:
        """Add indicator for a symbol (adhoc, automatic bar provisioning).
        
        Uses requirement_analyzer to automatically provision required bars
        (historical + session). This is the UNIFIED routine used by both
        session_config and adhoc scanner indicators.
        
        Args:
            symbol: Symbol to add indicator for
            indicator_type: Indicator name (e.g., "sma", "rsi")
            config: Indicator configuration dict
                {
                    "period": 20,
                    "interval": "1d",
                    "type": "trend",
                    "params": {}
                }
        
        Returns:
            True if successful, False if already exists
        """
        from app.indicators import IndicatorConfig, IndicatorType
        
        symbol = symbol.upper()
        
        logger.info(f"[ADHOC] add_indicator({symbol}, {indicator_type}, interval={config.get('interval')})")
        
        with self._lock:
            # Register symbol if not exists
            if symbol not in self._symbols:
                self.register_symbol(symbol)
            
            symbol_data = self._symbols[symbol]
            
            # Create IndicatorConfig
            indicator_config = IndicatorConfig(
                name=indicator_type,
                type=IndicatorType(config.get("type", "trend")),
                period=config.get("period", 0),
                interval=config["interval"],
                params=config.get("params", {})
            )
            
            key = indicator_config.make_key()
            
            # Check if already exists
            if key in symbol_data.indicators:
                logger.debug(f"{symbol}: Indicator {key} already exists")
                return False
            
            # UNIFIED ROUTINE: Use requirement_analyzer to determine needed bars
            logger.debug(f"Analyzing requirements for {key}...")
            
            # Get SystemManager from SessionCoordinator
            if not self._session_coordinator:
                logger.error("SessionCoordinator not set - cannot analyze indicator requirements")
                return False
            
            system_manager = self._session_coordinator._system_manager
            
            # Analyze requirements (creates its own DB session internally)
            from app.threads.quality.requirement_analyzer import analyze_indicator_requirements
            requirements = analyze_indicator_requirements(
                indicator_config=indicator_config,
                system_manager=system_manager,
                warmup_multiplier=2.0,  # 2x period for warmup
                from_date=None,  # Use current date
                exchange="NYSE"
            )
            
            logger.info(
                f"[ADHOC] Indicator {key} requires: "
                f"intervals={requirements.required_intervals}, "
                f"historical_bars={requirements.historical_bars}, "
                f"historical_days={requirements.historical_days}"
            )
            logger.debug(f"[ADHOC] Reasoning: {requirements.reason}")
            
            # Provision required bars automatically
            for required_interval in requirements.required_intervals:
                # Add historical bars for warmup
                if requirements.historical_days > 0:
                    logger.debug(
                        f"[ADHOC] Provisioning {requirements.historical_days} days "
                        f"of {required_interval} bars for {symbol}"
                    )
                    self.add_historical_bars(
                        symbol=symbol,
                        interval=required_interval,
                        days=requirements.historical_days
                    )
                
                # Add session bars for real-time updates
                logger.debug(f"[ADHOC] Provisioning {required_interval} session bars for {symbol}")
                self.add_session_bars(
                    symbol=symbol,
                    interval=required_interval
                )
            
            # Add metadata (invalid until calculated)
            from app.indicators import IndicatorData
            symbol_data.indicators[key] = IndicatorData(
                name=indicator_type,
                type=config.get("type", "trend"),
                interval=config["interval"],
                current_value=None,
                last_updated=None,
                valid=False
            )
            
            # Register with IndicatorManager
            if self._indicator_manager:
                self._indicator_manager.register_symbol_indicators(
                    symbol=symbol,
                    indicators=[indicator_config],
                    historical_bars=None  # Will calculate when bars available
                )
                logger.debug(f"Registered indicator {key} with IndicatorManager")
            else:
                logger.warning("IndicatorManager not set, indicator not registered")
            
            logger.success(
                f"[ADHOC] Added indicator {key} for {symbol} "
                f"(provisioned {len(requirements.required_intervals)} intervals, "
                f"{requirements.historical_days} days historical)"
            )
            return True
    
    def add_symbol(self, symbol: str) -> bool:
        """Add symbol as full strategy symbol (idempotent).
        
        Promotes a symbol to full strategy symbol with all streams,
        indicators, and historical data from session_config.
        
        This is IDEMPOTENT - safe to call multiple times.
        
        Args:
            symbol: Symbol to add
        
        Returns:
            True if added, False if already exists as config symbol
        """
        symbol = symbol.upper()
        
        logger.info(f"[ADHOC] add_symbol({symbol})")
        
        with self._lock:
            # Check if already a config symbol
            if symbol in self._config_symbols:
                logger.debug(f"{symbol} already exists as config symbol (idempotent)")
                return False
            
            # Register as config symbol
            self._config_symbols.add(symbol)
        
        # Add symbol via session coordinator (triggers full loading)
        if self._session_coordinator:
            logger.info(f"Calling coordinator to add {symbol} (full loading)...")
            # TODO: Call coordinator method
            # success = await self._session_coordinator.add_symbol_mid_session(symbol)
            # return success
            logger.warning("Session coordinator add_symbol_mid_session not called (TODO)")
            return True
        else:
            logger.error("SessionCoordinator not set, cannot add symbol")
            return False
    
    # =========================================================================
    # Phase 5c: Unified Entry Points (Three-Phase Pattern)
    # =========================================================================
    
    def add_indicator_unified(
        self,
        symbol: str,
        indicator_config,
        source: str = "scanner"
    ) -> bool:
        """Add indicator with unified three-phase pattern.
        
        Phase 5c: Unified entry point for indicator addition that uses the
        three-phase provisioning pattern (analyze → validate → provision).
        
        This method replaces the old add_indicator() with a unified approach
        that handles requirement analysis, validation, and provisioning in a
        consistent way.
        
        Three-Phase Pattern:
            1. REQUIREMENT ANALYSIS → What's needed?
            2. VALIDATION → Can we proceed?
            3. PROVISIONING → Execute plan
        
        Args:
            symbol: Symbol to add indicator for
            indicator_config: IndicatorConfig object with indicator details
            source: Who is adding? ("scanner", "strategy", "adhoc")
        
        Returns:
            True if indicator added successfully, False otherwise
        
        Code Reuse:
            - REUSES: _analyze_requirements() from Phase 5a
            - REUSES: _execute_provisioning() from Phase 5b
            - REUSES: All validation and loading from Phases 1-4
        
        Auto-Provisioning:
            - If symbol doesn't exist, auto-provisions minimal structure
            - Loads only required intervals and warmup bars
            - Sets meets_session_config_requirements = False
        
        Example:
            >>> from app.indicators import IndicatorConfig, IndicatorType
            >>> sma_config = IndicatorConfig(
            ...     name="sma", type=IndicatorType.TREND,
            ...     period=20, interval="5m", params={}
            ... )
            >>> success = session_data.add_indicator_unified(
            ...     symbol="TSLA",
            ...     indicator_config=sma_config,
            ...     source="scanner"
            ... )
        """
        if not self._session_coordinator:
            logger.error("SessionCoordinator not set, cannot add indicator")
            return False
        
        symbol = symbol.upper()
        
        logger.info(
            f"[UNIFIED] add_indicator_unified({symbol}, "
            f"{indicator_config.name}, source={source})"
        )
        
        try:
            # Phase 1: Analyze requirements
            req = self._session_coordinator._analyze_requirements(
                operation_type="indicator",
                symbol=symbol,
                source=source,
                indicator_config=indicator_config
            )
            
            # Phase 2: Validate (done in analyze_requirements)
            if not req.can_proceed:
                logger.error(
                    f"[UNIFIED] {symbol}: Cannot add indicator - {req.validation_errors}"
                )
                return False
            
            # Phase 3: Provision
            success = self._session_coordinator._execute_provisioning(req)
            
            if success:
                logger.success(
                    f"[UNIFIED] {symbol}: Indicator {indicator_config.name} "
                    f"added successfully (source={source})"
                )
            else:
                logger.error(f"[UNIFIED] {symbol}: Provisioning failed")
            
            return success
            
        except Exception as e:
            logger.error(f"[UNIFIED] {symbol}: Exception adding indicator: {e}")
            logger.exception(e)
            return False
    
    def add_bar_unified(
        self,
        symbol: str,
        interval: str,
        days: int = 0,
        historical_only: bool = False,
        source: str = "scanner"
    ) -> bool:
        """Add bar with unified three-phase pattern.
        
        Phase 5c: Unified entry point for bar addition that uses the
        three-phase provisioning pattern (analyze → validate → provision).
        
        Three-Phase Pattern:
            1. REQUIREMENT ANALYSIS → What's needed?
            2. VALIDATION → Can we proceed?
            3. PROVISIONING → Execute plan
        
        Args:
            symbol: Symbol to add bar for
            interval: Bar interval (e.g., "1m", "5m", "1d")
            days: Historical days to load (0 for session only)
            historical_only: If True, no session streaming
            source: Who is adding? ("scanner", "strategy", "adhoc")
        
        Returns:
            True if bar added successfully, False otherwise
        
        Code Reuse:
            - REUSES: _analyze_requirements() from Phase 5a
            - REUSES: _execute_provisioning() from Phase 5b
            - REUSES: All validation and loading from Phases 1-4
        
        Auto-Provisioning:
            - If symbol doesn't exist, auto-provisions minimal structure
            - Adds base interval if needed (e.g., 1m for 5m)
            - Sets meets_session_config_requirements = False
        
        Example:
            >>> # Add 15m bars with 5 days historical
            >>> success = session_data.add_bar_unified(
            ...     symbol="RIVN",
            ...     interval="15m",
            ...     days=5,
            ...     source="scanner"
            ... )
        """
        if not self._session_coordinator:
            logger.error("SessionCoordinator not set, cannot add bar")
            return False
        
        symbol = symbol.upper()
        
        logger.info(
            f"[UNIFIED] add_bar_unified({symbol}, {interval}, "
            f"days={days}, source={source})"
        )
        
        try:
            # Phase 1: Analyze requirements
            req = self._session_coordinator._analyze_requirements(
                operation_type="bar",
                symbol=symbol,
                source=source,
                interval=interval,
                days=days,
                historical_only=historical_only
            )
            
            # Phase 2: Validate (done in analyze_requirements)
            if not req.can_proceed:
                logger.error(
                    f"[UNIFIED] {symbol}: Cannot add bar - {req.validation_errors}"
                )
                return False
            
            # Phase 3: Provision
            success = self._session_coordinator._execute_provisioning(req)
            
            if success:
                logger.success(
                    f"[UNIFIED] {symbol}: Bar {interval} added successfully "
                    f"({days} days historical, source={source})"
                )
            else:
                logger.error(f"[UNIFIED] {symbol}: Provisioning failed")
            
            return success
            
        except Exception as e:
            logger.error(f"[UNIFIED] {symbol}: Exception adding bar: {e}")
            logger.exception(e)
            return False
    
    def lock_symbol(self, symbol: str, reason: str) -> bool:
        """Lock symbol to prevent removal.
        
        Used by analysis engine when position is open.
        
        Args:
            symbol: Symbol to lock
            reason: Reason for lock (e.g., "open_position")
        
        Returns:
            True if locked
        """
        symbol = symbol.upper()
        
        with self._lock:
            self._symbol_locks[symbol] = reason
            logger.debug(f"Locked {symbol}: {reason}")
            return True
    
    def unlock_symbol(self, symbol: str) -> bool:
        """Unlock symbol to allow removal.
        
        Args:
            symbol: Symbol to unlock
        
        Returns:
            True if unlocked, False if not locked
        """
        symbol = symbol.upper()
        
        with self._lock:
            if symbol in self._symbol_locks:
                reason = self._symbol_locks.pop(symbol)
                logger.debug(f"Unlocked {symbol} (was: {reason})")
                return True
            return False
    
    def is_symbol_locked(self, symbol: str) -> bool:
        """Check if symbol is locked.
        
        Args:
            symbol: Symbol to check
        
        Returns:
            True if locked
        """
        symbol = symbol.upper()
        
        with self._lock:
            return symbol in self._symbol_locks
    
    # ==================== SYMBOL REMOVAL WITH LOCK PROTECTION ====================
    
    def remove_symbol_adhoc(self, symbol: str) -> bool:
        """Remove symbol (adhoc, with lock protection).
        
        Only removes if symbol is NOT locked (no open positions).
        Used by scanners in teardown to cleanup unused symbols.
        
        Args:
            symbol: Symbol to remove
        
        Returns:
            True if removed, False if locked or not found
        """
        symbol = symbol.upper()
        
        with self._lock:
            # Check if locked
            if symbol in self._symbol_locks:
                reason = self._symbol_locks[symbol]
                logger.warning(f"Cannot remove {symbol}: locked ({reason})")
                return False
            
            # Check if config symbol
            if symbol in self._config_symbols:
                logger.warning(f"Cannot remove {symbol}: config symbol")
                return False
        
        # Remove using existing method
        return self.remove_symbol(symbol)
    
    # ==================== JSON EXPORT ====================
    
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
            "_active_symbols": sorted(list(self._symbols.keys())),
            "symbols": {}
        }
        
        # Export each symbol's data
        with self._lock:
            for symbol, symbol_data in self._symbols.items():
                result["symbols"][symbol] = symbol_data.to_json(complete=complete)
            
            # Update last export time for next delta
            # Always use TimeManager through session coordinator
            if self._session_coordinator:
                self._last_export_time = self._session_coordinator._time_manager.get_current_time()
            else:
                # If no coordinator set, SessionData is being used incorrectly
                # This should only happen in isolated unit tests
                logger.warning("SessionData.to_json() called without session_coordinator - export timestamp unavailable")
                # Keep previous timestamp or None
                if self._last_export_time is None:
                    # Use a sentinel value for tests - they should mock this
                    self._last_export_time = None
        
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
