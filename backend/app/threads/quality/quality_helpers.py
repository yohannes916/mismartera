"""Shared Quality Calculation Helpers

This module provides common functions for calculating bar data quality,
used by both SessionCoordinator (historical bars) and DataQualityManager
(current session bars).

CRITICAL: All market hours come from TimeManager - NEVER hardcoded.
"""
from datetime import datetime, date
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from app.logger import logger


def parse_interval_to_minutes(
    interval: str,
    trading_session=None
) -> Optional[float]:
    """Parse interval string to minutes.
    
    CRITICAL: For 1d intervals, we MUST get actual trading hours from
    TimeManager via trading_session. Different days have different hours
    (regular: 390min, early close: varies, holiday: 0min).
    
    Args:
        interval: Interval string (e.g., "1s", "1m", "5m", "1d")
        trading_session: TradingSession object (required for 1d intervals)
    
    Returns:
        Number of minutes (can be fractional for seconds), or None if invalid
    """
    if isinstance(interval, int):
        # Already in minutes
        return float(interval)
    
    if not isinstance(interval, str):
        logger.warning(f"Invalid interval type: {type(interval)}")
        return None
    
    # Parse string intervals
    if interval.endswith("m"):
        # Minutes: 1m, 5m, 15m, etc.
        try:
            return float(interval[:-1])
        except ValueError:
            logger.warning(f"Cannot parse interval: {interval}")
            return None
    
    elif interval.endswith("s"):
        # Seconds: 1s, 5s, etc.
        # Convert to fractional minutes: 1s = 1/60 minute
        try:
            seconds = int(interval[:-1])
            return seconds / 60.0
        except ValueError:
            logger.warning(f"Cannot parse interval: {interval}")
            return None
    
    elif interval.endswith("h"):
        # Hours: 1h, 2h, etc.
        try:
            hours = int(interval[:-1])
            return float(hours * 60)
        except ValueError:
            logger.warning(f"Cannot parse interval: {interval}")
            return None
    
    elif interval.endswith("d"):
        # Daily bars: MUST get actual trading hours from TradingSession
        # NEVER hardcode (early closes vary, holidays are 0)
        if trading_session is None:
            logger.error(
                f"Cannot parse 1d interval without trading_session. "
                f"Must provide TradingSession to get actual trading hours."
            )
            return None
        
        if trading_session.is_holiday:
            logger.debug(f"Holiday on {trading_session.date}, 1d interval = 0 minutes")
            return 0.0
        
        # Get actual trading hours for this specific day
        open_dt = trading_session.get_regular_open_datetime()
        close_dt = trading_session.get_regular_close_datetime()
        
        if open_dt is None or close_dt is None:
            logger.warning(
                f"Cannot get trading hours for {trading_session.date}, "
                f"assuming 390 minutes as fallback"
            )
            return 390.0  # Fallback only
        
        # Calculate ACTUAL trading minutes for this day
        trading_minutes = (close_dt - open_dt).total_seconds() / 60
        
        logger.debug(
            f"1d interval for {trading_session.date}: {trading_minutes} minutes "
            f"(early_close={trading_session.is_early_close})"
        )
        
        return trading_minutes
    
    elif interval.endswith("w"):
        # Weekly bars: 5 trading days * 390 minutes/day
        try:
            weeks = int(interval[:-1])
            return float(weeks * 5 * 390)  # Approximate: 5 trading days per week
        except ValueError:
            logger.warning(f"Cannot parse interval: {interval}")
            return None
    
    else:
        # Unknown format - try to parse as plain number (assume minutes)
        try:
            return float(interval)
        except ValueError:
            logger.warning(f"Unknown interval format: {interval}, cannot parse")
            return None


def get_regular_trading_hours(
    time_manager,
    db_session,
    target_date: date
) -> Optional[Tuple[datetime, datetime]]:
    """Get regular market open and close times for a specific date.
    
    CRITICAL: Always query TimeManager - NEVER hardcode hours.
    Handles holidays, early closes, and any future market hour changes.
    
    Args:
        time_manager: TimeManager instance
        db_session: Database session for querying trading calendar
        target_date: Date to get hours for
    
    Returns:
        (open_datetime, close_datetime) tuple, or None if market closed/holiday
    """
    # Get trading session from TimeManager (single source of truth)
    trading_session = time_manager.get_trading_session(
        db_session,
        target_date
    )
    
    if trading_session is None:
        logger.debug(f"No trading session found for {target_date}")
        return None
    
    if trading_session.is_holiday:
        logger.debug(f"Market closed (holiday) on {target_date}: {trading_session.holiday_name}")
        return None
    
    # Get regular market hours (not pre/post market)
    open_dt = trading_session.get_regular_open_datetime()
    close_dt = trading_session.get_regular_close_datetime()
    
    if open_dt is None or close_dt is None:
        logger.warning(f"Missing regular hours for {target_date}")
        return None
    
    if trading_session.is_early_close:
        logger.debug(
            f"Early close on {target_date}: "
            f"{open_dt.strftime('%H:%M')} - {close_dt.strftime('%H:%M')}"
        )
    
    return (open_dt, close_dt)


