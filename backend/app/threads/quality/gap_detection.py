"""Gap Detection for 1-minute Bar Data

This module provides functionality to detect gaps (missing bars) in 1-minute
bar data within a trading session. It compares expected bars against actual
bars and identifies missing timestamps.

Used by the Data-Upkeep Thread to maintain data quality and completeness.
"""
from datetime import datetime, timedelta
from typing import List, Set, Dict
from dataclasses import dataclass, field

from app.models.trading import BarData
from app.logger import logger


@dataclass
class GapInfo:
    """Information about a gap in bar data.
    
    A gap represents one or more consecutive missing bars.
    """
    symbol: str
    start_time: datetime
    end_time: datetime
    bar_count: int  # Number of missing bars
    retry_count: int = 0
    last_retry: datetime = field(default_factory=lambda: datetime.min)
    
    def __str__(self) -> str:
        return (
            f"Gap({self.symbol}, {self.start_time} to {self.end_time}, "
            f"{self.bar_count} bars, retries={self.retry_count})"
        )


def generate_expected_timestamps(
    start_time: datetime,
    end_time: datetime,
    interval_minutes: int = 1
) -> Set[datetime]:
    """Generate set of expected bar timestamps for a time range.
    
    Args:
        start_time: Start of range (inclusive)
        end_time: End of range (exclusive)
        interval_minutes: Bar interval in minutes
        
    Returns:
        Set of expected timestamps
    """
    timestamps = set()
    current = start_time
    
    while current < end_time:
        timestamps.add(current)
        current += timedelta(minutes=interval_minutes)
    
    return timestamps


def group_consecutive_timestamps(
    missing_timestamps: Set[datetime]
) -> List[tuple[datetime, datetime]]:
    """Group consecutive missing timestamps into ranges.
    
    Args:
        missing_timestamps: Set of missing timestamps
        
    Returns:
        List of (start, end) tuples representing consecutive gaps
    """
    if not missing_timestamps:
        return []
    
    # Sort timestamps
    sorted_timestamps = sorted(missing_timestamps)
    
    # Group consecutive timestamps
    gaps = []
    gap_start = sorted_timestamps[0]
    gap_end = sorted_timestamps[0]
    
    for i in range(1, len(sorted_timestamps)):
        current = sorted_timestamps[i]
        expected_next = gap_end + timedelta(minutes=1)
        
        if current == expected_next:
            # Consecutive - extend current gap
            gap_end = current
        else:
            # Not consecutive - save current gap and start new one
            gaps.append((gap_start, gap_end))
            gap_start = current
            gap_end = current
    
    # Save last gap
    gaps.append((gap_start, gap_end))
    
    return gaps


def detect_gaps(
    symbol: str,
    session_start: datetime,
    current_time: datetime,
    existing_bars: List[BarData],
    interval_minutes: int = 1
) -> List[GapInfo]:
    """Detect gaps in bar data for a symbol.
    
    Compares expected bars (session_start to current_time) against
    actual bars to identify missing timestamps.
    
    Args:
        symbol: Stock symbol
        session_start: Start of trading session
        current_time: Current time (end of range to check)
        existing_bars: List of actual bars received
        interval_minutes: Bar interval in minutes (default: 1)
        
    Returns:
        List of GapInfo objects describing missing data
    """
    # Generate expected timestamps
    expected = generate_expected_timestamps(
        session_start,
        current_time,
        interval_minutes
    )
    
    # Get actual timestamps from existing bars
    actual = {bar.timestamp for bar in existing_bars}
    
    # Find missing timestamps
    missing = expected - actual
    
    if not missing:
        # No gaps - perfect data quality
        return []
    
    # Group consecutive missing timestamps into gaps
    gap_ranges = group_consecutive_timestamps(missing)
    
    # Create GapInfo objects
    gaps = []
    for gap_start, gap_end in gap_ranges:
        # Calculate number of bars in this gap
        bar_count = int((gap_end - gap_start).total_seconds() / 60) + 1
        
        gap = GapInfo(
            symbol=symbol,
            start_time=gap_start,
            end_time=gap_end + timedelta(minutes=1),  # Exclusive end
            bar_count=bar_count
        )
        gaps.append(gap)
    
    logger.debug(
        f"Detected {len(gaps)} gaps for {symbol}: "
        f"{sum(g.bar_count for g in gaps)} missing bars"
    )
    
    return gaps


def merge_overlapping_gaps(gaps: List[GapInfo]) -> List[GapInfo]:
    """Merge overlapping or adjacent gaps.
    
    Useful for consolidating gaps after partial fills.
    
    Args:
        gaps: List of GapInfo objects
        
    Returns:
        List of merged GapInfo objects
    """
    if not gaps:
        return []
    
    # Sort by start time
    sorted_gaps = sorted(gaps, key=lambda g: g.start_time)
    
    merged = []
    current = sorted_gaps[0]
    
    for i in range(1, len(sorted_gaps)):
        next_gap = sorted_gaps[i]
        
        # Check if gaps overlap or are adjacent
        if next_gap.start_time <= current.end_time:
            # Merge gaps
            current = GapInfo(
                symbol=current.symbol,
                start_time=current.start_time,
                end_time=max(current.end_time, next_gap.end_time),
                bar_count=current.bar_count + next_gap.bar_count,
                retry_count=max(current.retry_count, next_gap.retry_count)
            )
        else:
            # No overlap - save current and move to next
            merged.append(current)
            current = next_gap
    
    # Save last gap
    merged.append(current)
    
    return merged


def get_gap_summary(gaps: List[GapInfo]) -> Dict[str, any]:
    """Get summary statistics for a list of gaps.
    
    Args:
        gaps: List of GapInfo objects
        
    Returns:
        Dictionary with summary statistics
    """
    if not gaps:
        return {
            "gap_count": 0,
            "total_missing_bars": 0,
            "largest_gap": 0,
            "quality": 100.0
        }
    
    total_missing = sum(g.bar_count for g in gaps)
    largest = max(g.bar_count for g in gaps)
    
    return {
        "gap_count": len(gaps),
        "total_missing_bars": total_missing,
        "largest_gap": largest,
        "average_gap_size": total_missing / len(gaps)
    }
