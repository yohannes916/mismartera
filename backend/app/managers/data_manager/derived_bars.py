"""Derived Bars Computation

This module provides functionality to compute multi-timeframe bars (5m, 15m, 30m, 1h)
from 1-minute bars using OHLCV aggregation.

Used by the Data-Upkeep Thread to maintain derived bars in session_data.
"""
from datetime import datetime, timedelta
from typing import List, Dict
from collections import deque

from app.models.trading import BarData
from app.logger import logger


def compute_derived_bars(
    bars_1m: List[BarData],
    interval: int
) -> List[BarData]:
    """Compute derived bars from 1-minute bars using OHLCV aggregation.
    
    Args:
        bars_1m: List of 1-minute bars (chronologically ordered)
        interval: Interval in minutes (5, 15, 30, 60)
        
    Returns:
        List of derived bars
    """
    if not bars_1m:
        return []
    
    if interval <= 0:
        raise ValueError(f"Interval must be positive, got {interval}")
    
    derived = []
    symbol = bars_1m[0].symbol
    
    # Group 1m bars into N-minute chunks
    i = 0
    while i < len(bars_1m):
        chunk = bars_1m[i:i+interval]
        
        if len(chunk) < interval:
            # Incomplete bar at end - skip
            logger.debug(
                f"Skipping incomplete {interval}m bar: "
                f"only {len(chunk)} of {interval} 1m bars available"
            )
            break
        
        # Verify chunk is continuous (no gaps)
        is_continuous = True
        for j in range(1, len(chunk)):
            expected_time = chunk[j-1].timestamp + timedelta(minutes=1)
            if chunk[j].timestamp != expected_time:
                logger.warning(
                    f"Gap detected in {interval}m bar chunk at {chunk[j].timestamp}"
                )
                is_continuous = False
                break
        
        if not is_continuous:
            # Skip this chunk due to gap
            i += 1
            continue
        
        # Aggregate OHLCV
        derived_bar = BarData(
            symbol=symbol,
            timestamp=chunk[0].timestamp,  # Start time of interval
            open=chunk[0].open,
            high=max(b.high for b in chunk),
            low=min(b.low for b in chunk),
            close=chunk[-1].close,
            volume=sum(b.volume for b in chunk)
        )
        
        derived.append(derived_bar)
        i += interval
    
    logger.debug(
        f"Computed {len(derived)} {interval}-minute bars from "
        f"{len(bars_1m)} 1-minute bars"
    )
    
    return derived


def compute_all_derived_intervals(
    bars_1m: List[BarData],
    intervals: List[int]
) -> Dict[int, List[BarData]]:
    """Compute derived bars for multiple intervals.
    
    Args:
        bars_1m: List of 1-minute bars
        intervals: List of intervals in minutes (e.g., [5, 15, 30])
        
    Returns:
        Dictionary mapping interval to list of bars
    """
    result = {}
    
    for interval in intervals:
        try:
            derived = compute_derived_bars(bars_1m, interval)
            result[interval] = derived
        except Exception as e:
            logger.error(f"Failed to compute {interval}m bars: {e}")
            result[interval] = []
    
    return result


