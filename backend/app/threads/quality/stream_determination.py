"""Stream Determination and Historical Data Generation Logic

Determines:
1. Which interval to stream for current day (backtest & live)
2. Which historical intervals to load vs generate
3. Gap filling eligibility using higher-quality lower intervals

Architecture:
- Unified logic for backtest and live modes
- Stream ONLY smallest available base interval (1s > 1m > 1d)
- Generate ALL derived intervals on-the-fly
- Quote handling differs by mode (stream in live, generate in backtest)
- Require 100% complete data for derived bar generation
"""

from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
from enum import Enum
from datetime import date, datetime
import re

from app.logger import logger


# =============================================================================
# Enumerations
# =============================================================================

class IntervalType(Enum):
    """Interval type classification."""
    SECOND = "second"      # 1s, 5s, 10s, etc.
    MINUTE = "minute"      # 1m, 5m, 15m, etc.
    HOUR = "hour"          # 1h, 4h, etc.
    DAY = "day"            # 1d, 5d, etc.
    QUOTE = "quote"        # quotes
    TICK = "tick"          # ticks


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class IntervalInfo:
    """Information about a bar interval."""
    interval: str
    type: IntervalType
    seconds: int           # Duration in seconds
    can_be_stored: bool    # True if DB supports this interval (quotes, 1s, 1m, 1d)
    base_interval: Optional[str]  # Smallest interval this can be derived from


@dataclass
class StreamDecision:
    """Decision about what to stream for current day."""
    symbol: str
    stream_interval: Optional[str]      # Base interval to stream (None if error)
    stream_quotes: bool                 # Whether to stream quotes (live only)
    generate_intervals: List[str]       # Bar intervals to generate
    generate_quotes: bool               # Whether to generate quotes (backtest only)
    error: Optional[str] = None         # Error message if decision failed


@dataclass
class HistoricalDecision:
    """Decision about historical data loading."""
    symbol: str
    requested_interval: str
    load_from_db: Optional[str]          # Interval to load from DB (None if generate)
    generate_from: Optional[str]         # Source interval for generation
    needs_gap_fill: bool                 # Whether gap filling might be needed
    error: Optional[str] = None          # Error message if decision failed


@dataclass
class AvailabilityInfo:
    """Database interval availability for a symbol."""
    symbol: str
    has_1s: bool
    has_1m: bool
    has_1d: bool
    has_quotes: bool


# =============================================================================
# Interval Parsing
# =============================================================================

def parse_interval(interval: str) -> IntervalInfo:
    """Parse interval string into structured info.
    
    Args:
        interval: Interval string (e.g., "1s", "5m", "1d", "quotes", "ticks")
    
    Returns:
        IntervalInfo with type, seconds, and DB storage capability
    
    Raises:
        ValueError: If interval format is invalid
    """
    # Special cases
    if interval == "quotes":
        return IntervalInfo(
            interval="quotes",
            type=IntervalType.QUOTE,
            seconds=0,  # N/A
            can_be_stored=True,  # DB supports quotes
            base_interval=None
        )
    
    if interval == "ticks":
        return IntervalInfo(
            interval="ticks",
            type=IntervalType.TICK,
            seconds=0,  # N/A
            can_be_stored=False,  # DB does NOT support ticks
            base_interval=None
        )
    
    # Parse bar intervals (1s, 5m, 1d, etc.)
    match = re.match(r'^(\d+)([smhd])$', interval)
    if not match:
        raise ValueError(f"Invalid interval format: {interval}")
    
    number = int(match.group(1))
    unit = match.group(2)
    
    # Determine type and seconds
    if unit == 's':
        interval_type = IntervalType.SECOND
        seconds = number
    elif unit == 'm':
        interval_type = IntervalType.MINUTE
        seconds = number * 60
    elif unit == 'h':
        interval_type = IntervalType.HOUR
        seconds = number * 3600
    elif unit == 'd':
        interval_type = IntervalType.DAY
        seconds = number * 86400
    else:
        raise ValueError(f"Unknown unit: {unit}")
    
    # Database storage capability (ONLY quotes, 1s, 1m, 1d)
    can_be_stored = interval in ["1s", "1m", "1d"]
    
    # Determine base interval for generation
    base_interval = _determine_base_interval(interval, interval_type)
    
    return IntervalInfo(
        interval=interval,
        type=interval_type,
        seconds=seconds,
        can_be_stored=can_be_stored,
        base_interval=base_interval
    )


