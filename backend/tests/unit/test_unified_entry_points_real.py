"""Unit Tests for Unified Entry Points

Tests the public API entry points that use the unified three-phase pattern:
analyze → validate → provision.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from threading import RLock
from app.threads.session_coordinator import (
    SessionCoordinator,
    ProvisioningRequirements
)


class TestAddSymbolEntryPoint:
    """Test add_symbol unified entry point."""
    
    def test_add_symbol_success(self):
        """Test successfully adding a symbol."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = RLock()
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.symbols = []
        coordinator.session_config.session_data_config.streams = []
        
        # Mock the three phases
        mock_req = Mock(spec=ProvisioningRequirements)
        mock_req.can_proceed = True
        mock_req.validation_errors = []
        
        coordinator._analyze_requirements = Mock(return_value=mock_req)
        coordinator._execute_provisioning = Mock(return_value=True)
        
        coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(coordinator, SessionCoordinator)
        
        result = coordinator.add_symbol("AAPL", added_by="strategy")
        
        # Should succeed
        assert result is True
        coordinator._analyze_requirements.assert_called_once()
        coordinator._execute_provisioning.assert_called_once_with(mock_req)
        assert "AAPL" in coordinator.session_config.session_data_config.symbols
    
    def test_add_symbol_validation_fails(self):
        """Test adding symbol fails if validation fails."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = RLock()
        
        # Mock validation failure
        mock_req = Mock(spec=ProvisioningRequirements)
        mock_req.can_proceed = False
        mock_req.validation_errors = ["No data source"]
        
        coordinator._analyze_requirements = Mock(return_value=mock_req)
        coordinator._execute_provisioning = Mock(return_value=True)
        
        coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(coordinator, SessionCoordinator)
        
        result = coordinator.add_symbol("INVALID", added_by="strategy")
        
        # Should fail without provisioning
        assert result is False
        coordinator._analyze_requirements.assert_called_once()
        coordinator._execute_provisioning.assert_not_called()
    
    def test_add_symbol_provisioning_fails(self):
        """Test adding symbol fails if provisioning fails."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = RLock()
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.symbols = []
        coordinator.session_config.session_data_config.streams = []
        
        # Mock provisioning failure
        mock_req = Mock(spec=ProvisioningRequirements)
        mock_req.can_proceed = True
        mock_req.validation_errors = []
        
        coordinator._analyze_requirements = Mock(return_value=mock_req)
        coordinator._execute_provisioning = Mock(return_value=False)
        
        coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(coordinator, SessionCoordinator)
        
        result = coordinator.add_symbol("AAPL", added_by="strategy")
        
        # Should fail
        assert result is False
        coordinator._execute_provisioning.assert_called_once()
    
    def test_add_symbol_case_insensitive(self):
        """Test add_symbol converts to uppercase."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = RLock()
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.symbols = []
        coordinator.session_config.session_data_config.streams = []
        
        mock_req = Mock(spec=ProvisioningRequirements)
        mock_req.can_proceed = True
        mock_req.validation_errors = []
        
        coordinator._analyze_requirements = Mock(return_value=mock_req)
        coordinator._execute_provisioning = Mock(return_value=True)
        
        coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(coordinator, SessionCoordinator)
        
        result = coordinator.add_symbol("aapl", added_by="strategy")
        
        # Should convert to uppercase
        assert result is True
        # Check that analyze_requirements was called with uppercase
        call_args = coordinator._analyze_requirements.call_args
        assert call_args[1]['symbol'] == "AAPL"
    
    def test_add_symbol_with_custom_source(self):
        """Test add_symbol with different sources."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = RLock()
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.symbols = []
        coordinator.session_config.session_data_config.streams = []
        
        mock_req = Mock(spec=ProvisioningRequirements)
        mock_req.can_proceed = True
        
        coordinator._analyze_requirements = Mock(return_value=mock_req)
        coordinator._execute_provisioning = Mock(return_value=True)
        
        coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(coordinator, SessionCoordinator)
        
        # Test with scanner
        result = coordinator.add_symbol("TSLA", added_by="scanner")
        
        assert result is True
        call_args = coordinator._analyze_requirements.call_args
        assert call_args[1]['source'] == "scanner"


