"""Unit tests for historical bars functionality (Phase 3)."""
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import Mock, AsyncMock
from app.managers.data_manager.session_data import get_session_data, reset_session_data
from app.models.trading import BarData


@pytest.fixture
def session_data():
    """Create a fresh session_data instance."""
    reset_session_data()
    sd = get_session_data()
    sd.historical_bars_trailing_days = 5  # Set limit for tests
    return sd


@pytest.fixture
def mock_historical_bars():
    """Create mock historical database bars."""
    bars = []
    base_date = date(2025, 1, 1)
    
    class MockDBBar:
        def __init__(self, timestamp, price):
            self.timestamp = timestamp
            self.open = price
            self.high = price + 1.0
            self.low = price - 1.0
            self.close = price + 0.5
            self.volume = 1000
    
    # Create 5 days of mock data, 10 bars per day
    for day in range(5):
        bar_date = base_date + timedelta(days=day)
        for minute in range(10):
            ts = datetime.combine(bar_date, datetime.min.time()) + timedelta(minutes=minute)
            bars.append(MockDBBar(ts, 150.0 + day + minute * 0.1))
    
    return bars


@pytest.mark.asyncio
async def test_load_historical_bars(session_data, mock_historical_bars):
    """Test loading historical bars from database."""
    # Setup
    await session_data.start_new_session(date(2025, 1, 10))
    await session_data.register_symbol("AAPL")
    
    # Mock repository
    mock_repo = Mock()
    mock_repo.get_bars_by_symbol = AsyncMock(return_value=mock_historical_bars)
    
    # Load historical bars
    count = await session_data.load_historical_bars(
        symbol="AAPL",
        trailing_days=5,
        intervals=[1],
        data_repository=mock_repo
    )
    
    # Verify
    assert count == 50  # 5 days * 10 bars
    
    # Check historical data is accessible
    historical = await session_data.get_historical_bars("AAPL", days_back=5, interval=1)
    assert len(historical) == 5  # 5 days


@pytest.mark.asyncio
async def test_load_historical_bars_no_repository(session_data):
    """Test loading historical bars without repository."""
    await session_data.start_new_session(date(2025, 1, 10))
    await session_data.register_symbol("AAPL")
    
    count = await session_data.load_historical_bars(
        symbol="AAPL",
        trailing_days=5,
        intervals=[1],
        data_repository=None
    )
    
    assert count == 0


@pytest.mark.asyncio
async def test_get_historical_bars_days_back(session_data):
    """Test retrieving specific number of historical days."""
    await session_data.start_new_session(date(2025, 1, 10))
    symbol_data = await session_data.get_symbol_data("AAPL")
    
    # Manually add historical data
    for day in range(5):
        bar_date = date(2025, 1, 1) + timedelta(days=day)
        bars = [
            BarData("AAPL", datetime.combine(bar_date, datetime.min.time()), 150, 151, 149, 150.5, 1000)
        ]
        if 1 not in symbol_data.historical_bars:
            symbol_data.historical_bars[1] = {}
        symbol_data.historical_bars[1][bar_date] = bars
    
    # Get last 3 days
    historical = await session_data.get_historical_bars("AAPL", days_back=3, interval=1)
    
    assert len(historical) == 3
    assert date(2025, 1, 3) in historical
    assert date(2025, 1, 4) in historical
    assert date(2025, 1, 5) in historical


@pytest.mark.asyncio
async def test_get_historical_bars_all(session_data):
    """Test retrieving all historical bars."""
    await session_data.start_new_session(date(2025, 1, 10))
    symbol_data = await session_data.get_symbol_data("AAPL")
    
    # Add 5 days
    for day in range(5):
        bar_date = date(2025, 1, 1) + timedelta(days=day)
        bars = [
            BarData("AAPL", datetime.combine(bar_date, datetime.min.time()), 150, 151, 149, 150.5, 1000)
        ]
        if 1 not in symbol_data.historical_bars:
            symbol_data.historical_bars[1] = {}
        symbol_data.historical_bars[1][bar_date] = bars
    
    # Get all (days_back=0)
    historical = await session_data.get_historical_bars("AAPL", days_back=0, interval=1)
    
    assert len(historical) == 5