def _determine_base_interval(interval: str, interval_type: IntervalType) -> Optional[str]:
    """Determine the smallest base interval this can be derived from.
    
    Rules:
    - Sub-minute (5s, 10s) → ONLY from 1s
    - Minute (5m, 15m) → Prefer 1m, fallback 1s
    - Day (5d, etc.) → Prefer 1d, fallback 1m, fallback 1s
    
    Args:
        interval: Interval string
        interval_type: Type of interval
    
    Returns:
        Base interval string or None if it's already a base
    """
    # Base intervals have no source
    if interval in ["1s", "1m", "1d"]:
        return None
    
    # Sub-minute: ONLY from 1s
    if interval_type == IntervalType.SECOND:
        return "1s"
    
    # Minute: prefer 1m
    if interval_type == IntervalType.MINUTE:
        return "1m"  # Note: will fallback to 1s if 1m not available
    
    # Hour: prefer 1m
    if interval_type == IntervalType.HOUR:
        return "1m"  # Note: will fallback to 1s if 1m not available
    
    # Day: prefer 1d
    if interval_type == IntervalType.DAY:
        return "1d"  # Note: will fallback to 1m, then 1s if not available
    
    return None


# =============================================================================
# Database Availability Checking
# =============================================================================

def check_db_availability(
    session,
    symbol: str,
    date_range: Tuple[date, date]
) -> AvailabilityInfo:
    """Check which base intervals exist in Parquet storage for symbol/date range.
    
    **PARQUET ONLY**: Market data is stored exclusively in Parquet files.
    The 'session' parameter is kept for API compatibility but not used.
    
    Checks Parquet storage for:
    - 1s bars (stored as "tick" interval)
    - 1m bars
    - 1d bars
    - quotes
    
    Args:
        session: Database session (unused - kept for API compatibility)
        symbol: Symbol to check
        date_range: (start_date, end_date) tuple
    
    Returns:
        AvailabilityInfo with boolean flags for each interval
    """
    from app.managers.data_manager.parquet_storage import parquet_storage
    
    start_date, end_date = date_range
    logger.debug(f"Checking Parquet availability for {symbol} in range {start_date} to {end_date}")
    
    # Initialize availability flags
    has_1s = False
    has_1m = False
    has_1d = False
    has_quotes = False
    
    try:
        # Check 1s bars
        symbols_1s = parquet_storage.get_available_symbols('1s')
        if symbol in symbols_1s:
            # Verify data exists in date range
            start_1s, end_1s = parquet_storage.get_date_range('1s', symbol)
            if start_1s and end_1s:
                # Check if date range overlaps with requested range
                has_1s = (start_1s.date() <= end_date and end_1s.date() >= start_date)
    except Exception as e:
        logger.debug(f"1s Parquet check failed: {e}")
    
    try:
        # Check 1m bars
        symbols_1m = parquet_storage.get_available_symbols('1m')
        if symbol in symbols_1m:
            start_1m, end_1m = parquet_storage.get_date_range('1m', symbol)
            if start_1m and end_1m:
                has_1m = (start_1m.date() <= end_date and end_1m.date() >= start_date)
    except Exception as e:
        logger.debug(f"1m Parquet check failed: {e}")
    
    try:
        # Check 1d bars
        symbols_1d = parquet_storage.get_available_symbols('1d')
        if symbol in symbols_1d:
            start_1d, end_1d = parquet_storage.get_date_range('1d', symbol)
            if start_1d and end_1d:
                has_1d = (start_1d.date() <= end_date and end_1d.date() >= start_date)
    except Exception as e:
        logger.debug(f"1d Parquet check failed: {e}")
    
    try:
        # Check quotes
        symbols_quotes = parquet_storage.get_available_symbols('quotes')
        if symbol in symbols_quotes:
            start_q, end_q = parquet_storage.get_date_range('quotes', symbol)
            if start_q and end_q:
                has_quotes = (start_q.date() <= end_date and end_q.date() >= start_date)
    except Exception as e:
        logger.debug(f"Quotes Parquet check failed: {e}")
    
    availability = AvailabilityInfo(
        symbol=symbol,
        has_1s=has_1s,
        has_1m=has_1m,
        has_1d=has_1d,
        has_quotes=has_quotes
    )
    
    logger.debug(
        f"{symbol} Parquet availability: 1s={has_1s}, 1m={has_1m}, 1d={has_1d}, quotes={has_quotes}"
    )
    
    return availability


# =============================================================================
# Current Day Stream Determination
# =============================================================================

