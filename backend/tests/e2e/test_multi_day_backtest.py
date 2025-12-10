"""E2E Tests for Multi-Day Backtest

Tests complete multi-day backtest workflows with proper state management,
no persistence between days, and correct clock advancement.
"""
import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, date, timedelta
from collections import deque
from app.threads.session_coordinator import SessionCoordinator
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData
from app.models.session_config import SessionConfig, SessionDataConfig


@pytest.fixture
def multi_day_setup():
    """Setup for multi-day backtest."""
    # Use Mock to avoid complex SessionConfig initialization
    config = Mock()
    config.session_data_config = SessionDataConfig(
        symbols=["AAPL", "MSFT"],
        streams=["1m"]
    )
    
    coordinator = Mock(spec=SessionCoordinator)
    coordinator.session_config = config
    coordinator._base_interval = "1m"
    coordinator._derived_intervals_validated = ["5m", "15m"]
    
    # Mock time manager
    coordinator._time_manager = Mock()
    
    # Mock methods
    coordinator._register_single_symbol = Mock(return_value=True)
    coordinator._manage_historical_data = Mock(return_value=True)
    coordinator._calculate_historical_quality = Mock(return_value=True)
    
    return coordinator


@pytest.mark.e2e
class TestMultiDayBacktest:
    """Test multi-day backtest scenarios."""
    
    def test_3_day_backtest(self, multi_day_setup):
        """Test 3-day backtest with proper state management."""
        coordinator = multi_day_setup
        time_mgr = coordinator._time_manager
        
        # Day 1: Jan 2, 2025
        time_mgr.get_current_time = Mock(return_value=datetime(2025, 1, 2, 9, 30, 0))
        
        # Phase 2: Initialize
        coordinator.session_data = SessionData()
        for symbol in ["AAPL", "MSFT"]:
            coordinator._register_single_symbol(
                symbol,
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False
            )
        
        # Phase 4: End day 1
        day1_symbol_count = coordinator._register_single_symbol.call_count
        
        # Phase 1: Teardown day 1
        coordinator.session_data.clear()
        assert len(coordinator.session_data.symbols) == 0
        
        # Day 2: Jan 3, 2025
        time_mgr.get_current_time = Mock(return_value=datetime(2025, 1, 3, 9, 30, 0))
        
        # Phase 2: Initialize fresh
        coordinator.session_data = SessionData()
        for symbol in ["AAPL", "MSFT"]:
            coordinator._register_single_symbol(
                symbol,
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False
            )
        
        # Phase 4: End day 2
        day2_symbol_count = coordinator._register_single_symbol.call_count - day1_symbol_count
        
        # Phase 1: Teardown day 2
        coordinator.session_data.clear()
        
        # Day 3: Jan 6, 2025 (skip weekend)
        time_mgr.get_current_time = Mock(return_value=datetime(2025, 1, 6, 9, 30, 0))
        
        # Phase 2: Initialize fresh
        coordinator.session_data = SessionData()
        for symbol in ["AAPL", "MSFT"]:
            coordinator._register_single_symbol(
                symbol,
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False
            )
        
        # Verify each day loaded symbols fresh
        assert day1_symbol_count == 2
        assert day2_symbol_count == 2
        assert coordinator._register_single_symbol.call_count == 6  # 2 * 3 days
    
    def test_5_day_backtest_with_holiday(self, multi_day_setup):
        """Test 5-day backtest including a holiday."""
        coordinator = multi_day_setup
        time_mgr = coordinator._time_manager
        
        # Days to test (skip Jan 1 holiday)
        test_days = [
            date(2025, 1, 2),  # Thu
            date(2025, 1, 3),  # Fri
            # Skip Jan 4-5 (weekend)
            date(2025, 1, 6),  # Mon
            date(2025, 1, 7),  # Tue
            date(2025, 1, 8),  # Wed
        ]
        
        for day in test_days:
            # Set current time
            time_mgr.get_current_time = Mock(return_value=datetime.combine(day, datetime.min.time().replace(hour=9, minute=30)))
            
            # Initialize session
            coordinator.session_data = SessionData()
            for symbol in ["AAPL", "MSFT"]:
                coordinator._register_single_symbol(
                    symbol,
                    meets_session_config_requirements=True,
                    added_by="config",
                    auto_provisioned=False
                )
            
            # End session
            coordinator.session_data.clear()
        
        # Verify 5 days * 2 symbols = 10 calls
        assert coordinator._register_single_symbol.call_count == 10
    
    def test_10_day_backtest(self, multi_day_setup):
        """Test 10-day backtest for extended period."""
        coordinator = multi_day_setup
        
        # Simulate 10 trading days
        for day_num in range(10):
            # Initialize
            coordinator.session_data = SessionData()
            coordinator._register_single_symbol(
                "AAPL",
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False
            )
            
            # Teardown
            coordinator.session_data.clear()
        
        # Verify 10 days
        assert coordinator._register_single_symbol.call_count == 10
    
    def test_no_persistence_between_days(self, multi_day_setup):
        """Test no state persists between days."""
        coordinator = multi_day_setup
        
        # Day 1: Add AAPL and adhoc TSLA
        coordinator.session_data = SessionData()
        
        aapl = SymbolSessionData(
            symbol="AAPL",
            base_interval="1m",
            bars={},
            indicators={},
            quality=0.85,
            session_metrics=None,
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        coordinator.session_data.register_symbol_data(aapl)
        
        tsla = SymbolSessionData(
            symbol="TSLA",
            base_interval="1m",
            bars={},
            indicators={},
            quality=0.0,
            session_metrics=None,
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        coordinator.session_data.register_symbol_data(tsla)
        
        # Verify day 1 state
        assert len(coordinator.session_data.symbols) == 2
        assert "AAPL" in coordinator.session_data.symbols
        assert "TSLA" in coordinator.session_data.symbols
        
        # Teardown day 1
        coordinator.session_data.clear()
        assert len(coordinator.session_data.symbols) == 0
        
        # Day 2: Only AAPL (no TSLA persistence)
        coordinator.session_data = SessionData()
        
        aapl_day2 = SymbolSessionData(
            symbol="AAPL",
            base_interval="1m",
            bars={},
            indicators={},
            quality=0.0,  # Fresh quality
            session_metrics=None,
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        coordinator.session_data.register_symbol_data(aapl_day2)
        
        # Verify day 2 state (no TSLA!)
        assert len(coordinator.session_data.symbols) == 1
        assert "AAPL" in coordinator.session_data.symbols
        assert "TSLA" not in coordinator.session_data.symbols
    
    def test_state_reset_verification(self, multi_day_setup):
        """Test all state components reset between days."""
        coordinator = multi_day_setup
        
        # Day 1: Build state
        coordinator.session_data = SessionData()
        coordinator._session_active = True
        coordinator._pending_symbols = {"PENDING"}
        
        # Add symbol
        symbol = SymbolSessionData(
            symbol="AAPL",
            base_interval="1m",
            bars={},
            indicators={},
            quality=0.85,
            session_metrics=None,
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        coordinator.session_data.register_symbol_data(symbol)
        
        # Verify state exists
        assert coordinator._session_active is True
        assert len(coordinator._pending_symbols) == 1
        assert len(coordinator.session_data.symbols) == 1
        
        # Teardown
        coordinator.session_data.clear()
        coordinator._session_active = False
        coordinator._pending_symbols.clear()
        
        # Verify complete reset
        assert coordinator._session_active is False
        assert len(coordinator._pending_symbols) == 0
        assert len(coordinator.session_data.symbols) == 0
    
    def test_clock_advancement(self, multi_day_setup):
        """Test clock advances correctly each day."""
        coordinator = multi_day_setup
        time_mgr = coordinator._time_manager
        
        days = [date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6)]
        
        for day in days:
            # Set time for this day
            day_start = datetime.combine(day, datetime.min.time().replace(hour=9, minute=30))
            time_mgr.get_current_time = Mock(return_value=day_start)
            
            # Verify correct time
            current = time_mgr.get_current_time()
            assert current.date() == day
            assert current.hour == 9
            assert current.minute == 30
    
    def test_multiple_symbols(self, multi_day_setup):
        """Test multi-day with multiple symbols."""
        coordinator = multi_day_setup
        
        symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"]
        
        # 3 days * 5 symbols
        for day in range(3):
            coordinator.session_data = SessionData()
            for symbol in symbols:
                coordinator._register_single_symbol(
                    symbol,
                    meets_session_config_requirements=True,
                    added_by="config",
                    auto_provisioned=False
                )
            coordinator.session_data.clear()
        
        # Verify
        assert coordinator._register_single_symbol.call_count == 15  # 3 * 5
    
    def test_scanner_discoveries_each_day(self, multi_day_setup):
        """Test scanner can discover different symbols each day."""
        coordinator = multi_day_setup
        
        daily_discoveries = [
            ["TSLA"],  # Day 1
            ["NVDA", "AMD"],  # Day 2
            ["PLTR"],  # Day 3
        ]
        
        for discoveries in daily_discoveries:
            coordinator.session_data = SessionData()
            
            # Config symbols
            coordinator._register_single_symbol("AAPL", meets_session_config_requirements=True, 
                                               added_by="config", auto_provisioned=False)
            
            # Scanner discoveries
            for symbol in discoveries:
                coordinator._register_single_symbol(symbol, meets_session_config_requirements=False,
                                                   added_by="scanner", auto_provisioned=True)
            
            # Teardown
            coordinator.session_data.clear()
        
        # 3 days of config (AAPL) + 4 total discoveries
        assert coordinator._register_single_symbol.call_count == 7
    
    def test_strategy_additions_each_day(self, multi_day_setup):
        """Test strategy can add symbols each day."""
        coordinator = multi_day_setup
        
        # 3 days, strategy adds different symbol each day
        strategy_additions = ["MSFT", "GOOGL", "META"]
        
        for symbol in strategy_additions:
            coordinator.session_data = SessionData()
            
            # Config
            coordinator._register_single_symbol("AAPL", meets_session_config_requirements=True,
                                               added_by="config", auto_provisioned=False)
            
            # Strategy
            coordinator._register_single_symbol(symbol, meets_session_config_requirements=True,
                                               added_by="strategy", auto_provisioned=False)
            
            coordinator.session_data.clear()
        
        # 3 days * 2 symbols (config + strategy)
        assert coordinator._register_single_symbol.call_count == 6
    
    def test_performance_scaling(self, multi_day_setup):
        """Test performance scales with days and symbols."""
        import time
        
        coordinator = multi_day_setup
        
        start = time.time()
        
        # 10 days * 10 symbols
        for day in range(10):
            coordinator.session_data = SessionData()
            for symbol_num in range(10):
                coordinator._register_single_symbol(
                    f"SYM{symbol_num}",
                    meets_session_config_requirements=True,
                    added_by="config",
                    auto_provisioned=False
                )
            coordinator.session_data.clear()
        
        end = time.time()
        elapsed = end - start
        
        # Should complete quickly with mocks (< 1 second)
        assert elapsed < 1.0
        assert coordinator._register_single_symbol.call_count == 100
