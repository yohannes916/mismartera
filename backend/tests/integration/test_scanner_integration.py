"""
Integration tests for scanner framework.

Tests scanner execution with real SessionData and mocked system components.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, mock_open
from datetime import datetime
from pathlib import Path

from app.threads.scanner_manager import ScannerManager, ScannerState
from app.managers.data_manager.session_data import SessionData, get_session_data
from scanners.base import BaseScanner, ScanContext, ScanResult
from scanners.examples.gap_scanner_complete import GapScannerComplete
from app.models.session_config import SessionConfig


class TestScanner(BaseScanner):
    """Test scanner for integration tests."""
    
    def __init__(self, config):
        super().__init__(config)
        self.setup_called = False
        self.scan_called = False
        self.teardown_called = False
    
    def setup(self, context: ScanContext) -> bool:
        self.setup_called = True
        self._universe = ["AAPL", "MSFT", "GOOGL"]
        
        # Provision lightweight data
        for symbol in self._universe:
            context.session_data.add_indicator(symbol, "sma", {
                "period": 20,
                "interval": "1d"
            })
        
        return True
    
    def scan(self, context: ScanContext) -> ScanResult:
        self.scan_called = True
        
        # Simple criteria: just return first 2 symbols
        qualifying = self._universe[:2]
        
        # Promote symbols
        for symbol in qualifying:
            context.session_data.add_symbol(symbol)
        
        return ScanResult(
            symbols=qualifying,
            metadata={"scanned": len(self._universe)}
        )
    
    def teardown(self, context: ScanContext):
        self.teardown_called = True
        
        # Remove unqualified symbols
        config_symbols = context.session_data.get_config_symbols()
        qualified = set(self._universe[:2])
        
        for symbol in self._universe:
            if symbol not in config_symbols and symbol not in qualified:
                context.session_data.remove_symbol_adhoc(symbol)


@pytest.mark.integration
class TestScannerWithSessionData:
    """Test scanner execution with real SessionData."""
    
    @pytest.fixture
    def session_data(self):
        """Create fresh SessionData instance."""
        session_data = SessionData()
        yield session_data
        # Cleanup
        session_data._symbols.clear()
    
    @pytest.fixture
    def mock_system_manager(self, session_data):
        """Create mock system manager with real SessionData."""
        system_manager = Mock()
        system_manager.get_session_data.return_value = session_data
        
        time_manager = Mock()
        time_manager.get_current_time.return_value = datetime(2024, 1, 2, 9, 30)
        system_manager.get_time_manager.return_value = time_manager
        
        system_manager.session_config = Mock()
        system_manager.session_config.mode = "backtest"
        system_manager.session_config.session_data_config.scanners = []
        
        return system_manager
    
    def test_scanner_setup_provisions_data(self, session_data, mock_system_manager):
        """Scanner setup should provision indicators in SessionData."""
        scanner = TestScanner({})
        context = ScanContext(
            session_data=session_data,
            time_manager=mock_system_manager.get_time_manager(),
            mode="backtest",
            current_time=datetime(2024, 1, 2, 9, 30),
            config={}
        )
        
        result = scanner.setup(context)
        
        assert result is True
        assert scanner.setup_called is True
        # Note: add_indicator is a placeholder in this test
        # In real usage it would provision bars via requirement_analyzer
    
    def test_scanner_scan_promotes_symbols(self, session_data, mock_system_manager):
        """Scanner scan should promote symbols via add_symbol."""
        scanner = TestScanner({})
        scanner._universe = ["AAPL", "MSFT", "GOOGL"]
        
        context = ScanContext(
            session_data=session_data,
            time_manager=mock_system_manager.get_time_manager(),
            mode="backtest",
            current_time=datetime(2024, 1, 2, 9, 30),
            config={}
        )
        
        # Register symbols in session_data first
        for symbol in scanner._universe:
            session_data.register_symbol(symbol)
        
        result = scanner.scan(context)
        
        assert result.symbols == ["AAPL", "MSFT"]
        assert result.metadata["scanned"] == 3
        assert scanner.scan_called is True
    
    def test_scanner_teardown_removes_symbols(self, session_data, mock_system_manager):
        """Scanner teardown should remove unqualified symbols."""
        scanner = TestScanner({})
        scanner._universe = ["AAPL", "MSFT", "GOOGL"]
        
        # Register all symbols
        for symbol in scanner._universe:
            session_data.register_symbol(symbol)
        
        context = ScanContext(
            session_data=session_data,
            time_manager=mock_system_manager.get_time_manager(),
            mode="backtest",
            current_time=datetime(2024, 1, 2, 9, 30),
            config={}
        )
        
        # Track config symbols (empty for this test)
        session_data._config_symbols = set()
        
        scanner.teardown(context)
        
        assert scanner.teardown_called is True


@pytest.mark.integration
class TestScannerManagerIntegration:
    """Test ScannerManager with real components."""
    
    @pytest.fixture
    def session_data(self):
        """Create fresh SessionData instance."""
        session_data = SessionData()
        yield session_data
        session_data._symbols.clear()
    
    @pytest.fixture
    def manager_with_real_scanner(self, session_data):
        """Create ScannerManager with test scanner."""
        system_manager = Mock()
        system_manager.get_session_data.return_value = session_data
        
        time_manager = Mock()
        time_manager.get_current_time.return_value = datetime(2024, 1, 2, 9, 30)
        system_manager.get_time_manager.return_value = time_manager
        
        system_manager.session_config = Mock()
        system_manager.session_config.mode = "backtest"
        
        # Create scanner config
        scanner_config = Mock()
        scanner_config.module = "test_scanner"
        scanner_config.enabled = True
        scanner_config.pre_session = True
        scanner_config.regular_session = None
        scanner_config.config = {}
        
        system_manager.session_config.session_data_config.scanners = [scanner_config]
        
        manager = ScannerManager(system_manager)
        
        # Manually add test scanner
        from app.threads.scanner_manager import ScannerInstance
        scanner = TestScanner({})
        instance = ScannerInstance(
            module="test_scanner",
            scanner=scanner,
            config={},
            pre_session=True,  # Enable pre-session scanning
            regular_schedules=[]  # No regular schedules (pre-session only)
        )
        manager._scanners["test_scanner"] = instance
        manager._session_data = session_data
        manager._time_manager = time_manager
        manager._mode = "backtest"
        manager._initialized = True
        
        return manager
    
    def test_setup_pre_session_scanners_executes_lifecycle(self, manager_with_real_scanner):
        """setup_pre_session_scanners should execute full lifecycle."""
        result = manager_with_real_scanner.setup_pre_session_scanners()
        
        assert result is True
        
        scanner = manager_with_real_scanner._scanners["test_scanner"].scanner
        assert scanner.setup_called is True
        assert scanner.scan_called is True
        assert scanner.teardown_called is True
    
    def test_scanner_state_progression(self, manager_with_real_scanner):
        """Scanner should progress through states correctly."""
        instance = manager_with_real_scanner._scanners["test_scanner"]
        
        # Initial state
        assert instance.state == ScannerState.INITIALIZED
        
        # After setup
        manager_with_real_scanner._execute_setup(instance)
        assert instance.state == ScannerState.SETUP_COMPLETE
        
        # After scan
        manager_with_real_scanner._execute_scan(instance, "pre-session")
        assert instance.state == ScannerState.SCAN_COMPLETE
        assert instance.scan_count == 1
        
        # After teardown
        manager_with_real_scanner._execute_teardown(instance)
        assert instance.state == ScannerState.TEARDOWN_COMPLETE
    
    def test_scanner_qualifying_symbols_tracked(self, manager_with_real_scanner):
        """Scanner should track qualifying symbols."""
        instance = manager_with_real_scanner._scanners["test_scanner"]
        
        manager_with_real_scanner._execute_setup(instance)
        manager_with_real_scanner._execute_scan(instance, "pre-session")
        
        assert len(instance.qualifying_symbols) == 2
        assert "AAPL" in instance.qualifying_symbols
        assert "MSFT" in instance.qualifying_symbols


@pytest.mark.integration
class TestScannerConfigLoading:
    """Test scanner loading from real config files."""
    
    def test_load_scanner_from_config(self):
        """Scanner manager should load scanners from config."""
        # Create a test config
        config_data = {
            "mode": "backtest",
            "session_data_config": {
                "symbols": ["AAPL"],
                "streams": ["1m"],
                "scanners": [
                    {
                        "module": "scanners.examples.gap_scanner_complete",
                        "enabled": True,
                        "pre_session": True,
                        "config": {
                            "universe": "data/universes/test.txt"
                        }
                    }
                ]
            }
        }
        
        # Mock system manager
        system_manager = Mock()
        session_data = SessionData()
        system_manager.get_session_data.return_value = session_data
        
        time_manager = Mock()
        time_manager.get_current_time.return_value = datetime(2024, 1, 2, 9, 30)
        system_manager.get_time_manager.return_value = time_manager
        
        # Create config from dict
        with patch.object(SessionConfig, 'from_file') as mock_from_file:
            mock_config = Mock()
            mock_config.mode = "backtest"
            mock_config.session_data_config.scanners = []
            
            # Create scanner config mock
            scanner_config = Mock()
            scanner_config.module = "scanners.examples.gap_scanner_complete"
            scanner_config.enabled = True
            scanner_config.pre_session = True
            scanner_config.regular_session = None
            scanner_config.config = {"universe": "data/universes/test.txt"}
            
            mock_config.session_data_config.scanners = [scanner_config]
            mock_from_file.return_value = mock_config
            system_manager.session_config = mock_config
            
            manager = ScannerManager(system_manager)
            
            # Mock the import
            with patch("importlib.import_module") as mock_import:
                mock_module = Mock()
                mock_module.GapScannerComplete = GapScannerComplete
                mock_import.return_value = mock_module
                
                result = manager.initialize()
        
        assert result is True
        assert len(manager._scanners) == 1
        assert "scanners.examples.gap_scanner_complete" in manager._scanners


@pytest.mark.integration
class TestScannerErrorHandling:
    """Test scanner error handling."""
    
    def test_scanner_setup_failure_handled(self):
        """Scanner setup failure should be handled gracefully."""
        class FailingScanner(BaseScanner):
            def setup(self, context):
                raise ValueError("Setup failed")
            
            def scan(self, context):
                return ScanResult()
        
        system_manager = Mock()
        session_data = SessionData()
        system_manager.get_session_data.return_value = session_data
        
        time_manager = Mock()
        time_manager.get_current_time.return_value = datetime(2024, 1, 2, 9, 30)
        system_manager.get_time_manager.return_value = time_manager
        
        manager = ScannerManager(system_manager)
        manager._session_data = session_data
        manager._time_manager = time_manager
        manager._mode = "backtest"
        
        from app.threads.scanner_manager import ScannerInstance
        scanner = FailingScanner({})
        instance = ScannerInstance(
            module="failing_scanner",
            scanner=scanner,
            config={}
        )
        
        result = manager._execute_setup(instance)
        
        assert result is False
        assert instance.state == ScannerState.ERROR
        assert instance.error is not None
        assert "Setup failed" in instance.error
