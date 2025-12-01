"""Parquet Test Data Fixtures

Provides fixtures for creating controlled Parquet test data.

Architecture:
- **Setup (Backdoor):** Direct Parquet file creation for test data
- **Access (Production):** Use data_manager APIs to read data
- **Verification:** Through data_manager and stream_determination

This ensures tests verify the full production stack.
"""

import pytest
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta, date, time as dt_time
from typing import List, Dict, Tuple
import tempfile
import shutil

from app.managers.data_manager.parquet_storage import ParquetStorage, parquet_storage
from app.models.trading import BarData


# =============================================================================
# Test Data Helpers
# =============================================================================

def create_1s_bars(
    symbol: str,
    start_time: datetime,
    count: int,
    base_price: float = 100.0
) -> pd.DataFrame:
    """Create synthetic 1s bar data.
    
    Args:
        symbol: Stock symbol
        start_time: Start timestamp
        count: Number of bars to create
        base_price: Base price (varies slightly per bar)
    
    Returns:
        DataFrame with 1s bars
    """
    bars = []
    current = start_time
    
    for i in range(count):
        price = base_price + (i * 0.01)  # Slight uptrend
        bars.append({
            'timestamp': current,
            'symbol': symbol,
            'open': price,
            'high': price + 0.02,
            'low': price - 0.01,
            'close': price + 0.01,
            'volume': 1000 + (i * 10)
        })
        current += timedelta(seconds=1)
    
    return pd.DataFrame(bars)


def create_1m_bars(
    symbol: str,
    start_time: datetime,
    count: int,
    base_price: float = 100.0
) -> pd.DataFrame:
    """Create synthetic 1m bar data.
    
    Args:
        symbol: Stock symbol
        start_time: Start timestamp
        count: Number of bars to create
        base_price: Base price (varies slightly per bar)
    
    Returns:
        DataFrame with 1m bars
    """
    bars = []
    current = start_time
    
    for i in range(count):
        price = base_price + (i * 0.05)
        bars.append({
            'timestamp': current,
            'symbol': symbol,
            'open': price,
            'high': price + 0.10,
            'low': price - 0.05,
            'close': price + 0.07,
            'volume': 60000 + (i * 100)
        })
        current += timedelta(minutes=1)
    
    return pd.DataFrame(bars)


def create_1d_bars(
    symbol: str,
    start_date: date,
    count: int,
    base_price: float = 100.0
) -> pd.DataFrame:
    """Create synthetic 1d bar data.
    
    Args:
        symbol: Stock symbol
        start_date: Start date
        count: Number of bars to create
        base_price: Base price (varies per day)
    
    Returns:
        DataFrame with 1d bars
    """
    bars = []
    current_date = start_date
    
    for i in range(count):
        # Set timestamp to market open (9:30 AM ET)
        timestamp = datetime.combine(current_date, dt_time(9, 30))
        price = base_price + (i * 1.0)
        
        bars.append({
            'timestamp': timestamp,
            'symbol': symbol,
            'open': price,
            'high': price + 2.0,
            'low': price - 1.5,
            'close': price + 1.0,
            'volume': 10000000 + (i * 100000)
        })
        current_date += timedelta(days=1)
    
    return pd.DataFrame(bars)


def create_quote_data(
    symbol: str,
    start_time: datetime,
    count: int,
    base_price: float = 100.0
) -> pd.DataFrame:
    """Create synthetic quote data.
    
    Args:
        symbol: Stock symbol
        start_time: Start timestamp
        count: Number of quotes to create
        base_price: Base price for bid/ask
    
    Returns:
        DataFrame with quote data
    """
    quotes = []
    current = start_time
    
    for i in range(count):
        price = base_price + (i * 0.01)
        quotes.append({
            'timestamp': current,
            'symbol': symbol,
            'bid_price': price - 0.01,
            'ask_price': price + 0.01,
            'bid_size': 100.0,
            'ask_size': 100.0,
            'exchange': 'TEST'
        })
        current += timedelta(seconds=1)
    
    return pd.DataFrame(quotes)


# =============================================================================
# Test Parquet Storage Fixture
# =============================================================================

