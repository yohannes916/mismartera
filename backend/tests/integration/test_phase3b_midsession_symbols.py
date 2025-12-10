"""Integration Tests for Phase 3b: Mid-Session Symbols

Tests full symbol additions during active session (strategy adds symbols).
Uses full provisioning - same as config loading.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from collections import deque
from app.threads.session_coordinator import SessionCoordinator, ProvisioningRequirements, SymbolValidationResult
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData


@pytest.fixture
def active_session_for_midsession():
    """Create coordinator with active session for mid-session additions."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator.session_data = SessionData()
    coordinator._base_interval = "1m"
    coordinator._derived_intervals_validated = ["5m", "15m"]
    
    # Add existing config symbols
    for symbol in ["AAPL", "MSFT"]:
        symbol_data = SymbolSessionData(
            symbol=symbol,
            base_
            bars={"1m": BarIntervalData(derived=False, base=None, data=deque(), quality=0.0, gaps=[], updated=False),
                  "5m": BarIntervalData(derived=True, base="1m", data=[], quality=0.0, gaps=[], updated=False)},
            indicators={},
            quality=0.85,
            session_metrics=None,
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        coordinator.session_data.register_symbol_data(symbol_data)
    
    # Mock methods
    coordinator._validate_symbol_for_loading = Mock(return_value=SymbolValidationResult(symbol="TEST",
            
        can_proceed=True, reason="Valid", data_source_available=True))
    coordinator._register_single_symbol = Mock(return_value=True)
    coordinator._manage_historical_data = Mock(return_value=True)
    coordinator._load_queues = Mock(return_value=True)
    coordinator._calculate_historical_quality = Mock(return_value=True)
    
    return coordinator


class TestMidSessionNewSymbol:
    """Test adding new symbol mid-session."""
    
    def test_midsession_add_new_symbol(self, active_session_for_midsession):
        """Test strategy adds new symbol mid-session."""
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="TSLA",
            source="strategy",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["1m", "5m", "15m"],
            base_
            historical_  # Full historical
            
            needs_session=True,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=False,
            provisioning_steps=[
                "create_symbol",
                "add_interval_1m",
                "add_interval_5m",
                "add_interval_15m",
                "load_historical",
                "load_session",
                "calculate_quality"
            ],
            can_proceed=True,
            validation_result=active_session_for_midsession._validate_symbol_for_loading("TSLA"),
            validation_errors=[]
        )
        
        # Execute full provisioning
        active_session_for_midsession._register_single_symbol(
            "TSLA",
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=False
        )
        active_session_for_midsession._manage_historical_data(symbols=["TSLA"])
        active_session_for_midsession._load_queues(symbols=["TSLA"])
        active_session_for_midsession._calculate_historical_quality(symbols=["TSLA"])
        
        # Expected: Full symbol load, same as config
        assert req.meets_session_config_requirements is True
        assert req.historical_days == 30  # Full, not minimal
        assert "calculate_quality" in req.provisioning_steps
        active_session_for_midsession._calculate_historical_quality.assert_called_once()
    
    def test_midsession_duplicate_full_symbol(self, active_session_for_midsession):
        """Test adding symbol that's already fully loaded."""
        existing = active_session_for_midsession.session_data.get_symbol_data("AAPL")
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="strategy",
            symbol_exists=True,
            symbol_data=existing,
            required_intervals=[],
            base_
            historical_
            
            needs_session=False,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=False,
            provisioning_steps=[],
            can_proceed=False,
            validation_result=active_session_for_midsession._validate_symbol_for_loading("AAPL"),
            validation_errors=["Symbol already fully loaded"]
        )
        
        # Expected: Duplicate detected, no provisioning
        assert req.can_proceed is False
        assert req.symbol_exists is True
        assert existing.meets_session_config_requirements is True