def determine_stream_interval(
    symbol: str,
    requested_intervals: List[str],
    availability: AvailabilityInfo,
    mode: str = "backtest"
) -> StreamDecision:
    """Determine which single interval to stream for current day.
    
    Rules:
    1. Find smallest available base interval (1s > 1m > 1d)
    2. Stream ONLY that interval
    3. Generate all others
    4. Ignore quotes and ticks for base interval selection
    5. Handle quotes based on mode:
       - Live: stream if requested
       - Backtest: generate if requested
    6. Error if no base interval available
    
    Args:
        symbol: Symbol to stream
        requested_intervals: List of requested intervals from config
        availability: Database availability info
        mode: "live" or "backtest"
    
    Returns:
        StreamDecision with stream/generate marking
    """
    logger.debug(
        f"Determining stream interval for {symbol}: "
        f"requested={requested_intervals}, mode={mode}, "
        f"availability=(1s={availability.has_1s}, 1m={availability.has_1m}, 1d={availability.has_1d})"
    )
    
    # Separate bar intervals from quotes/ticks
    bar_intervals = []
    has_quotes = "quotes" in requested_intervals
    has_ticks = "ticks" in requested_intervals
    
    for interval in requested_intervals:
        if interval not in ["quotes", "ticks"]:
            bar_intervals.append(interval)
    
    # Find smallest available base interval
    # Priority: 1s > 1m > 1d
    stream_interval = None
    
    if availability.has_1s:
        stream_interval = "1s"
    elif availability.has_1m:
        stream_interval = "1m"
    elif availability.has_1d:
        stream_interval = "1d"
    
    # Error if no base interval available
    if stream_interval is None:
        error_msg = (
            f"No base interval (1s, 1m, 1d) available in database for {symbol}. "
            f"Cannot stream or generate requested intervals: {requested_intervals}"
        )
        logger.error(error_msg)
        return StreamDecision(
            symbol=symbol,
            stream_interval=None,
            stream_quotes=False,
            generate_intervals=[],
            generate_quotes=False,
            error=error_msg
        )
    
    # All bar intervals except stream_interval are generated
    generate_intervals = [
        interval for interval in bar_intervals
        if interval != stream_interval
    ]
    
    # Handle quotes based on mode
    if mode == "live":
        stream_quotes = has_quotes
        generate_quotes = False
    else:  # backtest
        stream_quotes = False
        generate_quotes = has_quotes
    
    # Log ticks warning if requested
    if has_ticks:
        logger.warning(f"{symbol}: ticks requested but IGNORED (not supported)")
    
    decision = StreamDecision(
        symbol=symbol,
        stream_interval=stream_interval,
        stream_quotes=stream_quotes,
        generate_intervals=generate_intervals,
        generate_quotes=generate_quotes,
        error=None
    )
    
    logger.info(
        f"{symbol} stream decision: stream={stream_interval}, "
        f"generate={generate_intervals}, quotes=(stream={stream_quotes}, gen={generate_quotes})"
    )
    
    return decision


# =============================================================================
# Historical Data Loading Determination
# =============================================================================

