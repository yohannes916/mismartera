"""Momentum indicators - calculated from OHLCV data."""

import logging
from typing import List, Optional

from .base import BarData, IndicatorConfig, IndicatorResult
from .registry import indicator
from .utils import simple_moving_average, exponential_moving_average, typical_price

logger = logging.getLogger(__name__)


@indicator("rsi", "Relative Strength Index")
def calculate_rsi(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Relative Strength Index.
    
    Formula: RSI = 100 - (100 / (1 + RS))
    where RS = Average Gain / Average Loss
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with RSI value (0-100)
    """
    period = config.period
    
    # Need period + 1 bars (need previous close for first change)
    if len(bars) < period + 1:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Calculate price changes
    changes = []
    for i in range(1, len(bars)):
        change = bars[i].close - bars[i-1].close
        changes.append(change)
    
    # Separate gains and losses
    gains = [max(0, c) for c in changes[-period:]]
    losses = [abs(min(0, c)) for c in changes[-period:]]
    
    # Average gain and loss
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    # Calculate RSI
    if avg_loss == 0:
        rsi_value = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_value = 100.0 - (100.0 / (1.0 + rs))
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=rsi_value,
        valid=True
    )


@indicator("macd", "Moving Average Convergence Divergence")
def calculate_macd(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate MACD.
    
    Formula:
    - MACD = EMA(12) - EMA(26)
    - Signal = EMA(MACD, 9)
    - Histogram = MACD - Signal
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with dict: {macd, signal, histogram}
    """
    # Get periods from params or use defaults
    fast_period = config.params.get("fast", 12)
    slow_period = config.params.get("slow", 26)
    signal_period = config.params.get("signal", 9)
    
    # Need enough bars for slow EMA + signal EMA
    if len(bars) < slow_period + signal_period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    closes = [b.close for b in bars]
    
    # Calculate fast EMA (12)
    fast_sma = simple_moving_average(closes[:fast_period], fast_period)
    fast_ema = fast_sma
    alpha_fast = 2.0 / (fast_period + 1)
    
    fast_ema_values = []
    for close in closes[fast_period:]:
        fast_ema = alpha_fast * close + (1 - alpha_fast) * fast_ema
        fast_ema_values.append(fast_ema)
    
    # Calculate slow EMA (26)
    slow_sma = simple_moving_average(closes[:slow_period], slow_period)
    slow_ema = slow_sma
    alpha_slow = 2.0 / (slow_period + 1)
    
    slow_ema_values = []
    for close in closes[slow_period:]:
        slow_ema = alpha_slow * close + (1 - alpha_slow) * slow_ema
        slow_ema_values.append(slow_ema)
    
    # MACD line = Fast EMA - Slow EMA
    # Align the arrays (slow starts later)
    offset = slow_period - fast_period
    macd_values = []
    for i in range(len(slow_ema_values)):
        macd = fast_ema_values[i + offset] - slow_ema_values[i]
        macd_values.append(macd)
    
    # Signal line = EMA of MACD
    if len(macd_values) < signal_period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    signal_sma = simple_moving_average(macd_values[:signal_period], signal_period)
    signal = signal_sma
    alpha_signal = 2.0 / (signal_period + 1)
    
    for macd_val in macd_values[signal_period:]:
        signal = alpha_signal * macd_val + (1 - alpha_signal) * signal
    
    # Current values
    macd_line = macd_values[-1]
    signal_line = signal
    histogram = macd_line - signal_line
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value={
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram
        },
        valid=True
    )


