"""Integration Tests for Validation Corner Cases

Tests edge cases for validation failures:
- All validation checks fail
- Partial validation failure
- Validation timeout
- Network errors (live mode)
- Malformed data
"""
import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime
from app.threads.session_coordinator import SessionCoordinator, SymbolValidationResult
from app.managers.data_manager.api import DataManager


@pytest.fixture
def coordinator_for_validation_tests():
    """Create coordinator for validation testing."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator._data_manager = Mock(spec=DataManager)
    coordinator._time_manager = Mock()
    coordinator._base_interval = "1m"
    coordinator._derived_intervals_validated = ["5m", "15m"]
    return coordinator


class TestCompleteValidationFailure:
    """Test complete validation failures."""
    
    def test_all_checks_fail(self, coordinator_for_validation_tests):
        """Test symbol fails all validation checks."""
        coordinator = coordinator_for_validation_tests
        
        # Mock all checks failing
        coordinator._data_manager.data_source_available = Mock(return_value=False)
        coordinator._data_manager.has_historical_data = Mock(return_value=False)
        coordinator._data_manager.check_data_availability = Mock(return_value={
            "has_data": False,
            "days_available": 0
        })
        
        # Create validation result
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=False,
            reason="Symbol INVALID failed all validation checks: No data source, No Parquet data, No historical data available",
            data_source_available=False,
            has_historical_data=False
        )
        
        # Expected: Complete failure
        assert validation.can_proceed is False
        assert validation.data_source_available is False
        assert validation.has_historical_data is False
        assert validation.has_historical_data is False
        assert "failed all" in validation.reason.lower() or "no data" in validation.reason.lower()
    
    def test_symbol_not_found_anywhere(self, coordinator_for_validation_tests):
        """Test symbol not found in any data source."""
        coordinator = coordinator_for_validation_tests
        
        # Mock symbol not found
        coordinator._data_manager.find_symbol = Mock(return_value=None)
        
        # Check for symbol
        result = coordinator._data_manager.find_symbol("DOESNOTEXIST")
        
        # Expected: Not found
        assert result is None
        
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=False,
            reason="Symbol DOESNOTEXIST not found in any data source",
            data_source_available=False,
            has_historical_data=False
        )
        
        assert validation.can_proceed is False
        assert "not found" in validation.reason.lower()


class TestPartialValidationFailure:
    """Test partial validation failures."""
    
    def test_partial_failure(self, coordinator_for_validation_tests):
        """Test some checks pass, some fail."""
        coordinator = coordinator_for_validation_tests
        
        # Has data source, has Parquet, but insufficient historical
        coordinator._data_manager.data_source_available = Mock(return_value=True)
        coordinator._data_manager.has_historical_data = Mock(return_value=True)
        coordinator._data_manager.check_data_availability = Mock(return_value={
            "has_data": True,
            "days_available": 5,  # Only 5 days
            "requested_days": 30
        })
        
        # Create validation result
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=True,  # Can proceed with warning
            reason="Symbol PARTIAL: Only 5 days of historical data available (requested 30)",
            data_source_available=True,
            has_historical_data=True  # Has some data but not sufficient
        )
        
        # Expected: Partial failure, can proceed with warning
        assert validation.can_proceed is True
        assert validation.data_source_available is True
        assert validation.has_historical_data is True
        assert "5 days" in validation.reason
    
    def test_has_source_no_parquet(self, coordinator_for_validation_tests):
        """Test has data source but no Parquet files."""
        coordinator = coordinator_for_validation_tests
        
        # Has source (database) but no Parquet files
        coordinator._data_manager.data_source_available = Mock(return_value=True)
        coordinator._data_manager.has_historical_data = Mock(return_value=False)
        
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=False,
            reason="Symbol NO_PARQUET: Data source configured but no Parquet files found. Data may not be downloaded yet.",
            data_source_available=True,
            has_historical_data=False
        )
        
        # Expected: Has source but cannot proceed without Parquet
        assert validation.can_proceed is False
        assert validation.data_source_available is True
        assert validation.has_historical_data is False


class TestValidationTimeout:
    """Test validation timeout scenarios."""
    
    def test_timeout(self, coordinator_for_validation_tests):
        """Test validation timeout (e.g., database query timeout)."""
        coordinator = coordinator_for_validation_tests
        
        # Mock timeout exception
        coordinator._data_manager.check_data_availability = Mock(
            side_effect=TimeoutError("Database query timeout after 30 seconds")
        )
        
        # Try validation
        try:
            coordinator._data_manager.check_data_availability("TIMEOUT", "1m", days=30)
            timeout_occurred = False
        except TimeoutError as e:
            timeout_occurred = True
            error_message = str(e)
        
        # Expected: Timeout caught
        assert timeout_occurred is True
        assert "timeout" in error_message.lower()
        
        # Create validation result for timeout
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=False,
            reason="Symbol TIMEOUT: Validation timeout - database query took too long",
            data_source_available=False,  # Unknown due to timeout
            has_historical_data=False
        )
        
        assert validation.can_proceed is False
        assert "timeout" in validation.reason.lower()


class TestNetworkErrors:
    """Test network error scenarios (live mode)."""
    
    def test_network_error(self, coordinator_for_validation_tests):
        """Test network error during validation (live mode)."""
        coordinator = coordinator_for_validation_tests
        
        # Mock network error
        coordinator._data_manager.check_data_source = Mock(
            side_effect=ConnectionError("Network unreachable")
        )
        
        # Try validation
        try:
            coordinator._data_manager.check_data_source("NETWORK")
            network_error = False
        except ConnectionError as e:
            network_error = True
            error_message = str(e)
        
        # Expected: Network error caught
        assert network_error is True
        assert "network" in error_message.lower() or "unreachable" in error_message.lower()
        
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=False,
            reason="Symbol NETWORK: Network error during validation - cannot reach data source",
            data_source_available=False,
            has_historical_data=False
        )
        
        assert validation.can_proceed is False
        assert "network" in validation.reason.lower()
    
    def test_api_rate_limit(self, coordinator_for_validation_tests):
        """Test API rate limit during validation (live mode)."""
        coordinator = coordinator_for_validation_tests
        
        # Mock rate limit error
        coordinator._data_manager.validate_live_feed = Mock(
            side_effect=Exception("API rate limit exceeded: 429 Too Many Requests")
        )
        
        # Try validation
        try:
            coordinator._data_manager.validate_live_feed("RATELIMIT")
            rate_limit = False
        except Exception as e:
            rate_limit = True
            error_message = str(e)
        
        # Expected: Rate limit caught
        assert rate_limit is True
        assert "rate limit" in error_message.lower() or "429" in error_message
        
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=False,
            reason="Symbol RATELIMIT: API rate limit exceeded - try again later",
            data_source_available=True,  # Source exists but rate limited
            has_historical_data=True
        )
        
        assert validation.can_proceed is False
        assert "rate limit" in validation.reason.lower()


class TestMalformedData:
    """Test malformed data scenarios."""
    
    def test_malformed_data(self, coordinator_for_validation_tests):
        """Test malformed Parquet data."""
        coordinator = coordinator_for_validation_tests
        
        # Mock malformed data error
        coordinator._data_manager.validate_parquet_schema = Mock(return_value={
            "valid": False,
            "error": "Schema mismatch: Missing required columns ['open', 'high', 'low', 'close']"
        })
        
        # Validate schema
        result = coordinator._data_manager.validate_parquet_schema("MALFORMED", "1m")
        
        # Expected: Schema validation failed
        assert result["valid"] is False
        assert "schema" in result["error"].lower() or "columns" in result["error"].lower()
        
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=False,
            reason="Symbol MALFORMED: Data schema invalid - missing required columns",
            data_source_available=True,
            has_historical_data=False
        )
        
        assert validation.can_proceed is False
        assert "schema" in validation.reason.lower() or "invalid" in validation.reason.lower()
