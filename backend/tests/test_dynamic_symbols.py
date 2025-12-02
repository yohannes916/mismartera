"""
Unit tests for dynamic symbol management feature.

Tests the ability to add/remove symbols during an active session,
including pause/resume, session deactivation, and catchup logic.
"""

import pytest
import threading
import queue
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, date, time
from collections import deque

# Import the components we're testing
from app.threads.session_coordinator import SessionCoordinator
from app.managers.data_manager.session_data import SessionData
from app.threads.data_processor import DataProcessor


class TestDynamicSymbolValidation:
    """Test validation logic in add_symbol()."""
    
    def test_add_symbol_when_not_running(self):
        """Should raise RuntimeError when session not running."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._running = False
        coordinator._symbol_operation_lock = threading.Lock()
        coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(coordinator)
        
        with pytest.raises(RuntimeError, match="session not running"):
            coordinator.add_symbol("AAPL")
    
    def test_add_symbol_already_dynamic(self):
        """Should return False when symbol already added dynamically."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._running = True
        coordinator._dynamic_symbols = {"AAPL"}
        coordinator._symbol_operation_lock = threading.Lock()
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config.symbols = []
        coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(coordinator)
        
        result = coordinator.add_symbol("AAPL")
        assert result is False
    
    def test_add_symbol_already_in_config(self):
        """Should return False when symbol already in initial config."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._running = True
        coordinator._dynamic_symbols = set()
        coordinator._symbol_operation_lock = threading.Lock()
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config.symbols = ["AAPL"]
        coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(coordinator)
        
        result = coordinator.add_symbol("AAPL")
        assert result is False
    
    def test_add_symbol_valid_backtest(self):
        """Should queue request and return True in backtest mode."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._running = True
        coordinator._dynamic_symbols = set()
        coordinator._symbol_operation_lock = threading.Lock()
        coordinator._pending_symbol_additions = queue.Queue()
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config.symbols = []
        coordinator.mode = "backtest"
        coordinator._time_manager = Mock()
        coordinator._time_manager.get_current_time.return_value = datetime.now()
        
        # Bind methods
        coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(coordinator)
        coordinator._add_symbol_backtest = SessionCoordinator._add_symbol_backtest.__get__(coordinator)
        
        result = coordinator.add_symbol("TSLA")
        
        assert result is True
        assert not coordinator._pending_symbol_additions.empty()
        request = coordinator._pending_symbol_additions.get()
        assert request["symbol"] == "TSLA"
        assert request["streams"] == ["1m"]


class TestSessionDataAccessControl:
    """Test SessionData access blocking when deactivated."""
    
    def test_get_latest_bar_when_active(self):
        """Should return bar when session active."""
        session_data = SessionData()
        session_data._session_active = True
        session_data.register_symbol("AAPL")
        
        # Should not block access
        result = session_data.get_latest_bar("AAPL", interval=1)
        # Result is None because no bars, but access was allowed
        assert result is None
    
    def test_get_latest_bar_when_deactivated(self):
        """Should return None when session deactivated."""
        session_data = SessionData()
        session_data._session_active = False
        session_data.register_symbol("AAPL")
        
        # Should block access
        result = session_data.get_latest_bar("AAPL", interval=1)
        assert result is None
    
    def test_get_last_n_bars_when_deactivated(self):
        """Should return empty list when session deactivated."""
        session_data = SessionData()
        session_data._session_active = False
        session_data.register_symbol("AAPL")
        
        result = session_data.get_last_n_bars("AAPL", n=10, interval=1)
        assert result == []
    
    def test_get_bars_since_when_deactivated(self):
        """Should return empty list when session deactivated."""
        session_data = SessionData()
        session_data._session_active = False
        session_data.register_symbol("AAPL")
        
        result = session_data.get_bars_since("AAPL", datetime.now(), interval=1)
        assert result == []
    
    def test_get_bar_count_when_deactivated(self):
        """Should return 0 when session deactivated."""
        session_data = SessionData()
        session_data._session_active = False
        session_data.register_symbol("AAPL")
        
        result = session_data.get_bar_count("AAPL", interval=1)
        assert result == 0
    
    def test_get_active_symbols_when_deactivated(self):
        """Should return empty set when session deactivated."""
        session_data = SessionData()
        session_data._session_active = False
        session_data.register_symbol("AAPL")
        session_data.register_symbol("TSLA")
        
        result = session_data.get_active_symbols()
        assert result == set()


