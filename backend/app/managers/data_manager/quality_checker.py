"""Data Quality Checker with Caching.

This module provides a centralized, cached approach to checking 1-minute bar data quality.
All quality checks should use this module for consistency and performance.

Key Features:
- Caches expected minute counts for date ranges
- Uses trading calendar to accurately count trading minutes
- Accounts for holidays and early closes
- Assumes off-hours data is already filtered during import
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

from app.logger import logger
from app.repositories.trading_calendar_repository import TradingCalendarRepository


@dataclass
class QualityMetrics:
    """Data quality metrics for a symbol."""
    
    total_bars: int
    expected_minutes: int
    missing_minutes: int
    completeness_pct: float
    duplicate_count: int
    quality_score: float  # 0.0 to 1.0
    date_range_start: datetime
    date_range_end: datetime


class ExpectedMinutesCache:
    """Cache for expected trading minutes in date ranges."""
    
    def __init__(self):
        # Cache key: (start_date, end_date) -> expected_minutes
        self._cache: Dict[Tuple[date, date], int] = {}
    
    def get(self, start_date: date, end_date: date) -> Optional[int]:
        """Get cached expected minutes for date range."""
        key = (start_date, end_date)
        return self._cache.get(key)
    
    def set(self, start_date: date, end_date: date, minutes: int) -> None:
        """Cache expected minutes for date range."""
        key = (start_date, end_date)
        self._cache[key] = minutes
        logger.debug(f"Cached expected minutes for {start_date} to {end_date}: {minutes}")
    
    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()
        logger.debug("Expected minutes cache cleared")
    
    def size(self) -> int:
        """Get cache size."""
        return len(self._cache)


# Global cache instance
_expected_minutes_cache = ExpectedMinutesCache()


async def calculate_expected_trading_minutes(
    session: AsyncSession,
    start_date: date,
    end_date: date,
    use_cache: bool = True
) -> int:
    """Calculate expected trading minutes between two dates.
    
    This function:
    1. Checks cache first (if enabled)
    2. Queries trading calendar for each day in range
    3. Counts minutes for each trading day (accounting for early closes)
    4. Caches the result
    
    Args:
        session: Database session
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        use_cache: Whether to use/update cache
        
    Returns:
        Total expected trading minutes in the range
    """
    # Check cache first
    if use_cache:
        cached = _expected_minutes_cache.get(start_date, end_date)
        if cached is not None:
            logger.debug(f"Cache hit for {start_date} to {end_date}: {cached} minutes")
            return cached
    
    # Calculate expected minutes
    # Get TimeManager to query trading sessions from database
    from app.managers.system_manager import get_system_manager
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    total_minutes = 0
    current_date = start_date
    
    while current_date <= end_date:
        # Get trading session for this date (accounts for holidays and early closes)
        trading_session = time_mgr.get_trading_session(session, current_date)
        
        if not trading_session or trading_session.is_holiday:
            # Market closed this day
            current_date += timedelta(days=1)
            continue
        
        # Get market hours for this day (handles early closes automatically)
        open_dt = trading_session.get_regular_open_datetime()
        close_dt = trading_session.get_regular_close_datetime()
        
        if trading_session.early_close and trading_session.early_close_time:
            # Use early close time if applicable
            close_dt = datetime.combine(current_date, trading_session.early_close_time)
            close_dt = close_dt.replace(tzinfo=open_dt.tzinfo)
        
        # Calculate minutes for this day
        day_minutes = int((close_dt - open_dt).total_seconds() / 60)
        total_minutes += day_minutes
        
        current_date += timedelta(days=1)
    
    # Cache the result
    if use_cache:
        _expected_minutes_cache.set(start_date, end_date, total_minutes)
    
    logger.debug(f"Calculated expected minutes for {start_date} to {end_date}: {total_minutes}")
    return total_minutes


async def check_bar_quality(
    session: AsyncSession,
    symbol: str,
    bars: List,  # List of bar objects with timestamp attribute
    use_cache: bool = True
) -> QualityMetrics:
    """Check quality of 1-minute bar data for a symbol.
    
    This is the centralized quality check routine that should be used everywhere.
    
    Assumptions:
    - All bars are 1-minute bars
    - Bars are already filtered to regular trading hours (9:30-16:00 ET)
    - Off-hours data was removed during import
    
    Args:
        session: Database session
        symbol: Stock symbol
        bars: List of bar objects (must have .timestamp attribute)
        use_cache: Whether to use cached expected minute counts
        
    Returns:
        QualityMetrics object with all quality information
    """
    if not bars:
        return QualityMetrics(
            total_bars=0,
            expected_minutes=0,
            missing_minutes=0,
            completeness_pct=0.0,
            duplicate_count=0,
            quality_score=0.0,
            date_range_start=datetime.min,
            date_range_end=datetime.min
        )
    
    total_bars = len(bars)
    
    # Get date range
    timestamps = [b.timestamp for b in bars]
    date_range_start = min(timestamps)
    date_range_end = max(timestamps)
    
    start_date = date_range_start.date()
    end_date = date_range_end.date()
    
    # Check for duplicates
    unique_timestamps = set(timestamps)
    duplicate_count = total_bars - len(unique_timestamps)
    
    # Calculate expected minutes using cache
    expected_minutes = await calculate_expected_trading_minutes(
        session,
        start_date,
        end_date,
        use_cache=use_cache
    )
    
    # Calculate missing minutes
    missing_minutes = max(0, expected_minutes - total_bars)
    
    # Calculate completeness percentage
    if expected_minutes > 0:
        completeness_pct = (total_bars / expected_minutes) * 100.0
    else:
        completeness_pct = 100.0
    
    # Calculate quality score (0.0 to 1.0)
    # Factors: completeness (90% weight) + no duplicates (10% weight)
    completeness_score = min(1.0, total_bars / expected_minutes) if expected_minutes > 0 else 1.0
    duplicate_penalty = 0.1 if duplicate_count > 0 else 0.0
    quality_score = max(0.0, (completeness_score * 0.9) + ((1.0 - duplicate_penalty) * 0.1))
    
    metrics = QualityMetrics(
        total_bars=total_bars,
        expected_minutes=expected_minutes,
        missing_minutes=missing_minutes,
        completeness_pct=round(completeness_pct, 2),
        duplicate_count=duplicate_count,
        quality_score=round(quality_score, 3),
        date_range_start=date_range_start,
        date_range_end=date_range_end
    )
    
    # Log if quality is concerning
    if completeness_pct < 95.0:
        logger.warning(
            f"{symbol} data quality: {completeness_pct:.1f}% "
            f"({total_bars}/{expected_minutes} bars, {missing_minutes} missing)"
        )
    elif completeness_pct < 100.0:
        logger.info(
            f"{symbol} data quality: {completeness_pct:.1f}% "
            f"({total_bars}/{expected_minutes} bars, {missing_minutes} missing)"
        )
    
    return metrics


def calculate_session_quality(
    session_start: datetime,
    current_time: datetime,
    actual_bar_count: int
) -> float:
    """Calculate quality for an active session (used by upkeep thread).
    
    This is a simplified calculation for real-time quality monitoring during
    an active session. It assumes regular trading hours and doesn't account
    for holidays/early closes (those should be checked separately).
    
    Args:
        session_start: Session start time (e.g., 9:30 AM today)
        current_time: Current time
        actual_bar_count: Number of bars received so far
        
    Returns:
        Quality percentage (0.0 to 100.0)
    """
    if current_time <= session_start:
        return 100.0  # Session hasn't started yet
    
    # Calculate expected bars based on elapsed time
    elapsed_minutes = int((current_time - session_start).total_seconds() / 60)
    
    if elapsed_minutes == 0:
        return 100.0
    
    # Quality = (actual / expected) * 100
    quality_pct = (actual_bar_count / elapsed_minutes) * 100.0
    
    # Cap at 100%
    return min(100.0, quality_pct)


def get_cache_stats() -> Dict:
    """Get cache statistics for monitoring/debugging.
    
    Returns:
        Dictionary with cache statistics
    """
    return {
        "cache_size": _expected_minutes_cache.size(),
        "cache_enabled": True
    }


def clear_cache() -> None:
    """Clear the expected minutes cache.
    
    Useful for testing or when trading calendar is updated.
    """
    _expected_minutes_cache.clear()
