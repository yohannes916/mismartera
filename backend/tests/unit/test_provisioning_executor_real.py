"""Unit Tests for Provisioning Executor

Tests the _execute_provisioning and _execute_provisioning_step methods
that orchestrate the actual provisioning work.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch, call
from app.threads.session_coordinator import (
    SessionCoordinator,
    ProvisioningRequirements
)
from app.managers.data_manager.session_data import SymbolSessionData


class TestExecuteProvisioning:
    """Test _execute_provisioning orchestration."""
    
    def test_execute_empty_plan(self):
        """Test executing provisioning with no steps."""
        coordinator = Mock(spec=SessionCoordinator)
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config",
            can_proceed=True,
            provisioning_steps=[]
        )
        
        coordinator._execute_provisioning = SessionCoordinator._execute_provisioning.__get__(coordinator, SessionCoordinator)
        coordinator._execute_provisioning_step = Mock(return_value=True)
        
        result = coordinator._execute_provisioning(req)
        
        # Should succeed with no steps
        assert result is True
        coordinator._execute_provisioning_step.assert_not_called()
    
    def test_execute_single_step(self):
        """Test executing provisioning with single step."""
        coordinator = Mock(spec=SessionCoordinator)
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config",
            can_proceed=True,
            provisioning_steps=["create_symbol"]
        )
        
        coordinator._execute_provisioning = SessionCoordinator._execute_provisioning.__get__(coordinator, SessionCoordinator)
        coordinator._execute_provisioning_step = Mock(return_value=True)
        
        result = coordinator._execute_provisioning(req)
        
        # Should succeed
        assert result is True
        coordinator._execute_provisioning_step.assert_called_once_with(req, "create_symbol")
    
    def test_execute_multiple_steps(self):
        """Test executing provisioning with multiple steps."""
        coordinator = Mock(spec=SessionCoordinator)
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config",
            can_proceed=True,
            provisioning_steps=["create_symbol", "load_historical", "calculate_quality"]
        )
        
        coordinator._execute_provisioning = SessionCoordinator._execute_provisioning.__get__(coordinator, SessionCoordinator)
        coordinator._execute_provisioning_step = Mock(return_value=True)
        
        result = coordinator._execute_provisioning(req)
        
        # Should succeed and call all steps
        assert result is True
        assert coordinator._execute_provisioning_step.call_count == 3
        coordinator._execute_provisioning_step.assert_any_call(req, "create_symbol")
        coordinator._execute_provisioning_step.assert_any_call(req, "load_historical")
        coordinator._execute_provisioning_step.assert_any_call(req, "calculate_quality")
    
    def test_execute_fails_on_validation_error(self):
        """Test execution fails if can_proceed is False."""
        coordinator = Mock(spec=SessionCoordinator)
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config",
            can_proceed=False,
            validation_errors=["No data source"],
            provisioning_steps=["create_symbol"]
        )
        
        coordinator._execute_provisioning = SessionCoordinator._execute_provisioning.__get__(coordinator, SessionCoordinator)
        coordinator._execute_provisioning_step = Mock(return_value=True)
        
        result = coordinator._execute_provisioning(req)
        
        # Should fail without executing steps
        assert result is False
        coordinator._execute_provisioning_step.assert_not_called()
    
    def test_execute_stops_on_step_failure(self):
        """Test execution stops if a step fails."""
        coordinator = Mock(spec=SessionCoordinator)
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config",
            can_proceed=True,
            provisioning_steps=["create_symbol", "load_historical", "calculate_quality"]
        )
        
        coordinator._execute_provisioning = SessionCoordinator._execute_provisioning.__get__(coordinator, SessionCoordinator)
        # Second step fails
        coordinator._execute_provisioning_step = Mock(side_effect=[True, False, True])
        
        result = coordinator._execute_provisioning(req)
        
        # Should fail and stop at second step
        assert result is False
        assert coordinator._execute_provisioning_step.call_count == 2  # Stopped at failure


class TestExecuteProvisioningStep:
    """Test _execute_provisioning_step dispatcher."""
    
    def test_dispatch_create_symbol(self):
        """Test dispatching create_symbol step."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._provision_create_symbol = Mock(return_value=True)
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config"
        )
        
        coordinator._execute_provisioning_step = SessionCoordinator._execute_provisioning_step.__get__(coordinator, SessionCoordinator)
        
        result = coordinator._execute_provisioning_step(req, "create_symbol")
        
        assert result is True
        coordinator._provision_create_symbol.assert_called_once_with(req)
    
    def test_dispatch_upgrade_symbol(self):
        """Test dispatching upgrade_symbol step."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._provision_upgrade_symbol = Mock(return_value=True)
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="strategy"
        )
        
        coordinator._execute_provisioning_step = SessionCoordinator._execute_provisioning_step.__get__(coordinator, SessionCoordinator)
        
        result = coordinator._execute_provisioning_step(req, "upgrade_symbol")
        
        assert result is True
        coordinator._provision_upgrade_symbol.assert_called_once_with(req)
    
    def test_dispatch_add_interval(self):
        """Test dispatching add_interval_X step."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._provision_add_interval = Mock(return_value=True)
        
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="AAPL",
            source="config"
        )
        
        coordinator._execute_provisioning_step = SessionCoordinator._execute_provisioning_step.__get__(coordinator, SessionCoordinator)
        
        result = coordinator._execute_provisioning_step(req, "add_interval_5m")
        
        assert result is True
        coordinator._provision_add_interval.assert_called_once_with(req, "5m")
    
    def test_dispatch_unknown_step(self):
        """Test dispatching unknown step doesn't fail."""
        coordinator = Mock(spec=SessionCoordinator)
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config"
        )
        
        coordinator._execute_provisioning_step = SessionCoordinator._execute_provisioning_step.__get__(coordinator, SessionCoordinator)
        
        result = coordinator._execute_provisioning_step(req, "unknown_step")
        
        # Should return True (don't fail on unknown)
        assert result is True


