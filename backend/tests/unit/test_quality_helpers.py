"""Unit Tests for Quality Calculation Helpers

Tests all quality calculation functions to ensure:
1. Interval parsing handles all types (1s, 1m, 5m, 1d, etc.)
2. Market hours queried from TimeManager (not hardcoded)
3. Early closes and holidays handled correctly
4. Close time capping works properly
5. Quality calculations are accurate
"""
import pytest
from datetime import datetime, date, time
from unittest.mock import Mock, MagicMock, patch
from zoneinfo import ZoneInfo

from app.threads.quality.quality_helpers import (
    parse_interval_to_minutes,
    get_regular_trading_hours,
    calculate_expected_bars,
    calculate_quality_percentage,
    calculate_quality_for_current_session,
    calculate_quality_for_historical_date
)


# ============================================================================
# Mock Helpers
# ============================================================================

def mock_trading_session(
    target_date: date,
    regular_open: time = time(9, 30),
    regular_close: time = time(16, 0),
    is_holiday: bool = False,
    is_early_close: bool = False,
    timezone: str = "America/New_York"
):
    """Create a mock TradingSession object."""
    session = Mock()
    session.date = target_date
    session.regular_open = regular_open
    session.regular_close = regular_close
    session.is_holiday = is_holiday
    session.is_early_close = is_early_close
    session.timezone = timezone
    
    # Mock the datetime methods
    if regular_open and regular_close:
        tz = ZoneInfo(timezone)
        session.get_regular_open_datetime.return_value = datetime.combine(
            target_date, regular_open, tzinfo=tz
        )
        session.get_regular_close_datetime.return_value = datetime.combine(
            target_date, regular_close, tzinfo=tz
        )
    else:
        session.get_regular_open_datetime.return_value = None
        session.get_regular_close_datetime.return_value = None
    
    return session


def mock_time_manager(get_trading_session_fn=None):
    """Create a mock TimeManager."""
    time_mgr = Mock()
    
    if get_trading_session_fn:
        time_mgr.get_trading_session = get_trading_session_fn
    else:
        # Default: regular trading day
        def default_get_session(db_session, target_date, exchange="NYSE"):
            return mock_trading_session(target_date)
        time_mgr.get_trading_session = default_get_session
    
    return time_mgr


# ============================================================================
# Test parse_interval_to_minutes()
# ============================================================================

class TestParseIntervalToMinutes:
    """Test interval parsing for all supported formats."""
    
    def test_minute_intervals(self):
        """Test minute intervals: 1m, 5m, 15m, etc."""
        assert parse_interval_to_minutes("1m") == 1.0
        assert parse_interval_to_minutes("5m") == 5.0
        assert parse_interval_to_minutes("15m") == 15.0
        assert parse_interval_to_minutes("30m") == 30.0
        assert parse_interval_to_minutes("60m") == 60.0
    
    def test_second_intervals(self):
        """Test second intervals: 1s, 5s, 30s (fractional minutes)."""
        assert parse_interval_to_minutes("1s") == pytest.approx(1/60, rel=1e-6)
        assert parse_interval_to_minutes("5s") == pytest.approx(5/60, rel=1e-6)
        assert parse_interval_to_minutes("30s") == pytest.approx(30/60, rel=1e-6)
        assert parse_interval_to_minutes("60s") == pytest.approx(1.0, rel=1e-6)
    
    def test_hour_intervals(self):
        """Test hour intervals: 1h, 2h, 4h."""
        assert parse_interval_to_minutes("1h") == 60.0
        assert parse_interval_to_minutes("2h") == 120.0
        assert parse_interval_to_minutes("4h") == 240.0
    
    def test_daily_interval_regular_day(self):
        """Test 1d interval with regular trading day (390 minutes)."""
        session = mock_trading_session(
            date(2025, 12, 1),
            regular_open=time(9, 30),
            regular_close=time(16, 0)
        )
        
        result = parse_interval_to_minutes("1d", session)
        assert result == 390.0  # 6.5 hours
    
    def test_daily_interval_early_close(self):
        """Test 1d interval with early close (210 minutes)."""
        session = mock_trading_session(
            date(2024, 11, 28),  # Thanksgiving half-day
            regular_open=time(9, 30),
            regular_close=time(13, 0),  # 1:00 PM close
            is_early_close=True
        )
        
        result = parse_interval_to_minutes("1d", session)
        assert result == 210.0  # 3.5 hours
    
    def test_daily_interval_holiday(self):
        """Test 1d interval with holiday (0 minutes)."""
        session = mock_trading_session(
            date(2024, 12, 25),  # Christmas
            is_holiday=True
        )
        
        result = parse_interval_to_minutes("1d", session)
        assert result == 0.0
    
    def test_daily_interval_without_session(self):
        """Test 1d interval without trading session (error)."""
        result = parse_interval_to_minutes("1d", None)
        assert result is None
    
    def test_integer_interval(self):
        """Test integer interval (already in minutes)."""
        assert parse_interval_to_minutes(5) == 5.0
        assert parse_interval_to_minutes(15) == 15.0
    
    def test_invalid_interval(self):
        """Test invalid interval formats."""
        assert parse_interval_to_minutes("invalid") is None
        assert parse_interval_to_minutes("") is None
        assert parse_interval_to_minutes("xyz") is None


