"""Unit tests for Phase 4: Prefetch Mechanism

Tests for:
- TradingCalendar
- SessionDetector
- PrefetchManager
"""
import pytest
from datetime import date, datetime, time, timedelta
from unittest.mock import Mock, AsyncMock, patch

from app.managers.data_manager.trading_calendar import TradingCalendar
from app.managers.data_manager.session_detector import SessionDetector
from app.managers.data_manager.prefetch_manager import PrefetchManager, SymbolPrefetchData
from app.managers.data_manager.session_data import get_session_data, reset_session_data
from app.models.trading import BarData


# ==================== Trading Calendar Tests ====================

def test_trading_calendar_is_trading_day():
    """Test trading day validation."""
    cal = TradingCalendar()
    
    # Regular trading day (Thursday, Jan 2, 2025)
    assert cal.is_trading_day(date(2025, 1, 2)) == True
    
    # New Year's Day (holiday)
    assert cal.is_trading_day(date(2025, 1, 1)) == False
    
    # Weekend (Saturday, Jan 4, 2025)
    assert cal.is_trading_day(date(2025, 1, 4)) == False
    
    # Weekend (Sunday, Jan 5, 2025)
    assert cal.is_trading_day(date(2025, 1, 5)) == False


def test_trading_calendar_next_trading_day():
    """Test getting next trading day."""
    cal = TradingCalendar()
    
    # From New Year's Day (Wed holiday) → next is Thu Jan 2
    next_day = cal.get_next_trading_day(date(2025, 1, 1))
    assert next_day == date(2025, 1, 2)
    
    # From Friday → skip weekend → next Monday
    next_day = cal.get_next_trading_day(date(2025, 1, 3))
    assert next_day == date(2025, 1, 6)


def test_trading_calendar_previous_trading_day():
    """Test getting previous trading day."""
    cal = TradingCalendar()
    
    # From Monday → previous Friday
    prev_day = cal.get_previous_trading_day(date(2025, 1, 6))
    assert prev_day == date(2025, 1, 3)


def test_trading_calendar_count_trading_days():
    """Test counting trading days in range."""
    cal = TradingCalendar()
    
    # Count Jan 2-10, 2025 (skipping weekend and New Year's)
    count = cal.count_trading_days(date(2025, 1, 2), date(2025, 1, 10))
    assert count == 7  # Thu-Fri, Mon-Fri (skip Sat-Sun)


def test_trading_calendar_holidays():
    """Test major holidays are recognized."""
    cal = TradingCalendar()
    
    # Test all major 2025 holidays
    assert cal.is_holiday(date(2025, 1, 1))   # New Year's
    assert cal.is_holiday(date(2025, 1, 20))  # MLK Day
    assert cal.is_holiday(date(2025, 7, 4))   # Independence Day
    assert cal.is_holiday(date(2025, 12, 25)) # Christmas


# ==================== Session Detector Tests ====================

def test_session_detector_next_session():
    """Test detecting next trading session."""
    detector = SessionDetector()
    
    # From Thursday → next is Friday
    next_session = detector.get_next_session(date(2025, 1, 2))
    assert next_session == date(2025, 1, 3)
    
    # From Friday → skip weekend → next is Monday
    next_session = detector.get_next_session(date(2025, 1, 3))
    assert next_session == date(2025, 1, 6)


def test_session_detector_should_prefetch():
    """Test prefetch timing logic."""
    detector = SessionDetector()
    
    # 30 minutes before market open → should prefetch (within 60 min window)
    next_session = date(2025, 1, 10)
    current_time = datetime(2025, 1, 10, 9, 0)  # 9:00 AM (30 min before)
    
    should_prefetch = detector.should_prefetch(current_time, next_session, prefetch_window_minutes=60)
    assert should_prefetch == True
    
    # 90 minutes before → too early
    current_time = datetime(2025, 1, 10, 8, 0)  # 8:00 AM (90 min before)
    should_prefetch = detector.should_prefetch(current_time, next_session, prefetch_window_minutes=60)
    assert should_prefetch == False
    
    # After market open → too late
    current_time = datetime(2025, 1, 10, 10, 0)  # 10:00 AM (after open)
    should_prefetch = detector.should_prefetch(current_time, next_session, prefetch_window_minutes=60)
    assert should_prefetch == False


