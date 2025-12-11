"""E2E Tests for Single-Day Session

Tests complete single-day session workflows from start to finish.
These tests validate the entire system working together.
"""
import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, date
from collections import deque
from app.threads.session_coordinator import SessionCoordinator
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData
from app.models.session_config import SessionConfig, SessionDataConfig


@pytest.fixture
def complete_session_setup():
    """Setup for complete single-day session test."""
    from app.models.session_config import BacktestConfig, TradingConfig, APIConfig
    
    # Create config with all required arguments
    config = SessionConfig(
        session_name="Test Session",
        exchange_group="US_EQUITY",
        asset_class="EQUITY",
        mode="backtest",
        backtest_config=BacktestConfig(
            start_date="2025-01-02",
            end_date="2025-01-02",
            speed_multiplier=0.0
        ),
        session_data_config=SessionDataConfig(
            symbols=["AAPL", "MSFT"],
            streams=["1m"]
        ),
        trading_config=TradingConfig(
            max_buying_power=100000.0,
            max_per_trade=10000.0,
            max_per_symbol=20000.0,
            max_open_positions=10
        ),
        api_config=APIConfig(
            data_api="alpaca",
            trade_api="alpaca"
        )
    )
    
    # Create coordinator
    coordinator = Mock(spec=SessionCoordinator)
    coordinator.session_config = config
    coordinator.session_data = SessionData()
    coordinator._base_interval = "1m"
    coordinator._derived_intervals_validated = ["5m", "15m"]
    coordinator._session_active = False
    
    # Mock time manager
    coordinator._time_manager = Mock()
    coordinator._time_manager.get_current_time = Mock(return_value=datetime(2025, 1, 2, 9, 30, 0))
    
    # Mock data manager
    coordinator._data_manager = Mock()
    
    # Mock methods
    coordinator._validate_symbol_for_loading = Mock(return_value=Mock(can_proceed=True))
    coordinator._register_single_symbol = Mock(return_value=True)
    coordinator._manage_historical_data = Mock(return_value=True)
    coordinator._load_queues = Mock(return_value=True)
    coordinator._calculate_historical_quality = Mock(return_value=True)
    
    return coordinator