@pytest.mark.asyncio
async def test_get_all_bars_including_historical(session_data):
    """Test getting combined historical + current session bars."""
    await session_data.start_new_session(date(2025, 1, 10))
    
    # Add historical data
    symbol_data = await session_data.get_symbol_data("AAPL")
    for day in range(3):
        bar_date = date(2025, 1, 1) + timedelta(days=day)
        bar = BarData(
            "AAPL",
            datetime.combine(bar_date, datetime.min.time()),
            150, 151, 149, 150.5, 1000
        )
        if 1 not in symbol_data.historical_bars:
            symbol_data.historical_bars[1] = {}
        symbol_data.historical_bars[1][bar_date] = [bar]
    
    # Add current session data
    current_bar = BarData(
        "AAPL",
        datetime.combine(date(2025, 1, 10), datetime.min.time()),
        152, 153, 151, 152.5, 1500
    )
    await session_data.add_bar("AAPL", current_bar)
    
    # Get all bars
    all_bars = await session_data.get_all_bars_including_historical("AAPL", interval=1)
    
    # Should have 3 historical + 1 current = 4 total
    assert len(all_bars) == 4
    # Should be chronologically ordered
    assert all_bars[0].timestamp.date() == date(2025, 1, 1)
    assert all_bars[-1].timestamp.date() == date(2025, 1, 10)


@pytest.mark.asyncio
async def test_session_roll(session_data):
    """Test rolling session moves current to historical."""
    # Start session on Jan 1
    await session_data.start_new_session(date(2025, 1, 1))
    
    # Add current session bars
    for i in range(5):
        bar = BarData(
            "AAPL",
            datetime(2025, 1, 1, 9, 30 + i),
            150, 151, 149, 150.5, 1000
        )
        await session_data.add_bar("AAPL", bar)
    
    # Verify current session has data
    assert await session_data.get_bar_count("AAPL") == 5
    
    # Roll to new session
    await session_data.roll_session(date(2025, 1, 2))
    
    # Current session should be empty
    assert await session_data.get_bar_count("AAPL") == 0
    
    # Historical should have Jan 1 data
    historical = await session_data.get_historical_bars("AAPL", days_back=1, interval=1)
    assert date(2025, 1, 1) in historical
    assert len(historical[date(2025, 1, 1)]) == 5


@pytest.mark.asyncio
async def test_session_roll_maintains_trailing_days(session_data):
    """Test that session roll removes oldest days when exceeding limit."""
    session_data.historical_bars_trailing_days = 3  # Keep only 3 days
    
    # Add 5 sessions
    for day in range(1, 6):
        session_date = date(2025, 1, day)
        await session_data.start_new_session(session_date)
        
        # Add bars
        bar = BarData(
            "AAPL",
            datetime.combine(session_date, datetime.min.time()),
            150, 151, 149, 150.5, 1000
        )
        await session_data.add_bar("AAPL", bar)
        
        # Roll to next (except last)
        if day < 5:
            await session_data.roll_session(date(2025, 1, day + 1))
    
    # Should only have last 3 days (3, 4, 5)
    historical = await session_data.get_historical_bars("AAPL", days_back=0, interval=1)
    
    # Note: Day 5 is current session, so historical has days 2, 3, 4
    assert len(historical) <= 3


@pytest.mark.asyncio
async def test_session_roll_first_session(session_data):
    """Test rolling when there's no previous session."""
    # Roll without starting session first
    await session_data.roll_session(date(2025, 1, 1))
    
    # Should just start new session
    assert session_data.current_session_date == date(2025, 1, 1)


@pytest.mark.asyncio
async def test_session_roll_clears_metrics(session_data):
    """Test that session roll resets session metrics."""
    await session_data.start_new_session(date(2025, 1, 1))
    
    # Add bars to build up metrics
    for i in range(3):
        bar = BarData(
            "AAPL",
            datetime(2025, 1, 1, 9, 30 + i),
            150 + i, 151 + i, 149 + i, 150.5 + i, 1000 + i * 100
        )
        await session_data.add_bar("AAPL", bar)
    
    # Verify metrics exist
    metrics = await session_data.get_session_metrics("AAPL")
    assert metrics["session_volume"] > 0
    assert metrics["session_high"] > 0
    
    # Roll session
    await session_data.roll_session(date(2025, 1, 2))
    
    # Metrics should be reset
    new_metrics = await session_data.get_session_metrics("AAPL")
    assert new_metrics["session_volume"] == 0
    assert new_metrics["session_high"] == 0