# ============================================================================
# Test get_regular_trading_hours()
# ============================================================================

class TestGetRegularTradingHours:
    """Test retrieval of regular trading hours from TimeManager."""
    
    def test_regular_trading_day(self):
        """Test regular trading day returns correct hours."""
        target_date = date(2025, 12, 1)
        time_mgr = mock_time_manager()
        db_session = Mock()
        
        open_dt, close_dt = get_regular_trading_hours(
            time_mgr,
            db_session,
            target_date
        )
        
        assert open_dt.time() == time(9, 30)
        assert close_dt.time() == time(16, 0)
        assert open_dt.date() == target_date
        assert close_dt.date() == target_date
    
    def test_early_close_day(self):
        """Test early close day returns correct hours."""
        target_date = date(2024, 11, 28)
        
        def get_session(db, dt, exchange="NYSE"):
            return mock_trading_session(
                dt,
                regular_open=time(9, 30),
                regular_close=time(13, 0),
                is_early_close=True
            )
        
        time_mgr = mock_time_manager(get_session)
        db_session = Mock()
        
        open_dt, close_dt = get_regular_trading_hours(
            time_mgr,
            db_session,
            target_date
        )
        
        assert open_dt.time() == time(9, 30)
        assert close_dt.time() == time(13, 0)
    
    def test_holiday_returns_none(self):
        """Test holiday returns None."""
        target_date = date(2024, 12, 25)
        
        def get_session(db, dt, exchange="NYSE"):
            return mock_trading_session(dt, is_holiday=True)
        
        time_mgr = mock_time_manager(get_session)
        db_session = Mock()
        
        result = get_regular_trading_hours(
            time_mgr,
            db_session,
            target_date
        )
        
        assert result is None
    
    def test_no_trading_session_returns_none(self):
        """Test no trading session returns None."""
        target_date = date(2025, 12, 1)
        
        def get_session(db, dt, exchange="NYSE"):
            return None
        
        time_mgr = mock_time_manager(get_session)
        db_session = Mock()
        
        result = get_regular_trading_hours(
            time_mgr,
            db_session,
            target_date
        )
        
        assert result is None


# ============================================================================
# Test calculate_expected_bars()
# ============================================================================

class TestCalculateExpectedBars:
    """Test expected bar calculations."""
    
    def test_one_minute_interval(self):
        """Test 1-minute bars for 1 hour."""
        start = datetime(2025, 12, 1, 9, 30)
        end = datetime(2025, 12, 1, 10, 30)
        
        expected = calculate_expected_bars(start, end, 1.0)
        assert expected == 60
    
    def test_five_minute_interval(self):
        """Test 5-minute bars for 1 hour."""
        start = datetime(2025, 12, 1, 9, 30)
        end = datetime(2025, 12, 1, 10, 30)
        
        expected = calculate_expected_bars(start, end, 5.0)
        assert expected == 12
    
    def test_full_trading_day(self):
        """Test 1-minute bars for full trading day (390 minutes)."""
        start = datetime(2025, 12, 1, 9, 30)
        end = datetime(2025, 12, 1, 16, 0)
        
        expected = calculate_expected_bars(start, end, 1.0)
        assert expected == 390
    
    def test_second_interval(self):
        """Test 1-second bars for 1 minute (60 bars)."""
        start = datetime(2025, 12, 1, 9, 30, 0)
        end = datetime(2025, 12, 1, 9, 31, 0)
        
        expected = calculate_expected_bars(start, end, 1/60)  # 1 second
        assert expected == 60
    
    def test_zero_elapsed_time(self):
        """Test zero elapsed time returns 0."""
        start = datetime(2025, 12, 1, 9, 30)
        end = datetime(2025, 12, 1, 9, 30)
        
        expected = calculate_expected_bars(start, end, 1.0)
        assert expected == 0
    
    def test_negative_elapsed_time(self):
        """Test negative elapsed time returns 0."""
        start = datetime(2025, 12, 1, 10, 30)
        end = datetime(2025, 12, 1, 9, 30)
        
        expected = calculate_expected_bars(start, end, 1.0)
        assert expected == 0


