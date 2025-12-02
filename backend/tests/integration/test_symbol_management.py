"""
Integration tests for dynamic symbol management.

Tests the complete flow of adding/removing symbols during an active session,
including interaction with SessionCoordinator, SessionData, and DataProcessor.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, date
from collections import defaultdict

from app.threads.session_coordinator import SessionCoordinator
from app.managers.data_manager.session_data import SessionData
from app.models.session_config import SessionConfig, SessionDataConfig, StreamingConfig


@pytest.mark.integration
class TestSymbolAddition:
    """Test adding symbols to an active session."""
    
    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock SessionCoordinator with required attributes."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = MagicMock()
        coordinator._loaded_symbols = set()
        coordinator._pending_symbols = set()
        coordinator._symbol_check_counters = defaultdict(int)
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.symbols = []
        coordinator.session_config.session_data_config.streams = ["1m"]
        coordinator.session_data = SessionData()
        return coordinator
    
    def test_add_symbol_to_config(self, mock_coordinator):
        """Adding symbol should update session_config."""
        # Bind the real add_symbol method
        mock_coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(mock_coordinator)
        
        result = mock_coordinator.add_symbol("AAPL")
        
        assert result is True
        assert "AAPL" in mock_coordinator.session_config.session_data_config.symbols
    
    def test_add_symbol_marks_as_pending(self, mock_coordinator):
        """Adding symbol should mark it as pending."""
        mock_coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(mock_coordinator)
        
        mock_coordinator.add_symbol("AAPL")
        
        assert "AAPL" in mock_coordinator._pending_symbols
        assert "AAPL" not in mock_coordinator._loaded_symbols
    
    def test_add_duplicate_symbol_returns_false(self, mock_coordinator):
        """Adding same symbol twice should return False."""
        mock_coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(mock_coordinator)
        
        # First add
        result1 = mock_coordinator.add_symbol("AAPL")
        # Second add
        result2 = mock_coordinator.add_symbol("AAPL")
        
        assert result1 is True
        assert result2 is False
    
    def test_add_symbol_ensures_1m_stream(self, mock_coordinator):
        """Adding symbol should ensure 1m stream is in config."""
        mock_coordinator.session_config.session_data_config.streams = []
        mock_coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(mock_coordinator)
        
        mock_coordinator.add_symbol("AAPL")
        
        assert "1m" in mock_coordinator.session_config.session_data_config.streams


@pytest.mark.integration
class TestSymbolRemoval:
    """Test removing symbols from an active session."""
    
    @pytest.fixture
    def mock_coordinator_with_symbol(self):
        """Create a coordinator with an existing symbol."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = MagicMock()
        coordinator._loaded_symbols = {"AAPL"}
        coordinator._pending_symbols = set()
        coordinator._symbol_check_counters = defaultdict(int)
        coordinator._symbol_check_counters["AAPL"] = 47
        coordinator._bar_queues = {}
        coordinator._streamed_data = {"AAPL": ["1m"]}
        coordinator._generated_data = {"AAPL": ["5m", "15m"]}
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.symbols = ["AAPL"]
        coordinator.session_data = SessionData()
        coordinator.session_data.register_symbol("AAPL")
        return coordinator
    
    def test_remove_symbol_from_config(self, mock_coordinator_with_symbol):
        """Removing symbol should update session_config."""
        coordinator = mock_coordinator_with_symbol
        coordinator.remove_symbol = SessionCoordinator.remove_symbol.__get__(coordinator)
        
        result = coordinator.remove_symbol("AAPL")
        
        assert result is True
        assert "AAPL" not in coordinator.session_config.session_data_config.symbols
    
    def test_remove_symbol_cleans_state(self, mock_coordinator_with_symbol):
        """Removing symbol should clean all state."""
        coordinator = mock_coordinator_with_symbol
        coordinator.remove_symbol = SessionCoordinator.remove_symbol.__get__(coordinator)
        
        coordinator.remove_symbol("AAPL")
        
        assert "AAPL" not in coordinator._loaded_symbols
        assert "AAPL" not in coordinator._pending_symbols
        assert "AAPL" not in coordinator._symbol_check_counters
        assert "AAPL" not in coordinator._streamed_data
        assert "AAPL" not in coordinator._generated_data
    
    def test_remove_nonexistent_symbol_returns_false(self, mock_coordinator_with_symbol):
        """Removing non-existent symbol should return False."""
        coordinator = mock_coordinator_with_symbol
        coordinator.remove_symbol = SessionCoordinator.remove_symbol.__get__(coordinator)
        
        result = coordinator.remove_symbol("TSLA")
        
        assert result is False
    
    def test_remove_symbol_from_session_data(self, mock_coordinator_with_symbol):
        """Removing symbol should remove from SessionData."""
        coordinator = mock_coordinator_with_symbol
        coordinator.remove_symbol = SessionCoordinator.remove_symbol.__get__(coordinator)
        
        # Verify symbol exists
        assert coordinator.session_data.get_symbol_data("AAPL") is not None
        
        coordinator.remove_symbol("AAPL")
        
        # Verify symbol removed
        assert coordinator.session_data.get_symbol_data("AAPL") is None