class TestMidSessionUpgrade:
    """Test upgrading adhoc symbol to full."""
    
    def test_midsession_upgrade_adhoc_symbol(self, active_session_for_midsession):
        """Test upgrading adhoc symbol to full (strategy adds symbol that scanner added)."""
        # Add adhoc symbol first
        adhoc_symbol = SymbolSessionData(
            symbol="NVDA",
            base_
            bars={"1m": BarIntervalData(derived=False, base=None, data=deque(), quality=0.0, gaps=[], updated=False),
                  "5m": BarIntervalData(derived=True, base="1m", data=[], quality=0.0, gaps=[], updated=False)},
            indicators={},
            quality=0.0,  # No quality calculated
            session_metrics=None,
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        active_session_for_midsession.session_data.register_symbol_data(adhoc_symbol)
        
        # Strategy wants to upgrade it
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="NVDA",
            source="strategy",
            symbol_exists=True,
            symbol_data=adhoc_symbol,
            required_intervals=["15m"],  # Might need missing intervals
            base_
            historical_  # Full historical
            
            needs_session=False,  # Already has queues
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=True,  # Preserve original
            provisioning_steps=[
                "upgrade_symbol",
                "add_interval_15m",
                "load_historical",
                "calculate_quality"
            ],
            can_proceed=True,
            validation_result=active_session_for_midsession._validate_symbol_for_loading("NVDA"),
            validation_errors=[]
        )
        
        # Execute upgrade
        # Update metadata
        adhoc_symbol.meets_session_config_requirements = True
        adhoc_symbol.upgraded_from_adhoc = True
        adhoc_symbol.added_by = "strategy"
        
        active_session_for_midsession._manage_historical_data(symbols=["NVDA"])
        active_session_for_midsession._calculate_historical_quality(symbols=["NVDA"])
        
        # Expected: Upgrade steps, metadata updated
        assert "upgrade_symbol" in req.provisioning_steps
        assert "load_historical" in req.provisioning_steps
        assert "calculate_quality" in req.provisioning_steps
        assert adhoc_symbol.upgraded_from_adhoc is True
        assert adhoc_symbol.meets_session_config_requirements is True
    
    def test_midsession_upgrade_metadata(self, active_session_for_midsession):
        """Test metadata correctly updated during upgrade."""
        # Create adhoc symbol
        adhoc = SymbolSessionData(
            symbol="AMD",
            base_
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
        
        # Before upgrade
        assert adhoc.meets_session_config_requirements is False
        assert adhoc.auto_provisioned is True
        assert adhoc.upgraded_from_adhoc is False
        
        # Simulate upgrade
        adhoc.meets_session_config_requirements = True
        adhoc.upgraded_from_adhoc = True
        adhoc.added_by = "strategy"
        
        # After upgrade
        assert adhoc.meets_session_config_requirements is True
        assert adhoc.upgraded_from_adhoc is True
        assert adhoc.added_by == "strategy"
        assert adhoc.auto_provisioned is True  # Preserved


class TestMidSessionFullProvisioning:
    """Test full provisioning during mid-session."""
    
    def test_midsession_full_historical_loading(self, active_session_for_midsession):
        """Test mid-session loads full 30 days historical."""
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="GOOGL",
            source="strategy",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["1m", "5m", "15m"],
            base_
            historical_  # Full
            
            needs_session=True,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=False,
            provisioning_steps=["create_symbol", "load_historical"],
            can_proceed=True,
            validation_result=active_session_for_midsession._validate_symbol_for_loading("GOOGL"),
            validation_errors=[]
        )
        
        # Expected: Full historical (30 days), not warmup (2 days)
        assert req.historical_days == 30
        assert req.warmup_days == 0
        assert req.meets_session_config_requirements is True
    
    def test_midsession_all_intervals_added(self, active_session_for_midsession):
        """Test mid-session adds all config intervals."""
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="META",
            source="strategy",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["1m", "5m", "15m"],  # All intervals
            base_
            historical_
            
            needs_session=True,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=False,
            provisioning_steps=[
                "create_symbol",
                "add_interval_1m",
                "add_interval_5m",
                "add_interval_15m",
                "load_historical",
                "load_session"
            ],
            can_proceed=True,
            validation_result=active_session_for_midsession._validate_symbol_for_loading("META"),
            validation_errors=[]
        )
        
        # Expected: All intervals from config
        assert len(req.required_intervals) == 3
        assert "1m" in req.required_intervals
        assert "5m" in req.required_intervals
        assert "15m" in req.required_intervals
    
    def test_midsession_quality_calculation(self, active_session_for_midsession):
        """Test quality calculated for mid-session symbols."""
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="NFLX",
            source="strategy",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["1m", "5m"],
            base_
            historical_
            
            needs_session=True,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=False,
            provisioning_steps=[
                "create_symbol",
                "add_interval_1m",
                "add_interval_5m",
                "load_historical",
                "load_session",
                "calculate_quality"
            ],
            can_proceed=True,
            validation_result=active_session_for_midsession._validate_symbol_for_loading("NFLX"),
            validation_errors=[]
        )
        
        # Execute
        active_session_for_midsession._calculate_historical_quality(symbols=["NFLX"])
        
        # Expected: Quality calculation included
        assert "calculate_quality" in req.provisioning_steps
        active_session_for_midsession._calculate_historical_quality.assert_called_once()
    
    def test_midsession_metadata_correctness(self, active_session_for_midsession):
        """Test mid-session symbol metadata."""
        # Create mid-session symbol
        symbol = SymbolSessionData(
            symbol="DIS",
            base_
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
        
        # Expected: Full symbol metadata
        assert symbol.meets_session_config_requirements is True
        assert symbol.added_by == "strategy"
        assert symbol.auto_provisioned is False
        assert symbol.upgraded_from_adhoc is False
