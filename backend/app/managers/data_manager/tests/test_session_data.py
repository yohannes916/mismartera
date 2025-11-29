"""Unit tests for SessionData module."""
import pytest
from datetime import datetime, date, time
from app.managers.data_manager.session_data import (
    SessionData,
    SymbolSessionData,
    get_session_data,
    reset_session_data
)
from app.models.trading import BarData


@pytest.fixture
def session_data():
    """Create a fresh SessionData instance for each test."""
    reset_session_data()
    return get_session_data()


@pytest.mark.asyncio
async def test_register_symbol(session_data):
    """Test symbol registration."""
    symbol_data = await session_data.register_symbol("AAPL")
    
    assert symbol_data.symbol == "AAPL"
    assert "AAPL" in session_data.get_active_symbols()
    assert len(symbol_data.bars_1m) == 0


@pytest.mark.asyncio
async def test_add_bar(session_data):
    """Test adding a single bar."""
    bar = BarData(
        symbol="AAPL",
        timestamp=datetime(2025, 1, 1, 9, 30),
        open=150.0,
        high=151.0,
        low=149.0,
        close=150.5,
        volume=1000
    )
    
    await session_data.add_bar("AAPL", bar)
    
    bars = await session_data.get_bars("AAPL")
    assert len(bars) == 1
    assert bars[0].close == 150.5
    
    metrics = await session_data.get_session_metrics("AAPL")
    assert metrics["session_volume"] == 1000
    assert metrics["session_high"] == 151.0
    assert metrics["session_low"] == 149.0


@pytest.mark.asyncio
async def test_add_bars_batch(session_data):
    """Test batch bar insertion."""
    bars = [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 1, 9, 30 + i),
            open=150.0 + i,
            high=151.0 + i,
            low=149.0 + i,
            close=150.5 + i,
            volume=1000 * (i + 1)
        )
        for i in range(10)
    ]
    
    await session_data.add_bars_batch("AAPL", bars)
    
    stored_bars = await session_data.get_bars("AAPL")
    assert len(stored_bars) == 10
    
    metrics = await session_data.get_session_metrics("AAPL")
    assert metrics["bar_count"] == 10
    assert metrics["session_volume"] == sum(b.volume for b in bars)


@pytest.mark.asyncio
async def test_get_latest_bar(session_data):
    """Test O(1) access to latest bar."""
    bars = [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 1, 9, 30 + i),
            open=150.0 + i,
            high=151.0 + i,
            low=149.0 + i,
            close=150.5 + i,
            volume=1000
        )
        for i in range(100)
    ]
    
    await session_data.add_bars_batch("AAPL", bars)
    
    # Get latest bar (should be instant)
    latest = await session_data.get_latest_bar("AAPL")
    assert latest is not None
    assert latest.close == 150.5 + 99  # Last bar
    
    # Should be same as last in list
    all_bars = await session_data.get_bars("AAPL")
    assert latest.timestamp == all_bars[-1].timestamp


@pytest.mark.asyncio
async def test_get_last_n_bars(session_data):
    """Test efficient last-N access."""
    bars = [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 1, 9, 30 + i),
            open=150.0 + i,
            high=151.0 + i,
            low=149.0 + i,
            close=150.5 + i,
            volume=1000
        )
        for i in range(100)
    ]
    
    await session_data.add_bars_batch("AAPL", bars)
    
    # Get last 20 bars
    last_20 = await session_data.get_last_n_bars("AAPL", 20)
    assert len(last_20) == 20
    assert last_20[0].close == 150.5 + 80  # 80th bar
    assert last_20[-1].close == 150.5 + 99  # 99th bar
    
    # Request more than available
    all_bars = await session_data.get_last_n_bars("AAPL", 200)
    assert len(all_bars) == 100  # Only 100 available


@pytest.mark.asyncio
async def test_get_bars_since(session_data):
    """Test efficient time-based filtering."""
    bars = [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 1, 9, 30 + i),
            open=150.0,
            high=151.0,
            low=149.0,
            close=150.5,
            volume=1000
        )
        for i in range(100)
    ]
    
    await session_data.add_bars_batch("AAPL", bars)
    
    # Get bars since 9:50
    since_time = datetime(2025, 1, 1, 9, 50)
    recent = await session_data.get_bars_since("AAPL", since_time)
    
    assert len(recent) == 80  # Bars 20-99
    assert all(b.timestamp >= since_time for b in recent)


