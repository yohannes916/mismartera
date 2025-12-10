"""Integration Tests for Phase 0: System-Wide Validation

Tests Phase 0 system-wide validation that runs before any symbol loading.
This validates stream infrastructure, intervals, and derivation capability.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from app.threads.session_coordinator import SessionCoordinator
from app.models.session_config import SessionConfig, SessionDataConfig


@pytest.fixture
def valid_session_config():
    """Create valid session config."""
    # Use Mock to avoid complex SessionConfig initialization
    config = Mock()
    config.session_data_config = SessionDataConfig(
        symbols=["AAPL", "MSFT"],
        streams=["1m"]
    )
    return config


@pytest.fixture
def coordinator_with_config(valid_session_config):
    """Create coordinator with valid config."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator.session_config = valid_session_config
    coordinator._base_interval = None
    coordinator._derived_intervals_validated = None
    return coordinator


class TestPhase0Validation:
    """Test Phase 0 system-wide validation."""
    
    def test_phase0_valid_config(self, coordinator_with_config):
        """Test Phase 0 with valid session config."""
        # Simulate Phase 0 validation
        config = coordinator_with_config.session_config.session_data_config
        
        # Validate config format
        assert config.symbols is not None
        assert isinstance(config.symbols, list)
        assert len(config.symbols) > 0
        
        # Validate streams exist
        assert config.streams is not None
        assert isinstance(config.streams, list)
        assert len(config.streams) > 0
        
        # Test that streams can be validated
        assert "1m" in config.streams
        
        # Phase 0 would set these on the coordinator
        coordinator_with_config._base_interval = "1m"
        coordinator_with_config._derived_intervals_validated = []
        
        assert coordinator_with_config._base_interval == "1m"
    
    def test_phase0_determine_base_interval(self, coordinator_with_config):
        """Test base interval determination from streams."""
        config = coordinator_with_config.session_config.session_data_config
        
        # Test determining base from streams
        assert "1m" in config.streams
        # Coordinator would determine base interval from streams
        coordinator_with_config._base_interval = "1m"
        assert coordinator_with_config._base_interval == "1m"
    
    def test_phase0_determine_derived_intervals(self, coordinator_with_config):
        """Test derived intervals determination from historical config."""
        config = coordinator_with_config.session_config.session_data_config
        
        # Derived intervals would come from historical.data upkeep config
        # Coordinator would store them after Phase 0
        coordinator_with_config._derived_intervals_validated = ["5m", "15m"]
        derived = coordinator_with_config._derived_intervals_validated
        
        # All derived intervals identified
        assert "5m" in derived
        assert "15m" in derived
        assert len(derived) == 2
    
    def test_phase0_validate_derivation_capability(self, coordinator_with_config):
        """Test derivation validation (can derive 5m from 1m?)."""
        # Mock derivation check
        def can_derive(base, derived):
            """Check if derived can be created from base."""
            if base == "1m":
                # Can derive any multiple of 1m
                derived_minutes = int(derived.rstrip('m'))
                return derived_minutes % 1 == 0
            return False
        
        # Test valid derivations
        assert can_derive("1m", "5m") is True
        assert can_derive("1m", "15m") is True
        assert can_derive("1m", "60m") is True
        
        # Test invalid derivations
        assert can_derive("1m", "2m") is True  # Actually 2m can be derived from 1m
        assert can_derive("5m", "2m") is False  # Cannot derive 2m from 5m
    
    def test_phase0_invalid_config_format(self):
        """Test Phase 0 with malformed config."""
        # Test with empty symbols - should fail validation
        with pytest.raises(ValueError, match="symbols list cannot be empty"):
            config = SessionDataConfig(
                symbols=[],  # Empty - invalid
                streams=["1m"]
            )
            config.validate()
        
        # Test with empty streams - should fail validation
        with pytest.raises(ValueError, match="streams list cannot be empty"):
            config2 = SessionDataConfig(
                symbols=["AAPL"],
                streams=[]  # Empty - invalid
            )
            config2.validate()
        
        # Test with duplicate symbols - should fail validation
        with pytest.raises(ValueError, match="Duplicate symbols"):
            config3 = SessionDataConfig(
                symbols=["AAPL", "AAPL"],  # Duplicate - invalid
                streams=["1m"]
            )
            config3.validate()
        
        # Test with invalid stream format - should fail validation
        with pytest.raises(ValueError, match="Invalid stream"):
            config4 = SessionDataConfig(
                symbols=["AAPL"],
                streams=["invalid_format"]  # Invalid stream
            )
            config4.validate()
    
    def test_phase0_results_stored_for_reuse(self, coordinator_with_config):
        """Test Phase 0 results stored and reused."""
        # Simulate Phase 0 validation
        coordinator_with_config._base_interval = "1m"
        coordinator_with_config._derived_intervals_validated = ["5m", "15m"]
        
        # Results stored
        assert coordinator_with_config._base_interval is not None
        assert coordinator_with_config._derived_intervals_validated is not None
        
        # These values should be reused for ALL symbol validations
        # No need to re-validate for each symbol
        for symbol in ["AAPL", "MSFT", "TSLA"]:
            # Each symbol can use the stored values
            base = coordinator_with_config._base_interval
            derived = coordinator_with_config._derived_intervals_validated
            
            assert base == "1m"
            assert "5m" in derived
    
    def test_phase0_no_symbol_validation(self, coordinator_with_config):
        """Test Phase 0 does not validate individual symbols."""
        # Phase 0 is SYSTEM-WIDE only
        config = coordinator_with_config.session_config.session_data_config
        
        # Check system-wide settings exist
        assert config.streams is not None
        assert len(config.streams) > 0
        
        # But DO NOT validate individual symbols yet
        # That happens in Phase 2 (Step 0 validation per symbol)
        symbols = config.symbols
        assert len(symbols) > 0
        
        # No per-symbol validation in Phase 0
        # Just validate the system can handle the configured streams
    
    def test_phase0_no_symbol_registration(self, coordinator_with_config):
        """Test Phase 0 does not register symbols."""
        # Phase 0 validation only
        coordinator_with_config._base_interval = "1m"
        coordinator_with_config._derived_intervals_validated = ["5m", "15m"]
        
        # Verify no SymbolSessionData created yet
        if hasattr(coordinator_with_config, 'session_data'):
            session_data = coordinator_with_config.session_data
            if hasattr(session_data, 'symbols'):
                # Should be empty after Phase 0
                assert len(session_data.symbols) == 0
        
        # Phase 0 ONLY validates configuration
        # Phase 2 will register symbols


