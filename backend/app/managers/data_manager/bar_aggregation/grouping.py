"""Time Window Grouping Strategies

Different strategies for grouping items into time windows.
"""
from datetime import datetime, timedelta
from typing import List, Tuple, Dict
from collections import defaultdict

from app.models.trading import BarData
from app.threads.quality.requirement_analyzer import parse_interval
from app.logger import logger


def group_by_time_window(
    items: List[BarData],
    target_interval: str
) -> List[Tuple[datetime, List[BarData]]]:
    """Group items by rounding timestamps to time windows.
    
    Used for: Ticks → 1s
    
    Strategy: Round each item's timestamp to the target window.
    Multiple items can map to same window (e.g., multiple ticks per second).
    
    Args:
        items: Items to group
        target_interval: Target interval (e.g., "1s", "1m")
    
    Returns:
        List of (window_key, group_items) tuples, sorted chronologically
    """
    by_window = defaultdict(list)
    
    for item in items:
        # Round timestamp based on target interval
        if target_interval == "1s":
            window_key = item.timestamp.replace(microsecond=0)
        elif target_interval == "1m":
            window_key = item.timestamp.replace(second=0, microsecond=0)
        else:
            raise ValueError(
                f"TIME_WINDOW mode only supports 1s and 1m targets, "
                f"got {target_interval}"
            )
        
        by_window[window_key].append(item)
    
    # Sort by window key
    return sorted(by_window.items())


def group_by_fixed_chunks(
    items: List[BarData],
    source_interval: str,
    target_interval: str
) -> List[Tuple[datetime, List[BarData]]]:
    """Group items into fixed-size chunks aligned to interval boundaries.
    
    Used for: 1s → 1m, 1m → Nm
    
    Strategy: Group bars by aligning timestamps to target interval boundaries using modulo.
    For example, 5m bars must start at times where minute % 5 == 0 (04:00, 04:05, 04:10, etc.)
    
    Args:
        items: Items to group (must be sorted by timestamp)
        source_interval: Source interval (e.g., "1s", "1m")
        target_interval: Target interval (e.g., "1m", "5m")
    
    Returns:
        List of (window_key, chunk_items) tuples where window_key is the aligned start time
    """
    from collections import defaultdict
    
    # Calculate chunk size and target interval in seconds
    source_info = parse_interval(source_interval)
    target_info = parse_interval(target_interval)
    
    chunk_size = target_info.seconds // source_info.seconds
    target_seconds = target_info.seconds
    
    logger.debug(
        f"Grouping {len(items)} {source_interval} bars into {target_interval} bars "
        f"(chunk_size={chunk_size}, target_seconds={target_seconds})"
    )
    
    # Group by aligned window using modulo
    by_window = defaultdict(list)
    
    for item in items:
        # Calculate window start by rounding DOWN to nearest target interval boundary
        # Example: For 5m bars, 19:53 → 19:50 (floor to nearest 5-minute mark)
        timestamp = item.timestamp
        
        # Get total seconds since epoch
        total_seconds = int(timestamp.timestamp())
        
        # Round DOWN to nearest target interval
        window_start_seconds = (total_seconds // target_seconds) * target_seconds
        
        # Convert back to datetime (preserving timezone)
        from datetime import datetime
        window_start = datetime.fromtimestamp(window_start_seconds, tz=timestamp.tzinfo)
        
        by_window[window_start].append(item)
    
    # Return sorted by window start time
    return sorted(by_window.items())


def group_by_calendar(
    items: List[BarData],
    target_interval: str
) -> List[Tuple[datetime, List[BarData]]]:
    """Group items by trading calendar (days or weeks).
    
    Used for: 1m → 1d, 1d → Nd, 1d → 1w, 1w → Nw
    
    Strategy: Group by trading day, N-day periods, trading week, or N-week periods.
    Uses ISO calendar for week grouping.
    
    Args:
        items: Items to group
        target_interval: Target interval (e.g., "1d", "2d", "5d", "1w", "2w")
    
    Returns:
        List of (window_key, group_items) tuples, sorted chronologically
    """
    if not items:
        return []
    
    by_period = defaultdict(list)
    
    if target_interval.endswith('d'):
        # Daily intervals: parse N from "Nd"
        days = int(target_interval[:-1])
        
        if days == 1:
            # Single day: group by date
            for item in items:
                period_key = item.timestamp.date()
                by_period[period_key].append(item)
        else:
            # Multi-day: group by N-day chunks
            # Use first item's date as epoch (reference point)
            epoch_date = items[0].timestamp.date()
            
            for item in items:
                current_date = item.timestamp.date()
                days_since_epoch = (current_date - epoch_date).days
                
                # Period index (0, 1, 2, ...) for each N-day chunk
                period_index = days_since_epoch // days
                
                # Store as tuple (period_index, first_date_in_period)
                # This allows sorting and preserves chronological order
                first_date_in_period = epoch_date + timedelta(days=period_index * days)
                period_key = (period_index, first_date_in_period)
                
                by_period[period_key].append(item)
    
    elif target_interval.endswith('w'):
        # Weekly intervals: parse N from "Nw"
        weeks = int(target_interval[:-1])
        
        if weeks == 1:
            # Single week: group by ISO week
            for item in items:
                iso = item.timestamp.isocalendar()
                period_key = (iso.year, iso.week)
                by_period[period_key].append(item)
        else:
            # Multi-week: group by N-week chunks
            # Use first item's week as epoch
            first_iso = items[0].timestamp.isocalendar()
            epoch_year = first_iso.year
            epoch_week = first_iso.week
            
            for item in items:
                iso = item.timestamp.isocalendar()
                
                # Calculate absolute week number from epoch
                # (Simplified: assumes all in same year or consecutive years)
                if iso.year == epoch_year:
                    weeks_since_epoch = iso.week - epoch_week
                else:
                    # Handle year boundary (approximate: 52 weeks/year)
                    weeks_since_epoch = (iso.year - epoch_year) * 52 + (iso.week - epoch_week)
                
                # Period index for each N-week chunk
                period_index = weeks_since_epoch // weeks
                
                # Store as tuple for sorting
                period_key = (period_index, iso.year, iso.week)
                
                by_period[period_key].append(item)
    
    else:
        raise ValueError(
            f"CALENDAR mode only supports 'd' and 'w' intervals, "
            f"got {target_interval}"
        )
    
    # Sort by period
    sorted_periods = sorted(by_period.items())
    
    result = []
    for period_key, group_items in sorted_periods:
        # Use first item's timestamp as window key
        if group_items:
            result.append((group_items[0].timestamp, group_items))
    
    return result
