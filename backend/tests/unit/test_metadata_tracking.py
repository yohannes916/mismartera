"""Unit Tests for Metadata Tracking

Tests that metadata fields on SymbolSessionData are set correctly
for different symbol loading scenarios.
"""
import pytest
from datetime import datetime, timedelta
from app.managers.data_manager.session_data import SymbolSessionData


class TestMetadataForConfigSymbols:
    """Test metadata for symbols loaded from config."""
    
    def test_config_symbol_metadata(self):
        """Test config symbol has correct metadata."""
        symbol = SymbolSessionData(
            symbol="AAPL",
            base_interval="1m",
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        
        assert symbol.meets_session_config_requirements is True
        assert symbol.added_by == "config"
        assert symbol.auto_provisioned is False
        assert symbol.upgraded_from_adhoc is False
        assert symbol.added_at is not None


class TestMetadataForScannerSymbols:
    """Test metadata for symbols added by scanner."""
    
    def test_scanner_adhoc_metadata(self):
        """Test scanner adhoc symbol has correct metadata."""
        symbol = SymbolSessionData(
            symbol="TSLA",
            base_interval="1m",
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        
        assert symbol.meets_session_config_requirements is False
        assert symbol.added_by == "scanner"
        assert symbol.auto_provisioned is True
        assert symbol.upgraded_from_adhoc is False


class TestMetadataForStrategySymbols:
    """Test metadata for symbols added by strategy."""
    
    def test_strategy_full_metadata(self):
        """Test strategy symbol has correct metadata."""
        symbol = SymbolSessionData(
            symbol="MSFT",
            base_interval="1m",
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        
        assert symbol.meets_session_config_requirements is True
        assert symbol.added_by == "strategy"
        assert symbol.auto_provisioned is False


class TestMetadataForUpgradedSymbols:
    """Test metadata for symbols upgraded from adhoc to full."""
    
    def test_upgraded_symbol_metadata(self):
        """Test upgraded symbol preserves original metadata."""
        # Create as adhoc
        added_time = datetime.now()
        symbol = SymbolSessionData(
            symbol="NVDA",
            base_interval="1m",
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            upgraded_from_adhoc=False,
            added_at=added_time
        )
        
        # Simulate upgrade
        symbol.meets_session_config_requirements = True
        symbol.upgraded_from_adhoc = True
        symbol.added_by = "strategy"
        
        # Verify metadata after upgrade
        assert symbol.meets_session_config_requirements is True
        assert symbol.upgraded_from_adhoc is True
        assert symbol.added_by == "strategy"
        assert symbol.auto_provisioned is True  # Preserved
        assert symbol.added_at == added_time  # Preserved


class TestTimestampTracking:
    """Test added_at timestamp tracking."""
    
    def test_timestamp_set_on_creation(self):
        """Test added_at is set when symbol created."""
        before = datetime.now()
        
        symbol = SymbolSessionData(
            symbol="TEST",
            base_interval="1m",
            added_at=datetime.now()
        )
        
        after = datetime.now()
        
        assert symbol.added_at is not None
        assert before <= symbol.added_at <= after
    
    def test_timestamp_ordering(self):
        """Test timestamps can be used for ordering."""
        time1 = datetime.now()
        symbol1 = SymbolSessionData(
            symbol="FIRST",
            base_interval="1m",
            added_at=time1
        )
        
        # Wait a tiny bit
        time2 = time1 + timedelta(seconds=1)
        symbol2 = SymbolSessionData(
            symbol="SECOND",
            base_interval="1m",
            added_at=time2
        )
        
        # Can order by timestamp
        symbols = sorted([symbol2, symbol1], key=lambda s: s.added_at)
        
        assert symbols[0].symbol == "FIRST"
        assert symbols[1].symbol == "SECOND"


class TestMetadataExport:
    """Test metadata can be exported."""
    
    def test_metadata_dict_export(self):
        """Test metadata can be exported to dict."""
        symbol = SymbolSessionData(
            symbol="EXPORT",
            base_interval="1m",
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime(2025, 1, 2, 10, 30, 0)
        )
        
        # Create metadata dict
        metadata = {
            "symbol": symbol.symbol,
            "meets_requirements": symbol.meets_session_config_requirements,
            "added_by": symbol.added_by,
            "auto_provisioned": symbol.auto_provisioned,
            "upgraded": symbol.upgraded_from_adhoc,
            "added_at": symbol.added_at.isoformat()
        }
        
        assert metadata["symbol"] == "EXPORT"
        assert metadata["meets_requirements"] is True
        assert metadata["added_by"] == "config"
        assert metadata["auto_provisioned"] is False
        assert metadata["upgraded"] is False
        assert "2025-01-02" in metadata["added_at"]


class TestMetadataQuery:
    """Test querying symbols by metadata."""
    
    def test_filter_by_added_by(self):
        """Test filtering symbols by added_by field."""
        # Create symbols with different sources
        config_symbol = SymbolSessionData(
            symbol="AAPL",
            base_interval="1m",
            added_by="config",
            added_at=datetime.now()
        )
        
        scanner_symbol = SymbolSessionData(
            symbol="TSLA",
            base_interval="1m",
            added_by="scanner",
            added_at=datetime.now()
        )
        
        strategy_symbol = SymbolSessionData(
            symbol="NVDA",
            base_interval="1m",
            added_by="strategy",
            added_at=datetime.now()
        )
        
        # Collect in list for filtering
        all_symbols = [config_symbol, scanner_symbol, strategy_symbol]
        
        # Filter by source
        config_symbols = [s for s in all_symbols if s.added_by == "config"]
        scanner_symbols = [s for s in all_symbols if s.added_by == "scanner"]
        
        assert len(config_symbols) == 1
        assert config_symbols[0].symbol == "AAPL"
        assert len(scanner_symbols) == 1
        assert scanner_symbols[0].symbol == "TSLA"
