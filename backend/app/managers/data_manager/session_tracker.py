"""Session Tracker for Real-time Session Metrics

DEPRECATED: This module is being replaced by session_data.py

SessionTracker functionality has been moved to the new SessionData singleton
which provides more comprehensive session management. This module is kept
for backward compatibility during the migration period.

New code should use:
    from app.managers.data_manager.session_data import get_session_data
    session_data = get_session_data()

See: app/managers/data_manager/session_data.py

Tracks current trading session metrics like cumulative volume,
session high/low, and provides caching for performance.
"""
import warnings

warnings.warn(
    "SessionTracker is deprecated. Use session_data.get_session_data() instead. "
    "This module will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2
)
from datetime import datetime, date, time
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from functools import lru_cache
import asyncio


@dataclass
class SessionMetrics:
    """Metrics for a trading session."""
    
    date: date
    symbol: str
    session_volume: int = 0
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    last_update: Optional[datetime] = None
    
    def update_from_bar(self, bar_high: float, bar_low: float, bar_volume: int, timestamp: datetime) -> None:
        """Update session metrics from a bar.
        
        Args:
            bar_high: Bar high price
            bar_low: Bar low price
            bar_volume: Bar volume
            timestamp: Bar timestamp
        """
        # Update volume
        self.session_volume += bar_volume
        
        # Update high
        if self.session_high is None or bar_high > self.session_high:
            self.session_high = bar_high
        
        # Update low
        if self.session_low is None or bar_low < self.session_low:
            self.session_low = bar_low
        
        self.last_update = timestamp