class TestDataProcessorNotifications:
    """Test DataProcessor notification pause/resume."""
    
    def test_notifications_initially_active(self):
        """Notifications should be active on initialization."""
        processor = Mock(spec=DataProcessor)
        processor._notifications_paused = threading.Event()
        processor._notifications_paused.set()  # Active
        
        assert processor._notifications_paused.is_set()
    
    def test_pause_notifications(self):
        """Should clear event when paused."""
        processor = Mock(spec=DataProcessor)
        processor._notifications_paused = threading.Event()
        processor._notifications_paused.set()  # Active
        processor.pause_notifications = DataProcessor.pause_notifications.__get__(processor)
        
        processor.pause_notifications()
        
        assert not processor._notifications_paused.is_set()
    
    def test_resume_notifications(self):
        """Should set event when resumed."""
        processor = Mock(spec=DataProcessor)
        processor._notifications_paused = threading.Event()
        processor._notifications_paused.clear()  # Paused
        processor.resume_notifications = DataProcessor.resume_notifications.__get__(processor)
        
        processor.resume_notifications()
        
        assert processor._notifications_paused.is_set()
    
    def test_notify_drops_when_paused(self):
        """Should drop notifications when paused."""
        processor = Mock(spec=DataProcessor)
        processor._notifications_paused = threading.Event()
        processor._notifications_paused.clear()  # Paused
        processor._analysis_engine_queue = queue.Queue()
        processor._derived_intervals = [5]  # List of integers, not dict
        processor._realtime_indicators = []
        processor._notify_analysis_engine = DataProcessor._notify_analysis_engine.__get__(processor)
        
        processor._notify_analysis_engine("AAPL", "1m")
        
        # Queue should be empty (notification dropped)
        assert processor._analysis_engine_queue.empty()
    
    def test_notify_sends_when_active(self):
        """Should send notifications when active."""
        processor = Mock(spec=DataProcessor)
        processor._notifications_paused = threading.Event()
        processor._notifications_paused.set()  # Active
        processor._analysis_engine_queue = queue.Queue()
        processor._derived_intervals = [5]  # List of integers, not dict
        processor._realtime_indicators = []
        processor._notify_analysis_engine = DataProcessor._notify_analysis_engine.__get__(processor)
        
        processor._notify_analysis_engine("AAPL", "1m")
        
        # Queue should have notification
        assert not processor._analysis_engine_queue.empty()
        notification = processor._analysis_engine_queue.get()
        assert notification == ("AAPL", "5m", "bars")


class TestBacktestCatchupFlow:
    """Test backtest mode catchup logic."""
    
    def test_pending_queue_initially_empty(self):
        """Pending additions queue should start empty."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._pending_symbol_additions = queue.Queue()
        
        assert coordinator._pending_symbol_additions.empty()
    
    def test_process_returns_early_when_empty(self):
        """Should return immediately when no pending additions."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._pending_symbol_additions = queue.Queue()
        coordinator._process_pending_symbol_additions = \
            SessionCoordinator._process_pending_symbol_additions.__get__(coordinator)
        
        # Should return early without error
        coordinator._process_pending_symbol_additions()
    
    def test_stream_paused_event(self):
        """Should pause and resume stream correctly."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._stream_paused = threading.Event()
        coordinator._stream_paused.set()  # Initially active
        
        # Pause
        coordinator._stream_paused.clear()
        assert not coordinator._stream_paused.is_set()
        
        # Resume
        coordinator._stream_paused.set()
        assert coordinator._stream_paused.is_set()
    
    def test_catchup_stops_at_current_time(self):
        """Catchup should stop processing when reaching current time."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._time_manager = Mock()
        coordinator._bar_queues = {}
        coordinator.session_data = Mock(spec=SessionData)
        coordinator.session_data._lock = threading.Lock()
        coordinator.session_data._symbols = {}
        
        # Create test queue with bars
        test_queue = deque()
        current_time = datetime(2025, 7, 3, 10, 30)
        coordinator._time_manager.get_current_time.return_value = current_time
        
        # Add bars before and after current time
        bar_before = Mock()
        bar_before.timestamp = datetime(2025, 7, 3, 10, 25)
        bar_at = Mock()
        bar_at.timestamp = datetime(2025, 7, 3, 10, 30)
        bar_after = Mock()
        bar_after.timestamp = datetime(2025, 7, 3, 10, 35)
        
        test_queue.append(bar_before)
        test_queue.append(bar_at)
        test_queue.append(bar_after)
        
        coordinator._bar_queues[("TSLA", "1m")] = test_queue
        coordinator._catchup_symbol_to_current_time = \
            SessionCoordinator._catchup_symbol_to_current_time.__get__(coordinator)
        
        # Should process bar_before only
        coordinator._catchup_symbol_to_current_time("TSLA")
        
        # Queue should still have bar_at and bar_after
        assert len(test_queue) == 2
        assert test_queue[0].timestamp == current_time


class TestErrorHandling:
    """Test error handling and recovery."""
    
    def test_session_reactivates_on_error(self):
        """Session should always reactivate even if error occurs."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._pending_symbol_additions = queue.Queue()
        coordinator._stream_paused = threading.Event()
        coordinator._stream_paused.set()
        coordinator.session_data = Mock(spec=SessionData)
        coordinator.data_processor = Mock()
        
        # Add a request that will cause error
        request = {"symbol": "TSLA", "streams": ["1m"]}
        coordinator._pending_symbol_additions.put(request)
        
        # Make load_symbol_historical raise error
        coordinator._load_symbol_historical = Mock(side_effect=Exception("Test error"))
        coordinator._symbol_operation_lock = threading.Lock()
        
        coordinator._process_pending_symbol_additions = \
            SessionCoordinator._process_pending_symbol_additions.__get__(coordinator)
        
        # Process (will error but should recover)
        coordinator._process_pending_symbol_additions()
        
        # Session should be reactivated despite error
        coordinator.session_data.activate_session.assert_called()
        coordinator.data_processor.resume_notifications.assert_called()
        assert coordinator._stream_paused.is_set()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
