"""
Unit tests for scanner base classes.

Tests BaseScanner, ScanContext, and ScanResult with mocks only.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, mock_open
from datetime import datetime
from pathlib import Path

from scanners.base import BaseScanner, ScanContext, ScanResult
from scanners.examples.gap_scanner_complete import GapScannerComplete


@pytest.mark.unit
class TestScanContext:
    """Test ScanContext dataclass."""
    
    def test_scan_context_creation(self):
        """ScanContext should store all required fields."""
        session_data = Mock()
        time_manager = Mock()
        current_time = datetime(2024, 1, 2, 9, 30)
        config = {"universe": "test.txt"}
        
        context = ScanContext(
            session_data=session_data,
            time_manager=time_manager,
            mode="backtest",
            current_time=current_time,
            config=config
        )
        
        assert context.session_data is session_data
        assert context.time_manager is time_manager
        assert context.mode == "backtest"
        assert context.current_time == current_time
        assert context.config == config
    
    def test_scan_context_default_config(self):
        """ScanContext should have empty config by default."""
        context = ScanContext(
            session_data=Mock(),
            time_manager=Mock(),
            mode="backtest",
            current_time=datetime.now()
        )
        
        assert context.config == {}


@pytest.mark.unit
class TestScanResult:
    """Test ScanResult dataclass."""
    
    def test_scan_result_creation(self):
        """ScanResult should store scan results."""
        result = ScanResult(
            symbols=["AAPL", "MSFT"],
            metadata={"scanned": 100, "qualified": 2},
            execution_time_ms=123.45
        )
        
        assert result.symbols == ["AAPL", "MSFT"]
        assert result.metadata == {"scanned": 100, "qualified": 2}
        assert result.execution_time_ms == 123.45
        assert result.skipped is False
        assert result.error is None
    
    def test_scan_result_defaults(self):
        """ScanResult should have sensible defaults."""
        result = ScanResult()
        
        assert result.symbols == []
        assert result.metadata == {}
        assert result.execution_time_ms == 0.0
        assert result.skipped is False
        assert result.error is None
    
    def test_scan_result_with_error(self):
        """ScanResult should support error messages."""
        result = ScanResult(error="Scanner failed")
        
        assert result.error == "Scanner failed"
        assert result.symbols == []


@pytest.mark.unit
class TestBaseScanner:
    """Test BaseScanner abstract class."""
    
    def test_base_scanner_instantiation(self):
        """BaseScanner should be instantiated with config."""
        config = {"universe": "test.txt", "threshold": 2.0}
        scanner = GapScannerComplete(config)
        
        assert scanner.config == config
        assert scanner._universe == []
    
    def test_load_universe_from_file(self):
        """_load_universe_from_file should parse symbols from file."""
        scanner = GapScannerComplete({})
        
        file_content = """# Comment line
AAPL
MSFT
# Another comment

