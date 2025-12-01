"""Integration tests for database validator.

Tests Requirements: 13-17, 62, 64
"""

import pytest
from datetime import date
from unittest.mock import Mock

from app.threads.quality.database_validator import (
    validate_base_interval_availability,
    validate_all_symbols,
    get_available_base_intervals
)


# =============================================================================
# Single Symbol Validation Tests (Req 13-17)
# =============================================================================

class TestSingleSymbolValidation:
    """Test validation for a single symbol."""
    
    def test_data_exists_returns_true(self):
        """Test validation succeeds when data exists (Req 13)."""
        # Setup: Mock data_checker that returns count
        def mock_data_checker(symbol, interval, start, end):
            return 100  # 100 bars available
        
        # Test
        available, error = validate_base_interval_availability(
            symbol="AAPL",
            required_base_interval="1m",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            data_checker=mock_data_checker
        )
        
        # Verify
        assert available is True
        assert error is None
    
    def test_no_data_returns_false(self):
        """Test validation fails when no data exists (Req 16)."""
        # Setup: Mock data_checker that returns 0
        def mock_data_checker(symbol, interval, start, end):
            return 0  # No bars
        
        # Test
        available, error = validate_base_interval_availability(
            symbol="AAPL",
            required_base_interval="1m",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            data_checker=mock_data_checker
        )
        
        # Verify
        assert available is False
        assert error is not None
        assert "not available" in error  # Req 17
        assert "AAPL" in error  # Req 64
        assert "1m" in error  # Req 64
    
    def test_1s_interval_validation(self):
        """Test 1s interval can be validated."""
        def mock_data_checker(symbol, interval, start, end):
            return 50
        
        available, error = validate_base_interval_availability(
            symbol="AAPL",
            required_base_interval="1s",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            data_checker=mock_data_checker
        )
        
        assert available is True
        assert error is None
    
    def test_1d_interval_validation(self):
        """Test 1d interval can be validated."""
        def mock_data_checker(symbol, interval, start, end):
            return 10
        
        available, error = validate_base_interval_availability(
            symbol="AAPL",
            required_base_interval="1d",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            data_checker=mock_data_checker
        )
        
        assert available is True
        assert error is None
    
    def test_invalid_interval_returns_error(self):
        """Test invalid interval returns error (Req 64)."""
        def mock_data_checker(symbol, interval, start, end):
            return 100
        
        available, error = validate_base_interval_availability(
            symbol="AAPL",
            required_base_interval="5m",  # Not a base interval
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            data_checker=mock_data_checker
        )
        
        assert available is False
        assert "Invalid base interval" in error
        assert "5m" in error
    
    def test_data_source_error_handled(self):
        """Test data source errors are handled gracefully."""
        def mock_data_checker(symbol, interval, start, end):
            raise RuntimeError("Connection lost")
        
        available, error = validate_base_interval_availability(
            symbol="AAPL",
            required_base_interval="1m",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            data_checker=mock_data_checker
        )
        
        assert available is False
        assert "Error checking" in error
        assert "Connection lost" in error
    
    def test_date_range_filtering(self):
        """Test date range is passed to data_checker (Req 14)."""
        received_params = []
        
        def mock_data_checker(symbol, interval, start, end):
            received_params.append((symbol, interval, start, end))
            return 20
        
        start = date(2025, 1, 1)
        end = date(2025, 1, 10)
        
        validate_base_interval_availability(
            symbol="AAPL",
            required_base_interval="1m",
            start_date=start,
            end_date=end,
            data_checker=mock_data_checker
        )
        
        # Verify dates were passed
        assert len(received_params) == 1
        assert received_params[0] == ("AAPL", "1m", start, end)
    
    def test_error_message_includes_dates(self):
        """Test error message includes date range (Req 17, 64)."""
        def mock_data_checker(symbol, interval, start, end):
            return 0  # No data
        
        start = date(2025, 7, 1)
        end = date(2025, 7, 2)
        
        available, error = validate_base_interval_availability(
            symbol="TSLA",
            required_base_interval="1m",
            start_date=start,
            end_date=end,
            data_checker=mock_data_checker
        )
        
        assert "2025-07-01" in error
        assert "2025-07-02" in error
        assert "TSLA" in error


# =============================================================================
# Multi-Symbol Validation Tests (Req 15, 62)
# =============================================================================

class TestMultiSymbolValidation:
    """Test validation for multiple symbols."""
    
    def test_all_symbols_valid(self):
        """Test all symbols passing validation (Req 15)."""
        def mock_data_checker(symbol, interval, start, end):
            return 100  # All symbols have data
        
        valid, error = validate_all_symbols(
            symbols=["AAPL", "GOOGL", "MSFT"],
            required_base_interval="1m",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            data_checker=mock_data_checker
        )
        
        assert valid is True
        assert error is None
    
    def test_one_symbol_fails_all_fail(self):
        """Test one symbol failing causes all to fail (Req 62)."""
        def mock_data_checker(symbol, interval, start, end):
            # AAPL has data, TSLA doesn't
            return 100 if symbol == "AAPL" else 0
        
        valid, error = validate_all_symbols(
            symbols=["AAPL", "TSLA"],
            required_base_interval="1m",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            data_checker=mock_data_checker
        )
        
        assert valid is False
        assert "TSLA" in error
        assert "1m" in error
        assert "Cannot start session" in error  # Req 62
    
    def test_multiple_symbols_fail_all_listed(self):
        """Test all failing symbols are listed in error."""
        def mock_data_checker(symbol, interval, start, end):
            # AAPL and GOOGL have data, TSLA and NVDA don't
            return 100 if symbol in ["AAPL", "GOOGL"] else 0
        
        valid, error = validate_all_symbols(
            symbols=["AAPL", "TSLA", "GOOGL", "NVDA"],
            required_base_interval="1m",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            data_checker=mock_data_checker
        )
        
        assert valid is False
        assert "TSLA" in error
        assert "NVDA" in error
        assert "2 symbol(s) missing" in error
    
    def test_empty_symbols_list(self):
        """Test empty symbols list."""
        def mock_data_checker(symbol, interval, start, end):
            return 100
        
        valid, error = validate_all_symbols(
            symbols=[],
            required_base_interval="1m",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            data_checker=mock_data_checker
        )
        
        # Empty list means all symbols passed (vacuous truth)
        assert valid is True
        assert error is None


# =============================================================================
# Helper Function Tests
# =============================================================================

    def test_no_data_checker_returns_error(self):
        """Test validation fails when data_checker not provided."""
        available, error = validate_base_interval_availability(
            symbol="AAPL",
            required_base_interval="1m",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            data_checker=None  # No checker provided
        )
        
        assert available is False
        assert "No data source configured" in error


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestHelperFunctions:
    """Test helper functions for diagnostics."""
    
    def test_get_available_intervals(self):
        """Test getting list of available intervals."""
        def mock_data_checker(symbol, interval, start, end):
            # Has 1m and 1d, but not 1s
            return 100 if interval in ["1m", "1d"] else 0
        
        available = get_available_base_intervals(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            data_checker=mock_data_checker
        )
        
        assert "1m" in available
        assert "1d" in available
        assert "1s" not in available
    
    def test_no_available_intervals(self):
        """Test when no intervals are available."""
        def mock_data_checker(symbol, interval, start, end):
            return 0  # No data for any interval
        
        available = get_available_base_intervals(
            symbol="MISSING",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            data_checker=mock_data_checker
        )
        
        assert available == []