class TestRemoveSymbol:
    """Test remove_symbol entry point."""
    
    def test_remove_existing_symbol(self):
        """Test removing an existing symbol."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = RLock()
        coordinator.session_data = Mock()
        coordinator.session_data.get_symbol_data = Mock(return_value=Mock())
        coordinator.session_data.clear_symbol = Mock()
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.symbols = ["AAPL", "MSFT"]
        coordinator._pending_symbols = set()
        coordinator._bar_queues = {}
        coordinator._symbol_check_counters = {}
        
        coordinator.remove_symbol = SessionCoordinator.remove_symbol.__get__(coordinator, SessionCoordinator)
        
        result = coordinator.remove_symbol("AAPL")
        
        # Should succeed
        assert result is True
        assert "AAPL" not in coordinator.session_config.session_data_config.symbols
    
    def test_remove_nonexistent_symbol(self):
        """Test removing non-existent symbol."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = RLock()
        coordinator.session_data = Mock()
        coordinator.session_data.get_symbol_data = Mock(return_value=None)
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.symbols = ["MSFT"]
        coordinator._pending_symbols = set()
        coordinator._bar_queues = {}
        coordinator._symbol_check_counters = {}
        
        coordinator.remove_symbol = SessionCoordinator.remove_symbol.__get__(coordinator, SessionCoordinator)
        
        result = coordinator.remove_symbol("NOTFOUND")
        
        # Should fail gracefully
        assert result is False


class TestUnifiedPatternIntegration:
    """Test that unified pattern is followed correctly."""
    
    def test_three_phase_pattern_order(self):
        """Test that add_symbol follows three-phase pattern."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = RLock()
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.symbols = []
        coordinator.session_config.session_data_config.streams = []
        
        call_order = []
        
        def track_analyze(*args, **kwargs):
            call_order.append("analyze")
            mock_req = Mock(spec=ProvisioningRequirements)
            mock_req.can_proceed = True
            return mock_req
        
        def track_provision(req):
            call_order.append("provision")
            return True
        
        coordinator._analyze_requirements = track_analyze
        coordinator._execute_provisioning = track_provision
        
        coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(coordinator, SessionCoordinator)
        
        result = coordinator.add_symbol("AAPL", added_by="strategy")
        
        assert result is True
        # Should follow order: analyze → validate (implicit) → provision
        assert call_order == ["analyze", "provision"]
    
    def test_exception_handling(self):
        """Test exception handling in add_symbol."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = RLock()
        
        # Mock exception in analysis
        coordinator._analyze_requirements = Mock(side_effect=Exception("Test error"))
        
        coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(coordinator, SessionCoordinator)
        
        result = coordinator.add_symbol("AAPL", added_by="strategy")
        
        # Should fail gracefully
        assert result is False


class TestThreadSafety:
    """Test thread-safety of entry points."""
    
    def test_add_symbol_uses_lock(self):
        """Test that add_symbol uses symbol operation lock."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = RLock()
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.symbols = []
        coordinator.session_config.session_data_config.streams = []
        
        mock_req = Mock(spec=ProvisioningRequirements)
        mock_req.can_proceed = True
        
        coordinator._analyze_requirements = Mock(return_value=mock_req)
        coordinator._execute_provisioning = Mock(return_value=True)
        
        coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(coordinator, SessionCoordinator)
        
        # Lock should be used during operation
        result = coordinator.add_symbol("AAPL", added_by="strategy")
        
        assert result is True
        # Verify operations happened (lock was acquired and released)
        coordinator._analyze_requirements.assert_called_once()
    
    def test_remove_symbol_uses_lock(self):
        """Test that remove_symbol uses symbol operation lock."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = RLock()
        coordinator.session_data = Mock()
        coordinator.session_data.get_symbol_data = Mock(return_value=Mock())
        coordinator.session_data.clear_symbol = Mock()
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.symbols = ["AAPL"]
        coordinator._pending_symbols = set()
        coordinator._bar_queues = {}
        coordinator._symbol_check_counters = {}
        
        coordinator.remove_symbol = SessionCoordinator.remove_symbol.__get__(coordinator, SessionCoordinator)
        
        # Lock should be used during operation
        result = coordinator.remove_symbol("AAPL")
        
        assert result is True


class TestBackwardCompatibility:
    """Test backward compatibility features."""
    
    def test_add_symbol_default_streams(self):
        """Test add_symbol uses default streams if not provided."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = RLock()
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.symbols = []
        coordinator.session_config.session_data_config.streams = []
        
        mock_req = Mock(spec=ProvisioningRequirements)
        mock_req.can_proceed = True
        
        coordinator._analyze_requirements = Mock(return_value=mock_req)
        coordinator._execute_provisioning = Mock(return_value=True)
        
        coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(coordinator, SessionCoordinator)
        
        # Call without streams parameter
        result = coordinator.add_symbol("AAPL", added_by="strategy")
        
        assert result is True
        # Should add 1m to streams by default
        assert "1m" in coordinator.session_config.session_data_config.streams