def test_session_detector_is_during_market_hours():
    """Test market hours detection."""
    detector = SessionDetector()
    
    # During market hours (trading day, 10 AM)
    check_time = datetime(2025, 1, 2, 10, 0)
    assert detector.is_during_market_hours(check_time) == True
    
    # Before market open (trading day, 8 AM)
    check_time = datetime(2025, 1, 2, 8, 0)
    assert detector.is_during_market_hours(check_time) == False
    
    # After market close (trading day, 5 PM)
    check_time = datetime(2025, 1, 2, 17, 0)
    assert detector.is_during_market_hours(check_time) == False
    
    # Weekend (not trading day)
    check_time = datetime(2025, 1, 4, 10, 0)  # Saturday
    assert detector.is_during_market_hours(check_time) == False


def test_session_detector_boundary_status():
    """Test session boundary detection."""
    detector = SessionDetector()
    
    # Pre-market (before 9:30 AM)
    status = detector.get_session_boundary_status(
        datetime(2025, 1, 2, 8, 0),
        date(2025, 1, 2)
    )
    assert status == "pre_market"
    
    # Market hours (10 AM)
    status = detector.get_session_boundary_status(
        datetime(2025, 1, 2, 10, 0),
        date(2025, 1, 2)
    )
    assert status == "market_hours"
    
    # Post-market (5 PM)
    status = detector.get_session_boundary_status(
        datetime(2025, 1, 2, 17, 0),
        date(2025, 1, 2)
    )
    assert status == "post_market"
    
    # Session ended (next day)
    status = detector.get_session_boundary_status(
        datetime(2025, 1, 3, 10, 0),
        date(2025, 1, 2)
    )
    assert status == "session_end"


def test_session_detector_should_roll_session():
    """Test session roll determination."""
    detector = SessionDetector()
    
    # Same day, during market - no roll
    should_roll = detector.should_roll_session(
        datetime(2025, 1, 2, 10, 0),
        date(2025, 1, 2)
    )
    assert should_roll == False
    
    # Next day - should roll
    should_roll = detector.should_roll_session(
        datetime(2025, 1, 3, 10, 0),
        date(2025, 1, 2)
    )
    assert should_roll == True


# ==================== Prefetch Manager Tests ====================

@pytest.fixture
def mock_session_data():
    """Create mock session_data."""
    reset_session_data()
    sd = get_session_data()
    sd.current_session_date = date(2025, 1, 2)
    return sd


@pytest.fixture
def mock_repository():
    """Create mock data repository."""
    return Mock()


@pytest.mark.asyncio
async def test_prefetch_manager_initialization(mock_session_data, mock_repository):
    """Test prefetch manager initialization."""
    manager = PrefetchManager(
        mock_session_data,
        mock_repository
    )
    
    assert manager._session_data == mock_session_data
    assert manager._data_repository == mock_repository
    assert manager._prefetch_complete == False
    assert manager._running == False


@pytest.mark.asyncio
async def test_prefetch_manager_start_stop(mock_session_data, mock_repository):
    """Test starting and stopping prefetch manager."""
    manager = PrefetchManager(
        mock_session_data,
        mock_repository
    )
    
    # Start
    manager.start()
    assert manager._running == True
    assert manager._thread is not None
    
    # Stop
    manager.stop(timeout=1.0)
    assert manager._running == False


