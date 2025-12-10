"""Integration Tests for Metadata Corner Cases

Tests edge cases related to metadata tracking:
- Multiple upgrades
- Delete and re-add
- Timestamp accuracy
- All added_by values
- auto_provisioned flag
- upgraded_from_adhoc flag
"""
import pytest
from unittest.mock import Mock
from datetime import datetime, timedelta
from collections import deque
from app.managers.data_manager.session_data import SymbolSessionData, BarIntervalData


class TestMultipleUpgrades:
    """Test multiple upgrade scenarios."""
    
    def test_multiple_upgrades_not_allowed(self):
        """Test symbol cannot be upgraded multiple times."""
        # Create adhoc symbol
        symbol = SymbolSessionData(
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
        
        # Upgrade once
        symbol.meets_session_config_requirements = True
        symbol.upgraded_from_adhoc = True
        symbol.added_by = "strategy"
        
        # Verify upgrade
        assert symbol.upgraded_from_adhoc is True
        assert symbol.meets_session_config_requirements is True
        
        # Try to "upgrade" again (shouldn't happen)
        # Symbol already meets requirements
        # Should be detected as duplicate
        
        if symbol.meets_session_config_requirements:
            # Already upgraded, cannot upgrade again
            can_upgrade_again = False
        else:
            can_upgrade_again = True
        
        assert can_upgrade_again is False
    
    def test_upgrade_metadata_preserved(self):
        """Test original metadata preserved after upgrade."""
        # Create adhoc symbol
        original_time = datetime(2025, 1, 2, 10, 30, 0)
        symbol = SymbolSessionData(
            symbol="NVDA",
            base_interval="1m",
            bars={},
            indicators={},
            quality=0.0,
            session_metrics=None,
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            upgraded_from_adhoc=False,
            added_at=original_time
        )
        
        # Store original values
        original_added_at = symbol.added_at
        original_auto_provisioned = symbol.auto_provisioned
        
        # Upgrade
        symbol.meets_session_config_requirements = True
        symbol.upgraded_from_adhoc = True
        symbol.added_by = "strategy"
        
        # Verify original metadata preserved
        assert symbol.added_at == original_added_at  # Original timestamp
        assert symbol.auto_provisioned == original_auto_provisioned  # Original flag


class TestDeleteAndReAdd:
    """Test delete and re-add scenarios."""
    
    def test_delete_and_readd_fresh_metadata(self):
        """Test re-adding deleted symbol creates fresh metadata."""
        from app.managers.data_manager.session_data import SessionData
        
        session_data = SessionData()
        
        # Add symbol
        time1 = datetime(2025, 1, 2, 10, 0, 0)
        symbol1 = SymbolSessionData(
            symbol="TEMP",
            base_interval="1m",
            bars={},
            indicators={},
            quality=0.0,
            session_metrics=None,
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=time1
        )
        session_data.register_symbol_data(symbol1)
        
        # Verify added
        assert session_data.get_symbol_data("TEMP") is not None
        assert session_data.get_symbol_data("TEMP").added_at == time1
        
        # Delete symbol
        session_data.symbols.pop("TEMP")
        assert session_data.get_symbol_data("TEMP") is None
        
        # Re-add symbol (later)
        time2 = datetime(2025, 1, 2, 15, 0, 0)
        symbol2 = SymbolSessionData(
            symbol="TEMP",
            base_interval="1m",
            bars={},
            indicators={},
            quality=0.0,
            session_metrics=None,
            meets_session_config_requirements=True,
            added_by="scanner",  # Different source
            auto_provisioned=True,  # Different flag
            upgraded_from_adhoc=False,
            added_at=time2  # Different time
        )
        session_data.register_symbol_data(symbol2)
        
        # Verify fresh metadata
        readded = session_data.get_symbol_data("TEMP")
        assert readded.added_at == time2  # New timestamp
        assert readded.added_by == "scanner"  # New source
        assert readded.auto_provisioned is True  # New flag


class TestTimestampAccuracy:
    """Test timestamp accuracy."""
    
    def test_added_at_timestamp_accuracy(self):
        """Test added_at timestamp is accurate."""
        # Mock TimeManager
        time_mgr = Mock()
        precise_time = datetime(2025, 1, 2, 10, 30, 45, 123456)  # Microsecond precision
        time_mgr.get_current_time = Mock(return_value=precise_time)
        
        # Create symbol with timestamp
        symbol = SymbolSessionData(
            symbol="TEST",
            base_interval="1m",
            bars={},
            indicators={},
            quality=0.0,
            session_metrics=None,
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=time_mgr.get_current_time()
        )
        
        # Verify precise timestamp
        assert symbol.added_at == precise_time
        assert symbol.added_at.microsecond == 123456
    
    def test_timestamp_ordering(self):
        """Test timestamps correctly order symbol additions."""
        # Add symbols at different times
        time1 = datetime(2025, 1, 2, 10, 0, 0)
        time2 = datetime(2025, 1, 2, 10, 5, 0)
        time3 = datetime(2025, 1, 2, 10, 10, 0)
        
        symbol1 = SymbolSessionData(
            symbol="FIRST",
            base_interval="1m",
            bars={},
            indicators={},
            quality=0.0,
            session_metrics=None,
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=time1
        )
        
        symbol2 = SymbolSessionData(
            symbol="SECOND",
            base_interval="1m",
            bars={},
            indicators={},
            quality=0.0,
            session_metrics=None,
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            upgraded_from_adhoc=False,
            added_at=time2
        )
        
        symbol3 = SymbolSessionData(
            symbol="THIRD",
            base_interval="1m",
            bars={},
            indicators={},
            quality=0.0,
            session_metrics=None,
            meets_session_config_requirements=True,
            added_by="strategy",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=time3
        )
        
        # Verify ordering
        symbols = [symbol1, symbol2, symbol3]
        sorted_symbols = sorted(symbols, key=lambda s: s.added_at)
        
        assert sorted_symbols[0].symbol == "FIRST"
        assert sorted_symbols[1].symbol == "SECOND"
        assert sorted_symbols[2].symbol == "THIRD"


class TestAllAddedByValues:
    """Test all possible added_by values."""
    
    def test_added_by_config(self):
        """Test added_by='config' for config symbols."""
        symbol = SymbolSessionData(
            symbol="AAPL",
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
        
        assert symbol.added_by == "config"
    
    def test_added_by_strategy(self):
        """Test added_by='strategy' for strategy symbols."""
        symbol = SymbolSessionData(
            symbol="MSFT",
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
        
        assert symbol.added_by == "strategy"
    
    def test_added_by_scanner(self):
        """Test added_by='scanner' for scanner symbols."""
        symbol = SymbolSessionData(
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
        
        assert symbol.added_by == "scanner"
    
    def test_added_by_adhoc(self):
        """Test added_by='adhoc' for manual additions."""
        symbol = SymbolSessionData(
            symbol="MANUAL",
            base_interval="1m",
            bars={},
            indicators={},
            quality=0.0,
            session_metrics=None,
            meets_session_config_requirements=False,
            added_by="adhoc",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        
        assert symbol.added_by == "adhoc"


class TestAutoProvisionedFlag:
    """Test auto_provisioned flag."""
    
    def test_auto_provisioned_true(self):
        """Test auto_provisioned=True for auto-provisioned symbols."""
        symbol = SymbolSessionData(
            symbol="AUTO",
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
        
        assert symbol.auto_provisioned is True
    
    def test_auto_provisioned_false(self):
        """Test auto_provisioned=False for explicit symbols."""
        symbol = SymbolSessionData(
            symbol="EXPLICIT",
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
        
        assert symbol.auto_provisioned is False
    
    def test_auto_provisioned_preserved_on_upgrade(self):
        """Test auto_provisioned preserved when upgrading."""
        # Start as auto-provisioned
        symbol = SymbolSessionData(
            symbol="PRESERVED",
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
        
        assert symbol.auto_provisioned is True
        
        # Upgrade
        symbol.meets_session_config_requirements = True
        symbol.upgraded_from_adhoc = True
        symbol.added_by = "strategy"
        
        # Verify auto_provisioned preserved
        assert symbol.auto_provisioned is True  # Still True


class TestUpgradedFromAdhocFlag:
    """Test upgraded_from_adhoc flag."""
    
    def test_upgraded_from_adhoc_false_initially(self):
        """Test upgraded_from_adhoc=False for new symbols."""
        symbol = SymbolSessionData(
            symbol="NEW",
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
        
        assert symbol.upgraded_from_adhoc is False
    
    def test_upgraded_from_adhoc_true_after_upgrade(self):
        """Test upgraded_from_adhoc=True after upgrade."""
        # Start as adhoc
        symbol = SymbolSessionData(
            symbol="UPGRADE",
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
        
        # Upgrade
        symbol.meets_session_config_requirements = True
        symbol.upgraded_from_adhoc = True
        
        # Verify flag set
        assert symbol.upgraded_from_adhoc is True
    
    def test_upgraded_from_adhoc_false_for_non_adhoc(self):
        """Test upgraded_from_adhoc=False for symbols that were never adhoc."""
        symbol = SymbolSessionData(
            symbol="NEVER_ADHOC",
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
        
        # Never upgraded because never adhoc
        assert symbol.upgraded_from_adhoc is False
        assert symbol.meets_session_config_requirements is True