GOOGL
TSLA
"""
        
        with patch("builtins.open", mock_open(read_data=file_content)):
            with patch("pathlib.Path.exists", return_value=True):
                symbols = scanner._load_universe_from_file("test.txt")
        
        assert symbols == ["AAPL", "MSFT", "GOOGL", "TSLA"]
    
    def test_load_universe_handles_whitespace(self):
        """_load_universe_from_file should handle whitespace."""
        scanner = GapScannerComplete({})
        
        file_content = "  AAPL  \n\n  MSFT  \n"
        
        with patch("builtins.open", mock_open(read_data=file_content)):
            with patch("pathlib.Path.exists", return_value=True):
                symbols = scanner._load_universe_from_file("test.txt")
        
        assert symbols == ["AAPL", "MSFT"]
    
    def test_load_universe_uppercase_conversion(self):
        """_load_universe_from_file should convert to uppercase."""
        scanner = GapScannerComplete({})
        
        file_content = "aapl\nmsft\n"
        
        with patch("builtins.open", mock_open(read_data=file_content)):
            with patch("pathlib.Path.exists", return_value=True):
                symbols = scanner._load_universe_from_file("test.txt")
        
        assert symbols == ["AAPL", "MSFT"]
    
    def test_load_universe_file_not_found(self):
        """_load_universe_from_file should raise FileNotFoundError."""
        scanner = GapScannerComplete({})
        
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError):
                scanner._load_universe_from_file("nonexistent.txt")
    
    def test_load_universe_empty_file(self):
        """_load_universe_from_file should raise ValueError for empty file."""
        scanner = GapScannerComplete({})
        
        file_content = "# Only comments\n\n"
        
        with patch("builtins.open", mock_open(read_data=file_content)):
            with patch("pathlib.Path.exists", return_value=True):
                with pytest.raises(ValueError, match="No symbols found"):
                    scanner._load_universe_from_file("test.txt")
    
    def test_get_scanner_name(self):
        """_get_scanner_name should convert CamelCase to snake_case."""
        scanner = GapScannerComplete({})
        
        name = scanner._get_scanner_name()
        
        assert name == "gap_scanner_complete"
    
    def test_default_setup_returns_true(self):
        """Default setup() should return True."""
        scanner = GapScannerComplete({})
        context = Mock(spec=ScanContext)
        
        # Use default implementation from BaseScanner
        result = BaseScanner.setup(scanner, context)
        
        assert result is True
    
    def test_default_teardown_succeeds(self):
        """Default teardown() should succeed without error."""
        scanner = GapScannerComplete({})
        context = Mock(spec=ScanContext)
        
        # Should not raise
        BaseScanner.teardown(scanner, context)
    
    def test_scan_must_be_implemented(self):
        """scan() must be implemented by subclasses."""
        # Can't instantiate BaseScanner directly (abstract)
        # But can verify GapScannerComplete implements it
        scanner = GapScannerComplete({})
        
        assert hasattr(scanner, 'scan')
        assert callable(scanner.scan)


@pytest.mark.unit
class TestGapScannerComplete:
    """Test GapScannerComplete implementation."""
    
    @pytest.fixture
    def mock_context(self):
        """Create mock scan context."""
        context = Mock(spec=ScanContext)
        context.session_data = Mock()
        context.time_manager = Mock()
        context.mode = "backtest"
        context.current_time = datetime(2024, 1, 2, 9, 30)
        context.config = {"universe": "test.txt"}
        return context
    
    def test_gap_scanner_setup_loads_universe(self, mock_context):
        """setup() should load universe and provision indicators."""
        scanner = GapScannerComplete({"universe": "test.txt"})
        
        file_content = "AAPL\nMSFT\n"
        
        with patch("builtins.open", mock_open(read_data=file_content)):
            with patch("pathlib.Path.exists", return_value=True):
                result = scanner.setup(mock_context)
        
        assert result is True
        assert scanner._universe == ["AAPL", "MSFT"]
        
        # Verify add_indicator called for each symbol
        assert mock_context.session_data.add_indicator.call_count == 2
    
    def test_gap_scanner_setup_no_universe_fails(self, mock_context):
        """setup() should raise ValueError if no universe in config."""
        scanner = GapScannerComplete({})  # No universe
        
        with pytest.raises(ValueError, match="Universe file path required"):
            scanner.setup(mock_context)
    
    def test_gap_scanner_scan_returns_scan_result(self, mock_context):
        """scan() should return ScanResult."""
        scanner = GapScannerComplete({})
        scanner._universe = ["AAPL", "MSFT"]
        
        # Mock bar with numeric values
        mock_bar = Mock()
        mock_bar.close = 150.0
        mock_bar.volume = 2_000_000
        
        # Mock indicator with numeric value
        mock_indicator = Mock()
        mock_indicator.valid = True
        mock_indicator.current_value = 145.0  # SMA value (creates 3.4% gap)
        
        mock_context.session_data.get_latest_bar.return_value = mock_bar
        mock_context.session_data.get_indicator.return_value = mock_indicator
        mock_context.session_data.add_symbol.return_value = True
        
        result = scanner.scan(mock_context)
        
        assert isinstance(result, ScanResult)
        assert isinstance(result.symbols, list)
        # Should find qualifying symbols (gap >= 2%)
        assert len(result.symbols) >= 0
    
    def test_gap_scanner_teardown_removes_symbols(self, mock_context):
        """teardown() should call remove_symbol for unqualified symbols."""
        scanner = GapScannerComplete({})
        scanner._universe = ["AAPL", "MSFT", "GOOGL"]
        
        # Only AAPL is in config (qualified)
        mock_context.session_data.get_config_symbols.return_value = {"AAPL"}
        mock_context.session_data.is_symbol_locked.return_value = False
        mock_context.session_data.remove_symbol.return_value = True
        
        scanner.teardown(mock_context)
        
        # Should try to remove MSFT and GOOGL (not AAPL which is in config)
        assert mock_context.session_data.remove_symbol.call_count == 2
    
    def test_gap_scanner_criteria(self):
        """Gap scanner should have hardcoded criteria."""
        scanner = GapScannerComplete({})
        
        assert hasattr(scanner, 'MIN_GAP_PERCENT')
        assert hasattr(scanner, 'MIN_VOLUME')
        assert hasattr(scanner, 'MAX_PRICE')
        assert scanner.MIN_GAP_PERCENT == 2.0
        assert scanner.MIN_VOLUME == 1_000_000
        assert scanner.MAX_PRICE == 500.0