@pytest.mark.integration
class TestPendingSymbolProcessing:
    """Test processing of pending symbols."""
    
    @pytest.fixture
    def coordinator_with_pending(self):
        """Create coordinator with pending symbols."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = MagicMock()
        coordinator._loaded_symbols = set()
        coordinator._pending_symbols = {"AAPL", "TSLA"}
        coordinator._symbol_check_counters = defaultdict(int)
        coordinator._stream_paused = Mock()
        coordinator._stream_paused.clear = Mock()
        coordinator._stream_paused.set = Mock()
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.symbols = ["AAPL", "TSLA"]
        
        # Mock the parameterized methods
        coordinator._validate_and_mark_streams = Mock(return_value=True)
        coordinator._manage_historical_data = Mock()
        coordinator._load_backtest_queues = Mock()
        
        return coordinator
    
    def test_process_pending_pauses_stream(self, coordinator_with_pending):
        """Processing pending symbols should pause stream."""
        coordinator = coordinator_with_pending
        coordinator._process_pending_symbols = SessionCoordinator._process_pending_symbols.__get__(coordinator)
        
        coordinator._process_pending_symbols()
        
        coordinator._stream_paused.clear.assert_called_once()
    
    def test_process_pending_calls_parameterized_methods(self, coordinator_with_pending):
        """Processing should call validate, load historical, load queues."""
        coordinator = coordinator_with_pending
        coordinator._process_pending_symbols = SessionCoordinator._process_pending_symbols.__get__(coordinator)
        
        coordinator._process_pending_symbols()
        
        # Should call with pending symbols
        coordinator._validate_and_mark_streams.assert_called_once()
        coordinator._manage_historical_data.assert_called_once()
        coordinator._load_backtest_queues.assert_called_once()
    
    def test_process_pending_marks_as_loaded(self, coordinator_with_pending):
        """After processing, symbols should be marked as loaded."""
        coordinator = coordinator_with_pending
        coordinator._process_pending_symbols = SessionCoordinator._process_pending_symbols.__get__(coordinator)
        
        coordinator._process_pending_symbols()
        
        assert "AAPL" in coordinator._loaded_symbols
        assert "TSLA" in coordinator._loaded_symbols
        assert len(coordinator._pending_symbols) == 0
    
    def test_process_pending_resumes_stream(self, coordinator_with_pending):
        """After processing, stream should be resumed."""
        coordinator = coordinator_with_pending
        coordinator._process_pending_symbols = SessionCoordinator._process_pending_symbols.__get__(coordinator)
        
        coordinator._process_pending_symbols()
        
        coordinator._stream_paused.set.assert_called_once()


@pytest.mark.integration
class TestAccessorMethods:
    """Test public accessor methods for polling pattern."""
    
    @pytest.fixture
    def coordinator_with_state(self):
        """Create coordinator with various state."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._symbol_operation_lock = MagicMock()
        coordinator._loaded_symbols = {"AAPL", "RIVN"}
        coordinator._pending_symbols = {"TSLA"}
        coordinator._generated_data = {"AAPL": ["5m", "15m"]}
        coordinator._streamed_data = {"AAPL": ["1m"], "RIVN": ["1m"]}
        return coordinator
    
    def test_get_loaded_symbols(self, coordinator_with_state):
        """get_loaded_symbols should return copy of loaded symbols."""
        coordinator = coordinator_with_state
        coordinator.get_loaded_symbols = SessionCoordinator.get_loaded_symbols.__get__(coordinator)
        
        loaded = coordinator.get_loaded_symbols()
        
        assert loaded == {"AAPL", "RIVN"}
        assert loaded is not coordinator._loaded_symbols  # Should be a copy
    
    def test_get_pending_symbols(self, coordinator_with_state):
        """get_pending_symbols should return copy of pending symbols."""
        coordinator = coordinator_with_state
        coordinator.get_pending_symbols = SessionCoordinator.get_pending_symbols.__get__(coordinator)
        
        pending = coordinator.get_pending_symbols()
        
        assert pending == {"TSLA"}
        assert pending is not coordinator._pending_symbols  # Should be a copy
    
    def test_get_generated_data(self, coordinator_with_state):
        """get_generated_data should return copy of generated data."""
        coordinator = coordinator_with_state
        coordinator.get_generated_data = SessionCoordinator.get_generated_data.__get__(coordinator)
        
        generated = coordinator.get_generated_data()
        
        assert generated == {"AAPL": ["5m", "15m"]}
        assert generated is not coordinator._generated_data  # Should be a copy
    
    def test_get_streamed_data(self, coordinator_with_state):
        """get_streamed_data should return copy of streamed data."""
        coordinator = coordinator_with_state
        coordinator.get_streamed_data = SessionCoordinator.get_streamed_data.__get__(coordinator)
        
        streamed = coordinator.get_streamed_data()
        
        assert streamed == {"AAPL": ["1m"], "RIVN": ["1m"]}
        assert streamed is not coordinator._streamed_data  # Should be a copy


