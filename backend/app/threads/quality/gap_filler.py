"""Gap Filling Logic for Historical Data

Uses higher-quality lower intervals to fill gaps in higher intervals.
Requires 100% completeness of source data for aggregation.
"""

from typing import List, Optional, Tuple
from datetime import datetime, date
from dataclasses import dataclass

from app.logger import logger
from app.models.trading import BarData


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class GapFillResult:
    """Result of gap filling operation."""
    success: bool
    filled_bar: Optional[BarData]
    quality: float              # Quality of filled data (0-100)
    source_interval: str        # Which interval was used
    bars_used: int              # Number of source bars used
    error: Optional[str] = None # Error if failed


# =============================================================================
# Completeness Checking
# =============================================================================

def calculate_expected_bar_count(
    target_interval: str,
    source_interval: str
) -> int:
    """Calculate expected number of source bars for target interval.
    
    Args:
        target_interval: Interval being generated (e.g., "5m")
        source_interval: Source interval (e.g., "1m")
    
    Returns:
        Expected count of source bars
    
    Examples:
        >>> calculate_expected_bar_count("5m", "1m")
        5
        >>> calculate_expected_bar_count("1d", "1m")
        390
        >>> calculate_expected_bar_count("1m", "1s")
        60
    """
    # Parse target and source to seconds
    target_seconds = _parse_interval_to_seconds(target_interval)
    source_seconds = _parse_interval_to_seconds(source_interval)
    
    # Special case: 1d from 1m = 390 bars (6.5 hours * 60 minutes)
    if target_interval == "1d" and source_interval == "1m":
        return 390  # Market hours: 9:30am - 4:00pm = 6.5 hours = 390 minutes
    
    # Special case: 1d from 1s = 23400 bars (390 minutes * 60 seconds)
    if target_interval == "1d" and source_interval == "1s":
        return 23400  # 390 minutes * 60 seconds
    
    # General case: divide target by source
    if source_seconds == 0:
        raise ValueError(f"Invalid source interval: {source_interval}")
    
    expected = target_seconds // source_seconds
    
    if expected == 0:
        raise ValueError(
            f"Source {source_interval} is larger than target {target_interval}"
        )
    
    return expected


def _parse_interval_to_seconds(interval: str) -> int:
    """Parse interval string to seconds.
    
    Args:
        interval: Interval string (e.g., "1s", "5m", "1d")
    
    Returns:
        Duration in seconds
    """
    if interval.endswith('s'):
        return int(interval[:-1])
    elif interval.endswith('m'):
        return int(interval[:-1]) * 60
    elif interval.endswith('h'):
        return int(interval[:-1]) * 3600
    elif interval.endswith('d'):
        return int(interval[:-1]) * 86400
    else:
        raise ValueError(f"Invalid interval format: {interval}")


def check_interval_completeness(
    target_interval: str,
    source_interval: str,
    source_bars: List[BarData],
    expected_count: Optional[int] = None
) -> Tuple[bool, float, int]:
    """Check if source bars are complete (100%) for aggregation.
    
    Args:
        target_interval: Interval being generated (e.g., "5m")
        source_interval: Source interval (e.g., "1m")
        source_bars: Available source bars
        expected_count: Expected bar count (calculated if None)
    
    Returns:
        (is_complete, quality_percentage, expected_count)
    
    Examples:
        >>> check_interval_completeness("5m", "1m", five_bars)
        (True, 100.0, 5)
        >>> check_interval_completeness("5m", "1m", four_bars)
        (False, 80.0, 5)
    """
    if expected_count is None:
        expected_count = calculate_expected_bar_count(target_interval, source_interval)
    
    actual_count = len(source_bars)
    quality = (actual_count / expected_count) * 100 if expected_count > 0 else 0.0
    is_complete = (actual_count == expected_count)
    
    return is_complete, quality, expected_count


# =============================================================================
# Bar Aggregation
# =============================================================================