@indicator("stochastic", "Stochastic Oscillator")
def calculate_stochastic(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Stochastic Oscillator.
    
    Formula:
    - %K = (Close - Low_N) / (High_N - Low_N) * 100
    - %D = SMA(%K, smooth)
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with dict: {k, d}
    """
    period = config.period
    smooth = config.params.get("smooth", 3)
    
    if len(bars) < period + smooth:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Calculate %K values
    k_values = []
    for i in range(period - 1, len(bars)):
        window = bars[i - period + 1:i + 1]
        highest = max(b.high for b in window)
        lowest = min(b.low for b in window)
        close = bars[i].close
        
        if highest == lowest:
            k = 50.0  # Neutral if no range
        else:
            k = ((close - lowest) / (highest - lowest)) * 100.0
        
        k_values.append(k)
    
    # %D = SMA of %K
    if len(k_values) < smooth:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    k_current = k_values[-1]
    d_current = simple_moving_average(k_values, smooth)
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value={
            "k": k_current,
            "d": d_current
        },
        valid=True
    )


@indicator("cci", "Commodity Channel Index")
def calculate_cci(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Commodity Channel Index.
    
    Formula: CCI = (TP - SMA(TP)) / (0.015 * Mean_Deviation)
    where TP = Typical Price = (H + L + C) / 3
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with CCI value
    """
    period = config.period
    
    if len(bars) < period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Calculate typical prices
    tp_values = [typical_price(b) for b in bars]
    
    # SMA of typical price
    tp_sma = simple_moving_average(tp_values, period)
    
    # Mean deviation
    recent_tp = tp_values[-period:]
    mean_dev = sum(abs(tp - tp_sma) for tp in recent_tp) / period
    
    # CCI
    current_tp = tp_values[-1]
    if mean_dev == 0:
        cci_value = 0.0
    else:
        cci_value = (current_tp - tp_sma) / (0.015 * mean_dev)
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=cci_value,
        valid=True
    )


@indicator("roc", "Rate of Change")
def calculate_roc(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Rate of Change.
    
    Formula: ROC = (Close - Close[N]) / Close[N] * 100
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with ROC value (percentage)
    """
    period = config.period
    
    if len(bars) < period + 1:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    current_close = bars[-1].close
    past_close = bars[-period - 1].close
    
    if past_close == 0:
        roc_value = 0.0
    else:
        roc_value = ((current_close - past_close) / past_close) * 100.0
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=roc_value,
        valid=True
    )


@indicator("mom", "Momentum")
def calculate_mom(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Momentum.
    
    Formula: MOM = Close - Close[N]
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with momentum value
    """
    period = config.period
    
    if len(bars) < period + 1:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    current_close = bars[-1].close
    past_close = bars[-period - 1].close
    mom_value = current_close - past_close
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=mom_value,
        valid=True
    )


@indicator("williams_r", "Williams %R")
def calculate_williams_r(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Williams %R.
    
    Formula: %R = (High_N - Close) / (High_N - Low_N) * -100
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with Williams %R value (-100 to 0)
    """
    period = config.period
    
    if len(bars) < period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    recent = bars[-period:]
    highest = max(b.high for b in recent)
    lowest = min(b.low for b in recent)
    current_close = bars[-1].close
    
    if highest == lowest:
        wr_value = -50.0  # Neutral
    else:
        wr_value = ((highest - current_close) / (highest - lowest)) * -100.0
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=wr_value,
        valid=True
    )


@indicator("ultimate_osc", "Ultimate Oscillator")
def calculate_ultimate_osc(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate Ultimate Oscillator.
    
    Multi-period momentum oscillator (7, 14, 28 periods).
    
    Args:
        bars: Historical bars
        config: Indicator configuration
        previous_result: Not used
        
    Returns:
        IndicatorResult with Ultimate Oscillator value (0-100)
    """
    # Use default periods
    period1 = config.params.get("period1", 7)
    period2 = config.params.get("period2", 14)
    period3 = config.params.get("period3", 28)
    
    if len(bars) < period3 + 1:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Calculate buying pressure and true range for each bar
    bp_values = []
    tr_values = []
    
    for i in range(1, len(bars)):
        current = bars[i]
        previous = bars[i - 1]
        
        # Buying Pressure = Close - min(Low, Previous Close)
        bp = current.close - min(current.low, previous.close)
        bp_values.append(bp)
        
        # True Range
        tr = max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close)
        )
        tr_values.append(tr)
    
    # Calculate averages for each period
    def calc_avg(values, period):
        return sum(values[-period:]) / period if len(values) >= period else 0
    
    avg_bp1 = calc_avg(bp_values, period1)
    avg_tr1 = calc_avg(tr_values, period1)
    
    avg_bp2 = calc_avg(bp_values, period2)
    avg_tr2 = calc_avg(tr_values, period2)
    
    avg_bp3 = calc_avg(bp_values, period3)
    avg_tr3 = calc_avg(tr_values, period3)
    
    # Ultimate Oscillator formula
    if avg_tr1 == 0 or avg_tr2 == 0 or avg_tr3 == 0:
        uo_value = 50.0
    else:
        raw1 = avg_bp1 / avg_tr1
        raw2 = avg_bp2 / avg_tr2
        raw3 = avg_bp3 / avg_tr3
        
        uo_value = ((raw1 * 4) + (raw2 * 2) + raw3) / 7.0 * 100.0
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=uo_value,
        valid=True
    )