@pytest.mark.asyncio
async def test_get_bar_count(session_data):
    """Test O(1) bar count."""
    bars = [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 1, 9, 30 + i),
            open=150.0,
            high=151.0,
            low=149.0,
            close=150.5,
            volume=1000
        )
        for i in range(100)
    ]
    
    await session_data.add_bars_batch("AAPL", bars)
    
    # Count should be instant
    count = await session_data.get_bar_count("AAPL")
    assert count == 100


@pytest.mark.asyncio
async def test_get_latest_bars_multi(session_data):
    """Test batch retrieval for multiple symbols."""
    # Add bars for multiple symbols
    for symbol in ["AAPL", "GOOGL", "MSFT"]:
        bars = [
            BarData(
                symbol=symbol,
                timestamp=datetime(2025, 1, 1, 9, 30 + i),
                open=150.0,
                high=151.0,
                low=149.0,
                close=150.5 + i,
                volume=1000
            )
            for i in range(10)
        ]
        await session_data.add_bars_batch(symbol, bars)
    
    # Get latest bars for all symbols in one call
    latest_bars = await session_data.get_latest_bars_multi(["AAPL", "GOOGL", "MSFT"])
    
    assert len(latest_bars) == 3
    assert latest_bars["AAPL"].close == 150.5 + 9
    assert latest_bars["GOOGL"].close == 150.5 + 9
    assert latest_bars["MSFT"].close == 150.5 + 9


@pytest.mark.asyncio
async def test_session_lifecycle(session_data):
    """Test session start/end lifecycle."""
    session_date = date(2025, 1, 1)
    
    # Start session
    await session_data.start_new_session(session_date)
    assert session_data.current_session_date == session_date
    assert session_data.is_session_active()
    
    # Add some data
    bar = BarData(
        symbol="AAPL",
        timestamp=datetime(2025, 1, 1, 9, 30),
        open=150.0,
        high=151.0,
        low=149.0,
        close=150.5,
        volume=1000
    )
    await session_data.add_bar("AAPL", bar)
    
    # End session
    await session_data.end_session()
    assert not session_data.is_session_active()
    
    # Start new session - should clear data
    await session_data.start_new_session(date(2025, 1, 2))
    bars = await session_data.get_bars("AAPL")
    assert len(bars) == 0  # Data cleared


@pytest.mark.asyncio
async def test_get_bars_with_filters(session_data):
    """Test bar retrieval with time filters."""
    bars = [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 1, 9, 30 + i),
            open=150.0,
            high=151.0,
            low=149.0,
            close=150.5,
            volume=1000
        )
        for i in range(10)
    ]
    
    await session_data.add_bars_batch("AAPL", bars)
    
    # Filter by start time
    start = datetime(2025, 1, 1, 9, 35)
    filtered = await session_data.get_bars("AAPL", start=start)
    assert len(filtered) == 5  # bars 5-9
    
    # Filter by end time
    end = datetime(2025, 1, 1, 9, 35)
    filtered = await session_data.get_bars("AAPL", end=end)
    assert len(filtered) == 5  # bars 0-4
    
    # Filter by both
    start = datetime(2025, 1, 1, 9, 32)
    end = datetime(2025, 1, 1, 9, 37)
    filtered = await session_data.get_bars("AAPL", start=start, end=end)
    assert len(filtered) == 5  # bars 2-6


@pytest.mark.asyncio
async def test_thread_safety(session_data):
    """Test concurrent access from multiple tasks."""
    import asyncio
    
    async def add_bars_task(symbol, count):
        for i in range(count):
            bar = BarData(
                symbol=symbol,
                timestamp=datetime(2025, 1, 1, 9, 30, i),
                open=150.0,
                high=151.0,
                low=149.0,
                close=150.5,
                volume=1000
            )
            await session_data.add_bar(symbol, bar)
            await asyncio.sleep(0.001)  # Small delay
    
    # Run multiple tasks concurrently
    tasks = [
        add_bars_task("AAPL", 10),
        add_bars_task("GOOGL", 10),
        add_bars_task("MSFT", 10),
    ]
    
    await asyncio.gather(*tasks)
    
    # Verify all bars were added
    assert len(await session_data.get_bars("AAPL")) == 10
    assert len(await session_data.get_bars("GOOGL")) == 10
    assert len(await session_data.get_bars("MSFT")) == 10