def aggregate_bars_to_interval(
    symbol: str,
    target_interval: str,
    source_interval: str,
    source_bars: List[BarData],
    require_complete: bool = True
) -> Optional[BarData]:
    """Aggregate source bars into target interval.
    
    CRITICAL: Only generates if 100% of source bars present (when require_complete=True).
    
    Args:
        symbol: Symbol
        target_interval: Interval to generate (e.g., "5m")
        source_interval: Source interval (e.g., "1m")
        source_bars: Available source bars (must be sorted by timestamp)
        require_complete: If True, require 100% completeness (default: True)
    
    Returns:
        Aggregated bar, or None if incomplete and require_complete=True
    
    Examples:
        >>> aggregate_bars_to_interval("AAPL", "5m", "1m", five_bars)
        BarData(...)  # Success
        >>> aggregate_bars_to_interval("AAPL", "5m", "1m", four_bars)
        None  # Incomplete - skipped
    """
    if not source_bars:
        logger.warning(
            f"Cannot aggregate {symbol} {target_interval}: no source bars provided"
        )
        return None
    
    # Check completeness
    is_complete, quality, expected_count = check_interval_completeness(
        target_interval, source_interval, source_bars
    )
    
    # Require 100% if specified
    if require_complete and not is_complete:
        logger.warning(
            f"Skipping {target_interval} generation for {symbol}: "
            f"incomplete data ({quality:.1f}%, need 100%, "
            f"have {len(source_bars)}/{expected_count} {source_interval} bars)"
        )
        return None
    
    # Log if generating with incomplete data (require_complete=False)
    if not is_complete:
        logger.info(
            f"Generating {target_interval} for {symbol} with incomplete data: "
            f"{quality:.1f}% ({len(source_bars)}/{expected_count} {source_interval} bars)"
        )
    
    # Aggregate OHLCV
    # Timestamp: use first bar's timestamp (start of interval)
    timestamp = source_bars[0].timestamp
    
    # OHLC
    open_price = source_bars[0].open
    high_price = max(bar.high for bar in source_bars)
    low_price = min(bar.low for bar in source_bars)
    close_price = source_bars[-1].close
    
    # Volume
    total_volume = sum(bar.volume for bar in source_bars)
    
    aggregated_bar = BarData(
        symbol=symbol,
        timestamp=timestamp,
        interval=target_interval,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=total_volume
    )
    
    logger.debug(
        f"Generated {target_interval} bar for {symbol} at {timestamp} "
        f"from {len(source_bars)} {source_interval} bars (quality={quality:.1f}%)"
    )
    
    return aggregated_bar


# =============================================================================
# Specialized Gap Filling Functions
# =============================================================================

def fill_1m_from_1s(
    symbol: str,
    target_timestamp: datetime,
    bars_1s: List[BarData]
) -> GapFillResult:
    """Fill missing 1m bar by aggregating sixty 1s bars.
    
    Args:
        symbol: Symbol
        target_timestamp: Timestamp of missing 1m bar
        bars_1s: Available 1s bars for that minute
    
    Returns:
        GapFillResult with success status and filled bar
    """
    logger.debug(
        f"Attempting to fill 1m gap for {symbol} at {target_timestamp} "
        f"using {len(bars_1s)} 1s bars"
    )
    
    # Validate source bars
    if not bars_1s:
        return GapFillResult(
            success=False,
            filled_bar=None,
            quality=0.0,
            source_interval="1s",
            bars_used=0,
            error="No 1s bars provided"
        )
    
    # Check completeness (need 60 bars)
    is_complete, quality, expected = check_interval_completeness("1m", "1s", bars_1s, 60)
    
    if not is_complete:
        return GapFillResult(
            success=False,
            filled_bar=None,
            quality=quality,
            source_interval="1s",
            bars_used=len(bars_1s),
            error=f"Incomplete source data: {quality:.1f}% (need 100%)"
        )
    
    # Aggregate
    filled_bar = aggregate_bars_to_interval(
        symbol=symbol,
        target_interval="1m",
        source_interval="1s",
        source_bars=bars_1s,
        require_complete=True
    )
    
    if filled_bar is None:
        return GapFillResult(
            success=False,
            filled_bar=None,
            quality=quality,
            source_interval="1s",
            bars_used=len(bars_1s),
            error="Aggregation failed"
        )
    
    return GapFillResult(
        success=True,
        filled_bar=filled_bar,
        quality=100.0,
        source_interval="1s",
        bars_used=len(bars_1s)
    )


