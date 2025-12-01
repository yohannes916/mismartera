"""Integration Tests for Quality Calculation Flow

Tests the complete quality calculation flow across components:
1. SessionCoordinator calculating historical quality
2. DataQualityManager calculating current session quality
3. Both using shared quality_helpers
4. Both querying TimeManager for market hours
5. Consistency between components
"""
import pytest
from datetime import datetime, date, time
from unittest.mock import Mock, MagicMock, patch, call
from zoneinfo import ZoneInfo

from app.threads.quality.quality_helpers import (
    parse_interval_to_minutes,
    get_regular_trading_hours,
    calculate_quality_for_current_session,
    calculate_quality_for_historical_date
)


# ============================================================================
# Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_trading_session_regular():
    """Mock regular trading session (9:30 AM - 4:00 PM)."""
    session = Mock()
    session.date = date(2025, 12, 1)
    session.regular_open = time(9, 30)
    session.regular_close = time(16, 0)
    session.is_holiday = False
    session.is_early_close = False
    session.timezone = "America/New_York"
    
    tz = ZoneInfo("America/New_York")
    session.get_regular_open_datetime.return_value = datetime(
        2025, 12, 1, 9, 30, tzinfo=tz
    )
    session.get_regular_close_datetime.return_value = datetime(
        2025, 12, 1, 16, 0, tzinfo=tz
    )
    
    return session


@pytest.fixture
def mock_trading_session_early_close():
    """Mock early close trading session (9:30 AM - 1:00 PM)."""
    session = Mock()
    session.date = date(2024, 11, 28)
    session.regular_open = time(9, 30)
    session.regular_close = time(13, 0)
    session.is_holiday = False
    session.is_early_close = True
    session.timezone = "America/New_York"
    
    tz = ZoneInfo("America/New_York")
    session.get_regular_open_datetime.return_value = datetime(
        2024, 11, 28, 9, 30, tzinfo=tz
    )
    session.get_regular_close_datetime.return_value = datetime(
        2024, 11, 28, 13, 0, tzinfo=tz
    )
    
    return session


@pytest.fixture
def mock_trading_session_holiday():
    """Mock holiday (market closed)."""
    session = Mock()
    session.date = date(2024, 12, 25)
    session.regular_open = None
    session.regular_close = None
    session.is_holiday = True
    session.is_early_close = False
    session.timezone = "America/New_York"
    
    session.get_regular_open_datetime.return_value = None
    session.get_regular_close_datetime.return_value = None
    
    return session


@pytest.fixture
def mock_time_manager(
    mock_trading_session_regular,
    mock_trading_session_early_close,
    mock_trading_session_holiday
):
    """Mock TimeManager with multiple trading sessions."""
    time_mgr = Mock()
    
    def get_session(db_session, target_date, exchange="NYSE"):
        if target_date == date(2025, 12, 1):
            return mock_trading_session_regular
        elif target_date == date(2024, 11, 28):
            return mock_trading_session_early_close
        elif target_date == date(2024, 12, 25):
            return mock_trading_session_holiday
        else:
            # Default regular day
            session = Mock()
            session.date = target_date
            session.regular_open = time(9, 30)
            session.regular_close = time(16, 0)
            session.is_holiday = False
            session.is_early_close = False
            session.timezone = "America/New_York"
            
            tz = ZoneInfo("America/New_York")
            session.get_regular_open_datetime.return_value = datetime.combine(
                target_date, time(9, 30), tzinfo=tz
            )
            session.get_regular_close_datetime.return_value = datetime.combine(
                target_date, time(16, 0), tzinfo=tz
            )
            
            return session
    
    # Use Mock with side_effect to make it trackable
    time_mgr.get_trading_session = Mock(side_effect=get_session)
    return time_mgr


# ============================================================================
# Integration Test: Regular Trading Day
# ============================================================================

