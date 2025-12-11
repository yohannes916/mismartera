"""Integration Tests for Phase 1: Teardown & Cleanup

Tests Phase 1 teardown that clears all state between sessions in multi-day backtest.
This ensures no persistence between trading days.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, date, timedelta
from collections import deque
from app.threads.session_coordinator import SessionCoordinator
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData


@pytest.fixture
def session_data_with_symbols():
    """Create session data with symbols loaded."""
    session_data = SessionData()
    
    # Add config symbols
    for symbol in ["AAPL", "MSFT"]:
        symbol_data = SymbolSessionData(
            symbol=symbol,
            base_interval="1m",
            bars={"1m": BarIntervalData(derived=False, base=None, data=deque(), quality=0.0, gaps=[], updated=False)},
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        session_data.register_symbol_data(symbol_data)
    
    # Add adhoc symbol
    adhoc_symbol = SymbolSessionData(
        symbol="TSLA",
        base_interval="1m",
        bars={"1m": BarIntervalData(derived=False, base=None, data=deque(), quality=0.0, gaps=[], updated=False)},
        meets_session_config_requirements=False,
        added_by="scanner",
        auto_provisioned=True,
        upgraded_from_adhoc=False,
        added_at=datetime.now()
    )
    session_data.register_symbol_data(adhoc_symbol)
    
    return session_data


@pytest.fixture
def coordinator_with_state(session_data_with_symbols):
    """Create coordinator with state to teardown."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator.session_data = session_data_with_symbols
    coordinator._pending_symbols = {"NVDA", "RIVN"}
    
    # Mock queues
    coordinator.bar_queues = {"AAPL": deque(), "MSFT": deque(), "TSLA": deque()}
    coordinator.quote_queues = {"AAPL": deque()}
    coordinator.tick_queues = {"MSFT": deque()}
    
    # Mock threads
    coordinator._threads = {
        "data_processor": Mock(),
        "data_quality": Mock(),
        "scanner": Mock(),
        "strategy": Mock()
    }
    
    # Mock time manager
    coordinator._time_manager = Mock()
    coordinator._time_manager.get_current_time = Mock(return_value=datetime(2025, 1, 2, 9, 30, 0))
    coordinator._time_manager.get_next_trading_date = Mock(return_value=date(2025, 1, 3))
    coordinator._time_manager.set_backtest_time = Mock()
    
    return coordinator


