"""Unified Data Quality Analyzer

Analyzes market data quality for any bar type (1s, Ns, 1m, Nm, 1d, Nd, 1w, Nw).
Single source of truth for quality metrics across CLI, threads, and managers.
"""
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
import pandas as pd

from app.threads.quality.requirement_analyzer import parse_interval, IntervalType
from app.logger import logger


def analyze_quality(
    bars_df: pd.DataFrame,
    interval: str,
    symbol: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    time_manager=None,
    exchange: str = 'NYSE'
) -> Dict[str, Any]:
    """Unified quality analysis for any bar type.
    
    Performs comprehensive quality checks:
    - Gap detection (missing bars)
    - Duplicate detection
    - Continuity validation
    - Expected vs actual bar count
    - Quality score calculation
    
    Args:
        bars_df: DataFrame with bars (must have 'timestamp' column)
        interval: Interval string (e.g., "1s", "5m", "1d", "1w")
        symbol: Stock symbol (for logging)
        start_date: Optional analysis start date. If None, uses earliest bar.
        end_date: Optional analysis end date. If None, uses latest bar.
        time_manager: TimeManager instance (CRITICAL - provides trading calendar)
        exchange: Exchange name (e.g., 'NYSE', 'NASDAQ', 'TSE'). Default 'NYSE'.
    
    Returns:
        {
            "success": bool,
            "symbol": str,
            "interval": str,
            "total_bars": int,
            "expected_bars": int,
            "missing_bars": int,
            "duplicate_bars": int,
            "quality_score": float,  # 0.0 to 1.0
            "date_range": {
                "start": str,
                "end": str
            },
            "gaps": [
                {
                    "start": str,  # Gap start timestamp
                    "end": str,    # Gap end timestamp  
                    "missing_count": int
                }
            ],
            "message": str
        }
    
    Quality Score Calculation:
        score = (actual_bars - duplicates) / expected_bars
        Capped at 1.0 (can't exceed 100%)
    
    Examples:
        >>> df = pd.read_parquet("data/1m/AAPL/...")
        >>> result = analyze_quality(df, "1m", "AAPL")
        >>> print(f"Quality: {result['quality_score']*100:.1f}%")
    """
    if bars_df.empty:
        return {
            "success": False,
            "symbol": symbol,
            "interval": interval,
            "total_bars": 0,
            "expected_bars": 0,
            "missing_bars": 0,
            "duplicate_bars": 0,
            "quality_score": 0.0,
            "date_range": None,
            "gaps": [],
            "message": "No data available"
        }
    
    # Parse interval info
    try:
        interval_info = parse_interval(interval)
    except ValueError as e:
        return {
            "success": False,
            "symbol": symbol,
            "interval": interval,
            "total_bars": len(bars_df),
            "expected_bars": 0,
            "missing_bars": 0,
            "duplicate_bars": 0,
            "quality_score": 0.0,
            "date_range": None,
            "gaps": [],
            "message": f"Invalid interval: {e}"
        }
    
    # Get date range
    first_bar = bars_df['timestamp'].min()
    last_bar = bars_df['timestamp'].max()
    
    if start_date:
        analysis_start = datetime.combine(start_date, datetime.min.time())
    else:
        analysis_start = first_bar
    
    if end_date:
        analysis_end = datetime.combine(end_date, datetime.max.time())
    else:
        analysis_end = last_bar
    
    # Filter to analysis window
    mask = (bars_df['timestamp'] >= analysis_start) & (bars_df['timestamp'] <= analysis_end)
    window_df = bars_df[mask].copy()
    
    if window_df.empty:
        return {
            "success": False,
            "symbol": symbol,
            "interval": interval,
            "total_bars": 0,
            "expected_bars": 0,
            "missing_bars": 0,
            "duplicate_bars": 0,
            "quality_score": 0.0,
            "date_range": None,
            "gaps": [],
            "message": f"No bars in window {analysis_start} to {analysis_end}"
        }
    
    actual_first = window_df['timestamp'].min()
    actual_last = window_df['timestamp'].max()
    
    # Filter to only regular trading hours for quality calculation
    filtered_df = _filter_to_regular_hours(window_df, time_manager, exchange)
    total_bars = len(filtered_df)
    
    # Check for duplicates (only in regular hours)
    duplicate_bars = filtered_df['timestamp'].duplicated().sum()
    
    # Calculate expected bars and gaps
    if interval_info.type in [IntervalType.SECOND, IntervalType.MINUTE]:
        # Intraday intervals: use trading calendar for accurate calculation
        expected_bars, gaps = _analyze_intraday_quality(
            filtered_df,  # Use filtered data (regular hours only)
            interval_info.seconds,
            actual_first,
            actual_last,
            time_manager,  # TimeManager provides trading calendar
            exchange       # Exchange-specific hours/holidays/weekends
        )
    elif interval_info.type == IntervalType.DAY:
        # Daily intervals: check trading days
        expected_bars, gaps = _analyze_daily_quality(
            filtered_df,  # Use filtered data
            interval_info.value,  # e.g., 1 for "1d", 5 for "5d"
            actual_first,
            actual_last,
            time_manager,
            exchange
        )
    elif interval_info.type == IntervalType.WEEK:
        # Weekly intervals: check trading weeks
        expected_bars, gaps = _analyze_weekly_quality(
            filtered_df,  # Use filtered data
            interval_info.value,  # e.g., 1 for "1w", 2 for "2w"
            actual_first,
            actual_last,
            time_manager,
            exchange
        )
    else:
        # Unknown type
        expected_bars = total_bars
        gaps = []
    
    # Calculate quality score
    # score = (actual_unique_bars) / expected_bars
    unique_bars = total_bars - duplicate_bars
    if expected_bars > 0:
        quality_score = min(1.0, unique_bars / expected_bars)
    else:
        quality_score = 1.0 if total_bars > 0 else 0.0
    
    # Calculate missing vs surplus
    missing_bars = expected_bars - unique_bars
    if missing_bars < 0:
        # We have more bars than expected (surplus)
        surplus_bars = abs(missing_bars)
        missing_bars = 0
    else:
        surplus_bars = 0
    
    # Build message
    if quality_score >= 0.99:
        if surplus_bars > 0:
            message = f"Excellent quality ({surplus_bars} extra bars, likely extended hours)"
        else:
            message = "Excellent quality"
    elif quality_score >= 0.95:
        message = "Good quality with minor gaps"
    elif quality_score >= 0.85:
        message = "Acceptable quality with some gaps"
    elif quality_score >= 0.70:
        message = "Fair quality with significant gaps"
    else:
        message = "Poor quality with major gaps"
    
    return {
        "success": True,
        "symbol": symbol,
        "interval": interval,
        "total_bars": int(total_bars),
        "expected_bars": int(expected_bars),
        "missing_bars": int(missing_bars),
        "surplus_bars": int(surplus_bars),
        "duplicate_bars": int(duplicate_bars),
        "quality_score": float(quality_score),
        "date_range": {
            "start": actual_first.strftime('%Y-%m-%d %H:%M:%S'),
            "end": actual_last.strftime('%Y-%m-%d %H:%M:%S')
        },
        "gaps": gaps[:10],  # Limit to first 10 gaps for output
        "message": message
    }