@pytest.fixture
def isolated_parquet_storage(tmp_path, monkeypatch):
    """Create isolated Parquet storage for testing.
    
    This fixture:
    1. Creates a temporary directory for test Parquet files
    2. Monkey-patches the global parquet_storage instance
    3. Returns the isolated storage instance
    
    Use this to ensure tests don't interfere with each other or production data.
    
    Yields:
        ParquetStorage: Isolated storage instance pointing to temp directory
    """
    # Create temp directory structure
    test_data_dir = tmp_path / "test_parquet_data"
    test_data_dir.mkdir()
    
    # Create subdirectories for each interval type
    (test_data_dir / "tick").mkdir()
    (test_data_dir / "1m").mkdir()
    (test_data_dir / "1d").mkdir()
    (test_data_dir / "quotes").mkdir()
    
    # Create isolated storage instance
    test_storage = ParquetStorage(base_path=str(test_data_dir))
    
    # Monkey-patch the global singleton at the module where it's defined
    # This will affect all imports of parquet_storage
    monkeypatch.setattr(
        'app.managers.data_manager.parquet_storage.parquet_storage',
        test_storage
    )
    
    yield test_storage
    
    # Cleanup happens automatically via tmp_path fixture


# =============================================================================
# Test Data Setup Helpers (Backdoor Creation)
# =============================================================================

class ParquetTestDataBuilder:
    """Helper to build test Parquet data via backdoor (direct write).
    
    Usage:
        builder = ParquetTestDataBuilder(storage)
        builder.add_1s_bars("AAPL", start, 1000)
        builder.add_1m_bars("AAPL", start, 390)
        builder.build()  # Writes all data to Parquet
    """
    
    def __init__(self, storage: ParquetStorage):
        self.storage = storage
        self.data_to_write = []
    
    def add_1s_bars(
        self,
        symbol: str,
        start_time: datetime,
        count: int,
        base_price: float = 100.0
    ) -> 'ParquetTestDataBuilder':
        """Queue 1s bars for writing."""
        df = create_1s_bars(symbol, start_time, count, base_price)
        # Note: Use '1s' for write_bars, even though check_db_availability looks for 'tick'
        self.data_to_write.append(('1s', symbol, df))
        return self
    
    def add_1m_bars(
        self,
        symbol: str,
        start_time: datetime,
        count: int,
        base_price: float = 100.0
    ) -> 'ParquetTestDataBuilder':
        """Queue 1m bars for writing."""
        df = create_1m_bars(symbol, start_time, count, base_price)
        self.data_to_write.append(('1m', symbol, df))
        return self
    
    def add_1d_bars(
        self,
        symbol: str,
        start_date: date,
        count: int,
        base_price: float = 100.0
    ) -> 'ParquetTestDataBuilder':
        """Queue 1d bars for writing."""
        df = create_1d_bars(symbol, start_date, count, base_price)
        self.data_to_write.append(('1d', symbol, df))
        return self
    
    def add_quotes(
        self,
        symbol: str,
        start_time: datetime,
        count: int,
        base_price: float = 100.0
    ) -> 'ParquetTestDataBuilder':
        """Queue quotes for writing."""
        df = create_quote_data(symbol, start_time, count, base_price)
        self.data_to_write.append(('quotes', symbol, df))
        return self
    
    def build(self) -> None:
        """Write all queued data to Parquet files (BACKDOOR)."""
        for interval, symbol, df in self.data_to_write:
            if interval == 'quotes':
                # Convert DataFrame to list of dicts for write_quotes
                # write_quotes signature: write_quotes(quotes: List[Dict], symbol: str)
                quotes_list = df.to_dict('records')
                self.storage.write_quotes(quotes_list, symbol)
            else:
                # Convert DataFrame to list of dicts for write_bars
                # write_bars signature: write_bars(bars: List[Dict], data_type: str, symbol: str)
                bars_list = df.to_dict('records')
                self.storage.write_bars(bars_list, interval, symbol)


@pytest.fixture
def parquet_data_builder(isolated_parquet_storage):
    """Fixture that provides a ParquetTestDataBuilder.
    
    Use this to create test data via backdoor (direct Parquet write).
    
    Returns:
        ParquetTestDataBuilder: Builder for creating test data
    
    Example:
        def test_something(parquet_data_builder):
            # Setup (BACKDOOR): Create test data
            parquet_data_builder.add_1m_bars("AAPL", start, 390)
            parquet_data_builder.build()
            
            # Access (PRODUCTION): Use data_manager
            availability = check_db_availability(...)
            assert availability.has_1m == True
    """
    return ParquetTestDataBuilder(isolated_parquet_storage)


# =============================================================================
# Common Test Scenarios
# =============================================================================

@pytest.fixture
def perfect_1s_data(parquet_data_builder):
    """Scenario: Symbol with perfect 1s data.
    
    Creates:
    - AAPL: 23,400 1s bars (1 trading day, 6.5 hours)
    - Date: 2025-01-02
    """
    start_time = datetime(2025, 1, 2, 9, 30, 0)
    count_1s = 6 * 3600 + 30 * 60  # 6.5 hours in seconds = 23,400
    
    parquet_data_builder.add_1s_bars("AAPL", start_time, count_1s)
    parquet_data_builder.build()
    
    return {
        'symbol': 'AAPL',
        'interval': '1s',
        'start_time': start_time,
        'count': count_1s
    }


