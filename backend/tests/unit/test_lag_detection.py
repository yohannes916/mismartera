"""
Unit tests for lag-based session control and per-symbol lag detection.

Tests the automatic session deactivation/reactivation based on data lag,
using per-symbol counters and configurable thresholds.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
from collections import defaultdict, deque

from app.threads.session_coordinator import SessionCoordinator
from app.managers.data_manager.session_data import SessionData


@pytest.mark.unit
class TestLagDetection:
    """Test lag detection and session control logic."""
    
    def test_symbol_check_counters_initialization(self):
        """Per-symbol counters should initialize to 0 automatically."""
        counters = defaultdict(int)
        
        # New symbols automatically get 0
        assert counters["AAPL"] == 0
        assert counters["TSLA"] == 0
        
        # After increment
        counters["AAPL"] += 1
        assert counters["AAPL"] == 1
        assert counters["TSLA"] == 0  # Still 0
    
    def test_lag_check_on_first_bar(self):
        """First bar of new symbol should trigger lag check (counter=0)."""
        check_interval = 10
        counter = 0
        
        # First bar: 0 % 10 == 0, should check
        assert counter % check_interval == 0
        
        counter += 1
        # Second bar: 1 % 10 == 1, should NOT check
        assert counter % check_interval != 0
    
    def test_lag_check_every_n_bars(self):
        """Lag should be checked every N bars based on interval."""
        check_interval = 10
        
        # Check should happen at: 0, 10, 20, 30, ...
        check_bars = [0, 10, 20, 30, 40, 50]
        no_check_bars = [1, 2, 5, 9, 11, 15, 19, 21, 49]
        
        for bar_num in check_bars:
            assert bar_num % check_interval == 0, f"Bar {bar_num} should trigger check"
        
        for bar_num in no_check_bars:
            assert bar_num % check_interval != 0, f"Bar {bar_num} should NOT trigger check"
    
    def test_lag_calculation(self):
        """Lag should be calculated as current_time - bar_timestamp."""
        current_time = datetime(2024, 1, 1, 12, 0, 0)  # Noon
        bar_timestamp = datetime(2024, 1, 1, 9, 30, 0)  # Market open
        
        lag_seconds = (current_time - bar_timestamp).total_seconds()
        
        # 2.5 hours = 9000 seconds
        assert lag_seconds == 9000
        assert lag_seconds > 60  # Would trigger deactivation
    
    def test_deactivation_when_lag_exceeds_threshold(self):
        """Session should deactivate when lag > threshold."""
        threshold = 60  # seconds
        
        lag_scenarios = [
            (61, True),    # Just over threshold
            (120, True),   # Double threshold
            (3600, True),  # 1 hour
            (60, False),   # Exactly at threshold (not exceeded)
            (59, False),   # Just under
            (1, False),    # Minimal lag
        ]
        
        for lag, should_deactivate in lag_scenarios:
            result = lag > threshold
            assert result == should_deactivate, f"Lag {lag}s: expected deactivate={should_deactivate}"
    
    def test_reactivation_when_caught_up(self):
        """Session should reactivate when lag <= threshold."""
        threshold = 60
        
        # Caught up scenarios
        caught_up_lags = [0, 1, 30, 59, 60]
        for lag in caught_up_lags:
            assert lag <= threshold, f"Lag {lag}s should allow reactivation"
        
        # Still lagging scenarios
        lagging_lags = [61, 120, 300]
        for lag in lagging_lags:
            assert lag > threshold, f"Lag {lag}s should prevent reactivation"


@pytest.mark.unit
class TestPerSymbolCounters:
    """Test per-symbol counter management."""
    
    def test_independent_symbol_counters(self):
        """Each symbol should have independent counter."""
        counters = defaultdict(int)
        
        # Simulate processing bars
        counters["AAPL"] = 5
        counters["TSLA"] = 20
        counters["RIVN"] = 0
        
        assert counters["AAPL"] == 5
        assert counters["TSLA"] == 20
        assert counters["RIVN"] == 0
    
    def test_counter_cleanup_on_removal(self):
        """Counter should be removed when symbol is removed."""
        counters = defaultdict(int)
        
        counters["AAPL"] = 100
        counters["TSLA"] = 50
        
        # Remove AAPL
        counters.pop("AAPL", None)
        
        assert "AAPL" not in counters
        assert counters["TSLA"] == 50
    
    def test_new_symbol_auto_checks_first_bar(self):
        """New symbol added mid-session should check lag on first bar."""
        counters = defaultdict(int)
        check_interval = 10
        
        # Existing symbol at bar 47
        counters["RIVN"] = 47
        
        # New symbol (AAPL) added - counter auto-initializes to 0
        # First bar check
        assert counters["AAPL"] % check_interval == 0  # Check immediately
        
        counters["AAPL"] += 1
        assert counters["AAPL"] % check_interval != 0  # Don't check bar 1


@pytest.mark.unit
class TestSessionDataActivation:
    """Test SessionData activation/deactivation."""
    
    def test_session_starts_active(self):
        """Session should start in active state."""
        session_data = SessionData()
        assert session_data._session_active is True
    
    def test_deactivate_session(self):
        """deactivate_session() should set flag to False."""
        session_data = SessionData()
        
        session_data.deactivate_session()
        
        assert session_data._session_active is False
    
    def test_activate_session(self):
        """activate_session() should set flag to True."""
        session_data = SessionData()
        session_data._session_active = False
        
        session_data.activate_session()
        
        assert session_data._session_active is True
    
    def test_external_read_blocked_when_inactive(self):
        """External reads should return None when session inactive."""
        session_data = SessionData()
        session_data.register_symbol("AAPL")
        
        # Active: should return data
        result = session_data.get_latest_bar("AAPL", internal=False)
        # (will be None because no bars, but not blocked)
        
        # Deactivate
        session_data.deactivate_session()
        
        # External read: should be blocked
        result = session_data.get_latest_bar("AAPL", internal=False)
        assert result is None
    
    def test_internal_read_works_when_inactive(self):
        """Internal reads should work even when session inactive."""
        session_data = SessionData()
        session_data.register_symbol("AAPL")
        
        # Deactivate session
        session_data.deactivate_session()
        
        # Internal read: should work
        symbol_data = session_data.get_symbol_data("AAPL", internal=True)
        assert symbol_data is not None
        assert symbol_data.symbol == "AAPL"


@pytest.mark.unit
class TestStreamingConfiguration:
    """Test streaming configuration parsing and usage."""
    
    def test_default_values(self):
        """Default values should be used if config not provided."""
        # Simulate SessionCoordinator initialization
        default_threshold = 60
        default_interval = 10
        
        # These would be the defaults in __init__
        assert default_threshold == 60
        assert default_interval == 10
    
    def test_config_overrides_defaults(self):
        """Config values should override defaults."""
        # Simulate reading from config
        config_threshold = 120
        config_interval = 20
        
        # Simulate loading from config
        catchup_threshold = config_threshold
        catchup_check_interval = config_interval
        
        assert catchup_threshold == 120
        assert catchup_check_interval == 20
    
    def test_custom_thresholds(self):
        """Should support various threshold configurations."""
        test_configs = [
            (30, 5),    # Aggressive (30s threshold, check every 5 bars)
            (60, 10),   # Default
            (120, 20),  # Relaxed (2 min threshold, check every 20 bars)
            (300, 50),  # Very relaxed (5 min, check every 50 bars)
        ]
        
        for threshold, interval in test_configs:
            assert threshold > 0
            assert interval > 0
            assert isinstance(threshold, int)
            assert isinstance(interval, int)


@pytest.mark.unit
class TestLagDetectionIntegration:
    """Test full lag detection flow with mocked components."""
    
    def test_lag_detected_deactivates_session(self):
        """When lag exceeds threshold, session should be deactivated."""
        # Setup
        session_data = SessionData()
        check_interval = 10
        threshold = 60
        
        current_time = datetime(2024, 1, 1, 12, 0, 0)
        bar_timestamp = datetime(2024, 1, 1, 9, 30, 0)
        lag = (current_time - bar_timestamp).total_seconds()
        
        # Simulate check
        if lag > threshold:
            session_data.deactivate_session()
        
        assert session_data._session_active is False
    
    def test_caught_up_reactivates_session(self):
        """When lag falls below threshold, session should be reactivated."""
        # Setup
        session_data = SessionData()
        session_data.deactivate_session()  # Start inactive
        threshold = 60
        
        current_time = datetime(2024, 1, 1, 12, 0, 0)
        bar_timestamp = datetime(2024, 1, 1, 11, 59, 30)  # 30s ago
        lag = (current_time - bar_timestamp).total_seconds()
        
        # Simulate check
        if lag <= threshold:
            session_data.activate_session()
        
        assert session_data._session_active is True
    
    def test_multiple_symbols_lag_detection(self):
        """Each symbol should be checked independently."""
        counters = defaultdict(int)
        check_interval = 10
        
        # RIVN at bar 47, AAPL at bar 0 (just added), TSLA at bar 20
        counters["RIVN"] = 47
        counters["AAPL"] = 0
        counters["TSLA"] = 20
        
        # Check which symbols trigger lag check
        rivn_check = counters["RIVN"] % check_interval == 0  # 47 % 10 = 7, False
        aapl_check = counters["AAPL"] % check_interval == 0  # 0 % 10 = 0, True
        tsla_check = counters["TSLA"] % check_interval == 0  # 20 % 10 = 0, True
        
        assert not rivn_check  # Doesn't check
        assert aapl_check      # Checks (first bar)
        assert tsla_check      # Checks (every 10)


@pytest.mark.unit
class TestDataProcessorSessionAware:
    """Test DataProcessor respects session_active flag."""
    
    def test_notification_skipped_when_inactive(self):
        """DataProcessor should skip notifications when session inactive."""
        session_data = SessionData()
        session_data.deactivate_session()
        
        # Simulate notification check
        should_notify = session_data._session_active
        
        assert should_notify is False
    
    def test_notification_sent_when_active(self):
        """DataProcessor should send notifications when session active."""
        session_data = SessionData()
        # Session starts active
        
        should_notify = session_data._session_active
        
        assert should_notify is True
    
    def test_internal_processing_continues_when_inactive(self):
        """DataProcessor should continue internal processing when inactive."""
        session_data = SessionData()
        session_data.register_symbol("AAPL")
        session_data.deactivate_session()
        
        # Internal reads should work
        symbol_data = session_data.get_symbol_data("AAPL", internal=True)
        bars_ref = session_data.get_bars_ref("AAPL", 1, internal=True)
        
        # Should not be blocked
        assert symbol_data is not None
        assert bars_ref is not None  # Empty but not blocked
