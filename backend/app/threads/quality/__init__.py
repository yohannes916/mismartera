"""
Quality Management - Stream Determination, Gap Detection, and Quality Scoring

This module provides:
- Stream determination for current day and historical data loading
- Gap detection and filling logic
- Quality measurement and shared calculation helpers
"""

from app.threads.quality.gap_detection import (
    GapInfo,
    detect_gaps,
    generate_expected_timestamps,
    group_consecutive_timestamps,
    merge_overlapping_gaps
)

from app.threads.quality.quality_helpers import (
    parse_interval_to_minutes,
    get_regular_trading_hours,
    calculate_expected_bars,
    calculate_quality_percentage,
    calculate_quality_for_current_session,
    calculate_quality_for_historical_date
)

from app.threads.quality.stream_determination import (
    IntervalType,
    IntervalInfo,
    StreamDecision,
    HistoricalDecision,
    AvailabilityInfo,
    parse_interval,
    check_db_availability,
    determine_stream_interval,
    determine_historical_loading,
    get_generation_source_priority,
    can_fill_gap
)

from app.threads.quality.gap_filler import (
    GapFillResult,
    calculate_expected_bar_count,
    check_interval_completeness,
    aggregate_bars_to_interval,
    fill_1m_from_1s,
    fill_1d_from_1m,
    fill_interval_from_source
)

__all__ = [
    # Gap detection
    'GapInfo',
    'detect_gaps',
    'generate_expected_timestamps',
    'group_consecutive_timestamps',
    'merge_overlapping_gaps',
    # Quality helpers
    'parse_interval_to_minutes',
    'get_regular_trading_hours',
    'calculate_expected_bars',
    'calculate_quality_percentage',
    'calculate_quality_for_current_session',
    'calculate_quality_for_historical_date',
    # Stream determination
    'IntervalType',
    'IntervalInfo',
    'StreamDecision',
    'HistoricalDecision',
    'AvailabilityInfo',
    'parse_interval',
    'check_db_availability',
    'determine_stream_interval',
    'determine_historical_loading',
    'get_generation_source_priority',
    'can_fill_gap',
    # Gap filling
    'GapFillResult',
    'calculate_expected_bar_count',
    'check_interval_completeness',
    'aggregate_bars_to_interval',
    'fill_1m_from_1s',
    'fill_1d_from_1m',
    'fill_interval_from_source'
]
