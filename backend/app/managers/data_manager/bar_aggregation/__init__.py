"""Unified Bar Aggregation Framework

Generic, parameterized bar aggregation supporting:
- Ticks → 1s
- 1s → 1m
- 1m → Nm (5m, 15m, etc.)
- 1m → 1d
- 1d → 1w

All aggregations share core OHLCV logic with zero code duplication.
"""

from app.managers.data_manager.bar_aggregation.modes import AggregationMode
from app.managers.data_manager.bar_aggregation.aggregator import BarAggregator
from app.managers.data_manager.bar_aggregation.mode_detector import (
    detect_aggregation_mode,
    validate_aggregation_params,
    get_supported_targets,
)

__all__ = [
    'AggregationMode',
    'BarAggregator',
    'detect_aggregation_mode',
    'validate_aggregation_params',
    'get_supported_targets',
]