def calculate_expected_bars(
    start_time: datetime,
    end_time: datetime,
    interval_minutes: float
) -> int:
    """Calculate expected number of bars for a time range.
    
    Args:
        start_time: Start of range
        end_time: End of range (current time for live, close time for historical)
        interval_minutes: Bar interval in minutes (can be fractional for seconds)
    
    Returns:
        Expected number of bars
    """
    if interval_minutes <= 0:
        logger.warning(f"Invalid interval_minutes: {interval_minutes}")
        return 0
    
    elapsed_seconds = (end_time - start_time).total_seconds()
    
    if elapsed_seconds <= 0:
        return 0
    
    # For minute intervals, count complete intervals
    if interval_minutes >= 1.0:
        elapsed_minutes = elapsed_seconds / 60
        expected = int(elapsed_minutes / interval_minutes)
    else:
        # For sub-minute intervals (seconds), count more precisely
        interval_seconds = interval_minutes * 60
        expected = int(elapsed_seconds / interval_seconds)
    
    return expected


def calculate_quality_percentage(
    actual_bars: int,
    expected_bars: int
) -> float:
    """Calculate quality percentage.
    
    Args:
        actual_bars: Number of bars actually present
        expected_bars: Number of bars expected
    
    Returns:
        Quality percentage (0-100), capped at 100
    """
    if expected_bars <= 0:
        # No bars expected yet (e.g., before market open)
        return 100.0
    
    quality = (actual_bars / expected_bars) * 100.0
    
    # Cap at 100% (can happen if we receive bars slightly ahead)
    return min(100.0, quality)


def calculate_quality_for_current_session(
    time_manager,
    db_session,
    symbol: str,
    interval: str,
    current_time: datetime,
    actual_bars: int
) -> Optional[float]:
    """Calculate quality for current trading session (in progress).
    
    Used by DataQualityManager during live/backtest streaming.
    
    Quality = (actual_bars / expected_bars_so_far) * 100
    
    CRITICAL Rules:
    - Uses current_time as end point (not market close)
    - Only counts regular trading hours
    - Caps at market close if current_time is after close
    - Gets all hours from TimeManager
    
    Args:
        time_manager: TimeManager instance
        db_session: Database session
        symbol: Stock symbol
        interval: Bar interval (e.g., "1m", "5m", "1d")
        current_time: Current time (from TimeManager)
        actual_bars: Number of bars actually received
    
    Returns:
        Quality percentage (0-100), or None if cannot calculate
    """
    current_date = current_time.date()
    
    # Get trading hours from TimeManager
    hours = get_regular_trading_hours(time_manager, db_session, current_date)
    if hours is None:
        logger.debug(
            f"Cannot calculate quality for {symbol} on {current_date} - "
            f"market closed or no trading hours"
        )
        return None
    
    session_open, session_close = hours
    
    # Ensure current_time is timezone-aware for comparison
    if current_time.tzinfo is None:
        # Assume same timezone as trading session
        current_time = current_time.replace(tzinfo=session_open.tzinfo)
    
    # Cap end time at market close (don't count after-hours)
    effective_end_time = min(current_time, session_close)
    
    # If before market open, no bars expected yet
    if effective_end_time <= session_open:
        return 100.0
    
    # Parse interval to minutes
    trading_session = time_manager.get_trading_session(db_session, current_date)
    interval_minutes = parse_interval_to_minutes(interval, trading_session)
    
    if interval_minutes is None:
        logger.warning(f"Cannot parse interval '{interval}' for {symbol}")
        return None
    
    # Calculate expected bars from open to effective_end_time
    expected = calculate_expected_bars(
        session_open,
        effective_end_time,
        interval_minutes
    )
    
    # Calculate quality
    quality = calculate_quality_percentage(actual_bars, expected)
    
    return quality


def calculate_quality_for_historical_date(
    time_manager,
    db_session,
    symbol: str,
    interval: str,
    target_date: date,
    actual_bars: int
) -> Optional[float]:
    """Calculate quality for a complete historical trading day.
    
    Used by SessionCoordinator for historical bar quality.
    
    Quality = (actual_bars / expected_bars_full_day) * 100
    
    CRITICAL Rules:
    - Uses full trading day (open to close)
    - Only counts regular trading hours
    - Gets all hours from TimeManager
    - Handles early closes and holidays
    
    Args:
        time_manager: TimeManager instance
        db_session: Database session
        symbol: Stock symbol
        interval: Bar interval (e.g., "1m", "5m", "1d")
        target_date: Historical date to check
        actual_bars: Number of bars for this date
    
    Returns:
        Quality percentage (0-100), or None if cannot calculate
    """
    # Get trading hours from TimeManager
    hours = get_regular_trading_hours(time_manager, db_session, target_date)
    if hours is None:
        logger.debug(
            f"Cannot calculate quality for {symbol} on {target_date} - "
            f"market closed or no trading hours"
        )
        return None
    
    session_open, session_close = hours
    
    # Parse interval to minutes
    trading_session = time_manager.get_trading_session(db_session, target_date)
    interval_minutes = parse_interval_to_minutes(interval, trading_session)
    
    if interval_minutes is None:
        logger.warning(f"Cannot parse interval '{interval}' for {symbol}")
        return None
    
    # Calculate expected bars for FULL trading day
    expected = calculate_expected_bars(
        session_open,
        session_close,
        interval_minutes
    )
    
    # Calculate quality
    quality = calculate_quality_percentage(actual_bars, expected)
    
    return quality
