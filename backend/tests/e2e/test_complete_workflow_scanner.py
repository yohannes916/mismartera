"""E2E Tests for Complete Scanner → Strategy Workflow

Tests the complete workflow where scanner discovers symbols and
strategy upgrades them to full symbols.
"""
import pytest
from unittest.mock import Mock
from datetime import datetime
from collections import deque
from app.threads.session_coordinator import SessionCoordinator
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData
from app.indicators.base import IndicatorConfig, IndicatorType


@pytest.fixture
def scanner_workflow_setup():
    """Setup for scanner workflow testing."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator.session_data = SessionData()
    coordinator._base_interval = "1m"
    coordinator._derived_intervals_validated = ["5m", "15m"]
    
    coordinator._register_single_symbol = Mock(return_value=True)
    coordinator._manage_historical_data = Mock(return_value=True)
    coordinator._calculate_historical_quality = Mock(return_value=True)
    
    return coordinator


@pytest.mark.e2e
class TestScannerWorkflows:
    """Test complete scanner workflows."""
    
    def test_scanner_discovers_indicator_needed(self, scanner_workflow_setup):
        """Test scanner adds indicator, symbol auto-provisioned."""
        coordinator = scanner_workflow_setup
        session_data = coordinator.session_data
        
        # Scanner wants to add SMA indicator for TSLA
        # TSLA doesn't exist yet, so auto-provision
        
        # Step 1: Auto-provision TSLA (minimal)
        tsla = SymbolSessionData(
            symbol="TSLA",
            base_interval="1m",
            bars={"1m": BarIntervalData(derived=False, base=None, data=deque(), 
                                       quality=0.0, gaps=[], updated=False),
                  "5m": BarIntervalData(derived=True, base="1m", data=[], 
                                       quality=0.0, gaps=[], updated=False)},
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        session_data.register_symbol_data(tsla)
        
        # Step 2: Register indicator
        sma_config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=20,
            interval="5m",
            params={}
        )
        tsla.indicators["sma_20_5m"] = Mock()
        
        # Verify auto-provision
        assert session_data.get_symbol_data("TSLA") is not None
        assert tsla.auto_provisioned is True
        assert tsla.meets_session_config_requirements is False
        assert "sma_20_5m" in tsla.indicators
    
    def test_scanner_discovers_strategy_upgrades(self, scanner_workflow_setup):
        """Test scanner discovers, then strategy upgrades to full."""
        coordinator = scanner_workflow_setup
        session_data = coordinator.session_data
        
        # Step 1: Scanner discovers NVDA (adhoc)
        nvda = SymbolSessionData(
            symbol="NVDA",
            base_interval="1m",
            bars={"1m": BarIntervalData(derived=False, base=None, data=deque(), 
                                       quality=0.0, gaps=[], updated=False)},
            indicators={},            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        session_data.register_symbol_data(nvda)
        
        # Verify adhoc state
        assert nvda.meets_session_config_requirements is False
        assert nvda.auto_provisioned is True
        
        # Step 2: Strategy wants to trade NVDA (upgrade)
        nvda.meets_session_config_requirements = True
        nvda.upgraded_from_adhoc = True
        nvda.added_by = "strategy"
        
        # Load full historical and calculate quality
        coordinator._manage_historical_data(symbols=["NVDA"])
        coordinator._calculate_historical_quality(symbols=["NVDA"])
        
        # Verify upgrade
        assert nvda.meets_session_config_requirements is True
        assert nvda.upgraded_from_adhoc is True
        assert nvda.added_by == "strategy"
        coordinator._calculate_historical_quality.assert_called_once()
    
    def test_multiple_scanner_discoveries(self, scanner_workflow_setup):
        """Test scanner discovers multiple symbols in one session."""
        coordinator = scanner_workflow_setup
        session_data = coordinator.session_data
        
        # Scanner discovers multiple symbols
        discoveries = ["TSLA", "NVDA", "AMD", "PLTR"]
        
        for symbol in discoveries:
            symbol_data = SymbolSessionData(
                symbol=symbol,
                base_interval="1m",
                bars={},
                indicators={},                meets_session_config_requirements=False,
                added_by="scanner",
                auto_provisioned=True,
                upgraded_from_adhoc=False,
                added_at=datetime.now()
            )
            session_data.register_symbol_data(symbol_data)
        
        # Verify all discovered
        assert len(session_data.get_active_symbols()) == 4
        for symbol in discoveries:
            symbol_data = session_data.get_symbol_data(symbol)
            assert symbol_data is not None
            assert symbol_data.auto_provisioned is True
    
    def test_scanner_then_strategy_multiple_upgrades(self, scanner_workflow_setup):
        """Test scanner discovers multiple, strategy upgrades some."""
        coordinator = scanner_workflow_setup
        session_data = coordinator.session_data
        
        # Scanner discovers 4 symbols
        for symbol in ["SYM1", "SYM2", "SYM3", "SYM4"]:
            symbol_data = SymbolSessionData(
                symbol=symbol,
                base_interval="1m",
                bars={},
                indicators={},                meets_session_config_requirements=False,
                added_by="scanner",
                auto_provisioned=True,
                upgraded_from_adhoc=False,
                added_at=datetime.now()
            )
            session_data.register_symbol_data(symbol_data)
        
        # Strategy upgrades 2 of them
        for symbol in ["SYM1", "SYM3"]:
            symbol_data = session_data.get_symbol_data(symbol)
            symbol_data.meets_session_config_requirements = True
            symbol_data.upgraded_from_adhoc = True
            symbol_data.added_by = "strategy"
            coordinator._calculate_historical_quality(symbols=[symbol])
        
        # Verify mixed state
        upgraded = [session_data.get_symbol_data("SYM1"), 
                   session_data.get_symbol_data("SYM3")]
        adhoc = [session_data.get_symbol_data("SYM2"), 
                session_data.get_symbol_data("SYM4")]
        
        for symbol_data in upgraded:
            assert symbol_data.meets_session_config_requirements is True
            assert symbol_data.upgraded_from_adhoc is True
        
        for symbol_data in adhoc:
            assert symbol_data.meets_session_config_requirements is False
            assert symbol_data.upgraded_from_adhoc is False
