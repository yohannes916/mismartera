"""Integration Tests for Phase 3a: Adhoc Additions

Tests lightweight adhoc additions during active session (scanner adds indicators/bars).
Uses minimal provisioning - just what's needed for the operation.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from collections import deque
from app.threads.session_coordinator import SessionCoordinator, ProvisioningRequirements, SymbolValidationResult
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData
from app.indicators.base import IndicatorConfig, IndicatorType


@pytest.fixture
def active_session_coordinator():
    """Create coordinator with active session."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator.session_data = SessionData()
    coordinator._base_interval = "1m"
    coordinator._derived_intervals_validated = ["5m", "15m"]
    
    # Add existing config symbol
    existing = SymbolSessionData(
        symbol="AAPL",
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
    coordinator.session_data.register_symbol_data(existing)
    
    # Mock methods
    coordinator._validate_symbol_for_loading = Mock(return_value=SymbolValidationResult(symbol="TEST",
            
        can_proceed=True, reason="Valid", data_source_available=True))
    coordinator._register_single_symbol = Mock(return_value=True)
    coordinator._manage_historical_data = Mock(return_value=True)
    coordinator._load_queues = Mock(return_value=True)
    
    return coordinator


class TestAdhocIndicatorAdditions:
    """Test adhoc indicator additions."""
    
    def test_adhoc_add_indicator_new_symbol(self, active_session_coordinator):
        """Test scanner adds indicator for new symbol (auto-provision)."""
        sma_config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=20,
            
            params={}
        )
        
        # Requirement analysis
        req = ProvisioningRequirements(
            operation_type="indicator",
            symbol="TSLA",
            source="scanner",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["1m", "5m"],
            base_
            historical_
            
            needs_session=True,
            indicator_config=sma_config,
            
            
            
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            provisioning_steps=[
                "create_symbol",
                "add_interval_1m",
                "add_interval_5m",
                "load_historical",
                "load_session",
                "register_indicator"
            ],
            can_proceed=True,
            validation_result=active_session_coordinator._validate_symbol_for_loading("TSLA"),
            validation_errors=[]
        )
        
        # Execute provisioning
        active_session_coordinator._register_single_symbol(
            "TSLA",
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True
        )
        active_session_coordinator._manage_historical_data(symbols=["TSLA"])
        active_session_coordinator._load_queues(symbols=["TSLA"])
        
        # Expected: Symbol auto-provisioned, minimal structure
        assert req.auto_provisioned is True
        assert req.meets_session_config_requirements is False
        assert req.warmup_days > 0  # Warmup only, not full historical
        assert "register_indicator" in req.provisioning_steps
        active_session_coordinator._register_single_symbol.assert_called_once()
    
    def test_adhoc_add_indicator_existing_symbol(self, active_session_coordinator):
        """Test scanner adds indicator to existing symbol."""
        sma_config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=20,
            
            params={}
        )
        
        # Requirement analysis for existing symbol
        existing = active_session_coordinator.session_data.get_symbol_data("AAPL")
        
        req = ProvisioningRequirements(
            operation_type="indicator",
            symbol="AAPL",
            source="scanner",
            symbol_exists=True,
            symbol_data=existing,
            required_intervals=[],  # All intervals exist
            base_
            historical_
            
            needs_session=False,
            indicator_config=sma_config,
            
            
            
            meets_session_config_requirements=True,
            added_by="scanner",
            auto_provisioned=False,
            provisioning_steps=["register_indicator"],  # Only register
            can_proceed=True,
            validation_result=active_session_coordinator._validate_symbol_for_loading("AAPL"),
            validation_errors=[]
        )
        
        # Expected: Only indicator registration, no symbol creation
        assert req.symbol_exists is True
        assert req.provisioning_steps == ["register_indicator"]
        assert "create_symbol" not in req.provisioning_steps
        assert "load_historical" not in req.provisioning_steps


class TestAdhocBarAdditions:
    """Test adhoc bar additions."""
    
    def test_adhoc_add_bar_new_symbol(self, active_session_coordinator):
        """Test scanner adds bar for new symbol."""
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="NVDA",
            source="scanner",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["1m", "15m"],
            base_
            historical_
            
            needs_session=True,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            provisioning_steps=[
                "create_symbol",
                "add_interval_1m",
                "add_interval_15m",
                "load_historical",
                "load_session"
            ],
            can_proceed=True,
            validation_result=active_session_coordinator._validate_symbol_for_loading("NVDA"),
            validation_errors=[]
        )
        
        # Execute
        active_session_coordinator._register_single_symbol(
            "NVDA",
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True
        )
        
        # Expected: Symbol auto-provisioned, base + derived intervals
        assert req.auto_provisioned is True
        assert "1m" in req.required_intervals
        assert "15m" in req.required_intervals
        assert req.historical_days == 5  # Limited historical
    
    def test_adhoc_add_bar_existing_symbol(self, active_session_coordinator):
        """Test scanner adds bar interval to existing symbol."""
        existing = active_session_coordinator.session_data.get_symbol_data("AAPL")
        
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="AAPL",
            source="scanner",
            symbol_exists=True,
            symbol_data=existing,
            required_intervals=["15m"],  # New interval
            base_
            historical_
            
            needs_session=True,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="scanner",
            auto_provisioned=False,
            provisioning_steps=[
                "add_interval_15m",
                "load_historical",
                "load_session"
            ],
            can_proceed=True,
            validation_result=active_session_coordinator._validate_symbol_for_loading("AAPL"),
            validation_errors=[]
        )
        
        # Expected: Only add interval, no symbol creation
        assert req.symbol_exists is True
        assert "create_symbol" not in req.provisioning_steps
        assert "add_interval_15m" in req.provisioning_steps