class TestProvisionCreateSymbol:
    """Test _provision_create_symbol step."""
    
    def test_create_config_symbol(self):
        """Test creating config symbol."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._register_single_symbol = Mock()
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config",
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False
        )
        
        coordinator._provision_create_symbol = SessionCoordinator._provision_create_symbol.__get__(coordinator, SessionCoordinator)
        
        result = coordinator._provision_create_symbol(req)
        
        assert result is True
        coordinator._register_single_symbol.assert_called_once_with(
            "AAPL",
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False
        )
    
    def test_create_adhoc_symbol(self):
        """Test creating adhoc symbol."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._register_single_symbol = Mock()
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="TSLA",
            source="scanner",
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True
        )
        
        coordinator._provision_create_symbol = SessionCoordinator._provision_create_symbol.__get__(coordinator, SessionCoordinator)
        
        result = coordinator._provision_create_symbol(req)
        
        assert result is True
        coordinator._register_single_symbol.assert_called_once_with(
            "TSLA",
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True
        )


class TestProvisionUpgradeSymbol:
    """Test _provision_upgrade_symbol step."""
    
    def test_upgrade_adhoc_to_full(self):
        """Test upgrading adhoc symbol to full."""
        coordinator = Mock(spec=SessionCoordinator)
        
        # Create adhoc symbol data
        symbol_data = Mock(spec=SymbolSessionData)
        symbol_data.meets_session_config_requirements = False
        symbol_data.upgraded_from_adhoc = False
        symbol_data.added_by = "scanner"
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="NVDA",
            source="strategy",
            symbol_data=symbol_data,
            added_by="strategy"
        )
        
        coordinator._provision_upgrade_symbol = SessionCoordinator._provision_upgrade_symbol.__get__(coordinator, SessionCoordinator)
        
        result = coordinator._provision_upgrade_symbol(req)
        
        assert result is True
        # Verify metadata updated
        assert symbol_data.meets_session_config_requirements is True
        assert symbol_data.upgraded_from_adhoc is True
        assert symbol_data.added_by == "strategy"
    
    def test_upgrade_fails_without_symbol_data(self):
        """Test upgrade fails if no symbol_data."""
        coordinator = Mock(spec=SessionCoordinator)
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="NVDA",
            source="strategy",
            symbol_data=None,  # No data
            added_by="strategy"
        )
        
        coordinator._provision_upgrade_symbol = SessionCoordinator._provision_upgrade_symbol.__get__(coordinator, SessionCoordinator)
        
        result = coordinator._provision_upgrade_symbol(req)
        
        assert result is False


class TestProvisioningStepOrdering:
    """Test that steps execute in correct order."""
    
    def test_steps_execute_sequentially(self):
        """Test steps execute in the order provided."""
        coordinator = Mock(spec=SessionCoordinator)
        
        call_order = []
        
        def track_create(req):
            call_order.append("create")
            return True
        
        def track_historical(req):
            call_order.append("historical")
            return True
        
        def track_quality(req):
            call_order.append("quality")
            return True
        
        coordinator._provision_create_symbol = track_create
        coordinator._provision_load_historical = track_historical
        coordinator._provision_calculate_quality = track_quality
        coordinator._execute_provisioning_step = SessionCoordinator._execute_provisioning_step.__get__(coordinator, SessionCoordinator)
        coordinator._execute_provisioning = SessionCoordinator._execute_provisioning.__get__(coordinator, SessionCoordinator)
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config",
            can_proceed=True,
            provisioning_steps=["create_symbol", "load_historical", "calculate_quality"]
        )
        
        result = coordinator._execute_provisioning(req)
        
        assert result is True
        assert call_order == ["create", "historical", "quality"]