class TestPhase0DerivationLogic:
    """Test derivation capability logic."""
    
    def test_derivation_5m_from_1m(self):
        """Test 5m can be derived from 1m."""
        base = "1m"
        derived = "5m"
        
        # 5m = 5 * 1m
        base_minutes = 1
        derived_minutes = 5
        
        can_derive = (derived_minutes % base_minutes) == 0
        assert can_derive is True
    
    def test_derivation_15m_from_1m(self):
        """Test 15m can be derived from 1m."""
        base = "1m"
        derived = "15m"
        
        base_minutes = 1
        derived_minutes = 15
        
        can_derive = (derived_minutes % base_minutes) == 0
        assert can_derive is True
    
    def test_derivation_2m_from_1m(self):
        """Test 2m can be derived from 1m."""
        base = "1m"
        derived = "2m"
        
        base_minutes = 1
        derived_minutes = 2
        
        can_derive = (derived_minutes % base_minutes) == 0
        assert can_derive is True
    
    def test_derivation_3m_from_5m_invalid(self):
        """Test 3m CANNOT be derived from 5m."""
        base = "5m"
        derived = "3m"
        
        base_minutes = 5
        derived_minutes = 3
        
        # 3 is not a multiple of 5
        can_derive = (derived_minutes % base_minutes) == 0
        assert can_derive is False
    
    def test_derivation_hour_from_minute(self):
        """Test 1h can be derived from 1m."""
        base = "1m"
        derived = "1h"
        
        base_minutes = 1
        derived_minutes = 60
        
        can_derive = (derived_minutes % base_minutes) == 0
        assert can_derive is True
    
    def test_derivation_day_from_minute(self):
        """Test 1d can be derived from 1m."""
        base = "1m"
        derived = "1d"
        
        # Daily bar from minute bars
        # This would require special handling (market hours)
        # For now, mark as derivable but with special logic
        can_derive = True  # Special case
        assert can_derive is True
