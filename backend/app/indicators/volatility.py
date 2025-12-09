"""Volatility indicators - calculated from OHLCV data."""

import logging
import math
from typing import List, Optional

from .base import BarData, IndicatorConfig, IndicatorResult
from .registry import indicator
from .utils import (
    simple_moving_average,
    exponential_moving_average,
    standard_deviation,
    true_range,
    highest_high,
    lowest_low,
)

logger = logging.getLogger(__name__)


@indicator("atr", "Average True Range")
def calculate_atr(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Average True Range.
    
    Formula: ATR = SMA(TR, period)
    where TR = max(H-L, abs(H-prev_C), abs(L-prev_C))
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with ATR value
    """
    period = config.period
    
    # Need period + 1 bars (need previous close)
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
    
    # ATR = average of last N true ranges
    atr_value = simple_moving_average(tr_values, period)
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=atr_value,
        valid=True
    )


@indicator("bbands", "Bollinger Bands")
def calculate_bbands(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Bollinger Bands.
    
    Formula:
    - Middle = SMA(close, period)
    - Upper = Middle + (std_dev * num_std)
    - Lower = Middle - (std_dev * num_std)
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with dict: {upper, middle, lower, bandwidth}
    """
    period = config.period
    num_std = config.params.get("num_std", 2.0)
    
    if len(bars) < period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Calculate SMA (middle band)
    closes = [b.close for b in bars]
    middle = simple_moving_average(closes, period)
    
    # Calculate standard deviation
    std_dev = standard_deviation(closes, period)
    
    # Bollinger Bands
    upper = middle + (std_dev * num_std)
    lower = middle - (std_dev * num_std)
    
    # Bandwidth = (upper - lower) / middle
    bandwidth = (upper - lower) / middle if middle != 0 else 0.0
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value={
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "bandwidth": bandwidth
        },
        valid=True
    )


@indicator("keltner", "Keltner Channels")
def calculate_keltner(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Keltner Channels.
    
    Formula:
    - Middle = EMA(close, period)
    - Upper = Middle + (ATR * multiplier)
    - Lower = Middle - (ATR * multiplier)
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with dict: {upper, middle, lower}
    """
    period = config.period
    atr_period = config.params.get("atr_period", 10)
    multiplier = config.params.get("multiplier", 2.0)
    
    if len(bars) < max(period, atr_period + 1):
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Calculate EMA (middle line)
    closes = [b.close for b in bars]
    sma = simple_moving_average(closes[:period], period)
    middle = sma
    alpha = 2.0 / (period + 1)
    
    for close in closes[period:]:
        middle = alpha * close + (1 - alpha) * middle
    
    # Calculate ATR
    tr_values = []
    for i in range(1, len(bars)):
        tr = true_range(bars[i], bars[i-1])
        tr_values.append(tr)
    
    atr = simple_moving_average(tr_values, atr_period)
    
    # Keltner Channels
    upper = middle + (atr * multiplier)
    lower = middle - (atr * multiplier)
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value={
            "upper": upper,
            "middle": middle,
            "lower": lower
        },
        valid=True
    )


@indicator("donchian", "Donchian Channels")
def calculate_donchian(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Donchian Channels.
    
    Formula:
    - Upper = Highest_High(period)
    - Lower = Lowest_Low(period)
    - Middle = (Upper + Lower) / 2
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with dict: {upper, middle, lower}
    """
    period = config.period
    
    if len(bars) < period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Highest high and lowest low
    upper = highest_high(bars, period)
    lower = lowest_low(bars, period)
    middle = (upper + lower) / 2.0
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value={
            "upper": upper,
            "middle": middle,
            "lower": lower
        },
        valid=True
    )


@indicator("stddev", "Standard Deviation")
def calculate_stddev(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Standard Deviation.
    
    Formula: StdDev = sqrt(SUM((Close[i] - Mean)^2) / N)
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with standard deviation value
    """
    period = config.period
    
    if len(bars) < period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    closes = [b.close for b in bars]
    std_dev = standard_deviation(closes, period)
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=std_dev,
        valid=True
    )


@indicator("histvol", "Historical Volatility")
def calculate_histvol(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Historical Volatility (annualized).
    
    Formula: HV = StdDev(log_returns) * sqrt(252) * 100
    (for daily bars, use 252 trading days per year)
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with annualized volatility (percentage)
    """
    period = config.period
    
    if len(bars) < period + 1:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Calculate log returns
    log_returns = []
    for i in range(1, len(bars)):
        if bars[i-1].close > 0:
            log_ret = math.log(bars[i].close / bars[i-1].close)
            log_returns.append(log_ret)
        else:
            log_returns.append(0.0)
    
    # Standard deviation of log returns
    if len(log_returns) < period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    recent_returns = log_returns[-period:]
    mean_return = sum(recent_returns) / period
    variance = sum((r - mean_return) ** 2 for r in recent_returns) / period
    std_dev = variance ** 0.5
    
    # Annualize (assumes daily bars - adjust if needed)
    # For other intervals, would need to adjust the annualization factor
    annualized_vol = std_dev * math.sqrt(252) * 100.0
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=annualized_vol,
        valid=True
    )