def fill_1d_from_1m(
    symbol: str,
    target_date: date,
    bars_1m: List[BarData]
) -> GapFillResult:
    """Fill missing 1d bar by aggregating 390 1m bars.
    
    Args:
        symbol: Symbol
        target_date: Date of missing 1d bar
        bars_1m: Available 1m bars for that day
    
    Returns:
        GapFillResult with success status and filled bar
    """
    logger.debug(
        f"Attempting to fill 1d gap for {symbol} on {target_date} "
        f"using {len(bars_1m)} 1m bars"
    )
    
    # Validate source bars
    if not bars_1m:
        return GapFillResult(
            success=False,
            filled_bar=None,
            quality=0.0,
            source_interval="1m",
            bars_used=0,
            error="No 1m bars provided"
        )
    
    # Check completeness (need 390 bars for full trading day)
    is_complete, quality, expected = check_interval_completeness("1d", "1m", bars_1m, 390)
    
    if not is_complete:
        return GapFillResult(
            success=False,
            filled_bar=None,
            quality=quality,
            source_interval="1m",
            bars_used=len(bars_1m),
            error=f"Incomplete source data: {quality:.1f}% (need 100%)"
        )
    
    # Aggregate
    filled_bar = aggregate_bars_to_interval(
        symbol=symbol,
        target_interval="1d",
        source_interval="1m",
        source_bars=bars_1m,
        require_complete=True
    )
    
    if filled_bar is None:
        return GapFillResult(
            success=False,
            filled_bar=None,
            quality=quality,
            source_interval="1m",
            bars_used=len(bars_1m),
            error="Aggregation failed"
        )
    
    # Timestamp already set correctly by aggregate_bars_to_interval
    # (uses first source bar's timestamp, which represents the trading day)
    
    return GapFillResult(
        success=True,
        filled_bar=filled_bar,
        quality=100.0,
        source_interval="1m",
        bars_used=len(bars_1m)
    )


def fill_interval_from_source(
    symbol: str,
    target_interval: str,
    target_timestamp: datetime,
    source_interval: str,
    source_bars: List[BarData]
) -> GapFillResult:
    """Generic gap filling from any source to any target.
    
    Args:
        symbol: Symbol
        target_interval: Target interval (e.g., "5m")
        target_timestamp: Timestamp of missing bar
        source_interval: Source interval (e.g., "1m")
        source_bars: Available source bars
    
    Returns:
        GapFillResult with success status and filled bar
    """
    logger.debug(
        f"Attempting to fill {target_interval} gap for {symbol} at {target_timestamp} "
        f"using {len(source_bars)} {source_interval} bars"
    )
    
    # Validate source bars
    if not source_bars:
        return GapFillResult(
            success=False,
            filled_bar=None,
            quality=0.0,
            source_interval=source_interval,
            bars_used=0,
            error="No source bars provided"
        )
    
    # Check completeness
    is_complete, quality, expected = check_interval_completeness(
        target_interval, source_interval, source_bars
    )
    
    if not is_complete:
        return GapFillResult(
            success=False,
            filled_bar=None,
            quality=quality,
            source_interval=source_interval,
            bars_used=len(source_bars),
            error=f"Incomplete source data: {quality:.1f}% (need 100%)"
        )
    
    # Aggregate
    filled_bar = aggregate_bars_to_interval(
        symbol=symbol,
        target_interval=target_interval,
        source_interval=source_interval,
        source_bars=source_bars,
        require_complete=True
    )
    
    if filled_bar is None:
        return GapFillResult(
            success=False,
            filled_bar=None,
            quality=quality,
            source_interval=source_interval,
            bars_used=len(source_bars),
            error="Aggregation failed"
        )
    
    return GapFillResult(
        success=True,
        filled_bar=filled_bar,
        quality=100.0,
        source_interval=source_interval,
        bars_used=len(source_bars)
    )
