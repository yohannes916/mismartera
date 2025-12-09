"""Indicator calculation framework.

All indicators are calculated from OHLCV data only.
Unified, parameterized implementation that works across all intervals (s, m, d, w).
"""

from .base import (
    BarData,
    IndicatorResult,
    IndicatorConfig,
    IndicatorType,
    IndicatorData,
)
from .registry import (
    INDICATOR_REGISTRY,
    indicator,
    calculate_indicator,
    list_indicators,
)

# Import all indicators to trigger registration
from . import trend
from . import momentum
from . import volatility
from . import volume
from . import support

# Import manager and helper functions
from .manager import (
    IndicatorManager,
    get_indicator,
    get_indicator_value,
    is_indicator_ready,
    get_all_indicators,
)

__all__ = [
    "BarData",
    "IndicatorResult",
    "IndicatorConfig",
    "IndicatorType",
    "IndicatorData",
    "INDICATOR_REGISTRY",
    "indicator",
    "calculate_indicator",
    "list_indicators",
    "IndicatorManager",
    "get_indicator",
    "get_indicator_value",
    "is_indicator_ready",
    "get_all_indicators",
]
