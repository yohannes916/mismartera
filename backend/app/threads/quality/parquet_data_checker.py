"""Parquet Data Checker for Stream Requirements Validation

Creates data_checker callables that query Parquet storage via DataManager.
Follows architecture: Use DataManager API, not direct Parquet access.
"""

from typing import Callable, Optional
from datetime import date

from app.logger import logger


def create_parquet_data_checker(
    parquet_storage,
    exchange_group: str = "US_EQUITY"
) -> Callable[[str, str, date, date], int]:
    """Create a data_checker callable that queries Parquet storage.
    
    This factory creates the data_checker function required by
    database_validator and stream_requirements_coordinator.
    
    Args:
        parquet_storage: ParquetStorage instance (from DataManager)
        exchange_group: Exchange group for data
    
    Returns:
        Callable that returns bar count for (symbol, interval, start, end)
        
    Usage:
        >>> from app.managers.data_manager.parquet_storage import ParquetStorage
        >>> storage = ParquetStorage(exchange_group="US_EQUITY")
        >>> data_checker = create_parquet_data_checker(storage)
        >>> 
        >>> # Now use with validator
        >>> count = data_checker("AAPL", "1m", date(2025,7,2), date(2025,7,2))
        >>> print(f"Found {count} bars")
    
    Architecture Note:
        This uses DataManager's ParquetStorage API, not direct file access.
        For tests, you can write Parquet files directly (backdoor setup),
        but reading always goes through the proper API.
    """
    
    def data_checker(symbol: str, interval: str, start_date: date, end_date: date) -> int:
        """Check data availability in Parquet storage.
        
        Args:
            symbol: Stock symbol
            interval: Interval string (1s, 1m, 1d, quotes)
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
        
        Returns:
            Number of bars available (0 if none)
        """
        try:
            # Read bars using ParquetStorage API
            df = parquet_storage.read_bars(
                data_type=interval,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date
            )
            
            count = len(df)
            
            if count > 0:
                logger.debug(
                    f"[DATA_CHECKER] {symbol} {interval}: {count} bars "
                    f"({start_date} to {end_date})"
                )
            else:
                logger.debug(
                    f"[DATA_CHECKER] {symbol} {interval}: NO DATA "
                    f"({start_date} to {end_date})"
                )
            
            return count
            
        except Exception as e:
            logger.error(
                f"[DATA_CHECKER] Error checking {symbol} {interval}: {e}"
            )
            return 0
    
    return data_checker


def create_mock_data_checker(
    available_data: dict[tuple[str, str], int]
) -> Callable[[str, str, date, date], int]:
    """Create a mock data_checker for testing.
    
    Args:
        available_data: Dict mapping (symbol, interval) -> bar_count
                       Date range is ignored in mock
    
    Returns:
        Mock data_checker callable
        
    Usage:
        >>> # Setup: AAPL has 390 1m bars, GOOGL has 0
        >>> checker = create_mock_data_checker({
        ...     ("AAPL", "1m"): 390,
        ...     ("GOOGL", "1m"): 0,
        ... })
        >>> 
        >>> count = checker("AAPL", "1m", date(2025,7,2), date(2025,7,2))
        >>> assert count == 390
    """
    
    def mock_checker(symbol: str, interval: str, start_date: date, end_date: date) -> int:
        """Mock data checker."""
        key = (symbol.upper(), interval)
        return available_data.get(key, 0)
    
    return mock_checker