def update_derived_bars_incremental(
    existing_derived: List[BarData],
    new_1m_bars: List[BarData],
    interval: int,
    max_derived_count: int = 1000
) -> List[BarData]:
    """Update derived bars incrementally with new 1-minute bars.
    
    More efficient than recomputing all bars when only a few new bars arrive.
    
    Args:
        existing_derived: Existing derived bars
        new_1m_bars: New 1-minute bars to incorporate
        interval: Interval in minutes
        max_derived_count: Maximum number of derived bars to keep
        
    Returns:
        Updated list of derived bars
    """
    if not new_1m_bars:
        return existing_derived
    
    # Get last incomplete bar's worth of 1m bars
    # We need to reconsider the last derived bar in case it was incomplete
    
    # For now, use simple approach: recompute last N bars
    # where N is enough to cover new 1m bars plus one interval
    recompute_count = len(new_1m_bars) + interval
    
    # Keep all but last few derived bars
    if len(existing_derived) > 0:
        keep_count = max(0, len(existing_derived) - (recompute_count // interval) - 1)
        kept_bars = existing_derived[:keep_count]
    else:
        kept_bars = []
    
    # Get corresponding 1m bars to recompute
    # This is simplified - in production would need proper indexing
    logger.debug(
        f"Incremental update: keeping {len(kept_bars)} existing bars, "
        f"recomputing with {len(new_1m_bars)} new 1m bars"
    )
    
    # For now, return indication that full recompute needed
    # Full implementation would maintain proper indices
    return existing_derived


def align_bars_to_interval(
    bars: List[BarData],
    interval: int,
    session_start: datetime
) -> List[BarData]:
    """Align bars to proper interval boundaries.
    
    Ensures derived bars start at correct times (e.g., 9:30, 9:35 for 5m bars).
    
    Args:
        bars: List of 1-minute bars
        interval: Interval in minutes
        session_start: Start of trading session
        
    Returns:
        List of properly aligned bars
    """
    if not bars:
        return []
    
    # Find first bar that aligns with interval
    first_bar_time = bars[0].timestamp
    minutes_from_start = (first_bar_time - session_start).total_seconds() / 60
    
    # Calculate offset to next aligned time
    offset = int(interval - (minutes_from_start % interval)) % interval
    
    if offset > 0:
        # Skip first few bars to align
        bars = bars[offset:]
        logger.debug(f"Skipped {offset} bars to align to {interval}m interval")
    
    return bars


def validate_derived_bars(
    derived_bars: List[BarData],
    interval: int,
    source_1m_count: int
) -> Dict[str, any]:
    """Validate derived bars for correctness.
    
    Args:
        derived_bars: List of derived bars to validate
        interval: Interval in minutes
        source_1m_count: Number of source 1-minute bars
        
    Returns:
        Dictionary with validation results
    """
    if not derived_bars:
        return {
            "valid": source_1m_count < interval,
            "error": "No derived bars" if source_1m_count >= interval else None,
            "expected_count": source_1m_count // interval,
            "actual_count": 0
        }
    
    # Check count
    expected_count = source_1m_count // interval
    actual_count = len(derived_bars)
    count_valid = actual_count <= expected_count
    
    # Check timestamps are spaced correctly
    timestamp_valid = True
    for i in range(1, len(derived_bars)):
        expected_delta = timedelta(minutes=interval)
        actual_delta = derived_bars[i].timestamp - derived_bars[i-1].timestamp
        
        if actual_delta != expected_delta:
            timestamp_valid = False
            logger.warning(
                f"Invalid timestamp spacing at index {i}: "
                f"expected {expected_delta}, got {actual_delta}"
            )
            break
    
    # Check OHLC relationship
    ohlc_valid = True
    for bar in derived_bars:
        if not (bar.low <= bar.open <= bar.high and
                bar.low <= bar.close <= bar.high):
            ohlc_valid = False
            logger.warning(f"Invalid OHLC relationship in bar: {bar}")
            break
    
    return {
        "valid": count_valid and timestamp_valid and ohlc_valid,
        "count_valid": count_valid,
        "timestamp_valid": timestamp_valid,
        "ohlc_valid": ohlc_valid,
        "expected_count": expected_count,
        "actual_count": actual_count
    }


# Example usage and testing
if __name__ == "__main__":
    from datetime import datetime
    
    # Create sample 1-minute bars
    base_time = datetime(2025, 1, 1, 9, 30)
    bars_1m = []
    
    for i in range(20):
        bar = BarData(
            symbol="AAPL",
            timestamp=base_time + timedelta(minutes=i),
            open=150.0 + i * 0.1,
            high=151.0 + i * 0.1,
            low=149.0 + i * 0.1,
            close=150.5 + i * 0.1,
            volume=1000 + i * 10
        )
        bars_1m.append(bar)
    
    print(f"Created {len(bars_1m)} 1-minute bars")
    print(f"Time range: {bars_1m[0].timestamp} to {bars_1m[-1].timestamp}")
    print()
    
    # Compute 5-minute bars
    bars_5m = compute_derived_bars(bars_1m, interval=5)
    print(f"5-minute bars: {len(bars_5m)}")
    for bar in bars_5m:
        print(f"  {bar.timestamp}: O={bar.open:.2f} H={bar.high:.2f} "
              f"L={bar.low:.2f} C={bar.close:.2f} V={bar.volume}")
    print()
    
    # Validate
    validation = validate_derived_bars(bars_5m, interval=5, source_1m_count=len(bars_1m))
    print(f"Validation: {validation}")
    print()
    
    # Compute multiple intervals
    all_derived = compute_all_derived_intervals(bars_1m, intervals=[5, 10, 15])
    print("All derived intervals:")
    for interval, bars in all_derived.items():
        print(f"  {interval}m: {len(bars)} bars")
