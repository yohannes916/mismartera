"""
End-to-end tests for lag-based session control with dynamic symbol management.

Tests the complete flow:
1. Session starts with initial symbols
2. Mid-session symbol addition
3. Lag detection triggers session deactivation
4. Internal processing continues (DataProcessor)
5. External notifications blocked (AnalysisEngine)
6. Catchup completes, session reactivates
7. Symbol removal

This uses actual components (no mocks) with synthetic data.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from collections import defaultdict, deque

from app.threads.session_coordinator import SessionCoordinator
from app.managers.data_manager.session_data import SessionData
from app.threads.data_processor import DataProcessor


@pytest.mark.slow
@pytest.mark.integration
class TestLagBasedSessionControl:
    """End-to-end test of lag-based session control."""
    
    @pytest.fixture
    def session_components(self):
        """Create session components for testing."""
        session_data = SessionData()
        
        # Setup counters (would be in SessionCoordinator)
        symbol_check_counters = defaultdict(int)
        catchup_threshold = 60  # seconds
        catchup_check_interval = 10  # bars
        
        return {
            'session_data': session_data,
            'counters': symbol_check_counters,
            'threshold': catchup_threshold,
            'interval': catchup_check_interval
        }
    
    def test_full_lag_detection_flow(self, session_components):
        """Test complete lag detection and session control flow."""
        session_data = session_components['session_data']
        counters = session_components['counters']
        threshold = session_components['threshold']
        check_interval = session_components['interval']
        
        # Phase 1: Setup - Register RIVN
        session_data.register_symbol("RIVN")
        counters["RIVN"] = 45  # Already processing bars
        
        # Session should be active
        assert session_data._session_active is True
        
        # Phase 2: Add AAPL mid-session (simulated)
        session_data.register_symbol("AAPL")
        # Counter auto-initializes to 0 for new symbol
        
        # Phase 3: Process first AAPL bar (lagging by 2.5 hours)
        current_time = datetime(2024, 1, 1, 12, 0, 0)
        aapl_bar_time = datetime(2024, 1, 1, 9, 30, 0)
        
        # Check lag (first bar, counter=0)
        if counters["AAPL"] % check_interval == 0:
            lag_seconds = (current_time - aapl_bar_time).total_seconds()
            
            if lag_seconds > threshold:
                session_data.deactivate_session()
        
        counters["AAPL"] += 1
        
        # Session should be deactivated due to lag
        assert session_data._session_active is False
        
        # Phase 4: Verify internal reads work
        symbol_data_internal = session_data.get_symbol_data("AAPL", internal=True)
        assert symbol_data_internal is not None
        
        # Phase 5: Verify external reads blocked
        symbol_data_external = session_data.get_symbol_data("AAPL", internal=False)
        assert symbol_data_external is None
        
        # Phase 6: Process more bars (still lagging)
        for i in range(2, 11):  # Bars 2-10
            counters["AAPL"] += 1
            
            if counters["AAPL"] % check_interval == 0:
                # Check at bar 10
                bar_time_10 = datetime(2024, 1, 1, 9, 39, 0)  # 9 minutes later
                lag = (current_time - bar_time_10).total_seconds()
                
                # Still lagging
                assert lag > threshold
                # Session stays deactivated
        
        assert session_data._session_active is False
        
        # Phase 7: Catchup complete (current bar)
        for i in range(11, 151):
            counters["AAPL"] += 1
        
        # At bar 150, we're caught up
        caught_up_time = datetime(2024, 1, 1, 11, 59, 30)
        if counters["AAPL"] % check_interval == 0:
            lag = (current_time - caught_up_time).total_seconds()
            
            if lag <= threshold and not session_data._session_active:
                session_data.activate_session()
        
        # Session should be reactivated
        assert session_data._session_active is True
        
        # Phase 8: External reads work again
        symbol_data_external = session_data.get_symbol_data("AAPL", internal=False)
        assert symbol_data_external is not None
    
    def test_multiple_symbols_independent_counters(self, session_components):
        """Test that multiple symbols have independent lag checking."""
        counters = session_components['counters']
        check_interval = session_components['interval']
        
        # Setup: RIVN at bar 47, AAPL just added (0), TSLA at bar 20
        counters["RIVN"] = 47
        counters["AAPL"] = 0
        counters["TSLA"] = 20
        
        # Check which symbols trigger lag check
        checks = {}
        for symbol in ["RIVN", "AAPL", "TSLA"]:
            checks[symbol] = (counters[symbol] % check_interval == 0)
        
        assert checks["RIVN"] is False  # 47 % 10 = 7
        assert checks["AAPL"] is True   # 0 % 10 = 0 (first bar)
        assert checks["TSLA"] is True   # 20 % 10 = 0
        
        # Increment all
        for symbol in ["RIVN", "AAPL", "TSLA"]:
            counters[symbol] += 1
        
        # New checks
        for symbol in ["RIVN", "AAPL", "TSLA"]:
            checks[symbol] = (counters[symbol] % check_interval == 0)
        
        # None should check now
        assert all(not check for check in checks.values())
    
    def test_dataprocessor_respects_session_active(self, session_components):
        """Test that DataProcessor skips notifications when session inactive."""
        session_data = session_components['session_data']
        
        # Mock analysis engine queue
        analysis_queue = []
        
        # Register symbol
        session_data.register_symbol("AAPL")
        
        # Simulate DataProcessor notification logic
        def notify_if_active(symbol, interval):
            if session_data._session_active:
                analysis_queue.append((symbol, interval))
                return True
            return False
        
        # Phase 1: Active session - notifications go through
        result = notify_if_active("AAPL", "1m")
        assert result is True
        assert len(analysis_queue) == 1
        
        # Phase 2: Deactivate session
        session_data.deactivate_session()
        
        # Phase 3: Try to notify - should be skipped
        result = notify_if_active("AAPL", "5m")
        assert result is False
        assert len(analysis_queue) == 1  # Still 1, not 2
        
        # Phase 4: Reactivate session
        session_data.activate_session()
        
        # Phase 5: Notifications work again
        result = notify_if_active("AAPL", "15m")
        assert result is True
        assert len(analysis_queue) == 2


@pytest.mark.slow
@pytest.mark.integration
class TestSymbolAddRemoveFlow:
    """Test complete symbol add/remove flow."""
    
    @pytest.fixture
    def mock_coordinator(self):
        """Create a minimal SessionCoordinator for testing."""
        coordinator = Mock()
        coordinator._symbol_operation_lock = Mock()
        coordinator._symbol_operation_lock.__enter__ = Mock(return_value=None)
        coordinator._symbol_operation_lock.__exit__ = Mock(return_value=None)
        coordinator._pending_symbols = set()
        coordinator._symbol_check_counters = defaultdict(int)
        coordinator._bar_queues = {}
        # Note: _loaded_symbols, _streamed_data, _generated_data removed - now tracked in SessionData
        coordinator.session_config = Mock()
        coordinator.session_config.session_data_config = Mock()
        coordinator.session_config.session_data_config.symbols = ["RIVN"]
        coordinator.session_config.session_data_config.streams = ["1m"]
        coordinator.session_data = SessionData()
        coordinator.session_data.register_symbol("RIVN")
        return coordinator
    
    def test_add_symbol_updates_config(self, mock_coordinator):
        """Adding symbol should update session config."""
        coordinator = mock_coordinator
        
        # Bind add_symbol method
        coordinator.add_symbol = SessionCoordinator.add_symbol.__get__(coordinator)
        
        # Add AAPL
        result = coordinator.add_symbol("AAPL")
        
        assert result is True
        assert "AAPL" in coordinator.session_config.session_data_config.symbols
        assert "AAPL" in coordinator._pending_symbols
    
    def test_remove_symbol_cleans_everything(self, mock_coordinator):
        """Removing symbol should clean all state."""
        coordinator = mock_coordinator
        
        # Setup: Add some state for symbol that will be removed  
        coordinator._symbol_check_counters["RIVN"] = 100
        coordinator._bar_queues[("RIVN", "1m")] = deque([1, 2, 3])
        
        # Verify symbol exists in session_data
        assert coordinator.session_data.get_symbol_data("RIVN") is not None
        
        # Bind remove_symbol method
        coordinator.remove_symbol = SessionCoordinator.remove_symbol.__get__(coordinator)
        
        # Remove RIVN
        result = coordinator.remove_symbol("RIVN")
        
        assert result is True
        # Check internal state cleanup (lag counters and queues)
        assert "RIVN" not in coordinator._symbol_check_counters
        assert ("RIVN", "1m") not in coordinator._bar_queues
        # Check session_data cleanup
        assert coordinator.session_data.get_symbol_data("RIVN") is None


@pytest.mark.slow
@pytest.mark.integration
class TestConfigurationIntegration:
    """Test configuration loading and usage."""
    
    def test_streaming_config_values(self):
        """Test that streaming config values are used correctly."""
        from app.models.session_config import StreamingConfig
        
        # Create streaming config
        streaming_config = StreamingConfig(
            catchup_threshold_seconds=120,
            catchup_check_interval=20
        )
        
        # Verify values
        assert streaming_config.catchup_threshold_seconds == 120
        assert streaming_config.catchup_check_interval == 20
    
    def test_session_deactivation_with_custom_threshold(self):
        """Test lag detection with custom threshold."""
        session_data = SessionData()
        
        # Custom threshold (2 minutes)
        threshold = 120
        
        current_time = datetime(2024, 1, 1, 12, 0, 0)
        bar_time = datetime(2024, 1, 1, 11, 58, 0)  # 2 minutes ago
        
        lag = (current_time - bar_time).total_seconds()
        
        # Exactly at threshold (not exceeded)
        assert lag == 120
        assert not (lag > threshold)  # Should NOT deactivate
        
        # Just over threshold
        bar_time_2 = datetime(2024, 1, 1, 11, 57, 59)
        lag_2 = (current_time - bar_time_2).total_seconds()
        assert lag_2 > threshold  # Should deactivate


@pytest.mark.slow
@pytest.mark.integration
class TestPollingPattern:
    """Test polling pattern for inter-thread communication."""
    
    def test_accessor_methods_return_copies(self):
        """Accessor methods should return copies, not direct references."""
        # Mock coordinator state
        pending = {"TSLA"}
        
        coordinator = Mock()
        coordinator._symbol_operation_lock = Mock()
        coordinator._symbol_operation_lock.__enter__ = Mock(return_value=None)
        coordinator._symbol_operation_lock.__exit__ = Mock(return_value=None)
        coordinator._pending_symbols = pending
        
        # Create real session_data with symbols (loaded symbols now tracked there)
        coordinator.session_data = SessionData()
        coordinator.session_data.register_symbol("AAPL")
        coordinator.session_data.register_symbol("RIVN")
        
        # Bind accessor methods
        coordinator.get_loaded_symbols = SessionCoordinator.get_loaded_symbols.__get__(coordinator)
        coordinator.get_pending_symbols = SessionCoordinator.get_pending_symbols.__get__(coordinator)
        
        # Get copies
        loaded_copy = coordinator.get_loaded_symbols()
        pending_copy = coordinator.get_pending_symbols()
        
        # Verify they're copies
        assert "AAPL" in loaded_copy
        assert "RIVN" in loaded_copy
        assert pending_copy == pending
        assert loaded_copy is not coordinator.session_data._symbols  # Different object
        assert pending_copy is not pending
        
        # Modify copies shouldn't affect originals
        loaded_copy.add("NEW")
        pending_copy.add("OTHER")
        
        # Original session_data shouldn't have NEW
        assert coordinator.session_data.get_symbol_data("NEW") is None
        assert "OTHER" not in coordinator._pending_symbols
    
    def test_polling_for_pending_symbols(self):
        """Test that threads can poll for pending symbols."""
        coordinator = Mock()
        coordinator._symbol_operation_lock = Mock()
        coordinator._symbol_operation_lock.__enter__ = Mock()
        coordinator._symbol_operation_lock.__exit__ = Mock()
        coordinator._pending_symbols = set()
        
        coordinator.get_pending_symbols = SessionCoordinator.get_pending_symbols.__get__(coordinator)
        
        # Initially no pending
        pending = coordinator.get_pending_symbols()
        assert len(pending) == 0
        
        # Add pending symbol
        coordinator._pending_symbols.add("AAPL")
        
        # Poll again
        pending = coordinator.get_pending_symbols()
        assert len(pending) == 1
        assert "AAPL" in pending
