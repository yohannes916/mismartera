"""Support/Resistance and Historical indicators - calculated from OHLCV data."""

import logging
from typing import List, Optional

from .base import BarData, IndicatorConfig, IndicatorResult
from .registry import indicator
from .utils import (
    simple_moving_average,
    true_range,
    typical_price,
    highest_high,
    lowest_low,
)

logger = logging.getLogger(__name__)


@indicator("pivot_points", "Pivot Points")
def calculate_pivot_points(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Pivot Points.
    
    Formula (using previous day's OHLC):
    - PP = (High + Low + Close) / 3
    - R1 = 2*PP - Low
    - R2 = PP + (High - Low)
    - R3 = High + 2*(PP - Low)
    - S1 = 2*PP - High
    - S2 = PP - (High - Low)
    - S3 = Low - 2*(High - PP)
    
    Args:
        bars: Historical bars (need at least 1 day)
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with dict: {pp, r1, r2, r3, s1, s2, s3}
    """
    if len(bars) < 1:
        return IndicatorResult(
            timestamp=None,
            value=None,
            valid=False
        )
    
    # Use latest bar's OHLC (typically previous day for intraday trading)
    bar = bars[-1]
    high = bar.high
    low = bar.low
    close = bar.close
    
    # Pivot Point
    pp = (high + low + close) / 3.0
    
    # Resistance levels
    r1 = 2 * pp - low
    r2 = pp + (high - low)
    r3 = high + 2 * (pp - low)
    
    # Support levels
    s1 = 2 * pp - high
    s2 = pp - (high - low)
    s3 = low - 2 * (high - pp)
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value={
            "pp": pp,
            "r1": r1,
            "r2": r2,
            "r3": r3,
            "s1": s1,
            "s2": s2,
            "s3": s3
        },
        valid=True
    )


@indicator("high_low", "High/Low N Periods")
def calculate_high_low(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Highest High and Lowest Low over N periods.
    
    This is the UNIFIED indicator that works on ANY interval:
    - Apply to "1d" → N-day high/low (e.g., 20-day)
    - Apply to "1w" → N-week high/low (e.g., 4-week)
    - Apply to "15m" → N-period high/low on 15m bars
    
    Formula:
    - High_N = max(High[i] for i in last N)
    - Low_N = min(Low[i] for i in last N)
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with dict: {high, low}
    """
    period = config.period
    
    if len(bars) < period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    high = highest_high(bars, period)
    low = lowest_low(bars, period)
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value={
            "high": high,
            "low": low
        },
        valid=True
    )


@indicator("swing_high", "Swing High Detection")
def calculate_swing_high(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Detect swing high (local peak).
    
    A bar is a swing high if it's the highest high in a window of
    N bars before and N bars after.
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with swing high price (or None if not a swing high)
    """
    period = config.period
    window_size = (period * 2) + 1
    
    if len(bars) < window_size:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Check if center bar is highest in window
    center_idx = period
    window = bars[-window_size:]
    center_high = window[center_idx].high
    
    is_swing_high = all(
        center_high >= b.high for i, b in enumerate(window) if i != center_idx
    )
    
    if is_swing_high:
        swing_value = center_high
    else:
        swing_value = None
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=swing_value,
        valid=True
    )


@indicator("swing_low", "Swing Low Detection")
def calculate_swing_low(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Detect swing low (local trough).
    
    A bar is a swing low if it's the lowest low in a window of
    N bars before and N bars after.
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with swing low price (or None if not a swing low)
    """
    period = config.period
    window_size = (period * 2) + 1
    
    if len(bars) < window_size:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Check if center bar is lowest in window
    center_idx = period
    window = bars[-window_size:]
    center_low = window[center_idx].low
    
    is_swing_low = all(
        center_low <= b.low for i, b in enumerate(window) if i != center_idx
    )
    
    if is_swing_low:
        swing_value = center_low
    else:
        swing_value = None
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=swing_value,
        valid=True
    )


# Historical Context Indicators

@indicator("avg_volume", "Average Daily Volume")
def calculate_avg_volume(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Average Volume (typically on daily bars).
    
    Formula: SMA(Volume, N_days)
    
    Args:
        bars: Historical bars (typically daily)
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with average volume
    """
    period = config.period
    
    if len(bars) < period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    volumes = [float(b.volume) for b in bars]
    avg_vol = simple_moving_average(volumes, period)
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=avg_vol,
        valid=True
    )


@indicator("avg_range", "Average Range")
def calculate_avg_range(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Average Range (High - Low).
    
    Formula: SMA(High - Low, N)
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with average range
    """
    period = config.period
    
    if len(bars) < period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    ranges = [b.high - b.low for b in bars]
    avg_range = simple_moving_average(ranges, period)
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=avg_range,
        valid=True
    )


@indicator("atr_daily", "Average True Range (Daily)")
def calculate_atr_daily(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Average True Range on daily bars.
    
    Same as ATR but explicitly for daily context.
    
    Args:
        bars: Historical daily bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with ATR value
    """
    period = config.period
    
    if len(bars) < period + 1:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Calculate true ranges
    tr_values = []
    for i in range(1, len(bars)):
        tr = true_range(bars[i], bars[i-1])
        tr_values.append(tr)
    
    atr_value = simple_moving_average(tr_values, period)
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=atr_value,
        valid=True
    )


@indicator("gap_stats", "Gap Statistics")
def calculate_gap_stats(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Gap Statistics.
    
    Formula:
    - Gap = Open - prev_Close
    - Count gaps, average size
    
    Args:
        bars: Historical bars (typically daily)
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with dict: {avg_gap, gap_count, gap_up_count, gap_down_count}
    """
    period = config.period
    
    if len(bars) < period + 1:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Calculate gaps
    gaps = []
    gap_up_count = 0
    gap_down_count = 0
    
    recent_bars = bars[-period-1:]
    for i in range(1, len(recent_bars)):
        gap = recent_bars[i].open - recent_bars[i-1].close
        gaps.append(gap)
        
        if gap > 0:
            gap_up_count += 1
        elif gap < 0:
            gap_down_count += 1
    
    avg_gap = sum(gaps) / len(gaps) if gaps else 0.0
    gap_count = len([g for g in gaps if abs(g) > 0.01])  # Significant gaps
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value={
            "avg_gap": avg_gap,
            "gap_count": gap_count,
            "gap_up_count": gap_up_count,
            "gap_down_count": gap_down_count
        },
        valid=True
    )


@indicator("range_ratio", "Range Ratio")
def calculate_range_ratio(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Range Ratio.
    
    Formula: Current_Range / Avg_Range
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with range ratio (>1 = expansion)
    """
    period = config.period
    
    if len(bars) < period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    current_range = bars[-1].high - bars[-1].low
    ranges = [b.high - b.low for b in bars]
    avg_range = simple_moving_average(ranges, period)
    
    if avg_range == 0:
        ratio = 1.0
    else:
        ratio = current_range / avg_range
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=ratio,
        valid=True
    )
