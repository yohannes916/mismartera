"""Unit tests for gap filling functionality."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from app.managers.data_manager.data_upkeep_thread import DataUpkeepThread
from app.managers.data_manager.session_data import get_session_data, reset_session_data
from app.managers.data_manager.gap_detection import GapInfo
from app.models.trading import BarData


@pytest.fixture
def mock_system_manager():
    """Create a mock SystemManager."""
    mock_mgr = Mock()
    mock_mgr.is_backtest_mode.return_value = True
    mock_mgr.is_running.return_value = True
    return mock_mgr


@pytest.fixture
def session_data():
    """Create a fresh session_data instance."""
    reset_session_data()
    return get_session_data()


@pytest.fixture
def mock_db_bars():
    """Create mock database bars."""
    base_time = datetime(2025, 1, 1, 9, 30)
    
    class MockDBBar:
        def __init__(self, timestamp, price):
            self.timestamp = timestamp
            self.open = price
            self.high = price + 1.0
            self.low = price - 1.0
            self.close = price + 0.5
            self.volume = 1000
    
    return [
        MockDBBar(base_time + timedelta(minutes=i), 150.0 + i * 0.1)
        for i in range(5)
    ]


@pytest.mark.asyncio
async def test_fill_gap_with_database_session(mock_system_manager, session_data, mock_db_bars):
    """Test gap filling when data_repository is a database session."""
    # Create mock database session
    mock_session = Mock()
    mock_session.execute = AsyncMock()
    
    # Create mock repository that will be used
    with patch('app.managers.data_manager.data_upkeep_thread.MarketDataRepository') as MockRepo:
        MockRepo.get_bars_by_symbol = AsyncMock(return_value=mock_db_bars)
        
        # Create upkeep thread with mock session
        upkeep = DataUpkeepThread(
            session_data=session_data,
            system_manager=mock_system_manager,
            data_repository=mock_session
        )
        
        # Create a gap
        gap = GapInfo(
            symbol="AAPL",
            start_time=datetime(2025, 1, 1, 9, 30),
            end_time=datetime(2025, 1, 1, 9, 35),
            bar_count=5
        )
        
        # Fill the gap
        filled_count = await upkeep._fill_gap("AAPL", gap)
        
        assert filled_count == 5
        
        # Verify bars were added to session_data
        bars = await session_data.get_bars("AAPL")
        assert len(bars) == 5


@pytest.mark.asyncio
async def test_fill_gap_with_repository_interface(mock_system_manager, session_data, mock_db_bars):
    """Test gap filling when data_repository has get_bars_by_symbol method."""
    # Create mock repository with get_bars_by_symbol method
    mock_repo = Mock()
    mock_repo.get_bars_by_symbol = AsyncMock(return_value=mock_db_bars)
    
    upkeep = DataUpkeepThread(
        session_data=session_data,
        system_manager=mock_system_manager,
        data_repository=mock_repo
    )
    
    gap = GapInfo(
        symbol="AAPL",
        start_time=datetime(2025, 1, 1, 9, 30),
        end_time=datetime(2025, 1, 1, 9, 35),
        bar_count=5
    )
    
    filled_count = await upkeep._fill_gap("AAPL", gap)
    
    assert filled_count == 5
    
    # Verify the method was called with correct parameters
    mock_repo.get_bars_by_symbol.assert_called_once()
    call_args = mock_repo.get_bars_by_symbol.call_args
    assert call_args.kwargs['symbol'] == "AAPL"
    assert call_args.kwargs['start_date'] == gap.start_time
    assert call_args.kwargs['end_date'] == gap.end_time


@pytest.mark.asyncio
async def test_fill_gap_no_bars_found(mock_system_manager, session_data):
    """Test gap filling when no bars are found in database."""
    mock_repo = Mock()
    mock_repo.get_bars_by_symbol = AsyncMock(return_value=[])
    
    upkeep = DataUpkeepThread(
        session_data=session_data,
        system_manager=mock_system_manager,
        data_repository=mock_repo
    )
    
    gap = GapInfo(
        symbol="AAPL",
        start_time=datetime(2025, 1, 1, 9, 30),
        end_time=datetime(2025, 1, 1, 9, 35),
        bar_count=5
    )
    
    filled_count = await upkeep._fill_gap("AAPL", gap)
    
    assert filled_count == 0


@pytest.mark.asyncio
async def test_fill_gap_no_repository(mock_system_manager, session_data):
    """Test gap filling when no data_repository is provided."""
    upkeep = DataUpkeepThread(
        session_data=session_data,
        system_manager=mock_system_manager,
        data_repository=None
    )
    
    gap = GapInfo(
        symbol="AAPL",
        start_time=datetime(2025, 1, 1, 9, 30),
        end_time=datetime(2025, 1, 1, 9, 35),
        bar_count=5
    )
    
    filled_count = await upkeep._fill_gap("AAPL", gap)
    
    assert filled_count == 0


@pytest.mark.asyncio
async def test_fill_gap_with_invalid_bars(mock_system_manager, session_data):
    """Test gap filling with invalid/malformed database bars."""
    # Create bars with missing attributes
    class InvalidBar:
        def __init__(self):
            self.timestamp = datetime(2025, 1, 1, 9, 30)
            # Missing other required fields
    
    mock_repo = Mock()
    mock_repo.get_bars_by_symbol = AsyncMock(return_value=[InvalidBar()])
    
    upkeep = DataUpkeepThread(
        session_data=session_data,
        system_manager=mock_system_manager,
        data_repository=mock_repo
    )
    
    gap = GapInfo(
        symbol="AAPL",
        start_time=datetime(2025, 1, 1, 9, 30),
        end_time=datetime(2025, 1, 1, 9, 31),
        bar_count=1
    )
    
    filled_count = await upkeep._fill_gap("AAPL", gap)
    
    # Should return 0 because bars couldn't be converted
    assert filled_count == 0


@pytest.mark.asyncio
async def test_fill_gap_with_generic_interface(mock_system_manager, session_data, mock_db_bars):
    """Test gap filling with generic get_bars interface."""
    mock_repo = Mock()
    mock_repo.get_bars = AsyncMock(return_value=mock_db_bars)
    
    upkeep = DataUpkeepThread(
        session_data=session_data,
        system_manager=mock_system_manager,
        data_repository=mock_repo
    )
    
    gap = GapInfo(
        symbol="AAPL",
        start_time=datetime(2025, 1, 1, 9, 30),
        end_time=datetime(2025, 1, 1, 9, 35),
        bar_count=5
    )
    
    filled_count = await upkeep._fill_gap("AAPL", gap)
    
    assert filled_count == 5


@pytest.mark.asyncio
async def test_fill_gap_exception_handling(mock_system_manager, session_data):
    """Test that exceptions during gap filling are handled gracefully."""
    mock_repo = Mock()
    mock_repo.get_bars_by_symbol = AsyncMock(side_effect=Exception("Database error"))
    
    upkeep = DataUpkeepThread(
        session_data=session_data,
        system_manager=mock_system_manager,
        data_repository=mock_repo
    )
    
    gap = GapInfo(
        symbol="AAPL",
        start_time=datetime(2025, 1, 1, 9, 30),
        end_time=datetime(2025, 1, 1, 9, 35),
        bar_count=5
    )
    
    # Should not raise, should return 0
    filled_count = await upkeep._fill_gap("AAPL", gap)
    
    assert filled_count == 0


@pytest.mark.asyncio
async def test_fill_gap_partial_fill(mock_system_manager, session_data):
    """Test gap filling when only some bars are found."""
    # Create only 3 bars for a 5-bar gap
    base_time = datetime(2025, 1, 1, 9, 30)
    
    class MockDBBar:
        def __init__(self, timestamp, price):
            self.timestamp = timestamp
            self.open = price
            self.high = price + 1.0
            self.low = price - 1.0
            self.close = price + 0.5
            self.volume = 1000
    
    partial_bars = [
        MockDBBar(base_time + timedelta(minutes=i), 150.0)
        for i in range(3)
    ]
    
    mock_repo = Mock()
    mock_repo.get_bars_by_symbol = AsyncMock(return_value=partial_bars)
    
    upkeep = DataUpkeepThread(
        session_data=session_data,
        system_manager=mock_system_manager,
        data_repository=mock_repo
    )
    
    gap = GapInfo(
        symbol="AAPL",
        start_time=base_time,
        end_time=base_time + timedelta(minutes=5),
        bar_count=5
    )
    
    filled_count = await upkeep._fill_gap("AAPL", gap)
    
    # Should fill 3 bars (partial fill)
    assert filled_count == 3
    
    # Verify bars were added
    bars = await session_data.get_bars("AAPL")
    assert len(bars) == 3


@pytest.mark.asyncio
async def test_fill_gap_updates_session_data(mock_system_manager, session_data, mock_db_bars):
    """Test that filled gaps actually update session_data correctly."""
    mock_repo = Mock()
    mock_repo.get_bars_by_symbol = AsyncMock(return_value=mock_db_bars)
    
    upkeep = DataUpkeepThread(
        session_data=session_data,
        system_manager=mock_system_manager,
        data_repository=mock_repo
    )
    
    gap = GapInfo(
        symbol="AAPL",
        start_time=datetime(2025, 1, 1, 9, 30),
        end_time=datetime(2025, 1, 1, 9, 35),
        bar_count=5
    )
    
    # Initially no bars
    assert await session_data.get_bar_count("AAPL") == 0
    
    # Fill gap
    filled_count = await upkeep._fill_gap("AAPL", gap)
    
    # Should have bars now
    assert await session_data.get_bar_count("AAPL") == 5
    
    # Check latest bar
    latest = await session_data.get_latest_bar("AAPL")
    assert latest is not None
    assert latest.symbol == "AAPL"
    
    # Check session metrics updated
    metrics = await session_data.get_session_metrics("AAPL")
    assert metrics["session_volume"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
