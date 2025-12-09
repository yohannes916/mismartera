"""Base classes and types for indicator framework."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Union, Optional


@dataclass
class BarData:
    """Single bar of OHLCV data.
    
    This is the ONLY input to all indicators - no tick data, no bid/ask.
    """
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class IndicatorType(Enum):
    """Indicator classification."""
    TREND = "trend"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    SUPPORT_RESISTANCE = "support_resistance"
    HISTORICAL = "historical"


@dataclass
class IndicatorResult:
    """Result from indicator calculation.
    
    Attributes:
        timestamp: Bar timestamp this result corresponds to
        value: Indicator value (float for single-value, dict for multi-value)
        valid: True if warmup complete, False during warmup period
    """
    timestamp: datetime
    value: Union[float, Dict[str, float], None]
    valid: bool
    
    def is_ready(self) -> bool:
        """Check if indicator has completed warmup."""
        return self.valid and self.value is not None


@dataclass
class IndicatorConfig:
    """Configuration for an indicator.
    
    Attributes:
        name: Indicator name (e.g., "sma", "rsi", "bbands")
        type: Indicator type classification
        period: Lookback period (0 if not applicable)
        interval: Which bar interval to compute on (e.g., "5m", "1d")
        params: Additional parameters (e.g., {"num_std": 2.0} for Bollinger Bands)
    """
    name: str
    type: IndicatorType
    period: int
    interval: str
    params: Dict[str, Any] = field(default_factory=dict)
    
    def warmup_bars(self) -> int:
        """Calculate how many bars needed before valid output.
        
        Most indicators need their period, some need more.
        """
        # Special cases that need more than period
        warmup_map = {
            "macd": 26,  # Needs 26 for slow EMA
            "tema": self.period * 3,  # Triple EMA
            "dema": self.period * 2,  # Double EMA
            "stochastic": self.period + self.params.get("smooth", 3),
            "ultimate_osc": 28,  # Needs 28 periods
            "rsi": self.period + 1,  # Needs previous close
            "atr": self.period + 1,  # Needs previous close
            "swing_high": (self.period * 2) + 1,  # Needs N before and after
            "swing_low": (self.period * 2) + 1,
        }
        
        return warmup_map.get(self.name, max(1, self.period))
    
    def make_key(self) -> str:
        """Generate unique key for this indicator.
        
        Format: "{name}_{period}_{interval}" or "{name}_{interval}"
        
        Examples:
            sma_20_5m, rsi_14_15m, vwap_1m, high_low_20_1d
        """
        if self.period > 0:
            return f"{self.name}_{self.period}_{self.interval}"
        else:
            return f"{self.name}_{self.interval}"


@dataclass
class IndicatorData:
    """Indicator values stored in SessionData.
    
    This is what gets stored in SymbolSessionData.indicators dict.
    """
    name: str
    type: str  # "session" or "historical"
    interval: str
    current_value: Union[float, Dict[str, float], None]
    last_updated: datetime
    valid: bool
    
    # Optional: Full history (for charting, analysis)
    historical_values: Optional[list] = None
