"""Utility functions for indicator calculations."""

from typing import List
from .base import BarData


def typical_price(bar: BarData) -> float:
    """Calculate typical price (H + L + C) / 3."""
    return (bar.high + bar.low + bar.close) / 3.0


def true_range(current: BarData, previous: BarData) -> float:
    """Calculate true range.
    
    TR = max(H - L, abs(H - prev_C), abs(L - prev_C))
    
    Args:
        current: Current bar
        previous: Previous bar
        
    Returns:
        True range value
    """
    hl_range = current.high - current.low
    h_prev_close = abs(current.high - previous.close)
    l_prev_close = abs(current.low - previous.close)
    
    return max(hl_range, h_prev_close, l_prev_close)


def simple_moving_average(values: List[float], period: int) -> float:
    """Calculate simple moving average.
    
    Args:
        values: List of values
        period: Number of periods
        
    Returns:
        SMA value
    """
    if len(values) < period:
        raise ValueError(f"Not enough values: {len(values)} < {period}")
    
    recent = values[-period:]
    return sum(recent) / period


def exponential_moving_average(
    current_value: float,
    previous_ema: float,
    period: int
) -> float:
    """Calculate next EMA value given previous EMA.
    
    EMA = α * current + (1 - α) * prev_EMA
    where α = 2 / (period + 1)
    
    Args:
        current_value: Current price/value
        previous_ema: Previous EMA value
        period: EMA period
        
    Returns:
        New EMA value
    """
    alpha = 2.0 / (period + 1)
    return alpha * current_value + (1 - alpha) * previous_ema


def standard_deviation(values: List[float], period: int) -> float:
    """Calculate standard deviation.
    
    Args:
        values: List of values
        period: Number of periods
        
    Returns:
        Standard deviation
    """
    if len(values) < period:
        raise ValueError(f"Not enough values: {len(values)} < {period}")
    
    recent = values[-period:]
    mean = sum(recent) / period
    variance = sum((x - mean) ** 2 for x in recent) / period
    
    return variance ** 0.5


def weighted_moving_average(values: List[float], period: int) -> float:
    """Calculate weighted moving average (linear weights).
    
    Most recent value has weight = period, previous = period-1, etc.
    
    Args:
        values: List of values
        period: Number of periods
        
    Returns:
        WMA value
    """
    if len(values) < period:
        raise ValueError(f"Not enough values: {len(values)} < {period}")
    
    recent = values[-period:]
    weights = list(range(1, period + 1))
    
    weighted_sum = sum(v * w for v, w in zip(recent, weights))
    weight_sum = sum(weights)
    
    return weighted_sum / weight_sum


def percent_change(current: float, previous: float) -> float:
    """Calculate percentage change.
    
    Args:
        current: Current value
        previous: Previous value
        
    Returns:
        Percentage change
    """
    if previous == 0:
        return 0.0
    return ((current - previous) / previous) * 100.0


def highest_high(bars: List[BarData], period: int) -> float:
    """Get highest high over period.
    
    Args:
        bars: List of bars
        period: Number of periods
        
    Returns:
        Highest high value
    """
    if len(bars) < period:
        raise ValueError(f"Not enough bars: {len(bars)} < {period}")
    
    recent = bars[-period:]
    return max(b.high for b in recent)


def lowest_low(bars: List[BarData], period: int) -> float:
    """Get lowest low over period.
    
    Args:
        bars: List of bars
        period: Number of periods
        
    Returns:
        Lowest low value
    """
    if len(bars) < period:
        raise ValueError(f"Not enough bars: {len(bars)} < {period}")
    
    recent = bars[-period:]
    return min(b.low for b in recent)
