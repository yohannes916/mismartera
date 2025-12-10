"""Simple Unit Tests for Provisioning System

These tests verify the basic provisioning dataclasses work correctly
with the actual API (not assumed API).
"""
import pytest
from datetime import datetime
from app.threads.session_coordinator import (
    ProvisioningRequirements,
    SymbolValidationResult
)
from app.managers.data_manager.session_data import SymbolSessionData


class TestProvisioningRequirementsBasics:
    """Test ProvisioningRequirements dataclass basics."""
    
    def test_create_minimal_requirement(self):
        """Test creating minimal ProvisioningRequirements."""
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
            source="config"
        )
        
        # Verify required fields
        assert req.operation_type == "symbol"
        assert req.symbol == "AAPL"
        assert req.source == "config"
        
        # Verify defaults
        assert req.symbol_exists is False
        assert req.symbol_data is None
        assert req.required_intervals == []
        assert req.needs_historical is False
        assert req.historical_days == 0
        assert req.can_proceed is False
        assert req.added_by == "adhoc"
    
    def test_create_full_symbol_requirement(self):
        """Test creating full symbol loading requirement."""
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="MSFT",
            source="config",
            symbol_exists=False,
            required_intervals=["1m", "5m", "15m"],
            base_interval="1m",
            needs_historical=True,
            historical_days=30,
            needs_session=True,
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            can_proceed=True,
            provisioning_steps=[
                "create_symbol",
                "add_intervals",
                "load_historical"
            ]
        )
        
        assert req.symbol == "MSFT"
        assert req.needs_historical is True
        assert req.historical_days == 30
        assert req.needs_session is True
        assert req.can_proceed is True
        assert len(req.provisioning_steps) == 3


class TestSymbolValidationResultBasics:
    """Test SymbolValidationResult dataclass basics."""
    
    def test_create_validation_result(self):
        """Test creating SymbolValidationResult."""
        result = SymbolValidationResult(
            symbol="AAPL",
            can_proceed=True,
            reason="Valid",
            data_source_available=True,
            has_historical_data=True
        )
        
        assert result.symbol == "AAPL"
        assert result.can_proceed is True
        assert result.reason == "Valid"
        assert result.data_source_available is True
        assert result.has_historical_data is True
    
    def test_create_validation_failure(self):
        """Test creating failed validation result."""
        result = SymbolValidationResult(
            symbol="INVALID",
            can_proceed=False,
            reason="No data source",
            data_source_available=False
        )
        
        assert result.symbol == "INVALID"
        assert result.can_proceed is False
        assert result.data_source_available is False


class TestSymbolSessionDataBasics:
    """Test SymbolSessionData creation."""
    
    def test_create_symbol_data(self):
        """Test creating SymbolSessionData."""
        symbol_data = SymbolSessionData(
            symbol="AAPL",
            base_interval="1m",
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        
        assert symbol_data.symbol == "AAPL"
        assert symbol_data.base_interval == "1m"
        assert symbol_data.meets_session_config_requirements is True
        assert symbol_data.added_by == "config"
        assert symbol_data.auto_provisioned is False
        assert symbol_data.bars == {}  # Default
        assert symbol_data.indicators == {}  # Default