def _filter_to_regular_hours(
    df: pd.DataFrame,
    time_manager,
    exchange: str = 'NYSE'
) -> pd.DataFrame:
    """Filter bars to only those within regular trading hours.
    
    Removes pre-market and post-market bars to ensure quality calculation
    only considers regular session (9:30-16:00 ET, or early close time).
    
    Args:
        df: DataFrame with bars
        time_manager: TimeManager instance
        exchange: Exchange name
        
    Returns:
        Filtered DataFrame with only regular hours bars
    """
    from app.models.database import SessionLocal
    
    if df.empty or time_manager is None:
        return df
    
    try:
        with SessionLocal() as session:
            # Group bars by date
            df['date'] = df['timestamp'].dt.date
            filtered_rows = []
            
            for date, group in df.groupby('date'):
                # Get trading session for this date
                trading_session = time_manager.get_trading_session(session, date, exchange)
                
                if not trading_session or not trading_session.is_trading_day:
                    # Skip non-trading days
                    continue
                
                # Get regular hours for this date (handles early closes)
                regular_open = trading_session.regular_open
                regular_close = trading_session.regular_close
                
                if not regular_open or not regular_close:
                    continue
                
                # Build regular hours window
                # TimeManager provides times in exchange timezone, data is also in exchange timezone
                # Make timezone-aware using session's timezone
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(trading_session.timezone)
                open_dt = datetime.combine(date, regular_open).replace(tzinfo=tz)
                close_dt = datetime.combine(date, regular_close).replace(tzinfo=tz)
                
                # Filter bars within regular hours
                # Bar timestamps are at the END of the bar period:
                # - Bar at 09:30 covers [09:25-09:30), which is pre-market
                # - Bar at 09:35 covers [09:30-09:35), which is first regular bar
                # - Bar at 16:00 covers [15:55-16:00), which is last regular bar
                # Therefore: timestamp > open_dt (exclude bar AT open) and <= close_dt (include bar AT close)
                mask = (group['timestamp'] > open_dt) & (group['timestamp'] <= close_dt)
                filtered_rows.append(group[mask])
            
            if filtered_rows:
                result = pd.concat(filtered_rows, ignore_index=True)
                result = result.drop('date', axis=1)
                return result
            else:
                return pd.DataFrame(columns=df.columns)
                
    except Exception as e:
        logger.error(f"Failed to filter to regular hours: {e}", exc_info=True)
        # Fallback: return all bars
        return df


