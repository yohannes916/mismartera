"""
Unit tests for ScannerManager.

Tests scanner loading, state management, and lifecycle orchestration with mocks.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, time as dt_time
from collections import deque

from app.threads.scanner_manager import (
    ScannerManager,
    ScannerState,
    ScannerInstance
)
from scanners.base import BaseScanner, ScanContext, ScanResult


class MockScanner(BaseScanner):
    """Mock scanner for testing."""
    
    def scan(self, context: ScanContext) -> ScanResult:
        return ScanResult(symbols=["TEST"])


@pytest.mark.unit
class TestScannerState:
    """Test ScannerState enum."""
    
    def test_scanner_state_values(self):
        """ScannerState should have all required states."""
        assert ScannerState.INITIALIZED.value == "initialized"
        assert ScannerState.SETUP_PENDING.value == "setup_pending"
        assert ScannerState.SETUP_COMPLETE.value == "setup_complete"
        assert ScannerState.SCANNING.value == "scanning"
        assert ScannerState.SCAN_COMPLETE.value == "scan_complete"
        assert ScannerState.TEARDOWN_PENDING.value == "teardown_pending"
        assert ScannerState.TEARDOWN_COMPLETE.value == "teardown_complete"
        assert ScannerState.ERROR.value == "error"


@pytest.mark.unit
class TestScannerInstance:
    """Test ScannerInstance dataclass."""
    
    def test_scanner_instance_creation(self):
        """ScannerInstance should track scanner state."""
        scanner = MockScanner({})
        instance = ScannerInstance(
            module="test.scanner",
            scanner=scanner,
            config={"key": "value"},
            pre_session=True
        )
        
        assert instance.module == "test.scanner"
        assert instance.scanner is scanner
        assert instance.config == {"key": "value"}
        assert instance.pre_session is True
        assert instance.state == ScannerState.INITIALIZED
        assert instance.scan_count == 0
        assert instance.error is None
        assert len(instance.qualifying_symbols) == 0


@pytest.mark.unit
class TestScannerManagerInit:
    """Test ScannerManager initialization."""
    
    def test_scanner_manager_creation(self):
        """ScannerManager should initialize with system_manager."""
        system_manager = Mock()
        manager = ScannerManager(system_manager)
        
        assert manager._system_manager is system_manager
        assert manager._initialized is False
        assert len(manager._scanners) == 0
    
    def test_scanner_manager_initialize_no_scanners(self):
        """initialize() should succeed with no scanners configured."""
        system_manager = Mock()
        system_manager.get_session_data.return_value = Mock()
        system_manager.get_time_manager.return_value = Mock()
        system_manager.session_config.mode = "backtest"
        system_manager.session_config.session_data_config.scanners = []
        
        manager = ScannerManager(system_manager)
        result = manager.initialize()
        
        assert result is True
        assert manager._initialized is True
        assert len(manager._scanners) == 0


@pytest.mark.unit
class TestScannerLoading:
    """Test scanner loading and instantiation."""
    
    @pytest.fixture
    def mock_system_manager(self):
        """Create mock system manager."""
        system_manager = Mock()
        system_manager.get_session_data.return_value = Mock()
        system_manager.get_time_manager.return_value = Mock()
        system_manager.session_config.mode = "backtest"
        return system_manager
    
    def test_load_scanner_success(self, mock_system_manager):
        """_load_scanner should load and instantiate scanner."""
        manager = ScannerManager(mock_system_manager)
        
        scanner_config = Mock()
        scanner_config.module = "scanners.examples.gap_scanner_complete"
        scanner_config.config = {"universe": "test.txt"}
        scanner_config.pre_session = True
        scanner_config.regular_session = None
        
        with patch("importlib.import_module") as mock_import:
            # Mock the module with a scanner class
            mock_module = Mock()
            mock_module.GapScannerComplete = MockScanner
            mock_import.return_value = mock_module
            
            result = manager._load_scanner(scanner_config)
        
        assert result is True
        assert len(manager._scanners) == 1
        assert "scanners.examples.gap_scanner_complete" in manager._scanners
    
    def test_load_scanner_import_fails(self, mock_system_manager):
        """_load_scanner should handle import errors."""
        manager = ScannerManager(mock_system_manager)
        
        scanner_config = Mock()
        scanner_config.module = "nonexistent.scanner"
        scanner_config.config = {}
        
        with patch("importlib.import_module", side_effect=ImportError("No module")):
            result = manager._load_scanner(scanner_config)
        
        assert result is False
        assert len(manager._scanners) == 0
    
    def test_load_scanner_no_scanner_class(self, mock_system_manager):
        """_load_scanner should fail if no BaseScanner subclass found."""
        from types import SimpleNamespace
        
        manager = ScannerManager(mock_system_manager)
        
        scanner_config = Mock()
        scanner_config.module = "some.module"
        scanner_config.config = {}
        
        with patch("importlib.import_module") as mock_import:
            # Mock module with no scanner class (only non-BaseScanner classes)
            mock_module = SimpleNamespace(
                SomeClass=str,  # Not a BaseScanner
                AnotherClass=int  # Also not a BaseScanner
            )
            mock_import.return_value = mock_module
            
            result = manager._load_scanner(scanner_config)
        
        assert result is False


@pytest.mark.unit
class TestScannerExecution:
    """Test scanner execution methods."""
    
    @pytest.fixture
    def manager_with_scanner(self):
        """Create manager with a loaded scanner."""
        system_manager = Mock()
        system_manager.get_session_data.return_value = Mock()
        system_manager.get_time_manager.return_value = Mock()
        system_manager.get_time_manager.return_value.get_current_time.return_value = datetime(2024, 1, 2, 9, 30)
        system_manager.session_config.mode = "backtest"
        
        manager = ScannerManager(system_manager)
        manager._session_data = Mock()
        manager._time_manager = Mock()
        manager._time_manager.get_current_time.return_value = datetime(2024, 1, 2, 9, 30)
        manager._mode = "backtest"
        
        # Add a mock scanner instance
        scanner = MockScanner({})
        instance = ScannerInstance(
            module="test.scanner",
            scanner=scanner,
            config={},
            pre_session=True
        )
        manager._scanners["test.scanner"] = instance
        
        return manager
    
    def test_execute_setup_success(self, manager_with_scanner):
        """_execute_setup should call scanner.setup()."""
        instance = manager_with_scanner._scanners["test.scanner"]
        
        # Mock scanner setup to return True
        with patch.object(instance.scanner, 'setup', return_value=True):
            result = manager_with_scanner._execute_setup(instance)
        
        assert result is True
        assert instance.state == ScannerState.SETUP_COMPLETE
        assert instance.error is None
    
    def test_execute_setup_failure(self, manager_with_scanner):
        """_execute_setup should handle setup failure."""
        instance = manager_with_scanner._scanners["test.scanner"]
        
        # Mock scanner setup to return False
        with patch.object(instance.scanner, 'setup', return_value=False):
            result = manager_with_scanner._execute_setup(instance)
        
        assert result is False
        assert instance.state == ScannerState.ERROR
        assert instance.error is not None
    
    def test_execute_scan_success(self, manager_with_scanner):
        """_execute_scan should call scanner.scan()."""
        instance = manager_with_scanner._scanners["test.scanner"]
        instance.state = ScannerState.SETUP_COMPLETE
        
        result = manager_with_scanner._execute_scan(instance, "pre-session")
        
        assert result is True
        assert instance.state == ScannerState.SCAN_COMPLETE
        assert instance.scan_count == 1
        assert "TEST" in instance.qualifying_symbols
    
    def test_execute_scan_skips_if_already_scanning(self, manager_with_scanner):
        """_execute_scan should skip if already scanning."""
        instance = manager_with_scanner._scanners["test.scanner"]
        instance.state = ScannerState.SCANNING
        
        result = manager_with_scanner._execute_scan(instance, "regular")
        
        assert result is True
        assert instance.scan_count == 0  # No scan executed
    
    def test_execute_teardown_success(self, manager_with_scanner):
        """_execute_teardown should call scanner.teardown()."""
        instance = manager_with_scanner._scanners["test.scanner"]
        instance.state = ScannerState.SCAN_COMPLETE
        
        result = manager_with_scanner._execute_teardown(instance)
        
        assert result is True
        assert instance.state == ScannerState.TEARDOWN_COMPLETE


@pytest.mark.unit
class TestScheduleManagement:
    """Test scanner schedule management."""
    
    def test_parse_time(self):
        """_parse_time should convert HH:MM to time object."""
        system_manager = Mock()
        manager = ScannerManager(system_manager)
        
        result = manager._parse_time("09:35")
        
        assert result == dt_time(9, 35)
    
    def test_parse_time_with_leading_zeros(self):
        """_parse_time should handle leading zeros."""
        system_manager = Mock()
        manager = ScannerManager(system_manager)
        
        result = manager._parse_time("08:05")
        
        assert result == dt_time(8, 5)


@pytest.mark.unit
class TestScannerManagerLifecycle:
    """Test full scanner manager lifecycle."""
    
    @pytest.fixture
    def manager_setup(self):
        """Setup manager with mock scanners."""
        system_manager = Mock()
        system_manager.get_session_data.return_value = Mock()
        system_manager.get_time_manager.return_value = Mock()
        system_manager.session_config.mode = "backtest"
        system_manager.session_config.session_data_config.scanners = []
        
        manager = ScannerManager(system_manager)
        manager._session_data = Mock()
        manager._time_manager = Mock()
        manager._mode = "backtest"
        
        return manager
    
    def test_on_session_start(self, manager_setup):
        """on_session_start should set flags."""
        manager_setup.on_session_start()
        
        assert manager_setup._session_started is True
    
    def test_on_session_end(self, manager_setup):
        """on_session_end should set flags and teardown scanners."""
        # Add a scanner
        scanner = MockScanner({})
        instance = ScannerInstance(
            module="test.scanner",
            scanner=scanner,
            config={},
            state=ScannerState.SCAN_COMPLETE
        )
        manager_setup._scanners["test.scanner"] = instance
        manager_setup._time_manager.get_current_time.return_value = datetime(2024, 1, 2, 16, 0)
        
        manager_setup.on_session_end()
        
        assert manager_setup._session_ended is True
        # Teardown should have been called
        assert instance.state == ScannerState.TEARDOWN_COMPLETE
    
    def test_get_scanner_states(self, manager_setup):
        """get_scanner_states should return scanner state dict."""
        # Add a scanner
        scanner = MockScanner({})
        instance = ScannerInstance(
            module="test.scanner",
            scanner=scanner,
            config={},
            state=ScannerState.SCAN_COMPLETE,
            scan_count=3
        )
        instance.qualifying_symbols.add("AAPL")
        manager_setup._scanners["test.scanner"] = instance
        
        states = manager_setup.get_scanner_states()
        
        assert "test.scanner" in states
        assert states["test.scanner"]["state"] == "scan_complete"
        assert states["test.scanner"]["scan_count"] == 3
        assert "AAPL" in states["test.scanner"]["qualifying_symbols"]
    
    def test_shutdown_tears_down_all_scanners(self, manager_setup):
        """shutdown should teardown all remaining scanners."""
        # Add scanners
        for i in range(3):
            scanner = MockScanner({})
            instance = ScannerInstance(
                module=f"test.scanner{i}",
                scanner=scanner,
                config={},
                state=ScannerState.SCAN_COMPLETE
            )
            manager_setup._scanners[f"test.scanner{i}"] = instance
        
        manager_setup._time_manager.get_current_time.return_value = datetime(2024, 1, 2, 16, 0)
        manager_setup.shutdown()
        
        # All should be torn down
        for instance in manager_setup._scanners.values():
            assert instance.state == ScannerState.TEARDOWN_COMPLETE
