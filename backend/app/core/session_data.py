"""
SessionData - Unified data store for all session-relevant data.

This module provides a single interface for storing and accessing:
- Historical bars (trailing days of data)
- Current session bars (today's data)
- Historical indicators (pre-calculated before session)
- Real-time indicators (calculated during session)
- Quality metrics (per symbol, per data type)

Key Design Principles:
1. Zero-copy: Returns references to data structures, NOT copies
2. Fast containers: deque for O(1) append, dict for O(1) lookup
3. Single interface: Analysis Engine accesses ONLY from session_data
4. Thread-safe reads: Multiple threads can read concurrently

Reference: SESSION_ARCHITECTURE.md - Section 3: Session Data
"""

import logging
from collections import defaultdict, deque
from typing import Any, Dict, Optional, Deque

logger = logging.getLogger(__name__)


class SessionData:
    """Unified data store for all session-relevant data.
    
    Architecture:
        - Holds BOTH historical data (trailing days) AND current session data
        - From strategy perspective: ALL data required for current session
        - Contains all data available up to current time (NO future data)
    
    Data Flow:
        Coordinator Input Queues → session_data → Analysis Engine
    
    Performance:
        - Zero-copy access (return references, never copy)
        - Fast containers (deque for O(1) append)
        - Indexed access for historical indicators (O(1) lookup)
    """
    
    def __init__(self):
        """Initialize empty session data store."""
        # Bars: {symbol: {interval: deque([bar1, bar2, ...])}}
        # Example: {"AAPL": {"1m": deque([bar1, bar2, ...]), "5m": deque([...])}}
        self._bars: Dict[str, Dict[str, Deque]] = defaultdict(lambda: defaultdict(deque))
        
        # Historical indicators: {name: indexed_data}
        # indexed_data structure allows O(1) lookup by time index
        # Example: {"avg_volume": <indexed_data>, "high_52w": 245.67}
        self._historical_indicators: Dict[str, Any] = {}
        
        # Real-time indicators: {symbol: {name: value}}
        # Example: {"AAPL": {"rsi": 65.4, "macd": 1.23}}
        self._realtime_indicators: Dict[str, Dict[str, Any]] = defaultdict(dict)
        
        # Quality metrics: {symbol: {data_type: percentage}}
        # Example: {"AAPL": {"1m": 98.5, "5m": 98.5}, "RIVN": {"1m": 100.0}}
        self._quality_metrics: Dict[str, Dict[str, float]] = defaultdict(dict)
        
        logger.debug("SessionData initialized")
    
    # =========================================================================
    # Bar Operations
    # =========================================================================
    
    def append_bar(self, symbol: str, interval: str, bar: Any) -> None:
        """Append bar to session data (zero-copy).
        
        Args:
            symbol: Stock symbol (e.g., "AAPL")
            interval: Bar interval (e.g., "1m", "5m", "1d")
            bar: Bar object (NOT copied, reference stored)
        
        Performance: O(1) - deque append
        Thread-safety: Write operation, should be called by single thread (coordinator/processor)
        """
        self._bars[symbol][interval].append(bar)
    
    def get_bars(self, symbol: str, interval: str) -> Deque:
        """Get bars for symbol and interval (zero-copy).
        
        Args:
            symbol: Stock symbol
            interval: Bar interval
        
        Returns:
            deque reference (NOT a copy) - modifications will affect original
        
        Performance: O(1) - dict lookup
        Thread-safety: Safe for concurrent reads
        
        Critical: Returns the ACTUAL deque, not a copy. This is intentional for
        zero-copy design. Callers should treat as read-only.
        """
        return self._bars[symbol][interval]
    
    def get_bar_at_index(self, symbol: str, interval: str, index: int) -> Optional[Any]:
        """Get bar at specific index.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval
            index: Index in deque (0-indexed, negative for reverse)
        
        Returns:
            Bar object or None if index out of range
        
        Performance: O(n) for deque indexing, but fast for recent data
        
        Example:
            get_bar_at_index("AAPL", "1m", -1)  # Last bar
            get_bar_at_index("AAPL", "1m", 0)   # First bar
        """
        bars = self._bars[symbol][interval]
        try:
            return bars[index]
        except IndexError:
            return None
    
    def get_bar_count(self, symbol: str, interval: str) -> int:
        """Get number of bars for symbol and interval.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval
        
        Returns:
            Number of bars in deque
        
        Performance: O(1)
        """
        return len(self._bars[symbol][interval])
    
    # =========================================================================
    # Historical Indicator Operations
    # =========================================================================
    
    def set_historical_indicator(self, name: str, data: Any) -> None:
        """Store historical indicator with indexed access.
        
        Args:
            name: Indicator name (e.g., "avg_volume", "high_52w")
            data: Indexed data structure supporting O(1) lookup by time
        
        Note: The data structure should support fast indexed access.
        For single-value indicators (e.g., 52-week high), store the value directly.
        For time-series indicators (e.g., minute-by-minute averages), use indexed structure.
        """
        self._historical_indicators[name] = data
        logger.debug(f"Stored historical indicator: {name}")
    
    def get_historical_indicator(self, name: str, time_index: Optional[Any] = None) -> Any:
        """Get historical indicator value.
        
        Args:
            name: Indicator name
            time_index: Optional time index for time-series indicators
        
        Returns:
            Indicator value or indexed data structure
        
        Performance: O(1) for scalar, O(1) for indexed lookup
        
        Example:
            get_historical_indicator("high_52w")  # Returns single value
            get_historical_indicator("avg_volume_intraday", time_index=150)  # Indexed
        """
        indicator = self._historical_indicators.get(name)
        
        if time_index is not None and hasattr(indicator, '__getitem__'):
            # Time-series indicator with indexing
            return indicator[time_index]
        else:
            # Scalar indicator
            return indicator
    
    def has_historical_indicator(self, name: str) -> bool:
        """Check if historical indicator exists.
        
        Args:
            name: Indicator name
        
        Returns:
            True if indicator exists, False otherwise
        """
        return name in self._historical_indicators
    
    # =========================================================================
    # Real-time Indicator Operations
    # =========================================================================
    
    def set_realtime_indicator(self, symbol: str, name: str, value: Any) -> None:
        """Set real-time indicator value.
        
        Args:
            symbol: Stock symbol
            name: Indicator name (e.g., "rsi", "macd")
            value: Indicator value
        
        Note: Real-time indicators are calculated during the session as new bars arrive.
        """
        self._realtime_indicators[symbol][name] = value
    
    def get_realtime_indicator(self, symbol: str, name: str) -> Optional[Any]:
        """Get real-time indicator value.
        
        Args:
            symbol: Stock symbol
            name: Indicator name
        
        Returns:
            Indicator value or None if not found
        """
        return self._realtime_indicators[symbol].get(name)
    
    # =========================================================================
    # Quality Metric Operations
    # =========================================================================
    
    def set_quality_metric(self, symbol: str, data_type: str, percentage: float) -> None:
        """Set quality percentage for symbol and data type.
        
        Args:
            symbol: Stock symbol
            data_type: Data type (interval for bars, e.g., "1m", "5m")
            percentage: Quality percentage (0.0 to 100.0)
        
        Example:
            set_quality_metric("AAPL", "1m", 98.5)  # AAPL 1m bars are 98.5% complete
        
        Note: Quality is per symbol, per data type (not overall).
        """
        if not (0.0 <= percentage <= 100.0):
            logger.warning(
                f"Quality percentage {percentage} out of range for {symbol} {data_type}, "
                f"clamping to [0.0, 100.0]"
            )
            percentage = max(0.0, min(100.0, percentage))
        
        self._quality_metrics[symbol][data_type] = percentage
    
    def get_quality_metric(self, symbol: str, data_type: str) -> float:
        """Get quality percentage for symbol and data type.
        
        Args:
            symbol: Stock symbol
            data_type: Data type (interval for bars)
        
        Returns:
            Quality percentage (0.0 to 100.0), defaults to 100.0 if not set
        
        Note: Returns 100.0 by default (assume perfect quality unless explicitly set otherwise).
        """
        return self._quality_metrics[symbol].get(data_type, 100.0)
    
    # =========================================================================
    # Lifecycle Operations
    # =========================================================================
    
    def clear(self) -> None:
        """Clear all data from session_data.
        
        Called at session end (via session_coordinator.stop()) to free memory.
        Reloaded before each session with fresh historical data.
        """
        self._bars.clear()
        self._historical_indicators.clear()
        self._realtime_indicators.clear()
        self._quality_metrics.clear()
        logger.debug("SessionData cleared")
    
    def clear_historical_bars(self) -> None:
        """Clear all historical bars (called before reloading historical data).
        
        This clears all bars data. In practice, historical vs session bars
        are not distinguished in storage - the coordinator manages what's
        historical vs what's current session.
        """
        self._bars.clear()
        self._quality_metrics.clear()  # Quality tied to bars
        logger.debug("Historical bars cleared")
    
    def clear_session_bars(self) -> None:
        """Clear session bars but keep historical data.
        
        Called at end of session to prepare for next session.
        Since we reload all historical data each session, this currently
        clears everything for a clean slate.
        """
        # Clear all bars and quality metrics
        self._bars.clear()
        self._quality_metrics.clear()
        logger.debug("Session bars cleared")
    
    def set_session_active(self, active: bool) -> None:
        """Mark session as active or inactive.
        
        Args:
            active: True if session is active
        
        Note: This is a simple flag, could be expanded with more state.
        """
        # Could store as attribute if needed
        logger.debug(f"Session active: {active}")
    
    # =========================================================================
    # Debugging & Statistics
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about stored data (for debugging).
        
        Returns:
            Dictionary with statistics:
            - symbols: List of symbols
            - bar_counts: {symbol: {interval: count}}
            - historical_indicators: List of indicator names
            - quality_metrics: {symbol: {data_type: percentage}}
        """
        bar_counts = {}
        for symbol, intervals in self._bars.items():
            bar_counts[symbol] = {
                interval: len(bars)
                for interval, bars in intervals.items()
            }
        
        return {
            "symbols": list(self._bars.keys()),
            "bar_counts": bar_counts,
            "historical_indicators": list(self._historical_indicators.keys()),
            "realtime_indicators": {
                symbol: list(indicators.keys())
                for symbol, indicators in self._realtime_indicators.items()
            },
            "quality_metrics": dict(self._quality_metrics),
        }
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        stats = self.get_stats()
        return (
            f"SessionData("
            f"symbols={len(stats['symbols'])}, "
            f"historical_indicators={len(stats['historical_indicators'])}, "
            f"total_bars={sum(sum(counts.values()) for counts in stats['bar_counts'].values())}"
            f")"
        )
