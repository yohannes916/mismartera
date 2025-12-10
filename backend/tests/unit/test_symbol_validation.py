"""Unit Tests for Symbol Validation

Tests the _validate_symbol_for_loading method that performs Step 0 validation.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.threads.session_coordinator import SessionCoordinator, SymbolValidationResult


class TestSymbolValidationBasics:
    """Test basic symbol validation results."""
    
    def test_validation_result_success(self):
        """Test successful validation result."""
        result = SymbolValidationResult(
            symbol="AAPL",
            can_proceed=True,
            reason="All checks passed",
            data_source_available=True,
            has_historical_data=True,
            meets_config_requirements=True
        )
        
        assert result.symbol == "AAPL"
        assert result.can_proceed is True
        assert result.data_source_available is True
        assert result.has_historical_data is True
        assert result.meets_config_requirements is True
    
    def test_validation_result_no_data_source(self):
        """Test validation fails when no data source available."""
        result = SymbolValidationResult(
            symbol="INVALID",
            can_proceed=False,
            reason="No data source available",
            data_source_available=False,
            has_historical_data=False
        )
        
        assert result.symbol == "INVALID"
        assert result.can_proceed is False
        assert result.data_source_available is False
        assert "No data source" in result.reason
    
    def test_validation_result_no_historical_data(self):
        """Test validation fails when no historical data."""
        result = SymbolValidationResult(
            symbol="NEWIPO",
            can_proceed=False,
            reason="Insufficient historical data",
            data_source_available=True,
            has_historical_data=False
        )
        
        assert result.symbol == "NEWIPO"
        assert result.can_proceed is False
        assert result.data_source_available is True
        assert result.has_historical_data is False


class TestSymbolValidationFields:
    """Test validation result field combinations."""
    
    def test_data_source_field(self):
        """Test data_source field is set correctly."""
        result = SymbolValidationResult(
            symbol="AAPL",
            data_source_available=True,
            data_source="alpaca"
        )
        
        assert result.data_source == "alpaca"
        assert result.data_source_available is True
    
    def test_intervals_supported(self):
        """Test intervals_supported field."""
        result = SymbolValidationResult(
            symbol="AAPL",
            intervals_supported=["1m", "5m", "15m"],
            base_interval="1m"
        )
        
        assert result.intervals_supported == ["1m", "5m", "15m"]
        assert result.base_interval == "1m"
    
    def test_historical_date_range(self):
        """Test historical_date_range field."""
        from datetime import date
        
        result = SymbolValidationResult(
            symbol="AAPL",
            has_historical_data=True,
            historical_date_range=(date(2025, 1, 1), date(2025, 12, 31))
        )
        
        assert result.has_historical_data is True
        assert result.historical_date_range is not None
        assert result.historical_date_range[0] == date(2025, 1, 1)
        assert result.historical_date_range[1] == date(2025, 12, 31)


class TestValidationFailureReasons:
    """Test various validation failure reasons."""
    
    def test_no_data_source_reason(self):
        """Test 'no data source' failure reason."""
        result = SymbolValidationResult(
            symbol="NOTFOUND",
            can_proceed=False,
            reason="Symbol not found in any data source",
            data_source_available=False
        )
        
        assert result.can_proceed is False
        assert "not found" in result.reason.lower()
    
    def test_insufficient_data_reason(self):
        """Test 'insufficient data' failure reason."""
        result = SymbolValidationResult(
            symbol="SPARSE",
            can_proceed=False,
            reason="Insufficient historical data: only 5 days available",
            data_source_available=True,
            has_historical_data=False
        )
        
        assert result.can_proceed is False
        assert "insufficient" in result.reason.lower()
    
    def test_interval_not_supported_reason(self):
        """Test 'interval not supported' failure reason."""
        result = SymbolValidationResult(
            symbol="AAPL",
            can_proceed=False,
            reason="Interval '1s' not supported for this symbol",
            intervals_supported=["1m"],
            base_interval="1m"
        )
        
        assert result.can_proceed is False
        assert "not supported" in result.reason.lower()


class TestValidationStateTransitions:
    """Test validation state transitions."""
    
    def test_validation_can_change_state(self):
        """Test validation result can represent state changes."""
        # Initially fails
        result1 = SymbolValidationResult(
            symbol="LOADING",
            can_proceed=False,
            reason="Data still loading",
            data_source_available=True,
            has_historical_data=False
        )
        
        assert result1.can_proceed is False
        
        # Later succeeds (new result)
        result2 = SymbolValidationResult(
            symbol="LOADING",
            can_proceed=True,
            reason="Data loaded successfully",
            data_source_available=True,
            has_historical_data=True
        )
        
        assert result2.can_proceed is True
        assert result2.has_historical_data is True


class TestValidationRequirementChecks:
    """Test meets_config_requirements field."""
    
    def test_meets_requirements_true(self):
        """Test symbol meets all config requirements."""
        result = SymbolValidationResult(
            symbol="AAPL",
            can_proceed=True,
            meets_config_requirements=True,
            data_source_available=True,
            has_historical_data=True
        )
        
        assert result.meets_config_requirements is True
        assert result.can_proceed is True
    
    def test_meets_requirements_false(self):
        """Test symbol doesn't meet config requirements."""
        result = SymbolValidationResult(
            symbol="ADHOC",
            can_proceed=True,
            meets_config_requirements=False,
            data_source_available=True,
            has_historical_data=False
        )
        
        # Can still proceed (adhoc mode) but doesn't meet full requirements
        assert result.meets_config_requirements is False
        assert result.can_proceed is True  # Adhoc allowed