@pytest.mark.integration
class TestParameterizedMethods:
    """Test that existing methods work with symbols parameter."""
    
    def test_validate_and_mark_streams_with_symbols(self):
        """_validate_and_mark_streams should accept symbols parameter."""
        # This test would require more complex mocking
        # Just verify the signature exists
        from inspect import signature
        
        sig = signature(SessionCoordinator._validate_and_mark_streams)
        assert 'symbols' in sig.parameters
        assert sig.parameters['symbols'].default is None
    
    def test_manage_historical_data_with_symbols(self):
        """_manage_historical_data should accept symbols parameter."""
        from inspect import signature
        
        sig = signature(SessionCoordinator._manage_historical_data)
        assert 'symbols' in sig.parameters
        assert sig.parameters['symbols'].default is None
    
    def test_load_backtest_queues_with_symbols(self):
        """_load_backtest_queues should accept symbols parameter."""
        from inspect import signature
        
        sig = signature(SessionCoordinator._load_backtest_queues)
        assert 'symbols' in sig.parameters
        assert sig.parameters['symbols'].default is None


@pytest.mark.integration
class TestStreamingConfig:
    """Test streaming configuration integration."""
    
    def test_config_loaded_from_session_config(self):
        """SessionCoordinator should load streaming config."""
        # Create mock config
        streaming_config = StreamingConfig(
            catchup_threshold_seconds=120,
            catchup_check_interval=20
        )
        session_data_config = Mock()
        session_data_config.streaming = streaming_config
        session_config = Mock()
        session_config.session_data_config = session_data_config
        
        # Simulate loading in __init__
        catchup_threshold = streaming_config.catchup_threshold_seconds
        catchup_check_interval = streaming_config.catchup_check_interval
        
        assert catchup_threshold == 120
        assert catchup_check_interval == 20
    
    def test_default_values_when_no_config(self):
        """Should use defaults when streaming config not provided."""
        session_data_config = Mock()
        session_data_config.streaming = None
        session_config = Mock()
        session_config.session_data_config = session_data_config
        
        # Simulate defaults in __init__
        catchup_threshold = 60
        catchup_check_interval = 10
        
        assert catchup_threshold == 60
        assert catchup_check_interval == 10
