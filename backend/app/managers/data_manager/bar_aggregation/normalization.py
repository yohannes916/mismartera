"""Input Normalization

Converts various input formats (dicts, BarData) to standardized BarData objects.
"""
from typing import List, Union, Dict

from app.models.trading import BarData


def normalize_to_bars(
    items: List[Union[Dict, BarData]],
    source_interval: str
) -> List[BarData]:
    """Convert all inputs to BarData objects.
    
    Handles:
    - Ticks (dict with timestamp, symbol, close, volume)
    - Bar dicts (dict with all OHLCV fields)
    - BarData objects (pass through)
    
    Args:
        items: Source data (ticks or bars)
        source_interval: Source interval ("tick", "1s", "1m", etc.)
    
    Returns:
        List of BarData objects
    """
    if not items:
        return []
    
    # Check first item type
    if isinstance(items[0], BarData):
        return items  # Already normalized
    
    # Convert dicts to BarData
    result = []
    for item in items:
        if source_interval == "tick":
            # Tick: has timestamp, symbol, close (price), volume
            # Convert to bar with close as all OHLCV
            bar = BarData(
                timestamp=item['timestamp'],
                symbol=item['symbol'],
                open=item['close'],   # Tick price
                high=item['close'],
                low=item['close'],
                close=item['close'],
                volume=item.get('volume', 0)
            )
        else:
            # Bar dict: has all OHLCV fields
            bar = BarData(
                timestamp=item['timestamp'],
                symbol=item['symbol'],
                open=item['open'],
                high=item['high'],
                low=item['low'],
                close=item['close'],
                volume=item['volume']
            )
        
        result.append(bar)
    
    return result