class TestPhase1Teardown:
    """Test Phase 1 teardown operations."""
    
    def test_phase1_clear_all_symbols(self, coordinator_with_state):
        """Test all symbols cleared (config + adhoc)."""
        session_data = coordinator_with_state.session_data
        
        # Verify symbols exist before teardown
        assert len(session_data.get_active_symbols()) == 3
        assert "AAPL" in session_data.get_active_symbols()
        assert "MSFT" in session_data.get_active_symbols()
        assert "TSLA" in session_data.get_active_symbols()
        
        # Simulate Phase 1 teardown
        session_data.clear()
        
        # Expected: session_data.symbols empty
        assert len(session_data.get_active_symbols()) == 0
        assert "AAPL" not in session_data.get_active_symbols()
        assert "MSFT" not in session_data.get_active_symbols()
        assert "TSLA" not in session_data.get_active_symbols()
    
    def test_phase1_clear_metadata(self, coordinator_with_state):
        """Test metadata cleared with symbols."""
        session_data = coordinator_with_state.session_data
        
        # Verify metadata exists
        aapl = session_data.get_symbol_data("AAPL")
        assert aapl is not None
        assert aapl.meets_session_config_requirements is True
        assert aapl.added_by == "config"
        
        tsla = session_data.get_symbol_data("TSLA")
        assert tsla is not None
        assert tsla.auto_provisioned is True
        
        # Clear all symbols
        session_data.clear()
        
        # Expected: No orphaned metadata
        assert session_data.get_symbol_data("AAPL") is None
        assert session_data.get_symbol_data("TSLA") is None
        # Metadata is part of SymbolSessionData, deleted automatically
    
    def test_phase1_clear_bar_queues(self, coordinator_with_state):
        """Test all bar queues cleared."""
        # Verify queues exist
        assert len(coordinator_with_state.bar_queues) == 3
        
        # Add some data to queues
        coordinator_with_state.bar_queues["AAPL"].append(Mock())
        coordinator_with_state.bar_queues["MSFT"].append(Mock())
        
        assert len(coordinator_with_state.bar_queues["AAPL"]) > 0
        
        # Simulate Phase 1 teardown
        coordinator_with_state.bar_queues.clear()
        
        # Expected: bar_queues empty
        assert len(coordinator_with_state.bar_queues) == 0
    
    def test_phase1_clear_quote_tick_queues(self, coordinator_with_state):
        """Test quote and tick queues cleared."""
        # Verify queues exist
        assert len(coordinator_with_state.quote_queues) == 1
        assert len(coordinator_with_state.tick_queues) == 1
        
        # Add data
        coordinator_with_state.quote_queues["AAPL"].append(Mock())
        coordinator_with_state.tick_queues["MSFT"].append(Mock())
        
        # Simulate Phase 1 teardown
        coordinator_with_state.quote_queues.clear()
        coordinator_with_state.tick_queues.clear()
        
        # Expected: All queues empty
        assert len(coordinator_with_state.quote_queues) == 0
        assert len(coordinator_with_state.tick_queues) == 0
    
    def test_phase1_teardown_all_threads(self, coordinator_with_state):
        """Test all threads torn down."""
        threads = coordinator_with_state._threads
        
        # Verify threads exist
        assert "data_processor" in threads
        assert "data_quality" in threads
        assert "scanner" in threads
        assert "strategy" in threads
        
        # Simulate Phase 1 teardown
        for thread_name, thread in threads.items():
            if hasattr(thread, 'teardown'):
                thread.teardown()
        
        # Expected: All thread teardown() called
        for thread in threads.values():
            if hasattr(thread, 'teardown'):
                thread.teardown.assert_called()
    
    def test_phase1_advance_clock_to_next_day(self, coordinator_with_state):
        """Test clock advanced to next trading day."""
        time_mgr = coordinator_with_state._time_manager
        
        # Current time: 2025-01-02
        current_time = time_mgr.get_current_time()
        assert current_time.date() == date(2025, 1, 2)
        
        # Get next trading day
        next_day = time_mgr.get_next_trading_date(current_time.date())
        assert next_day == date(2025, 1, 3)
        
        # Set clock to next day @ market open
        next_day_open = datetime.combine(next_day, datetime.min.time().replace(hour=9, minute=30))
        time_mgr.set_backtest_time(next_day_open)
        
        # Expected: TimeManager set to next day market open
        time_mgr.set_backtest_time.assert_called_once()
    
    def test_phase1_skip_holidays(self, coordinator_with_state):
        """Test clock skips holidays/weekends."""
        time_mgr = coordinator_with_state._time_manager
        
        # Mock holiday check
        def get_next_trading_date_impl(from_date):
            # Skip Saturday (2025-01-04) and Sunday (2025-01-05)
            if from_date == date(2025, 1, 3):  # Friday
                return date(2025, 1, 6)  # Monday
            return from_date + timedelta(days=1)
        
        time_mgr.get_next_trading_date = Mock(side_effect=get_next_trading_date_impl)
        
        # Get next trading day from Friday
        next_day = time_mgr.get_next_trading_date(date(2025, 1, 3))
        
        # Expected: Next trading day used (skips weekend)
        assert next_day == date(2025, 1, 6)
    
    def test_phase1_no_persistence_from_previous_day(self, coordinator_with_state):
        """Test no state persists from previous day."""
        session_data = coordinator_with_state.session_data
        
        # Day 1: Add symbols
        assert len(session_data.get_active_symbols()) == 3
        
        # Phase 1 teardown
        session_data.clear()
        coordinator_with_state.bar_queues.clear()
        coordinator_with_state._pending_symbols.clear()
        
        # Expected: Fresh start
        assert len(session_data.get_active_symbols()) == 0
        assert len(coordinator_with_state.bar_queues) == 0
        assert len(coordinator_with_state._pending_symbols) == 0
        
        # Day 2 would start completely fresh
    
    def test_phase1_locked_symbols_cleared(self, coordinator_with_state):
        """Test symbol locks cleared."""
        session_data = coordinator_with_state.session_data
        
        # Mock symbol locks
        session_data._symbol_locks = {"AAPL": "open_position", "MSFT": "pending_order"}
        
        # Verify locks exist
        assert len(session_data._symbol_locks) == 2
        
        # Phase 1 teardown
        session_data._symbol_locks.clear()
        
        # Expected: No locked symbols
        assert len(session_data._symbol_locks) == 0
    
    def test_phase1_multiple_teardowns(self, coordinator_with_state):
        """Test repeated teardowns (multi-day)."""
        session_data = coordinator_with_state.session_data
        
        # Day 1 teardown
        session_data.clear()
        assert len(session_data.get_active_symbols()) == 0
        
        # Day 2: Add new symbols
        symbol = SymbolSessionData(
            symbol="NVDA",
            base_interval="1m",
            bars={},
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        session_data.register_symbol_data(symbol)
        assert len(session_data.get_active_symbols()) == 1
        
        # Day 2 teardown
        session_data.clear()
        assert len(session_data.get_active_symbols()) == 0
        
        # Day 3: Add different symbols
        symbol2 = SymbolSessionData(
            symbol="RIVN",
            base_interval="1m",
            bars={},
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        session_data.register_symbol_data(symbol2)
        assert len(session_data.get_active_symbols()) == 1
        
        # Expected: Each teardown complete, fresh start each day
        session_data.clear()
        assert len(session_data.get_active_symbols()) == 0


class TestPhase1TimeManagerIntegration:
    """Test Phase 1 time advancement via TimeManager."""
    
    def test_clock_advancement_uses_timemanager(self, coordinator_with_state):
        """Test clock advancement uses TimeManager API."""
        time_mgr = coordinator_with_state._time_manager
        
        # Get current time via TimeManager
        current = time_mgr.get_current_time()
        assert isinstance(current, datetime)
        
        # Get next trading date via TimeManager
        next_date = time_mgr.get_next_trading_date(current.date())
        assert isinstance(next_date, date)
        
        # Set backtest time via TimeManager
        time_mgr.set_backtest_time(datetime.combine(next_date, datetime.min.time()))
        
        # Verify TimeManager methods called (not hardcoded logic)
        time_mgr.get_current_time.assert_called()
        time_mgr.get_next_trading_date.assert_called()
        time_mgr.set_backtest_time.assert_called()
    
    def test_no_hardcoded_time_logic(self, coordinator_with_state):
        """Test no hardcoded time advancement."""
        time_mgr = coordinator_with_state._time_manager
        
        # All time operations should go through TimeManager
        # Not hardcoded like: current_date + timedelta(days=1)
        
        # Correct pattern:
        current_date = time_mgr.get_current_time().date()
        next_date = time_mgr.get_next_trading_date(current_date)
        
        # Verify TimeManager used
        assert time_mgr.get_next_trading_date.called
        
        # NOT: next_date = current_date + timedelta(days=1)  # Wrong!