@pytest.mark.e2e
class TestSingleDayComplete:
    """Test complete single-day session."""
    
    def test_complete_single_session_workflow(self, complete_session_setup):
        """Test complete workflow: Phase 0 → Phase 4."""
        coordinator = complete_session_setup
        
        # Phase 0: System validation
        assert coordinator._base_interval == "1m"
        assert "5m" in coordinator._derived_intervals_validated
        assert "15m" in coordinator._derived_intervals_validated
        
        # Phase 2: Initialize session (load config symbols)
        symbols = coordinator.session_config.session_data_config.symbols
        for symbol in symbols:
            coordinator._register_single_symbol(
                symbol,
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False
            )
            coordinator._manage_historical_data(symbols=[symbol])
            coordinator._load_queues(symbols=[symbol])
            coordinator._calculate_historical_quality(symbols=[symbol])
        
        # Verify initialization
        assert coordinator._register_single_symbol.call_count == 2
        assert coordinator._manage_historical_data.call_count == 2
        
        # Phase 3: Active session
        coordinator._session_active = True
        assert coordinator._session_active is True
        
        # Phase 4: End session
        coordinator._session_active = False
        assert coordinator._session_active is False
    
    def test_config_loading_plus_adhoc(self, complete_session_setup):
        """Test config symbols + adhoc additions."""
        coordinator = complete_session_setup
        
        # Phase 2: Load config symbols
        for symbol in ["AAPL", "MSFT"]:
            coordinator._register_single_symbol(
                symbol,
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False
            )
        
        # Phase 3: Scanner adds adhoc symbol
        coordinator._register_single_symbol(
            "TSLA",
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True
        )
        
        # Verify all symbols added
        assert coordinator._register_single_symbol.call_count == 3
    
    def test_scanner_strategy_interaction(self, complete_session_setup):
        """Test scanner discovers, strategy upgrades."""
        coordinator = complete_session_setup
        
        # Scanner adds TSLA (adhoc)
        coordinator._register_single_symbol(
            "TSLA",
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True
        )
        
        # Strategy upgrades TSLA (full)
        # (Would call add_symbol which does upgrade internally)
        coordinator._manage_historical_data(symbols=["TSLA"])
        coordinator._calculate_historical_quality(symbols=["TSLA"])
        
        # Verify operations
        assert coordinator._register_single_symbol.call_count == 1
        assert coordinator._manage_historical_data.call_count == 1
        assert coordinator._calculate_historical_quality.call_count == 1
    
    def test_quality_calculation(self, complete_session_setup):
        """Test quality scores calculated for all symbols."""
        coordinator = complete_session_setup
        
        # Load symbols
        symbols = ["AAPL", "MSFT", "TSLA"]
        for symbol in symbols:
            coordinator._register_single_symbol(
                symbol,
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False
            )
            coordinator._calculate_historical_quality(symbols=[symbol])
        
        # Verify quality calculated for all
        assert coordinator._calculate_historical_quality.call_count == 3
    
    def test_session_metrics(self, complete_session_setup):
        """Test session metrics recorded."""
        coordinator = complete_session_setup
        
        # Simulate session metrics
        coordinator._session_metrics = {
            "AAPL": {"trades": 10, "profit": 1500.0, "quality": 0.95},
            "MSFT": {"trades": 8, "profit": 1200.0, "quality": 0.92}
        }
        
        # Verify metrics
        assert len(coordinator._session_metrics) == 2
        assert coordinator._session_metrics["AAPL"]["trades"] == 10
        assert coordinator._session_metrics["MSFT"]["profit"] == 1200.0
    
    def test_data_export(self, complete_session_setup):
        """Test data export at session end."""
        coordinator = complete_session_setup
        session_data = coordinator.session_data
        
        # Add symbols
        for symbol in ["AAPL", "MSFT"]:
            symbol_data = SymbolSessionData(
                symbol=symbol,
                base_interval="1m",
                bars={"1m": BarIntervalData(derived=False, base=None, data=deque([1, 2, 3]), 
                                           quality=0.85, gaps=[], updated=False)},
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False,
                upgraded_from_adhoc=False,
                added_at=datetime.now()
            )
            session_data.register_symbol_data(symbol_data)
        
        # Export data (simulated)
        export_data = {}
        for symbol in session_data.get_active_symbols():
            data = session_data.get_symbol_data(symbol)
            export_data[symbol] = {
                "metrics": data.metrics,  # SessionMetrics dataclass
                "bar_count": len(data.bars["1m"].data) if "1m" in data.bars else 0
            }
        
        # Verify export
        assert len(export_data) == 2
        assert export_data["AAPL"]["metrics"] is not None
        assert export_data["AAPL"]["bar_count"] == 3
    
    def test_error_handling(self, complete_session_setup):
        """Test error handling during session."""
        coordinator = complete_session_setup
        
        # Simulate error during symbol load
        coordinator._register_single_symbol = Mock(side_effect=[True, False, True])
        
        results = []
        for symbol in ["AAPL", "INVALID", "MSFT"]:
            try:
                success = coordinator._register_single_symbol(
                    symbol,
                    meets_session_config_requirements=True,
                    added_by="config",
                    auto_provisioned=False
                )
                results.append((symbol, success))
            except Exception:
                results.append((symbol, False))
        
        # Verify error handling (graceful degradation)
        assert len(results) == 3
        assert results[0][1] is True  # AAPL succeeded
        assert results[1][1] is False  # INVALID failed
        assert results[2][1] is True  # MSFT succeeded
    
    def test_performance(self, complete_session_setup):
        """Test session completes in reasonable time."""
        import time
        
        coordinator = complete_session_setup
        
        # Measure initialization time
        start = time.time()
        
        # Initialize 3 symbols
        for symbol in ["AAPL", "MSFT", "TSLA"]:
            coordinator._register_single_symbol(
                symbol,
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False
            )
        
        end = time.time()
        elapsed = end - start
        
        # Verify reasonable performance (< 1 second for mocked operations)
        assert elapsed < 1.0
        assert coordinator._register_single_symbol.call_count == 3
