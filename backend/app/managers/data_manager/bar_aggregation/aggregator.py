"""Bar Aggregator

Main class that orchestrates all aggregation operations.
"""
from typing import List, Union, Dict, Optional

from app.models.trading import BarData
from app.managers.time_manager import TimeManager
from app.managers.data_manager.bar_aggregation.modes import AggregationMode
from app.managers.data_manager.bar_aggregation.ohlcv import aggregate_ohlcv
from app.managers.data_manager.bar_aggregation.normalization import normalize_to_bars
from app.managers.data_manager.bar_aggregation.grouping import (
    group_by_time_window,
    group_by_fixed_chunks,
    group_by_calendar
)
from app.managers.data_manager.bar_aggregation.validation import (
    is_complete,
    is_continuous
)
from app.threads.quality.requirement_analyzer import parse_interval
from app.logger import logger


class BarAggregator:
    """Generic bar aggregation engine.
    
    Handles all aggregation types via parameterization:
    - Ticks → 1s (TIME_WINDOW)
    - 1s → 1m (FIXED_CHUNK)
    - 1m → Nm (FIXED_CHUNK)
    - 1m → 1d (CALENDAR)
    - 1d → 1w (CALENDAR)
    
    Example usage:
        # Ticks to 1s
        agg = BarAggregator("tick", "1s", time_mgr, AggregationMode.TIME_WINDOW)
        bars_1s = agg.aggregate(ticks, require_complete=False, check_continuity=False)
        
        # 1m to 5m
        agg = BarAggregator("1m", "5m", time_mgr, AggregationMode.FIXED_CHUNK)
        bars_5m = agg.aggregate(bars_1m)
        
        # 1d to 1w
        agg = BarAggregator("1d", "1w", time_mgr, AggregationMode.CALENDAR)
        bars_1w = agg.aggregate(bars_1d, require_complete=False)
    """
    
    def __init__(
        self,
        source_interval: str,
        target_interval: str,
        time_manager: Optional[TimeManager],
        mode: AggregationMode
    ):
        """Initialize aggregator.
        
        Args:
            source_interval: Source interval ("tick", "1s", "1m", "1d")
            target_interval: Target interval ("1s", "1m", "5m", "1d", "1w")
            time_manager: TimeManager (required for CALENDAR mode)
            mode: Aggregation strategy
        
        Raises:
            ValueError: If intervals are incompatible with mode
        """
        self.source_interval = source_interval
        self.target_interval = target_interval
        self.time_manager = time_manager
        self.mode = mode
        
        # Parse intervals (skip for "tick")
        if source_interval != "tick":
            self.source_info = parse_interval(source_interval)
            # Reject hourly intervals (not supported)
            if self.source_info.type.value == "hour":
                raise ValueError(
                    f"Hourly intervals are not supported. "
                    f"Use minute intervals (e.g., '60m') instead of '{source_interval}'"
                )
        else:
            self.source_info = None
        
        self.target_info = parse_interval(target_interval)
        # Reject hourly intervals (not supported)
        if self.target_info.type.value == "hour":
            raise ValueError(
                f"Hourly intervals are not supported. "
                f"Use minute intervals (e.g., '60m') instead of '{target_interval}'"
            )
        
        # Validate
        self._validate_config()
        
        logger.debug(
            f"BarAggregator initialized: {source_interval} → {target_interval} "
            f"(mode={mode.value})"
        )
    
    def _validate_config(self):
        """Validate aggregator configuration.
        
        CRITICAL: TimeManager is REQUIRED for CALENDAR mode to:
        - Check trading days (skip weekends/holidays)
        - Validate calendar continuity
        - Determine session boundaries
        
        TimeManager is the single source of truth for all calendar operations.
        """
        if self.mode == AggregationMode.CALENDAR and self.time_manager is None:
            raise ValueError(
                f"TimeManager REQUIRED for CALENDAR mode "
                f"({self.source_interval} → {self.target_interval}). "
                f"Calendar aggregation needs TimeManager for holiday/trading day checks."
            )
        
        # Validate mode compatibility
        if self.mode == AggregationMode.TIME_WINDOW:
            if self.source_interval != "tick":
                logger.warning(
                    f"TIME_WINDOW mode typically used for ticks → 1s, "
                    f"got {self.source_interval} → {self.target_interval}"
                )
        
        elif self.mode == AggregationMode.FIXED_CHUNK:
            if self.source_interval == "tick":
                raise ValueError(
                    "FIXED_CHUNK mode not supported for ticks (use TIME_WINDOW)"
                )
        
        elif self.mode == AggregationMode.CALENDAR:
            if not (self.target_interval.endswith('d') or self.target_interval.endswith('w')):
                raise ValueError(
                    f"CALENDAR mode requires daily or weekly target, "
                    f"got {self.target_interval}"
                )
    
    def aggregate(
        self,
        items: List[Union[Dict, BarData]],
        require_complete: bool = True,
        check_continuity: bool = True
    ) -> List[BarData]:
        """Aggregate items to target interval.
        
        Args:
            items: Source data (ticks or bars)
            require_complete: Skip incomplete groups
            check_continuity: Validate no gaps
        
        Returns:
            Aggregated bars
        """
        if not items:
            return []
        
        # 1. Normalize input to BarData
        normalized = normalize_to_bars(items, self.source_interval)
        
        if not normalized:
            return []
        
        symbol = normalized[0].symbol
        
        logger.debug(
            f"Aggregating {len(normalized)} {self.source_interval} items → "
            f"{self.target_interval} (complete={require_complete}, "
            f"continuous={check_continuity})"
        )
        
        # 2. Group by time windows
        grouped = self._group_items(normalized)
        
        # 3. Validate and aggregate each group
        result = []
        skipped_incomplete = 0
        skipped_discontinuous = 0
        
        for window_key, group_items in grouped:
            # Validate completeness
            if require_complete:
                if not is_complete(
                    group_items,
                    self.mode,
                    self.source_interval,
                    self.target_interval
                ):
                    skipped_incomplete += 1
                    continue
            
            # Validate continuity
            if check_continuity:
                if not is_continuous(
                    group_items,
                    self.mode,
                    self.source_interval,
                    self.time_manager
                ):
                    skipped_discontinuous += 1
                    continue
            
            # Aggregate OHLCV
            bar = aggregate_ohlcv(window_key, group_items, symbol)
            result.append(bar)
        
        logger.info(
            f"Aggregated {len(result)} {self.target_interval} bars from "
            f"{len(normalized)} {self.source_interval} items "
            f"(skipped: {skipped_incomplete} incomplete, "
            f"{skipped_discontinuous} discontinuous)"
        )
        
        return result
    
    def _group_items(self, items: List[BarData]):
        """Group items by time window based on mode."""
        
        if self.mode == AggregationMode.TIME_WINDOW:
            return group_by_time_window(items, self.target_interval)
        
        elif self.mode == AggregationMode.FIXED_CHUNK:
            return group_by_fixed_chunks(
                items,
                self.source_interval,
                self.target_interval
            )
        
        elif self.mode == AggregationMode.CALENDAR:
            return group_by_calendar(items, self.target_interval)
        
        else:
            raise ValueError(f"Unknown aggregation mode: {self.mode}")
