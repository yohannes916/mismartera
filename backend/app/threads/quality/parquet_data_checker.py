"""Parquet Data Checker for Stream Requirements Validation

Creates data_checker callables that query data via DataManager API.
Follows architecture: Use DataManager API, not direct storage access.
"""

from typing import Callable
from datetime import date, datetime, time

from app.logger import logger


def create_data_manager_checker(
    data_manager
) -> Callable[[str, str, date, date], int]:
    """Create a data_checker callable that queries via DataManager API.
    
    This factory creates the data_checker function required by
    database_validator and stream_requirements_coordinator.
    
    Args:
        data_manager: DataManager instance (from system_manager)
    
    Returns:
        Callable that returns bar count for (symbol, interval, start, end)
        
    Usage:
        >>> data_manager = system_manager.get_data_manager()
        >>> data_checker = create_data_manager_checker(data_manager)
        >>> 
        >>> # Now use with validator
        >>> count = data_checker("AAPL", "1m", date(2025,7,2), date(2025,7,2))
        >>> print(f"Found {count} bars")
    
    Architecture Note:
        This uses DataManager's public API (get_bars), not direct storage access.
        DataManager handles Parquet reading internally.
    """
    
    def data_checker(symbol: str, interval: str, start_date: date, end_date: date) -> int:
        """Check data availability via DataManager API.
        
        Args:
            symbol: Stock symbol
            interval: Interval string (1s, 1m, 1d, quotes)
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
        
        Returns:
            Number of bars available (0 if none)
        """
        try:
            # Convert dates to datetime (full day range)
            start_dt = datetime.combine(start_date, time.min)
            end_dt = datetime.combine(end_date, time.max)
            
            # Use DataManager API to get bars
            # Note: session=None since DataManager doesn't use DB anymore
            bars = data_manager.get_bars(
                session=None,  # Not needed for Parquet storage
                symbol=symbol,
                start=start_dt,
                end=end_dt,
                interval=interval,
                regular_hours_only=False  # Get all data for validation
            )
            
            count = len(bars) if bars else 0
            
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


def create_parquet_data_checker(
    parquet_storage
) -> Callable[[str, str, date, date], int]:
    """Create a data_checker for tests using direct ParquetStorage access.
    
    **FOR TESTS ONLY** - Uses backdoor ParquetStorage access.
    Production code should use create_data_manager_checker().
    
    Args:
        parquet_storage: ParquetStorage instance
    
    Returns:
        Callable that returns bar count for (symbol, interval, start, end)
        
    Note:
        This is kept for E2E tests that write Parquet files directly (backdoor setup)
        but want to read through an API-like interface for validation testing.
    """
    
    def data_checker(symbol: str, interval: str, start_date: date, end_date: date) -> int:
        """Check data availability in Parquet storage (test backdoor)."""
        try:
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