@pytest.mark.asyncio
async def test_historical_bars_multiple_intervals(session_data, mock_historical_bars):
    """Test loading and accessing multiple intervals."""
    await session_data.start_new_session(date(2025, 1, 10))
    await session_data.register_symbol("AAPL")
    
    # Mock repository for both 1m and 5m
    mock_repo = Mock()
    mock_repo.get_bars_by_symbol = AsyncMock(return_value=mock_historical_bars)
    
    # Load both intervals
    count = await session_data.load_historical_bars(
        symbol="AAPL",
        trailing_days=5,
        intervals=[1, 5],
        data_repository=mock_repo
    )
    
    # Should have loaded for both intervals
    assert count == 100  # 50 * 2 calls
    
    # Both should be accessible
    hist_1m = await session_data.get_historical_bars("AAPL", days_back=5, interval=1)
    hist_5m = await session_data.get_historical_bars("AAPL", days_back=5, interval=5)
    
    assert len(hist_1m) > 0
    assert len(hist_5m) > 0


@pytest.mark.asyncio
async def test_session_roll_preserves_derived_bars(session_data):
    """Test that session roll moves derived bars to historical."""
    await session_data.start_new_session(date(2025, 1, 1))
    
    # Add 1m bars
    for i in range(10):
        bar = BarData(
            "AAPL",
            datetime(2025, 1, 1, 9, 30 + i),
            150, 151, 149, 150.5, 1000
        )
        await session_data.add_bar("AAPL", bar)
    
    # Manually add derived bars (normally done by upkeep thread)
    symbol_data = await session_data.get_symbol_data("AAPL")
    derived_bar = BarData(
        "AAPL",
        datetime(2025, 1, 1, 9, 30),
        150, 151, 149, 150.5, 5000
    )
    symbol_data.bars_derived[5] = [derived_bar]
    
    # Roll session
    await session_data.roll_session(date(2025, 1, 2))
    
    # Derived bars should be in historical
    historical_5m = await session_data.get_historical_bars("AAPL", days_back=1, interval=5)
    assert date(2025, 1, 1) in historical_5m
    assert len(historical_5m[date(2025, 1, 1)]) == 1


@pytest.mark.asyncio
async def test_get_historical_bars_nonexistent_symbol(session_data):
    """Test getting historical bars for symbol that doesn't exist."""
    await session_data.start_new_session(date(2025, 1, 10))
    
    historical = await session_data.get_historical_bars("NONEXISTENT", days_back=5)
    
    assert len(historical) == 0


@pytest.mark.asyncio
async def test_all_bars_chronological_order(session_data):
    """Test that all bars are returned in chronological order."""
    await session_data.start_new_session(date(2025, 1, 10))
    symbol_data = await session_data.get_symbol_data("AAPL")
    
    # Add historical bars (out of order dates)
    dates_to_add = [date(2025, 1, 3), date(2025, 1, 1), date(2025, 1, 2)]
    for bar_date in dates_to_add:
        bar = BarData(
            "AAPL",
            datetime.combine(bar_date, datetime.min.time()),
            150, 151, 149, 150.5, 1000
        )
        if 1 not in symbol_data.historical_bars:
            symbol_data.historical_bars[1] = {}
        symbol_data.historical_bars[1][bar_date] = [bar]
    
    # Add current session bar
    current_bar = BarData(
        "AAPL",
        datetime.combine(date(2025, 1, 10), datetime.min.time()),
        152, 153, 151, 152.5, 1500
    )
    await session_data.add_bar("AAPL", current_bar)
    
    # Get all bars
    all_bars = await session_data.get_all_bars_including_historical("AAPL")
    
    # Verify chronological order
    for i in range(1, len(all_bars)):
        assert all_bars[i].timestamp >= all_bars[i-1].timestamp


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
