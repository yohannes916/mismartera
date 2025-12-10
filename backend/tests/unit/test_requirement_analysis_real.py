"""Unit Tests for Requirement Analysis Methods

Tests the actual _analyze_*_requirements methods that exist in SessionCoordinator.
These methods analyze requirements for symbol, bar, and indicator operations.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from app.threads.session_coordinator import (
    SessionCoordinator,
    ProvisioningRequirements
)
from app.managers.data_manager.session_data import SymbolSessionData


class TestAnalyzeBarRequirements:
    """Test _analyze_bar_requirements method."""
    
    def test_analyze_base_interval(self):
        """Test analyzing requirements for base interval (1m)."""
        coordinator = Mock(spec=SessionCoordinator)
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="AAPL",
            source="config"
        )
        
        # Mock the method behavior
        coordinator._analyze_bar_requirements = SessionCoordinator._analyze_bar_requirements.__get__(coordinator, SessionCoordinator)
        
        # Call with base interval
        with patch('app.threads.quality.requirement_analyzer.parse_interval') as mock_parse:
            mock_parse.return_value = Mock(is_base=True)
            
            coordinator._analyze_bar_requirements(req, interval="1m", days=30)
        
        # Should set basic requirements
        assert "1m" in req.required_intervals
        assert req.historical_days == 30
        assert req.needs_historical is True
        assert req.needs_session is True
    
    def test_analyze_derived_interval(self):
        """Test analyzing requirements for derived interval (5m)."""
        coordinator = Mock(spec=SessionCoordinator)
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="AAPL",
            source="config"
        )
        
        coordinator._analyze_bar_requirements = SessionCoordinator._analyze_bar_requirements.__get__(coordinator, SessionCoordinator)
        
        # Call with derived interval
        with patch('app.threads.quality.requirement_analyzer.parse_interval') as mock_parse, \
             patch('app.threads.quality.requirement_analyzer.determine_required_base') as mock_base:
            mock_parse.return_value = Mock(is_base=False)
            mock_base.return_value = "1m"
            
            coordinator._analyze_bar_requirements(req, interval="5m", days=15)
        
        # Should include base interval
        assert "1m" in req.required_intervals
        assert "5m" in req.required_intervals
        assert req.base_interval == "1m"
        assert req.historical_days == 15
    
    def test_analyze_invalid_interval(self):
        """Test analyzing invalid interval fails gracefully."""
        coordinator = Mock(spec=SessionCoordinator)
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="AAPL",
            source="config"
        )
        
        coordinator._analyze_bar_requirements = SessionCoordinator._analyze_bar_requirements.__get__(coordinator, SessionCoordinator)
        
        # Call with invalid interval
        with patch('app.threads.quality.requirement_analyzer.parse_interval') as mock_parse:
            mock_parse.side_effect = ValueError("Invalid interval format")
            
            coordinator._analyze_bar_requirements(req, interval="invalid", days=0)
        
        # Should set error
        assert req.can_proceed is False
        assert len(req.validation_errors) > 0
        assert "Invalid interval" in req.validation_errors[0]
    
    def test_analyze_historical_only_bar(self):
        """Test analyzing bar with historical_only=True."""
        coordinator = Mock(spec=SessionCoordinator)
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="AAPL",
            source="config"
        )
        
        coordinator._analyze_bar_requirements = SessionCoordinator._analyze_bar_requirements.__get__(coordinator, SessionCoordinator)
        
        with patch('app.threads.quality.requirement_analyzer.parse_interval') as mock_parse:
            mock_parse.return_value = Mock(is_base=True)
            
            coordinator._analyze_bar_requirements(req, interval="1m", days=30, historical_only=True)
        
        # Should not need session
        assert req.needs_historical is True
        assert req.needs_session is False


class TestAnalyzeSymbolRequirements:
    """Test _analyze_symbol_requirements method."""
    
    def test_analyze_symbol_from_config(self):
        """Test analyzing symbol requirements from session config."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.streams = ["1m"]
        coordinator.session_config.session_data_config.derived_intervals = [5, 15]
        coordinator.session_config.session_data_config.historical = Mock()
        coordinator.session_config.session_data_config.historical.enabled = True
        coordinator.session_config.session_data_config.historical.data = [
            Mock(trailing_days=30)
        ]
        coordinator._base_interval = "1m"
        coordinator._derived_intervals_validated = []
        
        coordinator._analyze_symbol_requirements = SessionCoordinator._analyze_symbol_requirements.__get__(coordinator, SessionCoordinator)
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config"
        )
        
        coordinator._analyze_symbol_requirements(req)
        
        # Should infer from config
        assert "1m" in req.required_intervals
        assert 5 in req.required_intervals or "5m" in str(req.required_intervals)
        assert req.historical_days == 30
        assert req.needs_historical is True
        assert req.needs_session is True
    
    def test_analyze_symbol_no_historical(self):
        """Test analyzing symbol with no historical requirement."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.streams = ["1m"]
        coordinator.session_config.session_data_config.derived_intervals = []
        coordinator.session_config.session_data_config.historical = Mock()
        coordinator.session_config.session_data_config.historical.enabled = False
        coordinator._base_interval = "1m"
        coordinator._derived_intervals_validated = []
        
        coordinator._analyze_symbol_requirements = SessionCoordinator._analyze_symbol_requirements.__get__(coordinator, SessionCoordinator)
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config"
        )
        
        coordinator._analyze_symbol_requirements(req)
        
        # Should have no historical
        assert req.needs_historical is False or req.historical_days == 0


class TestDetermineProvisioningSteps:
    """Test _determine_provisioning_steps method."""
    
    def test_steps_for_new_symbol(self):
        """Test provisioning steps for new symbol."""
        coordinator = Mock(spec=SessionCoordinator)
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config",
            symbol_exists=False,
            required_intervals=["1m", "5m"],
            needs_historical=True
        )
        
        coordinator._determine_provisioning_steps = SessionCoordinator._determine_provisioning_steps.__get__(coordinator, SessionCoordinator)
        
        coordinator._determine_provisioning_steps(req)
        
        # Should include create_symbol
        assert "create_symbol" in req.provisioning_steps
    
    def test_steps_for_upgrade(self):
        """Test provisioning steps for upgrading adhoc to full."""
        coordinator = Mock(spec=SessionCoordinator)
        
        # Existing adhoc symbol
        existing = Mock(spec=SymbolSessionData)
        existing.meets_session_config_requirements = False
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="strategy",
            symbol_exists=True,
            symbol_data=existing,
            required_intervals=["1m", "5m"]
        )
        
        coordinator._determine_provisioning_steps = SessionCoordinator._determine_provisioning_steps.__get__(coordinator, SessionCoordinator)
        
        coordinator._determine_provisioning_steps(req)
        
        # Should include upgrade_symbol
        assert "upgrade_symbol" in req.provisioning_steps
    
    def test_steps_for_existing_full_symbol(self):
        """Test provisioning steps for symbol already fully loaded."""
        coordinator = Mock(spec=SessionCoordinator)
        
        # Existing full symbol
        existing = Mock(spec=SymbolSessionData)
        existing.meets_session_config_requirements = True
        existing.bars = {"1m": Mock(), "5m": Mock()}
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config",
            symbol_exists=True,
            symbol_data=existing,
            required_intervals=["1m", "5m"],
            intervals_exist={"1m": True, "5m": True}
        )
        
        coordinator._determine_provisioning_steps = SessionCoordinator._determine_provisioning_steps.__get__(coordinator, SessionCoordinator)
        
        coordinator._determine_provisioning_steps(req)
        
        # Should not include create or upgrade
        assert "create_symbol" not in req.provisioning_steps
        assert "upgrade_symbol" not in req.provisioning_steps


class TestRequirementReasonMessages:
    """Test that requirement analysis sets helpful reason messages."""
    
    def test_bar_requirement_reason(self):
        """Test bar requirement sets descriptive reason."""
        coordinator = Mock(spec=SessionCoordinator)
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="AAPL",
            source="config"
        )
        
        coordinator._analyze_bar_requirements = SessionCoordinator._analyze_bar_requirements.__get__(coordinator, SessionCoordinator)
        
        with patch('app.threads.quality.requirement_analyzer.parse_interval') as mock_parse:
            mock_parse.return_value = Mock(is_base=True)
            
            coordinator._analyze_bar_requirements(req, interval="1m", days=30)
        
        # Should have descriptive reason
        assert req.reason != ""
        assert "1m" in req.reason
        assert "30" in req.reason
    
    def test_symbol_requirement_reason(self):
        """Test symbol requirement sets descriptive reason."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.streams = ["1m"]
        coordinator.session_config.session_data_config.derived_intervals = []
        coordinator.session_config.session_data_config.historical = Mock()
        coordinator.session_config.session_data_config.historical.enabled = False
        coordinator._base_interval = "1m"
        coordinator._derived_intervals_validated = []
        
        coordinator._analyze_symbol_requirements = SessionCoordinator._analyze_symbol_requirements.__get__(coordinator, SessionCoordinator)
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config"
        )
        
        coordinator._analyze_symbol_requirements(req)
        
        # Should have descriptive reason
        assert req.reason != ""
        assert "Symbol" in req.reason or "symbol" in req.reason