class TestAdhocHistoricalLoading:
    """Test adhoc historical loading."""
    
    def test_adhoc_minimal_historical_loading(self, active_session_coordinator):
        """Test adhoc loads minimal historical (warmup only)."""
        req = ProvisioningRequirements(
            operation_type="indicator",
            symbol="RIVN",
            source="scanner",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["1m", "5m"],
            base_
            historical_
              # Only warmup, not full 30 days
            needs_session=True,
            indicator_config=IndicatorConfig(
                name="sma", type=IndicatorType.TREND,
                period=20,  params={}
            ),
            
            
            
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            provisioning_steps=["create_symbol", "load_historical"],
            can_proceed=True,
            validation_result=active_session_coordinator._validate_symbol_for_loading("RIVN"),
            validation_errors=[]
        )
        
        # Expected: Warmup days only (2), not full historical (30)
        assert req.historical_days == 0
        assert req.warmup_days == 2
        assert req.warmup_days < 30  # Much less than full
    
    def test_adhoc_no_quality_calculation(self, active_session_coordinator):
        """Test adhoc does not calculate quality."""
        req = ProvisioningRequirements(
            operation_type="indicator",
            symbol="PLTR",
            source="scanner",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["1m", "5m"],
            base_
            historical_
            
            needs_session=True,
            indicator_config=IndicatorConfig(
                name="ema", type=IndicatorType.TREND,
                period=12,  params={}
            ),
            
            
            
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            provisioning_steps=[
                "create_symbol",
                "add_interval_1m",
                "add_interval_5m",
                "load_historical",
                "load_session",
                "register_indicator"
            ],
            can_proceed=True,
            validation_result=active_session_coordinator._validate_symbol_for_loading("PLTR"),
            validation_errors=[]
        )
        
        # Expected: No quality calculation step
        assert "calculate_quality" not in req.provisioning_steps
        assert req.meets_session_config_requirements is False


class TestAdhocMetadata:
    """Test adhoc metadata."""
    
    def test_adhoc_metadata_correctness(self, active_session_coordinator):
        """Test adhoc symbol has correct metadata."""
        # Create adhoc symbol
        adhoc_symbol = SymbolSessionData(
            symbol="COIN",
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
        
        # Expected: Adhoc metadata
        assert adhoc_symbol.meets_session_config_requirements is False
        assert adhoc_symbol.added_by == "scanner"
        assert adhoc_symbol.auto_provisioned is True
        assert adhoc_symbol.upgraded_from_adhoc is False
    
    def test_adhoc_derived_interval_base_added(self, active_session_coordinator):
        """Test adhoc derived interval also adds base interval."""
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="SQ",
            source="scanner",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["1m", "5m"],  # Base + derived
            base_
            historical_
            
            needs_session=True,
            indicator_config=None,
              # Asked for 5m...
            
            
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            provisioning_steps=[
                "create_symbol",
                "add_interval_1m",  # ...but also gets 1m base
                "add_interval_5m",
                "load_historical",
                "load_session"
            ],
            can_proceed=True,
            validation_result=active_session_coordinator._validate_symbol_for_loading("SQ"),
            validation_errors=[]
        )
        
        # Expected: Both base and derived
        assert "1m" in req.required_intervals
        assert "5m" in req.required_intervals
        assert "add_interval_1m" in req.provisioning_steps
        assert "add_interval_5m" in req.provisioning_steps


class TestAdhocDuplicates:
    """Test adhoc duplicate detection."""
    
    def test_adhoc_duplicate_detection(self, active_session_coordinator):
        """Test duplicate adhoc indicator detected."""
        # First addition
        sma_config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=20,
            
            params={}
        )
        
        # Add indicator to AAPL
        existing = active_session_coordinator.session_data.get_symbol_data("AAPL")
        existing.indicators["sma_20_5m"] = Mock()
        
        # Try to add again
        req = ProvisioningRequirements(
            operation_type="indicator",
            symbol="AAPL",
            source="scanner",
            symbol_exists=True,
            symbol_data=existing,
            required_intervals=[],
            base_
            historical_
            
            needs_session=False,
            indicator_config=sma_config,
            
            
            
            meets_session_config_requirements=True,
            added_by="scanner",
            auto_provisioned=False,
            provisioning_steps=[],
            can_proceed=False,
            validation_result=active_session_coordinator._validate_symbol_for_loading("AAPL"),
            validation_errors=["Indicator already exists"]
        )
        
        # Expected: Duplicate detected
        assert req.can_proceed is False
        assert "already exists" in req.validation_errors[0].lower()
    
    def test_adhoc_multiple_concurrent(self, active_session_coordinator):
        """Test multiple concurrent adhoc additions."""
        symbols = ["GME", "AMC", "BB"]
        
        # Add multiple symbols concurrently (simulated)
        for symbol in symbols:
            active_session_coordinator._register_single_symbol(
                symbol,
                meets_session_config_requirements=False,
                added_by="scanner",
                auto_provisioned=True
            )
        
        # Expected: All symbols added independently
        assert active_session_coordinator._register_single_symbol.call_count == len(symbols)
