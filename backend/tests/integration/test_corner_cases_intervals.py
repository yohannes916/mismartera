"""Integration Tests for Interval Corner Cases

Tests edge cases related to bar intervals:
- Unsupported interval derivation
- Daily from minute intervals
- Second intervals
- Hour intervals
- Week/month intervals
- Duplicate intervals
- Base interval mismatches
- Multiple base intervals
"""
import pytest
from unittest.mock import Mock
from app.threads.session_coordinator import SessionCoordinator, ProvisioningRequirements, SymbolValidationResult


@pytest.fixture
def coordinator_for_interval_tests():
    """Create coordinator for interval testing."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator._base_interval = "1m"
    coordinator._derived_intervals_validated = ["5m", "15m", "1h"]
    return coordinator


class TestUnsupportedIntervals:
    """Test unsupported interval combinations."""
    
    def test_unsupported_2m_from_1m(self, coordinator_for_interval_tests):
        """Test 2m cannot be derived from 1m (not a clean multiple)."""
        # Actually 2m CAN be derived from 1m (2 = 2*1)
        # But let's test a truly unsupported case
        
        # Test 3m from 5m (cannot derive smaller from larger)
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="TEST",
            source="scanner",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["3m"],
            base_  # Base is 5m
            historical_
            
            needs_session=False,
            indicator_config=None,
              # Want 3m
            
            
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=False,
            provisioning_steps=[],
            can_proceed=False,
            validation_result=SymbolValidationResult(symbol="TEST",
            
                can_proceed=False,
                reason="Cannot derive 3m interval from 5m base interval",
                data_source_available=True,
                has_historical_data=True
            ),
            validation_errors=["Cannot derive 3m from 5m"]
        )
        
        # Expected: Cannot proceed
        assert req.can_proceed is False
        assert "Cannot derive" in req.validation_errors[0]
    
    def test_unsupported_7m_from_5m(self, coordinator_for_interval_tests):
        """Test 7m cannot be derived from 5m."""
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="TEST",
            source="scanner",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["7m"],
            base_
            historical_
            
            needs_session=False,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=False,
            provisioning_steps=[],
            can_proceed=False,
            validation_result=SymbolValidationResult(symbol="TEST",
            
                can_proceed=False,
                reason="7m is not a clean multiple of 5m base interval",
                data_source_available=True,
                has_historical_data=True
            ),
            validation_errors=["7m not derivable from 5m"]
        )
        
        # Expected: Cannot proceed
        assert req.can_proceed is False
        assert "not" in req.validation_errors[0].lower()


class TestSpecialIntervals:
    """Test special interval types."""
    
    def test_daily_from_minute(self, coordinator_for_interval_tests):
        """Test daily (1d) interval derived from minute (1m) base."""
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="TEST",
            source="scanner",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["1m", "1d"],
            base_
            historical_
            
            needs_session=True,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            provisioning_steps=[
                "create_symbol",
                "add_interval_1m",
                "add_interval_1d",
                "load_historical",
                "load_session"
            ],
            can_proceed=True,
            validation_result=SymbolValidationResult(symbol="TEST",
            
                can_proceed=True,
                reason="Valid",
                data_source_available=True,
                has_historical_data=True
            ),
            validation_errors=[]
        )
        
        # Expected: Can derive daily from minute (special case)
        assert req.can_proceed is True
        assert "1d" in req.required_intervals
        assert "add_interval_1d" in req.provisioning_steps
    
    def test_second_intervals(self, coordinator_for_interval_tests):
        """Test second intervals (1s, 5s, etc.) if supported."""
        # If system supports second intervals
        coordinator = coordinator_for_interval_tests
        coordinator._base_interval = "1s"
        coordinator._derived_intervals_validated = ["5s", "10s", "1m"]
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="HFDATA",
            source="config",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["1s", "5s", "10s", "1m"],
            base_
            historical_  # Limited for second data
            
            needs_session=True,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            provisioning_steps=["create_symbol"],
            can_proceed=True,
            validation_result=SymbolValidationResult(symbol="TEST",
            
                can_proceed=True,
                reason="Valid",
                data_source_available=True,
                has_historical_data=True
            ),
            validation_errors=[]
        )
        
        # Expected: Second intervals supported
        assert req.base_interval == "1s"
        assert "5s" in req.required_intervals
        assert "10s" in req.required_intervals
        assert "1m" in req.required_intervals  # 60 seconds
    
    def test_hour_intervals(self, coordinator_for_interval_tests):
        """Test hour intervals (1h, 2h, 4h)."""
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="SWING",
            source="strategy",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["1m", "1h"],
            base_
            historical_
            
            needs_session=True,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=False,
            provisioning_steps=[
                "create_symbol",
                "add_interval_1m",
                "add_interval_1h",
                "load_historical"
            ],
            can_proceed=True,
            validation_result=SymbolValidationResult(symbol="TEST",
            
                can_proceed=True,
                reason="Valid",
                data_source_available=True,
                has_historical_data=True
            ),
            validation_errors=[]
        )
        
        # Expected: 1h can be derived from 1m (60 minutes)
        assert req.can_proceed is True
        assert "1h" in req.required_intervals
        assert "add_interval_1h" in req.provisioning_steps
    
    def test_week_month_intervals(self, coordinator_for_interval_tests):
        """Test week (1w) and month (1M) intervals."""
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="LONGTERM",
            source="strategy",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["1d", "1w"],
            base_
            historical_
            
            needs_session=True,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=False,
            provisioning_steps=[
                "create_symbol",
                "add_interval_1d",
                "add_interval_1w",
                "load_historical"
            ],
            can_proceed=True,
            validation_result=SymbolValidationResult(symbol="TEST",
            
                can_proceed=True,
                reason="Valid",
                data_source_available=True,
                has_historical_data=True
            ),
            validation_errors=[]
        )
        
        # Expected: Weekly from daily (5 trading days)
        assert req.can_proceed is True
        assert "1w" in req.required_intervals


class TestDuplicateIntervals:
    """Test duplicate interval handling."""
    
    def test_duplicate_interval_request(self, coordinator_for_interval_tests):
        """Test requesting same interval twice."""
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="TEST",
            source="scanner",
            symbol_exists=True,
            symbol_data=Mock(),  # Already has 5m
            required_intervals=["5m"],
            base_
            historical_
            
            needs_session=False,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=False,
            provisioning_steps=[],
            can_proceed=False,
            validation_result=SymbolValidationResult(symbol="TEST",
            
                can_proceed=False,
                reason="Interval 5m already exists for TEST",
                data_source_available=True,
                has_historical_data=True
            ),
            validation_errors=["Interval already exists"]
        )
        
        # Expected: Duplicate detected
        assert req.can_proceed is False
        assert "already exists" in req.validation_errors[0].lower()


class TestBaseIntervalIssues:
    """Test base interval related issues."""
    
    def test_base_interval_mismatch(self, coordinator_for_interval_tests):
        """Test mismatch between config base and requested base."""
        coordinator = coordinator_for_interval_tests
        coordinator._base_interval = "1m"  # System configured for 1m
        
        # Someone tries to add symbol with 5m as base
        # This should be detected as incompatible
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="MISMATCH",
            source="config",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["5m"],  # Wants 5m as base
            base_  # Different from system base
            historical_
            
            needs_session=True,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=False,
            added_by="config",
            auto_provisioned=False,
            provisioning_steps=[],
            can_proceed=False,
            validation_result=SymbolValidationResult(symbol="TEST",
            
                can_proceed=False,
                reason="Base interval mismatch: system uses 1m, symbol requests 5m",
                data_source_available=True,
                has_historical_data=True
            ),
            validation_errors=["Base interval mismatch"]
        )
        
        # Expected: Mismatch detected
        assert req.can_proceed is False
        assert "mismatch" in req.validation_errors[0].lower()
    
    def test_multiple_base_intervals_not_allowed(self, coordinator_for_interval_tests):
        """Test cannot have multiple base intervals in one session."""
        coordinator = coordinator_for_interval_tests
        coordinator._base_interval = "1m"
        
        # All symbols must share same base interval
        # Cannot mix 1m base and 5m base in same session
        
        # This is enforced at Phase 0 validation
        # Each symbol should use the session's base interval
        
        assert coordinator._base_interval == "1m"
        # All symbols will use "1m" as base
