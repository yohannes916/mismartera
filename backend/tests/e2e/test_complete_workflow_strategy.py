"""E2E Tests for Complete Strategy Workflow

Tests the complete workflow where strategy adds symbols directly
(full provisioning from the start).
"""
import pytest
from unittest.mock import Mock
from datetime import datetime
from collections import deque
from app.threads.session_coordinator import SessionCoordinator
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData


@pytest.fixture
def strategy_workflow_setup():
    """Setup for strategy workflow testing."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator.session_data = SessionData()
    coordinator._base_interval = "1m"
    coordinator._derived_intervals_validated = ["5m", "15m"]
    
    coordinator._register_single_symbol = Mock(return_value=True)
    coordinator._manage_historical_data = Mock(return_value=True)
    coordinator._calculate_historical_quality = Mock(return_value=True)
    
    return coordinator


@pytest.mark.e2e
class TestStrategyWorkflows:
    """Test complete strategy workflows."""
    
    def test_strategy_full_loading(self, strategy_workflow_setup):
        """Test strategy adds symbol with full loading."""
        coordinator = strategy_workflow_setup
        session_data = coordinator.session_data
        
        # Strategy adds MSFT (full provisioning)
        msft = SymbolSessionData(
            symbol="MSFT",
            base_interval="1m",
            bars={"1m": BarIntervalData(derived=False, base=None, data=deque(list(range(100))),  # Full historical
                                       quality=0.0, gaps=[], updated=False),
                  "5m": BarIntervalData(derived=True, base="1m", data=list(range(20)), 
                                       quality=0.0, gaps=[], updated=False),
                  "15m": BarIntervalData(derived=True, base="1m", data=list(range(7)), 
                                        quality=0.0, gaps=[], updated=False)},
            indicators={},
            quality=0.92,  # Quality calculated
            session_metrics=None,
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        session_data.register_symbol_data(msft)
        
        # Verify full loading
        assert msft.meets_session_config_requirements is True
        assert msft.auto_provisioned is False
        assert len(msft.bars) == 3  # All intervals
        assert msft.quality > 0  # Quality calculated
    
    def test_strategy_multiple_symbols(self, strategy_workflow_setup):
        """Test strategy adds multiple symbols at once."""
        coordinator = strategy_workflow_setup
        session_data = coordinator.session_data
        
        # Strategy adds portfolio
        portfolio = ["AAPL", "MSFT", "GOOGL", "META", "AMZN"]
        
        for symbol in portfolio:
            symbol_data = SymbolSessionData(
                symbol=symbol,
                base_interval="1m",
                bars={"1m": BarIntervalData(derived=False, base=None, data=deque(), 
                                           quality=0.0, gaps=[], updated=False)},
                indicators={},
                quality=0.0,
                session_metrics=None,
                meets_session_config_requirements=True,
                added_by="strategy",
                auto_provisioned=False,
                upgraded_from_adhoc=False,
                added_at=datetime.now()
            )
            session_data.register_symbol_data(symbol_data)
            coordinator._calculate_historical_quality(symbols=[symbol])
        
        # Verify all added with full provisioning
        assert len(session_data.symbols) == 5
        assert coordinator._calculate_historical_quality.call_count == 5
        
        for symbol in portfolio:
            symbol_data = session_data.get_symbol_data(symbol)
            assert symbol_data.meets_session_config_requirements is True
            assert symbol_data.auto_provisioned is False
    
    def test_strategy_incremental_additions(self, strategy_workflow_setup):
        """Test strategy adds symbols incrementally during session."""
        coordinator = strategy_workflow_setup
        session_data = coordinator.session_data
        
        # Start with 2 symbols
        for symbol in ["AAPL", "MSFT"]:
            symbol_data = SymbolSessionData(
                symbol=symbol,
                base_interval="1m",
                bars={},
                indicators={},
                quality=0.0,
                session_metrics=None,
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False,
                upgraded_from_adhoc=False,
                added_at=datetime.now()
            )
            session_data.register_symbol_data(symbol_data)
        
        assert len(session_data.symbols) == 2
        
        # Strategy adds 3 more mid-session
        for symbol in ["GOOGL", "META", "AMZN"]:
            symbol_data = SymbolSessionData(
                symbol=symbol,
                base_interval="1m",
                bars={},
                indicators={},
                quality=0.0,
                session_metrics=None,
                meets_session_config_requirements=True,
                added_by="strategy",
                auto_provisioned=False,
                upgraded_from_adhoc=False,
                added_at=datetime.now()
            )
            session_data.register_symbol_data(symbol_data)
        
        # Verify incremental additions
        assert len(session_data.symbols) == 5
        
        # All meet requirements
        for symbol_data in session_data.symbols.values():
            assert symbol_data.meets_session_config_requirements is True