@pytest.mark.asyncio
async def test_symbol_prefetch_data():
    """Test SymbolPrefetchData dataclass."""
    historical = {
        1: {
            date(2025, 1, 1): [
                BarData("AAPL", datetime(2025, 1, 1, 9, 30), 150, 151, 149, 150.5, 1000)
            ]
        }
    }
    
    prefetch_data = SymbolPrefetchData(
        symbol="AAPL",
        session_date=date(2025, 1, 2),
        historical_bars=historical,
        prefetch_time=datetime.now()
    )
    
    assert prefetch_data.symbol == "AAPL"
    assert prefetch_data.bar_count == 1


@pytest.mark.asyncio
async def test_prefetch_manager_get_status(mock_session_data, mock_repository):
    """Test getting prefetch manager status."""
    manager = PrefetchManager(
        mock_session_data,
        mock_repository
    )
    
    status = manager.get_status()
    
    assert "running" in status
    assert "prefetch_complete" in status
    assert "cached_symbols" in status
    assert status["running"] == False
    assert status["prefetch_complete"] == False


@pytest.mark.asyncio
async def test_prefetch_manager_clear_cache(mock_session_data, mock_repository):
    """Test clearing prefetch cache."""
    manager = PrefetchManager(
        mock_session_data,
        mock_repository
    )
    
    # Manually add something to cache
    manager._prefetch_cache["AAPL"] = Mock()
    manager._prefetch_complete = True
    
    # Clear
    manager.clear_cache()
    
    assert len(manager._prefetch_cache) == 0
    assert manager._prefetch_complete == False


@pytest.mark.asyncio
async def test_prefetch_manager_activate_no_prefetch(mock_session_data, mock_repository):
    """Test activating when no prefetch available."""
    manager = PrefetchManager(
        mock_session_data,
        mock_repository
    )
    
    # Try to activate without prefetch
    result = await manager.activate_prefetch()
    
    assert result == False


@pytest.mark.asyncio
async def test_prefetch_manager_activate_mismatch(mock_session_data, mock_repository):
    """Test activating with session mismatch."""
    manager = PrefetchManager(
        mock_session_data,
        mock_repository
    )
    
    # Set up prefetch for different session
    manager._prefetch_complete = True
    manager._prefetch_session_date = date(2025, 1, 10)
    
    # Try to activate for current session (different date)
    result = await manager.activate_prefetch(date(2025, 1, 2))
    
    assert result == False


def test_trading_calendar_get_trading_days_in_range():
    """Test getting list of trading days in range."""
    cal = TradingCalendar()
    
    # Get trading days in Jan 2-10, 2025
    trading_days = cal.get_trading_days_in_range(
        date(2025, 1, 2),
        date(2025, 1, 10)
    )
    
    # Should have 7 days (Thu-Fri, Mon-Fri)
    assert len(trading_days) == 7
    assert date(2025, 1, 2) in trading_days  # Thursday
    assert date(2025, 1, 3) in trading_days  # Friday
    assert date(2025, 1, 4) not in trading_days  # Saturday
    assert date(2025, 1, 5) not in trading_days  # Sunday
    assert date(2025, 1, 6) in trading_days  # Monday


def test_session_detector_calculate_prefetch_start_time():
    """Test calculating when prefetch should start."""
    detector = SessionDetector()
    
    # For session on Jan 10, 2025 (market opens 9:30 AM)
    # With 60-minute prefetch window, should start at 8:30 AM
    prefetch_time = detector.calculate_prefetch_start_time(
        date(2025, 1, 10),
        prefetch_window_minutes=60
    )
    
    assert prefetch_time.date() == date(2025, 1, 10)
    assert prefetch_time.time() == time(8, 30)


def test_session_detector_time_until_next_session():
    """Test calculating time until next session."""
    detector = SessionDetector()
    
    # Current time: Jan 2, 8 AM
    # Next session: Jan 2, 9:30 AM (same day)
    current = datetime(2025, 1, 2, 8, 0)
    time_until = detector.get_time_until_next_session(current, date(2025, 1, 2))
    
    assert time_until is not None
    # Should be 1.5 hours (90 minutes)
    assert time_until.total_seconds() == 5400  # 90 * 60


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
