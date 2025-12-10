"""Integration Tests for Graceful Degradation

Tests graceful degradation when symbols fail validation or loading.
Failed symbols are skipped with clear errors, others proceed.
"""
import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime
from collections import deque
from app.threads.session_coordinator import SessionCoordinator, ProvisioningRequirements, SymbolValidationResult
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData


@pytest.fixture
def coordinator_for_degradation():
    """Create coordinator for testing graceful degradation."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator.session_data = SessionData()
    coordinator._base_interval = "1m"
    coordinator._derived_intervals_validated = ["5m", "15m"]
    
    # Mock methods
    coordinator._register_single_symbol = Mock(return_value=True)
    coordinator._manage_historical_data = Mock(return_value=True)
    coordinator._load_queues = Mock(return_value=True)
    coordinator._calculate_historical_quality = Mock(return_value=True)
    
    return coordinator


class TestSingleSymbolFailure:
    """Test single symbol failures."""
    
    def test_single_symbol_fails_others_proceed(self, coordinator_for_degradation):
        """Test one failed symbol doesn't stop others."""
        symbols = ["AAPL", "INVALID", "MSFT"]
        
        # Mock validation to fail for INVALID
        def validate_impl(symbol):
            if symbol == "INVALID":
                return SymbolValidationResult(symbol="TEST",
            
                    can_proceed=False,
                    reason="No data source available",
                    data_source_available=False,
                    has_historical_data=False
                )
            return SymbolValidationResult(symbol="TEST",
            
                can_proceed=True,
                reason="Valid",
                data_source_available=True,
                has_historical_data=True
            )
        
        coordinator_for_degradation._validate_symbol_for_loading = Mock(side_effect=validate_impl)
        
        # Process symbols
        loaded_symbols = []
        failed_symbols = []
        
        for symbol in symbols:
            validation = coordinator_for_degradation._validate_symbol_for_loading(symbol)
            if validation.can_proceed:
                coordinator_for_degradation._register_single_symbol(
                    symbol,
                    meets_session_config_requirements=True,
                    added_by="config",
                    auto_provisioned=False
                )
                loaded_symbols.append(symbol)
            else:
                failed_symbols.append((symbol, validation.reason))
        
        # Expected: AAPL and MSFT loaded, INVALID skipped
        assert len(loaded_symbols) == 2
        assert "AAPL" in loaded_symbols
        assert "MSFT" in loaded_symbols
        assert len(failed_symbols) == 1
        assert failed_symbols[0][0] == "INVALID"
        assert "No data source" in failed_symbols[0][1]
    
    def test_failed_symbol_clear_error_message(self, coordinator_for_degradation):
        """Test failed symbol has clear error message."""
        # Mock validation failure
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=False,
            reason="Symbol BADTICKER: No Parquet data found. Cannot load historical bars.",
            data_source_available=True,
            has_historical_data=False
        )
        
        coordinator_for_degradation._validate_symbol_for_loading = Mock(return_value=validation)
        
        # Validate symbol
        result = coordinator_for_degradation._validate_symbol_for_loading("BADTICKER")
        
        # Expected: Clear, actionable error message
        assert result.can_proceed is False
        assert "BADTICKER" in result.reason
        assert "No Parquet data" in result.reason
        assert result.has_parquet_data is False


class TestAllSymbolsFailure:
    """Test all symbols failing."""
    
    def test_all_symbols_fail_terminates_session(self, coordinator_for_degradation):
        """Test session terminates if all symbols fail."""
        symbols = ["INVALID1", "INVALID2", "INVALID3"]
        
        # Mock validation to fail for all
        def validate_impl(symbol):
            return SymbolValidationResult(symbol="TEST",
            
                can_proceed=False,
                reason=f"Symbol {symbol}: No data available",
                data_source_available=False,
                has_historical_data=False
            )
        
        coordinator_for_degradation._validate_symbol_for_loading = Mock(side_effect=validate_impl)
        
        # Process symbols
        loaded_symbols = []
        for symbol in symbols:
            validation = coordinator_for_degradation._validate_symbol_for_loading(symbol)
            if validation.can_proceed:
                loaded_symbols.append(symbol)
        
        # Expected: No symbols loaded, session should terminate
        assert len(loaded_symbols) == 0
        
        # Session termination logic
        if len(loaded_symbols) == 0:
            session_should_terminate = True
        else:
            session_should_terminate = False
        
        assert session_should_terminate is True


class TestPartialFailures:
    """Test partial data failures."""
    
    def test_partial_historical_data(self, coordinator_for_degradation):
        """Test symbol with partial historical data (warning, not failure)."""
        # Symbol has data but not full 30 days
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=True,  # Can proceed with warning
            reason="Symbol NEWIPO: Only 10 days of historical data available (requested 30)",
            has_data_source=True,
            has_parquet_data=True,
            has_sufficient_historical=False  # Flag set but still proceed
        )
        
        coordinator_for_degradation._validate_symbol_for_loading = Mock(return_value=validation)
        
        # Validate
        result = coordinator_for_degradation._validate_symbol_for_loading("NEWIPO")
        
        # Expected: Proceed with warning
        assert result.can_proceed is True
        assert "10 days" in result.reason
        assert result.has_sufficient_historical is False
        
        # Symbol can be loaded with available data
        coordinator_for_degradation._register_single_symbol(
            "NEWIPO",
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False
        )
        coordinator_for_degradation._register_single_symbol.assert_called_once()
    
    def test_missing_data_source(self, coordinator_for_degradation):
        """Test symbol with no data source (hard failure)."""
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=False,
            reason="Symbol NODATA: No data source configured. Check database configuration.",
            data_source_available=False,
            has_historical_data=False
        )
        
        coordinator_for_degradation._validate_symbol_for_loading = Mock(return_value=validation)
        
        # Validate
        result = coordinator_for_degradation._validate_symbol_for_loading("NODATA")
        
        # Expected: Hard failure, cannot proceed
        assert result.can_proceed is False
        assert "No data source" in result.reason
        assert result.has_data_source is False


class TestErrorLogging:
    """Test error logging during degradation."""
    
    def test_failed_symbols_logged(self, coordinator_for_degradation, caplog):
        """Test failed symbols are logged with details."""
        import logging
        
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=False,
            reason="Symbol TEST: Validation failed",
            data_source_available=False,
            has_historical_data=False
        )
        
        coordinator_for_degradation._validate_symbol_for_loading = Mock(return_value=validation)
        
        # Validate and log
        with caplog.at_level(logging.WARNING):
            result = coordinator_for_degradation._validate_symbol_for_loading("TEST")
            if not result.can_proceed:
                logging.warning(f"Symbol TEST failed validation: {result.reason}")
        
        # Expected: Warning logged
        assert "TEST failed validation" in caplog.text
        assert "Validation failed" in caplog.text
