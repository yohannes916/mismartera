"""Validation Logic

Validates completeness and continuity of bar groups.
"""
from datetime import timedelta
from typing import List, Optional

from app.models.trading import BarData
from app.managers.time_manager import TimeManager
from app.managers.data_manager.bar_aggregation.modes import AggregationMode
from app.threads.quality.requirement_analyzer import parse_interval
from app.models.database import SessionLocal
from app.logger import logger


def is_complete(
    items: List[BarData],
    mode: AggregationMode,
    source_interval: str,
    target_interval: str
) -> bool:
    """Check if group has required number of items.
    
    Completeness rules vary by mode:
    - TIME_WINDOW: Always complete (any number OK)
    - FIXED_CHUNK: Must have exact chunk size
    - CALENDAR: Always complete (partial OK for early close, short weeks)
    
    Args:
        items: Group to validate
        mode: Aggregation mode
        source_interval: Source interval
        target_interval: Target interval
    
    Returns:
        True if group is complete
    """
    if not items:
        return False
    
    if mode == AggregationMode.TIME_WINDOW:
        # Any number of ticks/items OK
        return True
    
    elif mode == AggregationMode.FIXED_CHUNK:
        # Require exact chunk size
        source_info = parse_interval(source_interval)
        target_info = parse_interval(target_interval)
        expected = target_info.seconds // source_info.seconds
        
        is_complete = len(items) == expected
        
        if not is_complete:
            logger.debug(
                f"Incomplete chunk: {len(items)} items (expected {expected}) "
                f"for {source_interval} → {target_interval}"
            )
        
        return is_complete
    
    elif mode == AggregationMode.CALENDAR:
        # Allow partial (early close, short weeks OK)
        return True
    
    return False


def is_continuous(
    items: List[BarData],
    mode: AggregationMode,
    source_interval: str,
    time_manager: Optional[TimeManager] = None
) -> bool:
    """Check if items are continuous (no gaps).
    
    Continuity rules vary by mode:
    - TIME_WINDOW: No check (sparse data OK)
    - FIXED_CHUNK: Strict (every bar must be consecutive)
    - CALENDAR: Calendar-aware (skip holidays/weekends)
    
    Args:
        items: Group to validate
        mode: Aggregation mode
        source_interval: Source interval
        time_manager: TimeManager (required for CALENDAR mode)
    
    Returns:
        True if group is continuous
    """
    if len(items) <= 1:
        return True
    
    if mode == AggregationMode.TIME_WINDOW:
        # Ticks/sparse data can have gaps
        return True
    
    elif mode == AggregationMode.FIXED_CHUNK:
        # Strict continuity: every bar must be consecutive
        source_info = parse_interval(source_interval)
        delta = timedelta(seconds=source_info.seconds)
        
        for i in range(1, len(items)):
            expected = items[i-1].timestamp + delta
            if items[i].timestamp != expected:
                logger.debug(
                    f"Gap detected at index {i}: expected {expected}, "
                    f"got {items[i].timestamp}"
                )
                return False
        
        return True
    
    elif mode == AggregationMode.CALENDAR:
        # Calendar continuity: check trading days using TimeManager
        # CRITICAL: TimeManager is the SINGLE SOURCE OF TRUTH for:
        # - Trading days (skip weekends)
        # - Holidays (market closed)
        # - Calendar navigation
        if time_manager is None:
            logger.warning(
                "TimeManager required for calendar continuity check, "
                "skipping validation"
            )
            return True
        
        # Use TimeManager to validate calendar continuity
        with SessionLocal() as session:
            for i in range(1, len(items)):
                prev_date = items[i-1].timestamp.date()
                curr_date = items[i].timestamp.date()
                
                # Query TimeManager for next trading date (handles holidays/weekends)
                next_trading = time_manager.get_next_trading_date(
                    session, prev_date
                )
                
                if curr_date != next_trading:
                    logger.debug(
                        f"Calendar gap: {curr_date} is not next trading day "
                        f"after {prev_date} (expected {next_trading})"
                    )
                    return False
        
        return True
    
    return True