@pytest.fixture
def perfect_1m_data(parquet_data_builder):
    """Scenario: Symbol with perfect 1m data.
    
    Creates:
    - AAPL: 390 1m bars (1 trading day)
    - Date: 2025-01-02
    """
    start_time = datetime(2025, 1, 2, 9, 30, 0)
    count_1m = 390  # Full trading day
    
    parquet_data_builder.add_1m_bars("AAPL", start_time, count_1m)
    parquet_data_builder.build()
    
    return {
        'symbol': 'AAPL',
        'interval': '1m',
        'start_time': start_time,
        'count': count_1m
    }


@pytest.fixture
def multi_symbol_data(parquet_data_builder):
    """Scenario: Multiple symbols with different intervals.
    
    Creates:
    - AAPL: 1s + 1m + 1d + quotes
    - RIVN: 1m + 1d
    - TSLA: 1d only
    """
    start_time = datetime(2025, 1, 2, 9, 30, 0)
    start_date = date(2025, 1, 2)
    
    # AAPL: Full data
    parquet_data_builder.add_1s_bars("AAPL", start_time, 23400)
    parquet_data_builder.add_1m_bars("AAPL", start_time, 390)
    parquet_data_builder.add_1d_bars("AAPL", start_date, 1)
    parquet_data_builder.add_quotes("AAPL", start_time, 23400)
    
    # RIVN: 1m + 1d
    parquet_data_builder.add_1m_bars("RIVN", start_time, 390)
    parquet_data_builder.add_1d_bars("RIVN", start_date, 1)
    
    # TSLA: 1d only
    parquet_data_builder.add_1d_bars("TSLA", start_date, 1)
    
    parquet_data_builder.build()
    
    return {
        'symbols': ['AAPL', 'RIVN', 'TSLA'],
        'start_time': start_time,
        'start_date': start_date
    }


@pytest.fixture
def date_range_data(parquet_data_builder):
    """Scenario: Data spanning multiple days.
    
    Creates:
    - AAPL: 5 days of 1m + 1d data
    - Date range: 2025-01-02 to 2025-01-08 (5 trading days)
    """
    start_date = date(2025, 1, 2)
    
    # Create 5 days of data
    for day_offset in range(5):
        current_date = start_date + timedelta(days=day_offset)
        start_time = datetime.combine(current_date, dt_time(9, 30))
        
        # 1m bars for each day
        parquet_data_builder.add_1m_bars("AAPL", start_time, 390)
    
    # 1d bars for full range
    parquet_data_builder.add_1d_bars("AAPL", start_date, 5)
    parquet_data_builder.build()
    
    return {
        'symbol': 'AAPL',
        'start_date': start_date,
        'end_date': start_date + timedelta(days=4),
        'trading_days': 5
    }


# =============================================================================
# Documentation and Examples
# =============================================================================

"""
Example Usage in Tests:

1. Simple Test with Perfect 1m Data:
    
    def test_stream_determination(perfect_1m_data, isolated_parquet_storage):
        # Setup: Data already created by fixture (BACKDOOR)
        
        # Access: Use production path (data_manager)
        from app.threads.quality.stream_determination import check_db_availability
        
        availability = check_db_availability(
            None,
            symbol="AAPL",
            date_range=(date(2025, 1, 2), date(2025, 1, 2))
        )
        
        # Verification
        assert availability.has_1m == True
        assert availability.has_1s == False

2. Custom Test Data:
    
    def test_custom_scenario(parquet_data_builder):
        # Setup: Create custom data (BACKDOOR)
        start = datetime(2025, 1, 2, 9, 30)
        parquet_data_builder.add_1m_bars("AAPL", start, 100)
        parquet_data_builder.add_quotes("AAPL", start, 6000)
        parquet_data_builder.build()
        
        # Access: Use data_manager (PRODUCTION)
        availability = check_db_availability(None, "AAPL", ...)
        
        # Verification
        assert availability.has_1m == True
        assert availability.has_quotes == True

3. Multiple Symbols:
    
    def test_multi_symbol(multi_symbol_data):
        # Test AAPL (full data)
        avail_aapl = check_db_availability(None, "AAPL", ...)
        assert avail_aapl.has_1s == True
        assert avail_aapl.has_1m == True
        
        # Test RIVN (partial data)
        avail_rivn = check_db_availability(None, "RIVN", ...)
        assert avail_rivn.has_1s == False
        assert avail_rivn.has_1m == True
"""
