"""Synthetic Bar Data Generation

Utilities for generating realistic bar data for testing.
"""
import pytest
import pandas as pd
from datetime import datetime, timedelta, date, time
from typing import List, Optional, Dict
from zoneinfo import ZoneInfo

from app.models.trading import BarData


@pytest.fixture
def bar_data_generator():
    """Factory fixture for generating synthetic bar data."""
    
    def generate_bars(
        symbol: str,
        target_date: date,
        start_time: time,
        end_time: time,
        interval_minutes: int = 1,
        missing_times: Optional[List[str]] = None,
        timezone: str = "America/New_York"
    ) -> List[BarData]:
        """
        Generate synthetic bar data for a trading day.
        
        Args:
            symbol: Symbol name (e.g., "SYMBOL_X")
            target_date: Date to generate bars for
            start_time: Market open time
            end_time: Market close time
            interval_minutes: Bar interval in minutes
            missing_times: List of times to skip (e.g., ["09:35", "10:15"])
            timezone: Timezone for bars
        
        Returns:
            List of BarData objects
        """
        tz = ZoneInfo(timezone)
        missing_set = set(missing_times or [])
        bars = []
        
        # Create datetime for start
        current_dt = datetime.combine(target_date, start_time, tzinfo=tz)
        end_dt = datetime.combine(target_date, end_time, tzinfo=tz)
        
        bar_index = 0
        base_price = 100.0
        
        while current_dt < end_dt:
            time_str = current_dt.strftime("%H:%M")
            
            if time_str not in missing_set:
                # Generate realistic OHLCV data
                open_price = base_price + (bar_index * 0.05)
                high_price = open_price + 0.75
                low_price = open_price - 0.50
                close_price = open_price + 0.25
                volume = 1000 + (bar_index * 50)
                
                bars.append(BarData(
                    symbol=symbol,
                    timestamp=current_dt,
                    open=round(open_price, 2),
                    high=round(high_price, 2),
                    low=round(low_price, 2),
                    close=round(close_price, 2),
                    volume=volume
                ))
                
                bar_index += 1
            
            current_dt += timedelta(minutes=interval_minutes)
        
        return bars
    
    return generate_bars


@pytest.fixture
def bar_data_generator_from_symbol(bar_data_generator):
    """Generate bars based on TestSymbol definition."""
    
    def generate_from_test_symbol(test_symbol, target_date: date, market_open: time, market_close: time):
        """
        Generate bars for a TestSymbol on a specific date.
        
        Args:
            test_symbol: TestSymbol instance
            target_date: Date to generate bars for
            market_open: Market open time for this date
            market_close: Market close time for this date
        
        Returns:
            List of BarData objects
        """
        missing_times = test_symbol.missing_bars.get(target_date, [])
        
        return bar_data_generator(
            symbol=test_symbol.symbol,
            target_date=target_date,
            start_time=market_open,
            end_time=market_close,
            interval_minutes=1,
            missing_times=missing_times
        )
    
    return generate_from_test_symbol


@pytest.fixture
def create_dataframe_from_bars():
    """Convert list of BarData to pandas DataFrame."""
    
    def to_dataframe(bars: List[BarData]) -> pd.DataFrame:
        """Convert BarData list to DataFrame."""
        if not bars:
            return pd.DataFrame(columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"])
        
        data = []
        for bar in bars:
            data.append({
                "symbol": bar.symbol,
                "timestamp": bar.timestamp,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume
            })
        
        return pd.DataFrame(data)
    
    return to_dataframe


@pytest.fixture
def gap_analyzer():
    """Analyze gaps in bar data."""
    
    def analyze(bars: List[BarData], expected_start: datetime, expected_end: datetime, interval_minutes: int = 1):
        """
        Analyze gaps in bar data.
        
        Returns:
            Dict with gap analysis:
            - total_expected: Total bars expected
            - total_actual: Total bars present
            - missing_count: Number of missing bars
            - gaps: List of (start_time, end_time, count) tuples
            - quality_percent: Quality percentage
        """
        # Generate expected timestamps
        expected_times = set()
        current = expected_start
        while current < expected_end:
            expected_times.add(current)
            current += timedelta(minutes=interval_minutes)
        
        # Get actual timestamps
        actual_times = {bar.timestamp for bar in bars}
        
        # Find missing
        missing_times = expected_times - actual_times
        
        # Calculate quality
        total_expected = len(expected_times)
        total_actual = len(actual_times)
        quality = (total_actual / total_expected * 100) if total_expected > 0 else 100.0
        
        return {
            "total_expected": total_expected,
            "total_actual": total_actual,
            "missing_count": len(missing_times),
            "quality_percent": round(quality, 2),
            "missing_times": sorted(missing_times)
        }
    
    return analyze