def determine_historical_loading(
    symbol: str,
    requested_interval: str,
    availability: AvailabilityInfo
) -> HistoricalDecision:
    """Determine how to obtain historical data for an interval.
    
    Rules:
    1. If DB supports interval and has it, load from DB
    2. Otherwise, find best source interval to generate from
    3. Sub-minute (5s): only from 1s
    4. Minute (5m, 15m): prefer 1m, fallback to 1s
    5. Day (5d): prefer 1d, fallback to 1m, fallback to 1s
    
    Args:
        symbol: Symbol to load
        requested_interval: Interval requested
        availability: Database availability info
    
    Returns:
        HistoricalDecision with loading strategy
    """
    logger.debug(
        f"Determining historical loading for {symbol} {requested_interval}"
    )
    
    # Parse interval
    try:
        info = parse_interval(requested_interval)
    except ValueError as e:
        error_msg = f"Invalid interval {requested_interval}: {e}"
        logger.error(error_msg)
        return HistoricalDecision(
            symbol=symbol,
            requested_interval=requested_interval,
            load_from_db=None,
            generate_from=None,
            needs_gap_fill=False,
            error=error_msg
        )
    
    # If interval can be stored and is available, load from DB
    if info.can_be_stored:
        if requested_interval == "1s" and availability.has_1s:
            return HistoricalDecision(
                symbol=symbol,
                requested_interval=requested_interval,
                load_from_db="1s",
                generate_from=None,
                needs_gap_fill=False
            )
        elif requested_interval == "1m" and availability.has_1m:
            return HistoricalDecision(
                symbol=symbol,
                requested_interval=requested_interval,
                load_from_db="1m",
                generate_from=None,
                needs_gap_fill=False
            )
        elif requested_interval == "1d" and availability.has_1d:
            return HistoricalDecision(
                symbol=symbol,
                requested_interval=requested_interval,
                load_from_db="1d",
                generate_from=None,
                needs_gap_fill=False
            )
    
    # Otherwise, need to generate - find source interval
    source_priority = get_generation_source_priority(requested_interval)
    
    # Find first available source
    source_interval = None
    for candidate in source_priority:
        if candidate == "1s" and availability.has_1s:
            source_interval = "1s"
            break
        elif candidate == "1m" and availability.has_1m:
            source_interval = "1m"
            break
        elif candidate == "1d" and availability.has_1d:
            source_interval = "1d"
            break
    
    # Error if no source available
    if source_interval is None:
        error_msg = (
            f"Cannot generate {requested_interval} for {symbol}: "
            f"no source interval available. Tried: {source_priority}"
        )
        logger.error(error_msg)
        return HistoricalDecision(
            symbol=symbol,
            requested_interval=requested_interval,
            load_from_db=None,
            generate_from=None,
            needs_gap_fill=False,
            error=error_msg
        )
    
    # Gap filling might be needed if generating
    needs_gap_fill = True
    
    decision = HistoricalDecision(
        symbol=symbol,
        requested_interval=requested_interval,
        load_from_db=source_interval,  # Load source from DB
        generate_from=source_interval,  # Generate target from source
        needs_gap_fill=needs_gap_fill
    )
    
    logger.info(
        f"{symbol} historical decision: {requested_interval} will be generated "
        f"from {source_interval} (gap_fill={needs_gap_fill})"
    )
    
    return decision


def get_generation_source_priority(target_interval: str) -> List[str]:
    """Get priority-ordered list of source intervals for generation.
    
    Rules:
    - Sub-minute (5s, 10s): ["1s"] only
    - Minute (5m, 15m): ["1m", "1s"] preferred 1m
    - Day (5d): ["1d", "1m", "1s"] preferred 1d
    
    Args:
        target_interval: Target interval to generate
    
    Returns:
        List of source intervals in priority order
    
    Examples:
        >>> get_generation_source_priority("5s")
        ["1s"]
        >>> get_generation_source_priority("5m")
        ["1m", "1s"]
        >>> get_generation_source_priority("5d")
        ["1d", "1m", "1s"]
    """
    try:
        info = parse_interval(target_interval)
    except ValueError:
        logger.warning(f"Invalid interval {target_interval}, returning empty priority")
        return []
    
    # Sub-minute: ONLY from 1s
    if info.type == IntervalType.SECOND:
        return ["1s"]
    
    # Minute: prefer 1m, fallback 1s
    if info.type == IntervalType.MINUTE:
        return ["1m", "1s"]
    
    # Hour: prefer 1m, fallback 1s
    if info.type == IntervalType.HOUR:
        return ["1m", "1s"]
    
    # Day: prefer 1d, fallback 1m, fallback 1s
    if info.type == IntervalType.DAY:
        return ["1d", "1m", "1s"]
    
    return []


# =============================================================================
# Gap Filling Eligibility
# =============================================================================

def can_fill_gap(
    target_interval: str,
    source_interval: str,
    source_quality: float
) -> Tuple[bool, Optional[str]]:
    """Check if target interval gap can be filled from source.
    
    Rules:
    1. Source must be smaller than target
    2. Source quality must be 100%
    3. Target must be derivable from source
    
    Args:
        target_interval: Interval with gap
        source_interval: Potential source interval
        source_quality: Quality % of source (0-100)
    
    Returns:
        (can_fill, reason_if_not)
    """
    # Parse intervals
    try:
        target_info = parse_interval(target_interval)
        source_info = parse_interval(source_interval)
    except ValueError as e:
        return False, f"Invalid interval: {e}"
    
    # Source must be smaller than target
    if source_info.seconds >= target_info.seconds:
        return False, f"Source {source_interval} not smaller than target {target_interval}"
    
    # Source quality must be 100%
    if source_quality < 100.0:
        return False, f"Source quality {source_quality:.1f}% < 100% required"
    
    # Check if target can be derived from source
    priority = get_generation_source_priority(target_interval)
    if source_interval not in priority:
        return False, f"Target {target_interval} cannot be derived from {source_interval}"
    
    return True, None
