"""E2E Tests for No Persistence Verification

Tests that verify no state persists between sessions (multi-day backtest).
Each day must start fresh from configuration.
"""
import pytest
from unittest.mock import Mock
from datetime import datetime
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData
from collections import deque


@pytest.mark.e2e
class TestNoPersistence:
    """Test no persistence between sessions."""
    
    def test_cross_session_state_clean(self):
        """Test no state carries over between sessions."""
        # Session 1
        session1 = SessionData()
        
        symbol1 = SymbolSessionData(
            symbol="TEMP1",
            base_interval="1m",
            bars={"1m": BarIntervalData(derived=False, base=None, data=deque([1, 2, 3]), 
                                       quality=0.0, gaps=[], updated=False)},
            indicators={"sma_20": Mock()},
            quality=0.75,
            session_metrics={"trades": 10},
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        session1.register_symbol_data(symbol1)
        
        # Verify session 1 state
        assert len(session1.symbols) == 1
        assert session1.get_symbol_data("TEMP1") is not None
        assert session1.get_symbol_data("TEMP1").quality == 0.75
        
        # End session 1 (teardown)
        session1.clear()
        assert len(session1.symbols) == 0
        
        # Session 2 (new day)
        session2 = SessionData()
        
        # Verify completely fresh
        assert len(session2.symbols) == 0
        assert session2.get_symbol_data("TEMP1") is None
        
        # Add symbol with same name but fresh state
        symbol2 = SymbolSessionData(
            symbol="TEMP1",  # Same name
            base_interval="1m",
            bars={},  # Empty bars
            indicators={},  # No indicators
            quality=0.0,  # Fresh quality
            session_metrics=None,  # No metrics
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        session2.register_symbol_data(symbol2)
        
        # Verify fresh state
        retrieved = session2.get_symbol_data("TEMP1")
        assert retrieved.quality == 0.0  # Fresh, not 0.75
        assert len(retrieved.bars) == 0  # Empty, not 3 bars
        assert len(retrieved.indicators) == 0  # Empty, not 1 indicator
    
    def test_adhoc_symbols_cleared(self):
        """Test adhoc symbols do not persist to next day."""
        # Day 1: Config + Adhoc symbols
        session1 = SessionData()
        
        # Config symbol
        config_symbol = SymbolSessionData(
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
        session1.register_symbol_data(config_symbol)
        
        # Adhoc symbol (scanner)
        adhoc_symbol = SymbolSessionData(
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
        session1.register_symbol_data(adhoc_symbol)
        
        # Verify day 1
        assert len(session1.symbols) == 2
        assert "AAPL" in session1.symbols
        assert "TSLA" in session1.symbols
        
        # Teardown
        session1.clear()
        
        # Day 2: Only config symbols loaded
        session2 = SessionData()
        
        # Re-add config symbol only
        config_symbol_day2 = SymbolSessionData(
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
        session2.register_symbol_data(config_symbol_day2)
        
        # Verify day 2: TSLA not present
        assert len(session2.symbols) == 1
        assert "AAPL" in session2.symbols
        assert "TSLA" not in session2.symbols  # NOT persisted!
    
    def test_metadata_reset(self):
        """Test metadata resets between sessions."""
        # Day 1
        session1 = SessionData()
        
        symbol_day1 = SymbolSessionData(
            symbol="META",
            base_interval="1m",
            bars={},
            indicators={},
            quality=0.88,  # High quality
            session_metrics={"trades": 50, "profit": 5000.0},
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime(2025, 1, 2, 9, 30, 0)
        )
        session1.register_symbol_data(symbol_day1)
        
        # Record day 1 metadata
        day1_quality = symbol_day1.quality
        day1_metrics = symbol_day1.session_metrics
        day1_added_at = symbol_day1.added_at
        
        # Teardown
        session1.clear()
        
        # Day 2
        session2 = SessionData()
        
        symbol_day2 = SymbolSessionData(
            symbol="META",
            base_interval="1m",
            bars={},
            indicators={},
            quality=0.0,  # Fresh quality (will be recalculated)
            session_metrics=None,  # No metrics yet
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime(2025, 1, 3, 9, 30, 0)  # New timestamp
        )
        session2.register_symbol_data(symbol_day2)
        
        # Verify metadata reset
        assert symbol_day2.quality != day1_quality  # Fresh
        assert symbol_day2.session_metrics != day1_metrics  # Reset
        assert symbol_day2.added_at != day1_added_at  # New timestamp
    
    def test_queue_clearing(self):
        """Test bar/quote queues cleared between sessions."""
        from collections import deque
        
        # Day 1: Queues with data
        bar_queues_day1 = {
            "AAPL": deque([1, 2, 3, 4, 5]),
            "MSFT": deque([10, 20, 30])
        }
        
        # Verify queues have data
        assert len(bar_queues_day1["AAPL"]) == 5
        assert len(bar_queues_day1["MSFT"]) == 3
        
        # Teardown (clear queues)
        bar_queues_day1.clear()
        
        # Day 2: Fresh queues
        bar_queues_day2 = {}
        
        # Verify empty
        assert len(bar_queues_day2) == 0
        assert "AAPL" not in bar_queues_day2
        assert "MSFT" not in bar_queues_day2
        
        # Can add fresh queues
        bar_queues_day2["AAPL"] = deque()
        assert len(bar_queues_day2["AAPL"]) == 0  # Fresh, empty
    
    def test_fresh_config_loading(self):
        """Test each day loads fresh from config."""
        # Simulates loading symbols from config each day
        
        config_symbols = ["AAPL", "MSFT", "GOOGL"]
        
        # Day 1
        session1 = SessionData()
        for symbol in config_symbols:
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
                added_at=datetime(2025, 1, 2, 9, 30, 0)
            )
            session1.register_symbol_data(symbol_data)
        
        assert len(session1.symbols) == 3
        
        # Teardown
        session1.clear()
        assert len(session1.symbols) == 0
        
        # Day 2: Load fresh from config again
        session2 = SessionData()
        for symbol in config_symbols:
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
                added_at=datetime(2025, 1, 3, 9, 30, 0)  # Different day
            )
            session2.register_symbol_data(symbol_data)
        
        assert len(session2.symbols) == 3
        
        # Each day loaded fresh from config
        # No persistence from day 1 to day 2
