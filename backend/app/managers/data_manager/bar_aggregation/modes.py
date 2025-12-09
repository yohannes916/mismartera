"""Aggregation Modes

Defines different strategies for grouping items into time windows.
"""
from enum import Enum


class AggregationMode(Enum):
    """Bar aggregation strategies.
    
    Different aggregation types require different grouping approaches:
    - TIME_WINDOW: Round timestamps to window (ticks → 1s)
    - FIXED_CHUNK: Group N consecutive bars (1s → 1m, 1m → 5m)
    - CALENDAR: Group by trading calendar (1m → 1d, 1d → 1w)
    """
    
    # Round timestamps to time window (ticks → 1s)
    # Multiple ticks per second, no continuity requirement
    TIME_WINDOW = "time_window"
    
    # Group N consecutive bars (1s → 1m, 1m → Nm)
    # Requires complete chunks and continuity
    FIXED_CHUNK = "fixed_chunk"
    
    # Group by trading calendar (1m → 1d, 1d → 1w)
    # Respects trading days/weeks, allows partial
    CALENDAR = "calendar"
