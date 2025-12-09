"""Derived Bars Computation

Unified bar aggregation supporting all interval types:
- 1s → 1m
- 1m → Nm (5m, 15m, 30m, etc.)
- 1m → 1d
- 1d → 1w

Uses the unified bar aggregation framework (no code duplication).
"""
from typing import List, Dict, Optional

from app.models.trading import BarData
from app.managers.time_manager import TimeManager
from app.managers.data_manager.bar_aggregation import (
    BarAggregator,
    AggregationMode
)
from app.logger import logger


def compute_derived_bars(
    source_bars: List[BarData],
    source_interval: str,
    target_interval: str,
    time_manager: Optional[TimeManager] = None
) -> List[BarData]:
    """Compute derived bars using unified aggregation framework.
    
    Supports all aggregation types:
    - 1s → 1m (FIXED_CHUNK)
    - 1m → Nm (FIXED_CHUNK) - e.g., 5m, 15m, 30m
    - 1m → 1d (CALENDAR)
    - 1d → 1w (CALENDAR)
    
    Args:
        source_bars: Source bars (chronologically ordered)
        source_interval: Source interval ("1s", "1m", "1d")
        target_interval: Target interval ("1m", "5m", "1d", "1w", etc.)
        time_manager: TimeManager (required for calendar-based aggregation)
        
    Returns:
        List of derived bars
        
    Examples:
        # 1m → 5m
        bars_5m = compute_derived_bars(bars_1m, "1m", "5m")
        
        # 1m → 1d
        bars_1d = compute_derived_bars(bars_1m, "1m", "1d", time_mgr)
        
        # 1d → 1w
        bars_1w = compute_derived_bars(bars_1d, "1d", "1w", time_mgr)
    """
    if not source_bars:
        return []
    
    # Determine aggregation mode based on intervals
    mode = _determine_mode(source_interval, target_interval)
    
    # Create aggregator
    aggregator = BarAggregator(
        source_interval=source_interval,
        target_interval=target_interval,
        time_manager=time_manager,
        mode=mode
    )
    
    # Configure validation based on mode
    if mode == AggregationMode.FIXED_CHUNK:
        # Require complete chunks and continuity
        require_complete = True
        check_continuity = True
    elif mode == AggregationMode.CALENDAR:
        # Allow partial (early close, short weeks) but check calendar
        require_complete = False
        check_continuity = True
    else:
        # TIME_WINDOW (shouldn't reach here for derived bars)
        require_complete = False
        check_continuity = False
    
    # Aggregate
    derived = aggregator.aggregate(
        source_bars,
        require_complete=require_complete,
        check_continuity=check_continuity
    )
    
    logger.debug(
        f"Computed {len(derived)} {target_interval} bars from "
        f"{len(source_bars)} {source_interval} bars (mode={mode.value})"
    )
    
    return derived


def _determine_mode(source_interval: str, target_interval: str) -> AggregationMode:
    """Determine appropriate aggregation mode for interval pair.
    
    Rules:
    - Daily/weekly targets → CALENDAR
    - Otherwise → FIXED_CHUNK
    """
    if target_interval.endswith('d') or target_interval.endswith('w'):
        return AggregationMode.CALENDAR
    else:
        return AggregationMode.FIXED_CHUNK


def compute_all_derived_intervals(
    source_bars: List[BarData],
    source_interval: str,
    target_intervals: List[str],
    time_manager: Optional[TimeManager] = None
) -> Dict[str, List[BarData]]:
    """Compute derived bars for multiple target intervals.
    
    Args:
        source_bars: Source bars
        source_interval: Source interval ("1m", "1d", etc.)
        target_intervals: Target intervals (["5m", "15m", "1d", "1w"], etc.)
        time_manager: TimeManager (required for calendar-based intervals)
        
    Returns:
        Dictionary mapping target_interval to list of bars
        
    Example:
        # Multiple minute intervals from 1m
        result = compute_all_derived_intervals(
            bars_1m,
            "1m",
            ["5m", "15m", "30m"]
        )
        
        # Daily and weekly from 1m
        result = compute_all_derived_intervals(
            bars_1m,
            "1m",
            ["1d", "1w"],
            time_mgr
        )
    """
    result = {}
    
    for target_interval in target_intervals:
        try:
            derived = compute_derived_bars(
                source_bars,
                source_interval,
                target_interval,
                time_manager
            )
            result[target_interval] = derived
        except Exception as e:
            logger.error(
                f"Failed to compute {source_interval} → {target_interval}: {e}",
                exc_info=True
            )
            result[target_interval] = []
    
    return result
