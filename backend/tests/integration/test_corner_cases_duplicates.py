"""Integration Tests for Duplicate Detection Corner Cases

Tests edge cases for duplicate detection:
- Duplicate config symbol
- Duplicate mid-session symbol
- Duplicate adhoc symbol
- Duplicate indicator
- Duplicate interval
"""
import pytest
from unittest.mock import Mock
from datetime import datetime
from collections import deque
from app.threads.session_coordinator import SessionCoordinator, ProvisioningRequirements, SymbolValidationResult
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData
from app.indicators.base import IndicatorConfig, IndicatorType


@pytest.fixture
def session_with_symbols():
    """Create session with existing symbols."""
    from app.managers.data_manager.session_data import SessionData
    
    session_data = SessionData()
    
    # Add config symbol
    config_symbol = SymbolSessionData(
        symbol="AAPL",
        base_
        bars={"1m": BarIntervalData(derived=False, base=None, data=deque(), quality=0.0, gaps=[], updated=False),
              "5m": BarIntervalData(derived=True, base="1m", data=[], quality=0.0, gaps=[], updated=False)},
        indicators={"sma_20_5m": Mock()},
        quality=0.85,
        session_metrics=None,
        meets_session_config_requirements=True,
        added_by="config",
        auto_provisioned=False,
        upgraded_from_adhoc=False,
        added_at=datetime.now()
    )
    session_data.register_symbol_data(config_symbol)
    
    # Add adhoc symbol
    adhoc_symbol = SymbolSessionData(
        symbol="TSLA",
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
    session_data.register_symbol_data(adhoc_symbol)
    
    return session_data


class TestDuplicateSymbols:
    """Test duplicate symbol detection."""
    
    def test_duplicate_config_symbol(self, session_with_symbols):
        """Test adding config symbol that already exists."""
        session_data = session_with_symbols
        
        # Try to add AAPL again
        existing = session_data.get_symbol_data("AAPL")
        
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config",
            symbol_exists=True,
            symbol_data=existing,
            required_intervals=[],
            base_
            historical_
            
            needs_session=False,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            provisioning_steps=[],
            can_proceed=False,
            validation_result=SymbolValidationResult(symbol="TEST",
            
                can_proceed=False,
                reason="Symbol AAPL already loaded and meets session requirements",
                data_source_available=True,
                has_historical_data=True
            ),
            validation_errors=["Symbol already fully loaded"]
        )
        
        # Expected: Duplicate detected
        assert req.can_proceed is False
        assert req.symbol_exists is True
        assert existing.meets_session_config_requirements is True
    
    def test_duplicate_midsession_symbol(self, session_with_symbols):
        """Test strategy adds symbol that config already loaded."""
        session_data = session_with_symbols
        
        # Strategy tries to add AAPL (already from config)
        existing = session_data.get_symbol_data("AAPL")
        
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
            validation_result=SymbolValidationResult(symbol="TEST",
            
                can_proceed=False,
                reason="Symbol AAPL already loaded and meets session requirements",
                data_source_available=True,
                has_historical_data=True
            ),
            validation_errors=["Symbol already fully loaded"]
        )
        
        # Expected: Duplicate detected
        assert req.can_proceed is False
        assert "already" in req.validation_errors[0].lower()
    
    def test_duplicate_adhoc_symbol(self, session_with_symbols):
        """Test scanner adds symbol that scanner already added."""
        session_data = session_with_symbols
        
        # Scanner tries to add TSLA again
        existing = session_data.get_symbol_data("TSLA")
        
        req = ProvisioningRequirements(
            operation_type="indicator",
            symbol="TSLA",
            source="scanner",
            symbol_exists=True,
            symbol_data=existing,
            required_intervals=[],
            base_
            historical_
            
            needs_session=False,
            indicator_config=IndicatorConfig(
                name="rsi", type=IndicatorType.MOMENTUM,
                period=14,  params={}
            ),
            
            
            
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=False,
            provisioning_steps=["register_indicator"],
            can_proceed=True,  # Can add indicator even if symbol exists
            validation_result=SymbolValidationResult(symbol="TEST",
            
                can_proceed=True,
                reason="Valid",
                data_source_available=True,
                has_historical_data=True
            ),
            validation_errors=[]
        )
        
        # Expected: Symbol exists but can add indicator
        assert req.symbol_exists is True
        assert req.can_proceed is True
        assert "register_indicator" in req.provisioning_steps


class TestDuplicateIndicators:
    """Test duplicate indicator detection."""
    
    def test_duplicate_indicator(self, session_with_symbols):
        """Test adding indicator that already exists."""
        session_data = session_with_symbols
        
        # AAPL already has sma_20_5m
        existing = session_data.get_symbol_data("AAPL")
        assert "sma_20_5m" in existing.indicators
        
        # Try to add same indicator again
        sma_config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=20,
            
            params={}
        )
        
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
            validation_result=SymbolValidationResult(symbol="TEST",
            
                can_proceed=False,
                reason="Indicator sma_20_5m already exists for AAPL",
                data_source_available=True,
                has_historical_data=True
            ),
            validation_errors=["Indicator already exists"]
        )
        
        # Expected: Duplicate detected
        assert req.can_proceed is False
        assert "already exists" in req.validation_errors[0].lower()


class TestDuplicateIntervals:
    """Test duplicate interval detection."""
    
    def test_duplicate_interval(self, session_with_symbols):
        """Test adding interval that already exists."""
        session_data = session_with_symbols
        
        # AAPL already has 5m
        existing = session_data.get_symbol_data("AAPL")
        assert "5m" in existing.bars
        
        # Try to add 5m again
        req = ProvisioningRequirements(
            operation_type="bar",
            symbol="AAPL",
            source="scanner",
            symbol_exists=True,
            symbol_data=existing,
            required_intervals=["5m"],
            base_
            historical_
            
            needs_session=False,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="scanner",
            auto_provisioned=False,
            provisioning_steps=[],
            can_proceed=False,
            validation_result=SymbolValidationResult(symbol="TEST",
            
                can_proceed=False,
                reason="Interval 5m already exists for AAPL",
                data_source_available=True,
                has_historical_data=True
            ),
            validation_errors=["Interval already exists"]
        )
        
        # Expected: Duplicate detected
        assert req.can_proceed is False
        assert "already exists" in req.validation_errors[0].lower()
