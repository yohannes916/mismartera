"""Integration tests for StreamRequirementsCoordinator.

Tests the integration of requirement analyzer and database validator.
"""

import pytest
from datetime import date
from unittest.mock import Mock

from app.threads.quality.stream_requirements_coordinator import (
    StreamRequirementsCoordinator,
    ValidationResult
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_session_config():
    """Create mock session config."""
    config = Mock()
    config.mode = "backtest"  # "backtest" or "live"
    config.session_data_config = Mock()
    config.session_data_config.symbols = ["AAPL", "GOOGL"]
    config.session_data_config.streams = ["1m", "5m"]
    return config


@pytest.fixture
def mock_time_manager():
    """Create mock time manager."""
    time_mgr = Mock()
    time_mgr.backtest_start_date = date(2025, 1, 1)
    time_mgr.backtest_end_date = date(2025, 1, 2)
    return time_mgr


# =============================================================================
# Configuration Validation Tests
# =============================================================================

class TestConfigurationValidation:
    """Test configuration validation step."""
    
    def test_invalid_config_fails_early(self, mock_session_config, mock_time_manager):
        """Test invalid config fails before database check."""
        # Setup: Invalid config (ticks not supported)
        mock_session_config.session_data_config.streams = ["1m", "ticks"]
        
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        # No data_checker needed - should fail on config
        result = coordinator.validate_requirements()
        
        assert result.valid is False
        assert "ticks" in result.error_message.lower()
        assert result.required_base_interval is None
    
    def test_valid_config_passes(self, mock_session_config, mock_time_manager):
        """Test valid config passes validation."""
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        # Without data_checker, should pass config validation
        result = coordinator.validate_requirements()
        
        assert result.valid is True
        assert result.required_base_interval == "1m"
        assert "5m" in result.derivable_intervals


# =============================================================================
# Requirement Analysis Tests
# =============================================================================

class TestRequirementAnalysis:
    """Test requirement analysis step."""
    
    def test_base_interval_determined(self, mock_session_config, mock_time_manager):
        """Test base interval is correctly determined."""
        mock_session_config.session_data_config.streams = ["5m", "15m"]
        
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        result = coordinator.validate_requirements()
        
        assert result.valid is True
        assert result.required_base_interval == "1m"
        assert set(result.derivable_intervals) == {"5m", "15m"}
    
    def test_derivable_intervals_identified(self, mock_session_config, mock_time_manager):
        """Test derivable intervals are identified."""
        mock_session_config.session_data_config.streams = ["1m", "5m", "1h"]
        
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        result = coordinator.validate_requirements()
        
        assert result.required_base_interval == "1m"
        assert "5m" in result.derivable_intervals
        assert "1h" in result.derivable_intervals
        assert "1m" not in result.derivable_intervals  # Not derivable, it's the base


# =============================================================================
# Database Validation Tests
# =============================================================================

class TestDatabaseValidation:
    """Test database validation step."""
    
    def test_data_available_passes(self, mock_session_config, mock_time_manager):
        """Test validation passes when data available."""
        def mock_data_checker(symbol, interval, start, end):
            return 100  # All symbols have data
        
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        result = coordinator.validate_requirements(mock_data_checker)
        
        assert result.valid is True
        assert result.error_message is None
    
    def test_missing_data_fails(self, mock_session_config, mock_time_manager):
        """Test validation fails when data missing."""
        def mock_data_checker(symbol, interval, start, end):
            # GOOGL has no data
            return 100 if symbol == "AAPL" else 0
        
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        result = coordinator.validate_requirements(mock_data_checker)
        
        assert result.valid is False
        assert "GOOGL" in result.error_message
        assert result.required_base_interval == "1m"  # Still set for diagnostics
    
    def test_no_data_checker_skips_db_validation(self, mock_session_config, mock_time_manager):
        """Test that without data_checker, DB validation is skipped."""
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        # No data_checker provided
        result = coordinator.validate_requirements()
        
        # Should pass (config valid, analysis done, DB check skipped)
        assert result.valid is True
        assert result.required_base_interval == "1m"
    
    def test_date_range_from_time_manager(self, mock_session_config, mock_time_manager):
        """Test that date range comes from TimeManager."""
        received_params = []
        
        def mock_data_checker(symbol, interval, start, end):
            received_params.append((start, end))
            return 100
        
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        result = coordinator.validate_requirements(mock_data_checker)
        
        # Should use TimeManager dates
        assert len(received_params) > 0
        for start, end in received_params:
            assert start == date(2025, 1, 1)
            assert end == date(2025, 1, 2)


# =============================================================================
# Integration Tests
# =============================================================================

class TestFullIntegration:
    """Test full validation flow."""
    
    def test_complete_success_flow(self, mock_session_config, mock_time_manager):
        """Test complete successful validation."""
        def mock_data_checker(symbol, interval, start, end):
            return 100
        
        mock_session_config.session_data_config.streams = ["1m", "5m", "quotes"]
        
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        result = coordinator.validate_requirements(mock_data_checker)
        
        # All steps pass
        assert result.valid is True
        assert result.required_base_interval == "1m"
        assert "5m" in result.derivable_intervals
        assert "quotes" in result.requirements.explicit_intervals
        assert result.error_message is None
    
    def test_complete_failure_flow(self, mock_session_config, mock_time_manager):
        """Test complete failure flow."""
        def mock_data_checker(symbol, interval, start, end):
            return 0  # No data
        
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        result = coordinator.validate_requirements(mock_data_checker)
        
        # DB validation fails
        assert result.valid is False
        assert result.error_message is not None
        assert "Cannot start session" in result.error_message
    
    def test_wrong_interval_available(self, mock_session_config, mock_time_manager):
        """Test when wrong interval is available."""
        def mock_data_checker(symbol, interval, start, end):
            # Only 1d available, but we need 1m
            return 100 if interval == "1d" else 0
        
        mock_session_config.session_data_config.streams = ["1m", "5m"]
        
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        result = coordinator.validate_requirements(mock_data_checker)
        
        # Should fail - need 1m, only have 1d
        assert result.valid is False
        assert "1m" in result.error_message


# =============================================================================
# Helper Methods Tests
# =============================================================================

class TestHelperMethods:
    """Test helper methods."""
    
    def test_get_validation_summary(self, mock_session_config, mock_time_manager):
        """Test validation summary."""
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        summary = coordinator.get_validation_summary()
        
        assert summary["symbols"] == ["AAPL", "GOOGL"]
        assert summary["streams"] == ["1m", "5m"]
        assert "2025-01-01" in summary["start_date"]
        assert "2025-01-02" in summary["end_date"]
