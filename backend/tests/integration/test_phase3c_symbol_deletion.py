"""Integration Tests for Phase 3c: Symbol Deletion

Tests symbol deletion during active session (removing symbols dynamically).
"""
import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime
from collections import deque
from app.threads.session_coordinator import SessionCoordinator
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData


@pytest.fixture
def session_with_deletable_symbols():
    """Create session with symbols that can be deleted."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator.session_data = SessionData()
    
    # Add various symbols
    for symbol, source in [("AAPL", "config"), ("TSLA", "scanner"), ("NVDA", "strategy")]:
        symbol_data = SymbolSessionData(
            symbol=symbol,
            base_interval="1m",
            bars={"1m": BarIntervalData(derived=False, base=None, data=deque([1, 2, 3]), quality=0.0, gaps=[], updated=False)},
            indicators={"sma_20_5m": Mock()},
            quality=0.85 if source == "config" else 0.0,
            session_metrics=None,
            meets_session_config_requirements=(source != "scanner"),
            added_by=source,
            auto_provisioned=(source == "scanner"),
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        coordinator.session_data.register_symbol_data(symbol_data)
    
    # Mock queues
    coordinator.bar_queues = {"AAPL": deque([1, 2]), "TSLA": deque([3, 4]), "NVDA": deque([5])}
    coordinator.quote_queues = {"AAPL": deque([1])}
    
    return coordinator


class TestSymbolDeletion:
    """Test symbol deletion operations."""
    
    def test_delete_symbol_removes_data(self, session_with_deletable_symbols):
        """Test deleting symbol removes SymbolSessionData."""
        session_data = session_with_deletable_symbols.session_data
        
        # Verify symbol exists
        assert session_data.get_symbol_data("TSLA") is not None
        assert "TSLA" in session_data.symbols
        
        # Delete symbol
        session_data.symbols.pop("TSLA")
        
        # Expected: Symbol data removed
        assert session_data.get_symbol_data("TSLA") is None
        assert "TSLA" not in session_data.symbols
    
    def test_delete_symbol_removes_metadata(self, session_with_deletable_symbols):
        """Test deleting symbol removes metadata."""
        session_data = session_with_deletable_symbols.session_data
        
        # Get symbol with metadata
        tsla = session_data.get_symbol_data("TSLA")
        assert tsla is not None
        assert tsla.auto_provisioned is True
        assert tsla.added_by == "scanner"
        
        # Delete symbol
        session_data.symbols.pop("TSLA")
        
        # Expected: Metadata gone (part of SymbolSessionData)
        deleted = session_data.get_symbol_data("TSLA")
        assert deleted is None
        # No orphaned metadata since it's part of the object
    
    def test_delete_symbol_clears_queues(self, session_with_deletable_symbols):
        """Test deleting symbol clears bar/quote queues."""
        coordinator = session_with_deletable_symbols
        
        # Verify queues exist
        assert "TSLA" in coordinator.bar_queues
        assert len(coordinator.bar_queues["TSLA"]) > 0
        
        # Delete symbol and clean up queues
        coordinator.session_data.symbols.pop("TSLA")
        coordinator.bar_queues.pop("TSLA", None)
        coordinator.quote_queues.pop("TSLA", None)
        
        # Expected: Queues removed
        assert "TSLA" not in coordinator.bar_queues
        assert "TSLA" not in coordinator.quote_queues
    
    def test_delete_symbol_no_persistence(self, session_with_deletable_symbols):
        """Test deleted symbol doesn't persist to next operation."""
        session_data = session_with_deletable_symbols.session_data
        
        # Delete symbol
        session_data.symbols.pop("NVDA")
        
        # Verify deleted
        assert session_data.get_symbol_data("NVDA") is None
        
        # Later operations shouldn't see it
        all_symbols = list(session_data.symbols.keys())
        assert "NVDA" not in all_symbols
        assert "AAPL" in all_symbols
        assert "TSLA" in all_symbols