# ============================================================================
# Test calculate_quality_percentage()
# ============================================================================

class TestCalculateQualityPercentage:
    """Test quality percentage calculations."""
    
    def test_perfect_quality(self):
        """Test 100% quality (all bars present)."""
        quality = calculate_quality_percentage(390, 390)
        assert quality == 100.0
    
    def test_partial_quality(self):
        """Test partial quality (some bars missing)."""
        quality = calculate_quality_percentage(350, 390)
        assert quality == pytest.approx(89.74, rel=0.01)
    
    def test_zero_quality(self):
        """Test 0% quality (no bars present)."""
        quality = calculate_quality_percentage(0, 390)
        assert quality == 0.0
    
    def test_no_bars_expected(self):
        """Test no bars expected returns 100%."""
        quality = calculate_quality_percentage(0, 0)
        assert quality == 100.0
    
    def test_over_100_percent_capped(self):
        """Test quality capped at 100% (more bars than expected)."""
        quality = calculate_quality_percentage(400, 390)
        assert quality == 100.0


# ============================================================================
# Test calculate_quality_for_current_session()
# ============================================================================

class TestCalculateQualityForCurrentSession:
    """Test current session quality calculation."""
    
    def test_full_quality_at_market_close(self):
        """Test 100% quality with all bars at market close."""
        target_date = date(2025, 12, 1)
        current_time = datetime(2025, 12, 1, 16, 0, tzinfo=ZoneInfo("America/New_York"))
        
        time_mgr = mock_time_manager()
        db_session = Mock()
        
        quality = calculate_quality_for_current_session(
            time_mgr,
            db_session,
            "AAPL",
            "1m",
            current_time,
            actual_bars=390  # All 390 1-minute bars present
        )
        
        assert quality == 100.0
    
    def test_partial_quality_midday(self):
        """Test partial quality at midday."""
        target_date = date(2025, 12, 1)
        current_time = datetime(2025, 12, 1, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        
        time_mgr = mock_time_manager()
        db_session = Mock()
        
        # From 9:30 to 12:00 = 2.5 hours = 150 minutes
        # If we have 140 bars instead of 150
        quality = calculate_quality_for_current_session(
            time_mgr,
            db_session,
            "AAPL",
            "1m",
            current_time,
            actual_bars=140
        )
        
        assert quality == pytest.approx(93.33, rel=0.01)
    
    def test_after_market_close_caps_at_close(self):
        """Test after market close time is capped at close time."""
        target_date = date(2025, 12, 1)
        current_time = datetime(2025, 12, 1, 17, 0, tzinfo=ZoneInfo("America/New_York"))  # 5 PM
        
        time_mgr = mock_time_manager()
        db_session = Mock()
        
        # Should cap at 4 PM close, not use 5 PM
        # Expected: 390 bars (9:30 to 4:00), not 450 (9:30 to 5:00)
        quality = calculate_quality_for_current_session(
            time_mgr,
            db_session,
            "AAPL",
            "1m",
            current_time,
            actual_bars=390
        )
        
        assert quality == 100.0  # All bars for market hours
    
    def test_before_market_open_returns_100(self):
        """Test before market open returns 100% (no bars expected yet)."""
        target_date = date(2025, 12, 1)
        current_time = datetime(2025, 12, 1, 9, 0, tzinfo=ZoneInfo("America/New_York"))  # 9 AM
        
        time_mgr = mock_time_manager()
        db_session = Mock()
        
        quality = calculate_quality_for_current_session(
            time_mgr,
            db_session,
            "AAPL",
            "1m",
            current_time,
            actual_bars=0
        )
        
        assert quality == 100.0
    
    def test_early_close_day(self):
        """Test quality calculation on early close day."""
        target_date = date(2024, 11, 28)
        current_time = datetime(2024, 11, 28, 13, 0, tzinfo=ZoneInfo("America/New_York"))  # 1 PM close
        
        def get_session(db, dt, exchange="NYSE"):
            return mock_trading_session(
                dt,
                regular_open=time(9, 30),
                regular_close=time(13, 0),
                is_early_close=True
            )
        
        time_mgr = mock_time_manager(get_session)
        db_session = Mock()
        
        # Early close: 9:30 to 1:00 = 3.5 hours = 210 minutes
        quality = calculate_quality_for_current_session(
            time_mgr,
            db_session,
            "AAPL",
            "1m",
            current_time,
            actual_bars=210
        )
        
        assert quality == 100.0
    
    def test_holiday_returns_none(self):
        """Test holiday returns None (no quality calculation)."""
        target_date = date(2024, 12, 25)
        current_time = datetime(2024, 12, 25, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        
        def get_session(db, dt, exchange="NYSE"):
            return mock_trading_session(dt, is_holiday=True)
        
        time_mgr = mock_time_manager(get_session)
        db_session = Mock()
        
        quality = calculate_quality_for_current_session(
            time_mgr,
            db_session,
            "AAPL",
            "1m",
            current_time,
            actual_bars=0
        )
        
        assert quality is None


# ============================================================================
# Test calculate_quality_for_historical_date()
# ============================================================================

class TestCalculateQualityForHistoricalDate:
    """Test historical date quality calculation."""
    
    def test_full_quality_regular_day(self):
        """Test 100% quality for complete regular trading day."""
        target_date = date(2025, 12, 1)
        
        time_mgr = mock_time_manager()
        db_session = Mock()
        
        quality = calculate_quality_for_historical_date(
            time_mgr,
            db_session,
            "AAPL",
            "1m",
            target_date,
            actual_bars=390
        )
        
        assert quality == 100.0
    
    def test_partial_quality_regular_day(self):
        """Test partial quality for incomplete data."""
        target_date = date(2025, 12, 1)
        
        time_mgr = mock_time_manager()
        db_session = Mock()
        
        # Only 350 out of 390 bars
        quality = calculate_quality_for_historical_date(
            time_mgr,
            db_session,
            "AAPL",
            "1m",
            target_date,
            actual_bars=350
        )
        
        assert quality == pytest.approx(89.74, rel=0.01)
    
    def test_full_quality_early_close_day(self):
        """Test 100% quality for early close day with all bars."""
        target_date = date(2024, 11, 28)
        
        def get_session(db, dt, exchange="NYSE"):
            return mock_trading_session(
                dt,
                regular_open=time(9, 30),
                regular_close=time(13, 0),
                is_early_close=True
            )
        
        time_mgr = mock_time_manager(get_session)
        db_session = Mock()
        
        # Early close: 210 minutes, all bars present
        quality = calculate_quality_for_historical_date(
            time_mgr,
            db_session,
            "AAPL",
            "1m",
            target_date,
            actual_bars=210
        )
        
        assert quality == 100.0
    
    def test_five_minute_bars(self):
        """Test quality calculation for 5-minute bars."""
        target_date = date(2025, 12, 1)
        
        time_mgr = mock_time_manager()
        db_session = Mock()
        
        # 390 minutes / 5 = 78 expected 5-minute bars
        quality = calculate_quality_for_historical_date(
            time_mgr,
            db_session,
            "AAPL",
            "5m",
            target_date,
            actual_bars=78
        )
        
        assert quality == 100.0
    
    def test_daily_bar(self):
        """Test quality calculation for daily bar."""
        target_date = date(2025, 12, 1)
        
        time_mgr = mock_time_manager()
        db_session = Mock()
        
        # 1 daily bar expected, 1 present
        quality = calculate_quality_for_historical_date(
            time_mgr,
            db_session,
            "AAPL",
            "1d",
            target_date,
            actual_bars=1
        )
        
        assert quality == 100.0
    
    def test_holiday_returns_none(self):
        """Test holiday returns None."""
        target_date = date(2024, 12, 25)
        
        def get_session(db, dt, exchange="NYSE"):
            return mock_trading_session(dt, is_holiday=True)
        
        time_mgr = mock_time_manager(get_session)
        db_session = Mock()
        
        quality = calculate_quality_for_historical_date(
            time_mgr,
            db_session,
            "AAPL",
            "1m",
            target_date,
            actual_bars=0
        )
        
        assert quality is None


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
