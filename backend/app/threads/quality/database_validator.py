"""Database Availability Validator

Validates that required base intervals exist in data storage for backtesting.

Key Principle:
    Data storage MUST have the exact required base interval. No fallbacks.
    If 1s required but only 1m available → FAIL.

Requirements Covered:
    13-17: Database validation with exact matching
    64: Clear error messages
    
Note:
    This module provides validation interface. Actual data checking will
    be implemented via DataManager integration in later phases.
"""

from typing import Tuple, Optional, Callable
from datetime import date

from app.logger import logger


# =============================================================================
# Database Validation
# =============================================================================

def validate_base_interval_availability(
    symbol: str,
    required_base_interval: str,
    start_date: date,
    end_date: date,
    data_checker: Optional[Callable[[str, str, date, date], int]] = None
) -> Tuple[bool, Optional[str]]:
    """Check if database has the required base interval for a symbol.
    
    This is a strict validation - database must have EXACTLY the interval
    we need. No fallbacks, no alternatives.
    
    Args:
        symbol: Symbol to check (e.g., "AAPL")
        required_base_interval: Required interval ("1s", "1m", or "1d" only)
        start_date: Start of date range (from TimeManager)
        end_date: End of date range (from TimeManager)
        data_checker: Optional callable that returns count of bars available
                     Signature: (symbol, interval, start_date, end_date) -> int
                     If None, returns error (no data source configured)
        
    Returns:
        Tuple of (available, error_message)
        - available: True if data exists, False otherwise
        - error_message: None if available, error string if not
        
    Requirements:
        13: Check exact required interval only
        14: Use TimeManager dates for range
        15: Multi-symbol validation (called per symbol)
        16: Fail fast if not available
        17: Clear error message
        64: Actionable error text
        
    Examples:
        >>> # Database has 1m data for AAPL
        >>> available, error = validate_base_interval_availability(
        ...     "AAPL", "1m", date(2025,1,1), date(2025,1,2), session
        ... )
        >>> available
        True
        >>> error
        None
        
        >>> # Database missing 1s data for RIVN
        >>> available, error = validate_base_interval_availability(
        ...     "RIVN", "1s", date(2025,1,1), date(2025,1,2), session
        ... )
        >>> available
        False
        >>> error
        'Required interval 1s not available for RIVN (2025-01-01 to 2025-01-02)'
    """
    # Validate interval
    if required_base_interval not in ["1s", "1m", "1d"]:
        return False, f"Invalid base interval: {required_base_interval} (must be 1s, 1m, or 1d)"
    
    # Check if data_checker provided
    if data_checker is None:
        error_msg = "No data source configured (data_checker not provided)"
        logger.error(error_msg)
        return False, error_msg
    
    try:
        # Call data_checker to get count
        # Requirement 14: Use TimeManager dates (passed as parameters)
        count = data_checker(symbol, required_base_interval, start_date, end_date)
        
        if count > 0:
            # Data exists!
            logger.debug(
                f"✓ Data storage has {required_base_interval} data for {symbol}: "
                f"{count} bars ({start_date} to {end_date})"
            )
            return True, None
        else:
            # No data found
            # Requirement 17, 64: Clear, actionable error message
            error_msg = (
                f"Required interval {required_base_interval} not available for {symbol} "
                f"({start_date} to {end_date})"
            )
            logger.warning(f"✗ {error_msg}")
            return False, error_msg
            
    except Exception as e:
        # Data source error
        error_msg = (
            f"Error checking {required_base_interval} for {symbol}: {str(e)}"
        )
        logger.error(error_msg)
        return False, error_msg


def validate_all_symbols(
    symbols: list[str],
    required_base_interval: str,
    start_date: date,
    end_date: date,
    data_checker: Optional[Callable[[str, str, date, date], int]] = None
) -> Tuple[bool, Optional[str]]:
    """Validate that ALL symbols have the required base interval.
    
    All-or-nothing check - if ANY symbol is missing data, validation fails.
    
    Args:
        symbols: List of symbols to check
        required_base_interval: Required interval for all symbols
        start_date: Start of date range
        end_date: End of date range
        db_session: Database session
        
    Returns:
        Tuple of (all_available, error_message)
        
    Requirements:
        15: Multi-symbol validation
        62: All symbols must pass or session fails
        
    Examples:
        >>> # All symbols have data
        >>> valid, error = validate_all_symbols(
        ...     ["AAPL", "GOOGL"], "1m", start, end, session
        ... )
        >>> valid
        True
        
        >>> # One symbol missing data
        >>> valid, error = validate_all_symbols(
        ...     ["AAPL", "MISSING"], "1m", start, end, session
        ... )
        >>> valid
        False
        >>> "MISSING" in error
        True
    """
    missing_symbols = []
    
    for symbol in symbols:
        available, error = validate_base_interval_availability(
            symbol, required_base_interval, start_date, end_date, data_checker
        )
        
        if not available:
            missing_symbols.append((symbol, error))
    
    if missing_symbols:
        # Requirement 62: All or nothing
        error_lines = [
            f"Cannot start session: {len(missing_symbols)} symbol(s) missing {required_base_interval} data:"
        ]
        for symbol, error in missing_symbols:
            error_lines.append(f"  - {symbol}: {error}")
        
        error_msg = "\n".join(error_lines)
        logger.error(error_msg)
        return False, error_msg
    
    # All symbols have data
    logger.info(
        f"✓ All {len(symbols)} symbols have {required_base_interval} data "
        f"({start_date} to {end_date})"
    )
    return True, None


def get_available_base_intervals(
    symbol: str,
    start_date: date,
    end_date: date,
    data_checker: Optional[Callable[[str, str, date, date], int]] = None
) -> list[str]:
    """Get list of available base intervals for a symbol.
    
    Helper function for diagnostics and error messages.
    Not used in validation (we check exact interval only).
    
    Args:
        symbol: Symbol to check
        start_date: Start of date range
        end_date: End of date range
        db_session: Database session
        
    Returns:
        List of available base intervals (e.g., ["1m", "1d"])
        
    Examples:
        >>> get_available_base_intervals("AAPL", start, end, session)
        ["1m", "1d"]  # Has 1m and 1d but not 1s
    """
    available = []
    
    for interval in ["1s", "1m", "1d"]:
        has_data, _ = validate_base_interval_availability(
            symbol, interval, start_date, end_date, data_checker
        )
        if has_data:
            available.append(interval)
    
    return available