class TestRegularTradingDay:
    """Test quality calculation for regular trading day."""
    
    def test_historical_quality_100_percent(self, mock_time_manager):
        """Test historical quality with all bars present."""
        db_session = Mock()
        
        quality = calculate_quality_for_historical_date(
            mock_time_manager,
            db_session,
            "AAPL",
            "1m",
            date(2025, 12, 1),
            actual_bars=390
        )
        
        assert quality == 100.0
    
    def test_current_session_quality_midday(self, mock_time_manager):
        """Test current session quality at midday."""
        db_session = Mock()
        current_time = datetime(2025, 12, 1, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        
        # From 9:30 to 12:00 = 150 minutes, all bars present
        quality = calculate_quality_for_current_session(
            mock_time_manager,
            db_session,
            "AAPL",
            "1m",
            current_time,
            actual_bars=150
        )
        
        assert quality == 100.0
    
    def test_current_session_quality_after_close(self, mock_time_manager):
        """Test current session quality after market close (caps at close)."""
        db_session = Mock()
        current_time = datetime(2025, 12, 1, 17, 0, tzinfo=ZoneInfo("America/New_York"))  # 5 PM
        
        # Should cap at 4 PM, so 390 bars expected (not 450)
        quality = calculate_quality_for_current_session(
            mock_time_manager,
            db_session,
            "AAPL",
            "1m",
            current_time,
            actual_bars=390
        )
        
        assert quality == 100.0
    
    def test_consistency_between_components(self, mock_time_manager):
        """Test both components calculate same quality for end-of-day."""
        db_session = Mock()
        target_date = date(2025, 12, 1)
        
        # Historical quality (full day)
        hist_quality = calculate_quality_for_historical_date(
            mock_time_manager,
            db_session,
            "AAPL",
            "1m",
            target_date,
            actual_bars=380
        )
        
        # Current session quality at end of day
        current_time = datetime(2025, 12, 1, 16, 0, tzinfo=ZoneInfo("America/New_York"))
        current_quality = calculate_quality_for_current_session(
            mock_time_manager,
            db_session,
            "AAPL",
            "1m",
            current_time,
            actual_bars=380
        )
        
        # Both should calculate same quality
        assert hist_quality == current_quality


# ============================================================================
# Integration Test: Early Close Day
# ============================================================================

class TestEarlyCloseDay:
    """Test quality calculation for early close day (Thanksgiving)."""
    
    def test_historical_quality_early_close(self, mock_time_manager):
        """Test historical quality on early close day."""
        db_session = Mock()
        
        # Early close: 210 minutes (9:30 to 1:00)
        quality = calculate_quality_for_historical_date(
            mock_time_manager,
            db_session,
            "AAPL",
            "1m",
            date(2024, 11, 28),
            actual_bars=210
        )
        
        assert quality == 100.0
    
    def test_current_session_quality_early_close(self, mock_time_manager):
        """Test current session quality at early close time."""
        db_session = Mock()
        current_time = datetime(2024, 11, 28, 13, 0, tzinfo=ZoneInfo("America/New_York"))
        
        # Early close at 1 PM: 210 minutes expected
        quality = calculate_quality_for_current_session(
            mock_time_manager,
            db_session,
            "AAPL",
            "1m",
            current_time,
            actual_bars=210
        )
        
        assert quality == 100.0
    
    def test_early_close_not_confused_with_regular(self, mock_time_manager):
        """Test early close doesn't use 390 minute assumption."""
        db_session = Mock()
        
        # If we incorrectly assumed 390 minutes, 210 bars would be 53.8% quality
        # With correct 210 minute expectation, it should be 100%
        quality = calculate_quality_for_historical_date(
            mock_time_manager,
            db_session,
            "AAPL",
            "1m",
            date(2024, 11, 28),
            actual_bars=210
        )
        
        # Correct: 210/210 = 100%
        # Wrong:   210/390 = 53.8%
        assert quality == 100.0


# ============================================================================
# Integration Test: Holiday
# ============================================================================

class TestHoliday:
    """Test quality calculation for holidays."""
    
    def test_historical_quality_holiday_returns_none(self, mock_time_manager):
        """Test historical quality on holiday returns None."""
        db_session = Mock()
        
        quality = calculate_quality_for_historical_date(
            mock_time_manager,
            db_session,
            "AAPL",
            "1m",
            date(2024, 12, 25),
            actual_bars=0
        )
        
        assert quality is None
    
    def test_current_session_quality_holiday_returns_none(self, mock_time_manager):
        """Test current session quality on holiday returns None."""
        db_session = Mock()
        current_time = datetime(2024, 12, 25, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        
        quality = calculate_quality_for_current_session(
            mock_time_manager,
            db_session,
            "AAPL",
            "1m",
            current_time,
            actual_bars=0
        )
        
        assert quality is None


# ============================================================================
# Integration Test: Multiple Intervals
# ============================================================================

class TestMultipleIntervals:
    """Test quality calculation across different bar intervals."""
    
    def test_one_minute_bars(self, mock_time_manager):
        """Test 1-minute bars."""
        db_session = Mock()
        
        quality = calculate_quality_for_historical_date(
            mock_time_manager,
            db_session,
            "AAPL",
            "1m",
            date(2025, 12, 1),
            actual_bars=390
        )
        
        assert quality == 100.0
    
    def test_five_minute_bars(self, mock_time_manager):
        """Test 5-minute bars (390 minutes / 5 = 78 bars)."""
        db_session = Mock()
        
        quality = calculate_quality_for_historical_date(
            mock_time_manager,
            db_session,
            "AAPL",
            "5m",
            date(2025, 12, 1),
            actual_bars=78
        )
        
        assert quality == 100.0
    
    def test_fifteen_minute_bars(self, mock_time_manager):
        """Test 15-minute bars (390 minutes / 15 = 26 bars)."""
        db_session = Mock()
        
        quality = calculate_quality_for_historical_date(
            mock_time_manager,
            db_session,
            "AAPL",
            "15m",
            date(2025, 12, 1),
            actual_bars=26
        )
        
        assert quality == 100.0
    
    def test_daily_bars(self, mock_time_manager):
        """Test daily bars (1 bar per day)."""
        db_session = Mock()
        
        quality = calculate_quality_for_historical_date(
            mock_time_manager,
            db_session,
            "AAPL",
            "1d",
            date(2025, 12, 1),
            actual_bars=1
        )
        
        assert quality == 100.0
    
    def test_daily_bars_early_close(self, mock_time_manager):
        """Test daily bars on early close day."""
        db_session = Mock()
        
        # Early close day should still be 1 daily bar
        quality = calculate_quality_for_historical_date(
            mock_time_manager,
            db_session,
            "AAPL",
            "1d",
            date(2024, 11, 28),
            actual_bars=1
        )
        
        assert quality == 100.0


# ============================================================================
# Integration Test: TimeManager Dependency
# ============================================================================

class TestTimeManagerDependency:
    """Test that quality calculation correctly depends on TimeManager."""
    
    def test_time_manager_called_for_each_date(self, mock_time_manager):
        """Test TimeManager.get_trading_session called for each date."""
        db_session = Mock()
        
        # Calculate quality for 3 different dates
        dates = [
            date(2025, 12, 1),
            date(2024, 11, 28),
            date(2024, 12, 25)
        ]
        
        for d in dates:
            calculate_quality_for_historical_date(
                mock_time_manager,
                db_session,
                "AAPL",
                "1m",
                d,
                actual_bars=390
            )
        
        # TimeManager should have been called (internal implementation may call multiple times)
        # Important: it's being called, not hardcoded
        assert mock_time_manager.get_trading_session.call_count >= len(dates)
        
        # Verify it was called with each date
        call_dates = [call[0][1] for call in mock_time_manager.get_trading_session.call_args_list]
        for d in dates:
            assert d in call_dates, f"Date {d} not queried from TimeManager"
    
    def test_never_uses_hardcoded_hours(self, mock_time_manager):
        """Test that no hardcoded hours are used."""
        db_session = Mock()
        
        # Use a non-standard day to ensure it's querying TimeManager
        target_date = date(2025, 6, 15)
        
        quality = calculate_quality_for_historical_date(
            mock_time_manager,
            db_session,
            "AAPL",
            "1m",
            target_date,
            actual_bars=390
        )
        
        # Verify TimeManager was called
        mock_time_manager.get_trading_session.assert_called()
        
        # Quality should be 100% (our mock returns regular hours)
        assert quality == 100.0


# ============================================================================
# Integration Test: Gap Scenarios
# ============================================================================

class TestGapScenarios:
    """Test quality calculation with various gap scenarios."""
    
    def test_small_gap_reduces_quality(self, mock_time_manager):
        """Test small gap reduces quality proportionally."""
        db_session = Mock()
        
        # Missing 10 bars out of 390
        quality = calculate_quality_for_historical_date(
            mock_time_manager,
            db_session,
            "AAPL",
            "1m",
            date(2025, 12, 1),
            actual_bars=380
        )
        
        # 380/390 = 97.44%
        assert quality == pytest.approx(97.44, rel=0.01)
    
    def test_large_gap_significant_reduction(self, mock_time_manager):
        """Test large gap significantly reduces quality."""
        db_session = Mock()
        
        # Missing 100 bars out of 390
        quality = calculate_quality_for_historical_date(
            mock_time_manager,
            db_session,
            "AAPL",
            "1m",
            date(2025, 12, 1),
            actual_bars=290
        )
        
        # 290/390 = 74.36%
        assert quality == pytest.approx(74.36, rel=0.01)
    
    def test_no_bars_zero_quality(self, mock_time_manager):
        """Test no bars results in 0% quality."""
        db_session = Mock()
        
        quality = calculate_quality_for_historical_date(
            mock_time_manager,
            db_session,
            "AAPL",
            "1m",
            date(2025, 12, 1),
            actual_bars=0
        )
        
        assert quality == 0.0


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
