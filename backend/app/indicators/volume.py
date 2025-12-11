"""Volume indicators - calculated from OHLCV data."""

import logging
from typing import List, Optional

from .base import BarData, IndicatorConfig, IndicatorResult
from .registry import indicator
from .utils import simple_moving_average

logger = logging.getLogger(__name__)


@indicator("obv", "On-Balance Volume")
def calculate_obv(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate On-Balance Volume.
    
    Formula:
    - If Close > prev_Close: OBV += Volume
    - If Close < prev_Close: OBV -= Volume
    - If Close == prev_Close: OBV unchanged
    
    OBV is cumulative from session start.
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Previous OBV value (for efficiency)
        
    Returns:
        IndicatorResult with OBV value
    """
    if not bars:
        return IndicatorResult(
            timestamp=None,
            value=None,
            valid=False
        )
    
    # If we have previous OBV, just update with latest bar
    if previous_result and previous_result.valid and len(bars) >= 2:
        prev_obv = previous_result.value
        latest = bars[-1]
        previous = bars[-2]
        
        if latest.close > previous.close:
            obv_value = prev_obv + latest.volume
        elif latest.close < previous.close:
            obv_value = prev_obv - latest.volume
        else:
            obv_value = prev_obv
    else:
        # Calculate from scratch (all session bars)
        if len(bars) < 2:
            return IndicatorResult(
                timestamp=bars[-1].timestamp,
                value=0.0,
                valid=True
            )
        
        obv_value = 0.0
        for i in range(1, len(bars)):
            if bars[i].close > bars[i-1].close:
                obv_value += bars[i].volume
            elif bars[i].close < bars[i-1].close:
                obv_value -= bars[i].volume
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=obv_value,
        valid=True
    )


@indicator("pvt", "Price-Volume Trend")
def calculate_pvt(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Price-Volume Trend.
    
    Formula: PVT += Volume * ((Close - prev_Close) / prev_Close)
    
    PVT is cumulative from session start.
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Previous PVT value (for efficiency)
        
    Returns:
        IndicatorResult with PVT value
    """
    if not bars:
        return IndicatorResult(
            timestamp=None,
            value=None,
            valid=False
        )
    
    # If we have previous PVT, just update with latest bar
    if previous_result and previous_result.valid and len(bars) >= 2:
        prev_pvt = previous_result.value
        latest = bars[-1]
        previous = bars[-2]
        
        if previous.close != 0:
            price_change_pct = (latest.close - previous.close) / previous.close
            pvt_value = prev_pvt + (latest.volume * price_change_pct)
        else:
            pvt_value = prev_pvt
    else:
        # Calculate from scratch (all session bars)
        if len(bars) < 2:
            return IndicatorResult(
                timestamp=bars[-1].timestamp,
                value=0.0,
                valid=True
            )
        
        pvt_value = 0.0
        for i in range(1, len(bars)):
            if bars[i-1].close != 0:
                price_change_pct = (bars[i].close - bars[i-1].close) / bars[i-1].close
                pvt_value += bars[i].volume * price_change_pct
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=pvt_value,
        valid=True
    )


@indicator("volume_sma", "Volume Simple Moving Average")
def calculate_volume_sma(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Volume Simple Moving Average.
    
    Formula: SMA(Volume, period)
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with volume SMA value
    """
    period = config.period
    
    if len(bars) < period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    volumes = [float(b.volume) for b in bars]
    vol_sma = simple_moving_average(volumes, period)
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=vol_sma,
        valid=True
    )


@indicator("volume_ratio", "Volume Ratio")
def calculate_volume_ratio(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Volume Ratio.
    
    Formula: Current_Volume / SMA(Volume, period)
    
    If period=0, uses default of 20 bars for average.
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with volume ratio (>1 = above average)
    """
    period = config.period if config.period > 0 else 20  # Default to 20 if period=0
    
    if len(bars) < period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    current_volume = float(bars[-1].volume)
    volumes = [float(b.volume) for b in bars]
    vol_sma = simple_moving_average(volumes, period)
    
    if vol_sma == 0:
        ratio = 1.0
    else:
        ratio = current_volume / vol_sma
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=ratio,
        valid=True
    )