def _analyze_intraday_quality(
    df: pd.DataFrame,
    interval_seconds: int,
    start: datetime,
    end: datetime,
    time_manager=None,
    exchange: str = 'NYSE'
) -> Tuple[int, List[Dict]]:
    """Analyze intraday data quality using trading calendar.
    
    Uses TimeManager as SINGLE SOURCE OF TRUTH for:
    - Trading hours (varies by exchange and day)
    - Holidays (market closed)
    - Early closes (half-days, varies by date)
    - Weekends (varies by exchange - not all exchanges close Sat/Sun)
    
    NO HARDCODED TIMES - everything from TimeManager.
    """
    from app.models.database import SessionLocal
    
    # Fallback: 24/7 continuous if no TimeManager
    if time_manager is None:
        logger.warning("TimeManager not available, using 24/7 calculation (inaccurate)")
        total_seconds = (end - start).total_seconds()
        expected = int(total_seconds // interval_seconds) + 1
        gaps = []
        return expected, gaps
    
    # Use TimeManager's unified API to count trading time
    try:
        with SessionLocal() as session:
            # Use unified TimeManager API - handles all complexity internally
            total_trading_seconds = time_manager.count_trading_time(
                session,
                start,
                end,
                unit='seconds',
                exchange=exchange
            )
            
            # Calculate expected bars from trading seconds
            expected_bars = total_trading_seconds // interval_seconds
            
            # Find gaps using trading calendar
            gaps = _find_gaps_with_calendar(
                df,
                interval_seconds,
                time_manager,
                session,
                start,
                end,
                exchange
            )
            
            return expected_bars, gaps
            
    except Exception as e:
        logger.error(f"Failed to use TimeManager for quality analysis: {e}", exc_info=True)
        # Fallback to simple calculation
        total_seconds = (end - start).total_seconds()
        expected = int(total_seconds // interval_seconds) + 1
        return expected, []


def _find_gaps_with_calendar(
    df: pd.DataFrame,
    interval_seconds: int,
    time_manager,
    session,
    start: datetime,
    end: datetime,
    exchange: str = 'NYSE'
) -> List[Dict]:
    """Find gaps in intraday data accounting for market closures.
    
    Only reports gaps WITHIN trading hours from TimeManager.
    Skips gaps during:
    - Holidays (from TimeManager)
    - Non-trading days (weekends vary by exchange - from TimeManager)
    - After-hours (hours vary by exchange and date - from TimeManager)
    - Between trading days
    
    NO HARDCODED ASSUMPTIONS about trading hours or weekends.
    """
    gaps = []
    
    if df.empty:
        return gaps
    
    df_sorted = df.sort_values('timestamp').reset_index(drop=True)
    delta = pd.Timedelta(seconds=interval_seconds)
    
    for i in range(1, len(df_sorted)):
        prev_ts = df_sorted.loc[i-1, 'timestamp']
        curr_ts = df_sorted.loc[i, 'timestamp']
        expected_ts = prev_ts + delta
        
        if curr_ts > expected_ts:
            # Potential gap - verify it's within same trading day
            gap_start = expected_ts
            gap_end = curr_ts
            
            # Skip gaps that span different dates (cross market close/open)
            if gap_start.date() != prev_ts.date():
                # Gap crosses into different day - not a real gap
                continue
            
            gap_start_date = gap_start.date()
            
            # Query TimeManager: is this date a trading day?
            trading_session = time_manager.get_trading_session(
                session,
                gap_start_date,
                exchange=exchange
            )
            
            # Skip gaps on non-trading days (weekends, holidays, etc.)
            if not trading_session or not trading_session.is_trading_day or trading_session.is_holiday:
                continue
            
            # Get trading hours from TimeManager (NO hardcoded times)
            regular_open = trading_session.regular_open
            regular_close = trading_session.regular_close
            
            if not regular_open or not regular_close:
                continue
            
            # Build trading window from TimeManager data
            # TimeManager provides times in exchange timezone
            # Make timezone-aware to match data
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(trading_session.timezone)
            session_open = datetime.combine(gap_start_date, regular_open).replace(tzinfo=tz)
            session_close = datetime.combine(gap_start_date, regular_close).replace(tzinfo=tz)
            
            # Only report gap if it starts WITHIN trading hours
            if gap_start >= session_open and gap_start < session_close:
                # Calculate missing bars within trading hours
                effective_gap_end = min(gap_end, session_close)
                gap_duration = (effective_gap_end - gap_start).total_seconds()
                missing_count = int(gap_duration // interval_seconds)
                
                if missing_count > 0:
                    gaps.append({
                        "start": str(gap_start),
                        "end": str(effective_gap_end),
                        "missing_count": missing_count
                    })
    
    return gaps


def _analyze_daily_quality(
    df: pd.DataFrame,
    interval_days: int,
    start: datetime,
    end: datetime,
    time_manager,
    exchange: str = 'NYSE'
) -> Tuple[int, List[Dict]]:
    """Analyze daily data quality using trading calendar."""
    from app.models.database import SessionLocal
    
    if time_manager is None:
        # Fallback: calendar days
        total_days = (end.date() - start.date()).days + 1
        expected = total_days // interval_days
        return expected, []
    
    # Use unified TimeManager API to count trading days
    try:
        with SessionLocal() as session:
            trading_days = time_manager.count_trading_time(
                session,
                start,
                end,
                unit='days',
                exchange=exchange
            )
            expected = trading_days // interval_days
            
            # Gap detection for daily data would require checking each trading day
            # Simplified for now
            gaps = []
            
            return expected, gaps
    except Exception as e:
        logger.warning(f"Failed to use TimeManager for quality analysis: {e}")
        # Fallback
        total_days = (end.date() - start.date()).days + 1
        expected = total_days // interval_days
        return expected, []


def _analyze_weekly_quality(
    df: pd.DataFrame,
    interval_weeks: int,
    start: datetime,
    end: datetime,
    time_manager,
    exchange: str = 'NYSE'
) -> Tuple[int, List[Dict]]:
    """Analyze weekly data quality using trading calendar."""
    from app.models.database import SessionLocal
    
    if time_manager is None:
        # Fallback: approximate using calendar weeks
        total_days = (end.date() - start.date()).days
        total_weeks = total_days // 7
        expected = total_weeks // interval_weeks
        return expected, []
    
    # Use unified TimeManager API to count trading weeks
    try:
        with SessionLocal() as session:
            trading_weeks = time_manager.count_trading_time(
                session,
                start,
                end,
                unit='weeks',
                exchange=exchange
            )
            expected = trading_weeks // interval_weeks
            
            # Simplified - no gap detection for weekly yet
            gaps = []
            
            return expected, gaps
    except Exception as e:
        logger.error(f"Failed to count trading weeks: {e}", exc_info=True)
        # Fallback
        total_days = (end.date() - start.date()).days
        total_weeks = total_days // 7
        expected = total_weeks // interval_weeks
        return expected, []
