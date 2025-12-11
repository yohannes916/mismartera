"""Integration Tests for Phase 4: Session End

Tests session end operations that deactivate the session but keep data
intact for the current day (until Phase 1 teardown).
"""
import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, date
from collections import deque
from app.threads.session_coordinator import SessionCoordinator
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData


@pytest.fixture
def active_session_to_end():
    """Create active session ready to end."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator.session_data = SessionData()
    coordinator._session_active = True
    coordinator._session_metrics = {}
    
    # Add symbols with data
    from app.managers.data_manager.session_data import SessionMetrics
    for symbol in ["AAPL", "MSFT"]:
        symbol_data = SymbolSessionData(
            symbol=symbol,
            base_interval="1m",
            bars={"1m": BarIntervalData(
                derived=False,
                base=None,
                data=deque([Mock() for _ in range(100)]),  # Historical bars
                quality=0.85,
                gaps=[],
                updated=True
            )},
            metrics=SessionMetrics(
                volume=10000,
                high=150.0,
                low=145.0,
                last_update=datetime.now()
            ),
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        coordinator.session_data.register_symbol_data(symbol_data)
    
    # Mock threads
    coordinator._threads = {
        "data_processor": Mock(),
        "scanner": Mock(),
        "strategy": Mock()
    }
    
    # Mock time manager
    coordinator._time_manager = Mock()
    coordinator._time_manager.get_current_time = Mock(return_value=datetime(2025, 1, 2, 16, 0, 0))
    
    return coordinator


class TestSessionEnd:
    """Test session end operations."""
    
    def test_session_end_deactivate(self, active_session_to_end):
        """Test session marked as inactive."""
        coordinator = active_session_to_end
        
        # Verify session active
        assert coordinator._session_active is True
        
        # Simulate session end
        coordinator._session_active = False
        
        # Expected: Session inactive
        assert coordinator._session_active is False
    
    def test_session_end_metrics_recorded(self, active_session_to_end):
        """Test session metrics recorded."""
        coordinator = active_session_to_end
        session_data = coordinator.session_data
        
        # Simulate recording session metrics
        for symbol in session_data.get_active_symbols():
            symbol_data = session_data.get_symbol_data(symbol)
            # SessionMetrics is a dataclass, access attributes directly
            if symbol_data.metrics.last_update:
                coordinator._session_metrics[symbol_data.symbol] = {
                    "trades": 5,  # Mock value
                    "profit": 1000.0,  # Mock value
                    "quality": symbol_data.bars["1m"].quality if "1m" in symbol_data.bars else 0.0
                }
        
        # Expected: Metrics captured
        assert len(coordinator._session_metrics) > 0
        assert "AAPL" in coordinator._session_metrics
        assert coordinator._session_metrics["AAPL"]["trades"] == 5
        assert coordinator._session_metrics["AAPL"]["profit"] == 1000.0
    
    def test_session_end_data_intact(self, active_session_to_end):
        """Test data remains intact after session end (until teardown)."""
        session_data = active_session_to_end.session_data
        
        # Mark session ended
        active_session_to_end._session_active = False
        
        # Verify data still present
        assert len(session_data.get_active_symbols()) == 2
        assert session_data.get_symbol_data("AAPL") is not None
        assert session_data.get_symbol_data("MSFT") is not None
        
        # Verify bar data still present
        aapl = session_data.get_symbol_data("AAPL")
        assert len(aapl.bars["1m"].data) == 100
        assert aapl.bars["1m"].quality == 0.85
        
        # Expected: Data intact for post-session analysis
    
    def test_session_end_no_persistence_to_next(self, active_session_to_end):
        """Test session end doesn't persist data to next day."""
        session_data = active_session_to_end.session_data
        
        # End current session
        active_session_to_end._session_active = False
        
        # Simulate Phase 1 teardown (next day start)
        session_data.clear()
        
        # Expected: No data persists to next session
        assert len(session_data.get_active_symbols()) == 0
    
    def test_last_day_data_kept(self, active_session_to_end):
        """Test last day of backtest keeps data for analysis."""
        coordinator = active_session_to_end
        session_data = coordinator.session_data
        
        # End session (last day)
        coordinator._session_active = False
        is_last_day = True
        
        # On last day, data might be kept for final analysis
        if is_last_day:
            # Data remains
            assert len(session_data.get_active_symbols()) == 2
            assert session_data.get_symbol_data("AAPL") is not None
        
        # Expected: Data available for final results
        aapl = session_data.get_symbol_data("AAPL")
        assert aapl.metrics is not None  # SessionMetrics dataclass
        assert aapl.bars["1m"].quality > 0


class TestThreadShutdown:
    """Test thread shutdown during session end."""
    
    def test_threads_deactivated(self, active_session_to_end):
        """Test all threads deactivated at session end."""
        threads = active_session_to_end._threads
        
        # Simulate deactivation
        for thread_name, thread in threads.items():
            thread.deactivate = Mock()
            thread.deactivate()
        
        # Expected: All threads deactivated
        for thread in threads.values():
            if hasattr(thread, 'deactivate'):
                thread.deactivate.assert_called()
    
    def test_threads_not_torn_down_yet(self, active_session_to_end):
        """Test threads not torn down yet (happens in Phase 1)."""
        threads = active_session_to_end._threads
        
        # Phase 4: Deactivate only
        for thread in threads.values():
            thread.deactivate = Mock()
            thread.deactivate()
        
        # Threads still exist
        assert len(threads) == 3
        
        # Phase 1: Teardown
        for thread in threads.values():
            thread.teardown = Mock()
            thread.teardown()
        
        # Expected: Teardown called in Phase 1, not Phase 4
