"""End-to-end tests for Stream Requirements with real Parquet data.

Tests the full flow: Parquet storage -> data_checker -> coordinator -> validation

Setup Strategy (Backdoor + Proper API):
- WRITE: Use backdoor (direct Parquet write) to create test data
- READ: Use proper API (ParquetStorage.read_bars) via data_checker
- This mirrors real usage: data setup is external, reading is through API
"""

import pytest
from pathlib import Path
from datetime import date, datetime, timezone
from unittest.mock import Mock, patch
import pandas as pd
import shutil
import tempfile

from app.managers.data_manager.parquet_storage import ParquetStorage
from app.threads.quality.parquet_data_checker import create_parquet_data_checker
from app.threads.quality.stream_requirements_coordinator import (
    StreamRequirementsCoordinator
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def mock_system_manager():
    """Mock SystemManager to provide timezone for ParquetStorage."""
    mock_sys_mgr = Mock()
    mock_sys_mgr.timezone = "America/New_York"  # ET timezone
    
    mock_time_mgr = Mock()
    mock_time_mgr.get_trading_session = Mock(return_value=None)  # No trading session in test
    mock_sys_mgr.get_time_manager = Mock(return_value=mock_time_mgr)
    
    # Patch where get_system_manager is imported FROM
    with patch('app.managers.system_manager.get_system_manager', return_value=mock_sys_mgr):
        yield mock_sys_mgr


@pytest.fixture
def temp_parquet_dir():
    """Create temporary directory for Parquet test data."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def parquet_storage(temp_parquet_dir):
    """Create ParquetStorage pointing to temp directory."""
    return ParquetStorage(
        base_path=str(temp_parquet_dir),
        exchange_group="US_EQUITY"
    )


@pytest.fixture
def mock_session_config():
    """Create mock session config."""
    config = Mock()
    config.mode = "backtest"
    config.session_data_config = Mock()
    config.session_data_config.symbols = ["AAPL", "GOOGL"]
    config.session_data_config.streams = ["1m", "5m"]
    return config


@pytest.fixture
def mock_time_manager():
    """Create mock time manager with date range."""
    time_mgr = Mock()
    time_mgr.backtest_start_date = date(2025, 7, 2)
    time_mgr.backtest_end_date = date(2025, 7, 2)
    return time_mgr


# =============================================================================
# Helper Functions
# =============================================================================

def write_test_bars_parquet(
    base_path: Path,
    symbol: str,
    interval: str,
    start_dt: datetime,
    bar_count: int,
    exchange_group: str = "US_EQUITY"
):
    """Backdoor: Write test Parquet data directly.
    
    This simulates external data ingestion. In production, data comes from
    data import processes. In tests, we write directly to set up scenarios.
    
    Args:
        base_path: Base Parquet directory
        symbol: Stock symbol
        interval: Data type (1s, 1m, 1d)
        start_dt: Start datetime (UTC)
        bar_count: Number of bars to create
        exchange_group: Exchange group
    """
    import pyarrow as pa
    import pyarrow.parquet as pq
    from datetime import timedelta
    from app.managers.data_manager.interval_storage import IntervalStorageStrategy
    
    # Use production storage strategy to get correct file path
    storage_strategy = IntervalStorageStrategy(base_path, exchange_group)
    file_path = storage_strategy.get_file_path(
        interval, 
        symbol, 
        start_dt.year, 
        start_dt.month, 
        start_dt.day
    )
    
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Generate test bars
    timestamps = []
    opens = []
    highs = []
    lows = []
    closes = []
    volumes = []
    
    current_dt = start_dt
    delta = timedelta(minutes=1) if interval == "1m" else timedelta(seconds=1)
    
    for i in range(bar_count):
        timestamps.append(current_dt)
        price = 100.0 + i * 0.1
        opens.append(price)
        highs.append(price + 0.5)
        lows.append(price - 0.5)
        closes.append(price + 0.2)
        volumes.append(1000 + i * 10)
        current_dt += delta
    
    # Create DataFrame
    df = pd.DataFrame({
        'timestamp': timestamps,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })
    
    # Convert timestamp to UTC timezone-aware
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    
    # Write to Parquet
    table = pa.Table.from_pandas(df)
    pq.write_table(table, file_path)
    
    print(f"[BACKDOOR] Wrote {bar_count} bars to {file_path}")


# =============================================================================
# E2E Tests
# =============================================================================

class TestParquetDataChecker:
    """Test Parquet data_checker creation and usage."""
    
    def test_create_data_checker(self, parquet_storage, temp_parquet_dir):
        """Test data_checker creation."""
        # Setup: Write test data (backdoor)
        write_test_bars_parquet(
            temp_parquet_dir,
            "AAPL",
            "1m",
            datetime(2025, 7, 2, 13, 30, 0, tzinfo=timezone.utc),  # UTC time
            390,  # Full trading day
        )
        
        # Create data_checker
        data_checker = create_parquet_data_checker(parquet_storage)
        
        # Query data (proper API through data_checker)
        count = data_checker("AAPL", "1m", date(2025, 7, 2), date(2025, 7, 2))
        
        # Should find all 390 bars
        assert count == 390
    
    def test_no_data_returns_zero(self, parquet_storage):
        """Test data_checker returns 0 when no data."""
        data_checker = create_parquet_data_checker(parquet_storage)
        
        # Query non-existent data
        count = data_checker("TSLA", "1m", date(2025, 7, 2), date(2025, 7, 2))
        
        assert count == 0
    
    def test_multiple_symbols(self, parquet_storage, temp_parquet_dir):
        """Test data_checker with multiple symbols."""
        # Setup: Write data for multiple symbols
        write_test_bars_parquet(
            temp_parquet_dir, "AAPL", "1m",
            datetime(2025, 7, 2, 13, 30, 0, tzinfo=timezone.utc), 390
        )
        write_test_bars_parquet(
            temp_parquet_dir, "GOOGL", "1m",
            datetime(2025, 7, 2, 13, 30, 0, tzinfo=timezone.utc), 385  # Slightly less
        )
        
        data_checker = create_parquet_data_checker(parquet_storage)
        
        # Query both
        aapl_count = data_checker("AAPL", "1m", date(2025, 7, 2), date(2025, 7, 2))
        googl_count = data_checker("GOOGL", "1m", date(2025, 7, 2), date(2025, 7, 2))
        
        assert aapl_count == 390
        assert googl_count == 385


class TestCoordinatorWithParquet:
    """Test full coordinator flow with real Parquet data."""
    
    def test_validation_success_with_data(
        self,
        parquet_storage,
        temp_parquet_dir,
        mock_session_config,
        mock_time_manager
    ):
        """Test validation succeeds when Parquet data exists."""
        # Setup: Write data for both symbols (backdoor)
        for symbol in ["AAPL", "GOOGL"]:
            write_test_bars_parquet(
                temp_parquet_dir, symbol, "1m",
                datetime(2025, 7, 2, 13, 30, 0, tzinfo=timezone.utc),
                390
            )
        
        # Create coordinator
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        # Create data_checker (proper API)
        data_checker = create_parquet_data_checker(parquet_storage)
        
        # Validate
        result = coordinator.validate_requirements(data_checker)
        
        # Should pass
        assert result.valid is True
        assert result.required_base_interval == "1m"
        assert "5m" in result.derivable_intervals
        assert result.error_message is None
    
    def test_validation_fails_missing_symbol(
        self,
        parquet_storage,
        temp_parquet_dir,
        mock_session_config,
        mock_time_manager
    ):
        """Test validation fails when one symbol missing."""
        # Setup: Only write AAPL, not GOOGL
        write_test_bars_parquet(
            temp_parquet_dir, "AAPL", "1m",
            datetime(2025, 7, 2, 13, 30, 0, tzinfo=timezone.utc),
            390
        )
        # GOOGL has no data
        
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        data_checker = create_parquet_data_checker(parquet_storage)
        
        # Validate
        result = coordinator.validate_requirements(data_checker)
        
        # Should fail
        assert result.valid is False
        assert "GOOGL" in result.error_message
        assert "Cannot start session" in result.error_message
    
    def test_validation_with_sparse_data(
        self,
        parquet_storage,
        temp_parquet_dir,
        mock_session_config,
        mock_time_manager
    ):
        """Test validation passes even with sparse data (gaps ok)."""
        # Setup: Write sparse data (only 100 bars for full day)
        for symbol in ["AAPL", "GOOGL"]:
            write_test_bars_parquet(
                temp_parquet_dir, symbol, "1m",
                datetime(2025, 7, 2, 13, 30, 0, tzinfo=timezone.utc),
                100  # Sparse data
            )
        
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        data_checker = create_parquet_data_checker(parquet_storage)
        
        # Validate
        result = coordinator.validate_requirements(data_checker)
        
        # Should PASS - we only check existence, not completeness
        # (Completeness is handled by quality checks later)
        assert result.valid is True
        assert result.required_base_interval == "1m"


class TestDifferentIntervals:
    """Test with different interval configurations."""
    
    def test_1s_interval_requirement(
        self,
        parquet_storage,
        temp_parquet_dir,
        mock_session_config,
        mock_time_manager
    ):
        """Test validation with 1s requirement."""
        # Config requests 1s and 5s
        mock_session_config.session_data_config.streams = ["1s", "5s"]
        
        # Setup: Write 1s data
        for symbol in ["AAPL", "GOOGL"]:
            write_test_bars_parquet(
                temp_parquet_dir, symbol, "1s",
                datetime(2025, 7, 2, 13, 30, 0, tzinfo=timezone.utc),
                23400  # 6.5 hours of 1s bars
            )
        
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        data_checker = create_parquet_data_checker(parquet_storage)
        
        # Validate
        result = coordinator.validate_requirements(data_checker)
        
        # Should pass with 1s as base
        assert result.valid is True
        assert result.required_base_interval == "1s"
        assert "5s" in result.derivable_intervals
    
    def test_wrong_interval_fails(
        self,
        parquet_storage,
        temp_parquet_dir,
        mock_session_config,
        mock_time_manager
    ):
        """Test validation fails when wrong interval available."""
        # Config needs 1m, but only 1d available
        mock_session_config.session_data_config.streams = ["1m", "5m"]
        
        # Setup: Write only 1d data (wrong interval)
        for symbol in ["AAPL", "GOOGL"]:
            write_test_bars_parquet(
                temp_parquet_dir, symbol, "1d",
                datetime(2025, 7, 2, 0, 0, 0, tzinfo=timezone.utc),
                1  # One daily bar
            )
        
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        data_checker = create_parquet_data_checker(parquet_storage)
        
        # Validate
        result = coordinator.validate_requirements(data_checker)
        
        # Should fail - needs 1m, only have 1d
        assert result.valid is False
        assert "1m" in result.error_message


# =============================================================================
# Integration Scenarios
# =============================================================================

class TestRealWorldScenarios:
    """Test realistic scenarios."""
    
    def test_multi_day_backtest(
        self,
        parquet_storage,
        temp_parquet_dir,
        mock_session_config,
        mock_time_manager
    ):
        """Test validation for multi-day backtest."""
        # Setup: 3-day backtest
        mock_time_manager.backtest_start_date = date(2025, 7, 1)
        mock_time_manager.backtest_end_date = date(2025, 7, 3)
        
        # Write data for all 3 days
        for day in [1, 2, 3]:
            for symbol in ["AAPL", "GOOGL"]:
                write_test_bars_parquet(
                    temp_parquet_dir, symbol, "1m",
                    datetime(2025, 7, day, 13, 30, 0, tzinfo=timezone.utc),
                    390
                )
        
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        data_checker = create_parquet_data_checker(parquet_storage)
        
        # Validate
        result = coordinator.validate_requirements(data_checker)
        
        # Should pass for all 3 days
        assert result.valid is True
    
    def test_partial_date_range_passes(
        self,
        parquet_storage,
        temp_parquet_dir,
        mock_session_config,
        mock_time_manager
    ):
        """Test validation passes if ANY data in range (per-day not required).
        
        NOTE: Validator checks existence in date range, not per-day completeness.
        Day-by-day validation would be too strict for real-world data gaps.
        Quality checks handle completeness separately.
        """
        # Setup: 3-day backtest
        mock_time_manager.backtest_start_date = date(2025, 7, 1)
        mock_time_manager.backtest_end_date = date(2025, 7, 3)
        
        # Only write data for day 1 and 2, day 3 has no data
        for day in [1, 2]:
            for symbol in ["AAPL", "GOOGL"]:
                write_test_bars_parquet(
                    temp_parquet_dir, symbol, "1m",
                    datetime(2025, 7, day, 13, 30, 0, tzinfo=timezone.utc),
                    390
                )
        # Day 3 missing, but that's OK - validation checks range existence
        
        coordinator = StreamRequirementsCoordinator(
            mock_session_config,
            mock_time_manager
        )
        
        data_checker = create_parquet_data_checker(parquet_storage)
        
        # Validate
        result = coordinator.validate_requirements(data_checker)
        
        # Should PASS - has data in range (days 1-2)
        # Per-day completeness is handled by quality checks, not validation
        assert result.valid is True
        assert result.required_base_interval == "1m"
