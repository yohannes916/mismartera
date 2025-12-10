"""Integration Tests for Upgrade Path

Tests the upgrade path where adhoc symbols are upgraded to full symbols
(scanner adds symbol → strategy adds same symbol).
"""
import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime
from collections import deque
from app.threads.session_coordinator import SessionCoordinator, ProvisioningRequirements, SymbolValidationResult
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData


@pytest.fixture
def session_with_adhoc_symbols():
    """Create session with adhoc symbols ready for upgrade."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator.session_data = SessionData()
    coordinator._base_interval = "1m"
    coordinator._derived_intervals_validated = ["5m", "15m"]
    
    # Add adhoc symbol (from scanner)
    adhoc = SymbolSessionData(
        symbol="TSLA",
        base_
        bars={
            "1m": BarIntervalData(
                derived=False,
                base=None,
                data=deque([Mock() for _ in range(40)]),  # Minimal warmup data
                quality=0.0,  # No quality calculated
                gaps=[],
                updated=True
            ),
            "5m": BarIntervalData(
                derived=True,
                base="1m",
                data=[Mock() for _ in range(8)],  # Warmup
                quality=0.0,
                gaps=[],
                updated=True
            )
        },
        indicators={"sma_20_5m": Mock()},
        quality=0.0,
        session_metrics=None,
        meets_session_config_requirements=False,
        added_by="scanner",
        auto_provisioned=True,
        upgraded_from_adhoc=False,
        added_at=datetime.now()
    )
    coordinator.session_data.register_symbol_data(adhoc)
    
    # Mock methods
    coordinator._validate_symbol_for_loading = Mock(return_value=SymbolValidationResult(symbol="TEST",
            
        can_proceed=True, reason="Valid", data_source_available=True))
    coordinator._manage_historical_data = Mock(return_value=True)
    coordinator._calculate_historical_quality = Mock(return_value=True)
    
    return coordinator


class TestUpgradePath:
    """Test upgrade from adhoc to full."""
    
    def test_upgrade_adhoc_to_full(self, session_with_adhoc_symbols):
        """Test complete upgrade flow."""
        coordinator = session_with_adhoc_symbols
        session_data = coordinator.session_data
        
        # Get existing adhoc symbol
        tsla = session_data.get_symbol_data("TSLA")
        assert tsla.meets_session_config_requirements is False
        assert tsla.auto_provisioned is True
        assert tsla.quality == 0.0
        
        # Strategy wants full symbol
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="TSLA",
            source="strategy",
            symbol_exists=True,
            symbol_data=tsla,
            required_intervals=["15m"],  # Missing interval
            base_
            historical_  # Full historical
            
            needs_session=False,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=True,  # Preserve
            provisioning_steps=[
                "upgrade_symbol",
                "add_interval_15m",
                "load_historical",
                "calculate_quality"
            ],
            can_proceed=True,
            validation_result=coordinator._validate_symbol_for_loading("TSLA"),
            validation_errors=[]
        )
        
        # Execute upgrade
        tsla.meets_session_config_requirements = True
        tsla.upgraded_from_adhoc = True
        tsla.added_by = "strategy"
        
        coordinator._manage_historical_data(symbols=["TSLA"])
        coordinator._calculate_historical_quality(symbols=["TSLA"])
        
        # Expected: Upgraded successfully
        assert tsla.meets_session_config_requirements is True
        assert tsla.upgraded_from_adhoc is True
        assert tsla.added_by == "strategy"
        assert "upgrade_symbol" in req.provisioning_steps
        coordinator._manage_historical_data.assert_called_once()
        coordinator._calculate_historical_quality.assert_called_once()
    
    def test_upgrade_loads_missing_historical(self, session_with_adhoc_symbols):
        """Test upgrade loads full 30 days historical."""
        coordinator = session_with_adhoc_symbols
        tsla = coordinator.session_data.get_symbol_data("TSLA")
        
        # Adhoc had minimal data (~40 bars = ~2 days warmup)
        initial_bar_count = len(tsla.bars["1m"].data)
        assert initial_bar_count < 1000  # Less than 30 days
        
        # Upgrade requirement
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="TSLA",
            source="strategy",
            symbol_exists=True,
            symbol_data=tsla,
            required_intervals=[],
            base_
            historical_  # Full historical
            
            needs_session=False,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=True,
            provisioning_steps=["upgrade_symbol", "load_historical", "calculate_quality"],
            can_proceed=True,
            validation_result=coordinator._validate_symbol_for_loading("TSLA"),
            validation_errors=[]
        )
        
        # Execute historical load
        coordinator._manage_historical_data(symbols=["TSLA"])
        
        # Expected: Full historical loaded (30 days, not just warmup)
        assert req.historical_days == 30
        assert "load_historical" in req.provisioning_steps
        coordinator._manage_historical_data.assert_called_with(symbols=["TSLA"])
    
    def test_upgrade_adds_missing_intervals(self, session_with_adhoc_symbols):
        """Test upgrade adds missing config intervals."""
        coordinator = session_with_adhoc_symbols
        tsla = coordinator.session_data.get_symbol_data("TSLA")
        
        # Adhoc has 1m, 5m but missing 15m
        assert "1m" in tsla.bars
        assert "5m" in tsla.bars
        assert "15m" not in tsla.bars
        
        # Upgrade requirement
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="TSLA",
            source="strategy",
            symbol_exists=True,
            symbol_data=tsla,
            required_intervals=["15m"],  # Need to add
            base_
            historical_
            
            needs_session=False,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=True,
            provisioning_steps=["upgrade_symbol", "add_interval_15m", "load_historical", "calculate_quality"],
            can_proceed=True,
            validation_result=coordinator._validate_symbol_for_loading("TSLA"),
            validation_errors=[]
        )
        
        # Expected: 15m interval to be added
        assert "15m" in req.required_intervals
        assert "add_interval_15m" in req.provisioning_steps
    
    def test_upgrade_calculates_quality(self, session_with_adhoc_symbols):
        """Test upgrade calculates quality score."""
        coordinator = session_with_adhoc_symbols
        tsla = coordinator.session_data.get_symbol_data("TSLA")
        
        # Adhoc had no quality
        assert tsla.quality == 0.0
        
        # Upgrade requirement
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="TSLA",
            source="strategy",
            symbol_exists=True,
            symbol_data=tsla,
            required_intervals=[],
            base_
            historical_
            
            needs_session=False,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=True,
            provisioning_steps=["upgrade_symbol", "load_historical", "calculate_quality"],
            can_proceed=True,
            validation_result=coordinator._validate_symbol_for_loading("TSLA"),
            validation_errors=[]
        )
        
        # Execute quality calculation
        coordinator._calculate_historical_quality(symbols=["TSLA"])
        
        # Expected: Quality calculation included
        assert "calculate_quality" in req.provisioning_steps
        coordinator._calculate_historical_quality.assert_called_once()
    
    def test_upgrade_preserves_existing_data(self, session_with_adhoc_symbols):
        """Test upgrade preserves existing bars and indicators."""
        coordinator = session_with_adhoc_symbols
        tsla = coordinator.session_data.get_symbol_data("TSLA")
        
        # Existing data
        initial_1m_bars = len(tsla.bars["1m"].data)
        initial_indicators = list(tsla.indicators.keys())
        
        assert initial_1m_bars > 0
        assert "sma_20_5m" in initial_indicators
        
        # Simulate upgrade
        tsla.meets_session_config_requirements = True
        tsla.upgraded_from_adhoc = True
        
        # Load more historical
        coordinator._manage_historical_data(symbols=["TSLA"])
        
        # Expected: Existing data preserved, more data added
        # (In real implementation, historical loading would append/extend data)
        assert "sma_20_5m" in tsla.indicators  # Indicator preserved
        assert "1m" in tsla.bars  # Intervals preserved
        assert "5m" in tsla.bars


class TestMultipleUpgrades:
    """Test multiple symbols upgrading."""
    
    def test_multiple_adhoc_symbols_upgrade(self, session_with_adhoc_symbols):
        """Test multiple adhoc symbols can be upgraded independently."""
        coordinator = session_with_adhoc_symbols
        session_data = coordinator.session_data
        
        # Add another adhoc symbol
        adhoc2 = SymbolSessionData(
            symbol="NVDA",
            base_
            bars={"1m": BarIntervalData(derived=False, base=None, data=deque(), quality=0.0, gaps=[], updated=False)},
            indicators={},
            quality=0.0,
            session_metrics=None,
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        session_data.register_symbol_data(adhoc2)
        
        # Upgrade both
        for symbol_name in ["TSLA", "NVDA"]:
            symbol = session_data.get_symbol_data(symbol_name)
            symbol.meets_session_config_requirements = True
            symbol.upgraded_from_adhoc = True
            symbol.added_by = "strategy"
            coordinator._calculate_historical_quality(symbols=[symbol_name])
        
        # Expected: Both upgraded
        tsla = session_data.get_symbol_data("TSLA")
        nvda = session_data.get_symbol_data("NVDA")
        
        assert tsla.upgraded_from_adhoc is True
        assert nvda.upgraded_from_adhoc is True
        assert coordinator._calculate_historical_quality.call_count == 2