class SessionTracker:
    """Tracks real-time session metrics across symbols.
    
    Maintains current session state for each symbol, tracking:
    - Cumulative session volume
    - Session high/low prices
    - Last update timestamp
    
    Thread-safe for concurrent access.
    """
    
    def __init__(self):
        """Initialize session tracker."""
        self._sessions: Dict[str, SessionMetrics] = {}
        self._lock = asyncio.Lock()
        
        # Cache for historical calculations
        self._avg_volume_cache: Dict[tuple, tuple] = {}  # (symbol, days) -> (value, timestamp)
        self._time_specific_cache: Dict[tuple, tuple] = {}  # (symbol, time, days) -> (value, timestamp)
        self._historical_hl_cache: Dict[tuple, tuple] = {}  # (symbol, days) -> (high, low, timestamp)
        
        # Cache TTL in seconds
        self.cache_ttl = 300  # 5 minutes
    
    async def get_session_metrics(self, symbol: str, session_date: date) -> SessionMetrics:
        """Get or create session metrics for a symbol.
        
        Args:
            symbol: Stock symbol
            session_date: Trading date
            
        Returns:
            SessionMetrics for the symbol and date
        """
        key = f"{symbol}:{session_date}"
        
        async with self._lock:
            if key not in self._sessions:
                self._sessions[key] = SessionMetrics(
                    date=session_date,
                    symbol=symbol.upper()
                )
            
            metrics = self._sessions[key]
            
            # Clear if date mismatch (new session)
            if metrics.date != session_date:
                self._sessions[key] = SessionMetrics(
                    date=session_date,
                    symbol=symbol.upper()
                )
                metrics = self._sessions[key]
            
            return metrics
    
    async def update_session(
        self,
        symbol: str,
        session_date: date,
        bar_high: float,
        bar_low: float,
        bar_volume: int,
        timestamp: datetime
    ) -> SessionMetrics:
        """Update session metrics from a new bar.
        
        Args:
            symbol: Stock symbol
            session_date: Trading date
            bar_high: Bar high price
            bar_low: Bar low price
            bar_volume: Bar volume
            timestamp: Bar timestamp
            
        Returns:
            Updated SessionMetrics
        """
        metrics = await self.get_session_metrics(symbol, session_date)
        
        async with self._lock:
            metrics.update_from_bar(bar_high, bar_low, bar_volume, timestamp)
        
        return metrics
    
    async def reset_session(self, symbol: str, session_date: date) -> None:
        """Reset session metrics for a symbol.
        
        Args:
            symbol: Stock symbol
            session_date: New session date
        """
        key = f"{symbol}:{session_date}"
        
        async with self._lock:
            self._sessions[key] = SessionMetrics(
                date=session_date,
                symbol=symbol.upper()
            )
    
    def _is_cache_valid(self, cached_timestamp: datetime) -> bool:
        """Check if cached value is still valid.
        
        Args:
            cached_timestamp: When the value was cached
            
        Returns:
            True if cache is still valid
        """
        age = (datetime.utcnow() - cached_timestamp).total_seconds()
        return age < self.cache_ttl
    
    def cache_avg_volume(self, symbol: str, days: int, value: float) -> None:
        """Cache average volume calculation.
        
        Args:
            symbol: Stock symbol
            days: Number of days
            value: Calculated average volume
        """
        key = (symbol.upper(), days)
        self._avg_volume_cache[key] = (value, datetime.utcnow())
    
    def get_cached_avg_volume(self, symbol: str, days: int) -> Optional[float]:
        """Get cached average volume if valid.
        
        Args:
            symbol: Stock symbol
            days: Number of days
            
        Returns:
            Cached average volume or None if not cached/expired
        """
        key = (symbol.upper(), days)
        if key in self._avg_volume_cache:
            value, timestamp = self._avg_volume_cache[key]
            if self._is_cache_valid(timestamp):
                return value
        return None
    
    def cache_time_specific_volume(
        self,
        symbol: str,
        target_time: time,
        days: int,
        value: float
    ) -> None:
        """Cache time-specific average volume.
        
        Args:
            symbol: Stock symbol
            target_time: Time of day
            days: Number of days lookback
            value: Calculated average
        """
        key = (symbol.upper(), target_time.isoformat(), days)
        self._time_specific_cache[key] = (value, datetime.utcnow())
    
    def get_cached_time_specific_volume(
        self,
        symbol: str,
        target_time: time,
        days: int
    ) -> Optional[float]:
        """Get cached time-specific average volume.
        
        Args:
            symbol: Stock symbol
            target_time: Time of day
            days: Number of days lookback
            
        Returns:
            Cached average or None
        """
        key = (symbol.upper(), target_time.isoformat(), days)
        if key in self._time_specific_cache:
            value, timestamp = self._time_specific_cache[key]
            if self._is_cache_valid(timestamp):
                return value
        return None
    
    def cache_historical_hl(
        self,
        symbol: str,
        days: int,
        high: float,
        low: float
    ) -> None:
        """Cache historical high/low.
        
        Args:
            symbol: Stock symbol
            days: Number of days lookback
            high: Highest price
            low: Lowest price
        """
        key = (symbol.upper(), days)
        self._historical_hl_cache[key] = (high, low, datetime.utcnow())
    
    def get_cached_historical_hl(
        self,
        symbol: str,
        days: int
    ) -> Optional[tuple[float, float]]:
        """Get cached historical high/low.
        
        Args:
            symbol: Stock symbol
            days: Number of days lookback
            
        Returns:
            Tuple of (high, low) or None
        """
        key = (symbol.upper(), days)
        if key in self._historical_hl_cache:
            high, low, timestamp = self._historical_hl_cache[key]
            if self._is_cache_valid(timestamp):
                return (high, low)
        return None
    
    async def clear_cache(self) -> None:
        """Clear all caches."""
        async with self._lock:
            self._avg_volume_cache.clear()
            self._time_specific_cache.clear()
            self._historical_hl_cache.clear()
    
    async def clear_all(self) -> None:
        """Clear all sessions and caches."""
        async with self._lock:
            self._sessions.clear()
            self._avg_volume_cache.clear()
            self._time_specific_cache.clear()
            self._historical_hl_cache.clear()


# Global session tracker instance
_session_tracker: Optional[SessionTracker] = None


def get_session_tracker() -> SessionTracker:
    """Get the global session tracker instance.
    
    Returns:
        SessionTracker singleton
    """
    global _session_tracker
    if _session_tracker is None:
        _session_tracker = SessionTracker()
    return _session_tracker


def reset_session_tracker() -> None:
    """Reset the global session tracker (useful for testing)."""
    global _session_tracker
    _session_tracker = None
