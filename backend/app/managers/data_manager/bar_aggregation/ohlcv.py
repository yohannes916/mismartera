"""OHLCV Aggregation Core

Shared aggregation logic used by ALL bar types.
This is the single source of truth for bar aggregation.
"""
from datetime import datetime
from typing import List

from app.models.trading import BarData


def aggregate_ohlcv(
    window_timestamp: datetime,
    items: List[BarData],
    symbol: str
) -> BarData:
    """Aggregate OHLCV for a group of bars.
    
    THIS IS THE CORE LOGIC - IDENTICAL FOR ALL AGGREGATION TYPES.
    
    OHLCV Rules (universal):
    - Open: First item's open
    - High: Maximum high across all items
    - Low: Minimum low across all items
    - Close: Last item's close
    - Volume: Sum of all volumes
    
    Args:
        window_timestamp: Start timestamp for the aggregated bar
        items: Bars to aggregate (chronologically sorted)
        symbol: Stock symbol
    
    Returns:
        Aggregated bar
        
    Raises:
        ValueError: If items is empty
    """
    if not items:
        raise ValueError("Cannot aggregate empty group")
    
    return BarData(
        symbol=symbol,
        timestamp=window_timestamp,
        open=items[0].open,                    # First bar's open
        high=max(bar.high for bar in items),   # Max high
        low=min(bar.low for bar in items),     # Min low
        close=items[-1].close,                 # Last bar's close
        volume=sum(bar.volume for bar in items)  # Sum volume
    )
