"""Unit tests for derived bars computation."""
import pytest
from datetime import datetime, timedelta
from app.managers.data_manager.derived_bars import (
    compute_derived_bars,
    compute_all_derived_intervals,
    align_bars_to_interval,
    validate_derived_bars
)
from app.models.trading import BarData


def create_test_bars(count: int, base_time: datetime, base_price: float = 150.0) -> list[BarData]:
    """Helper to create a sequence of test bars."""
    bars = []
    for i in range(count):
        bar = BarData(
            symbol="AAPL",
            timestamp=base_time + timedelta(minutes=i),
            open=base_price + i * 0.1,
            high=base_price + i * 0.1 + 1.0,
            low=base_price + i * 0.1 - 1.0,
            close=base_price + i * 0.1 + 0.5,
            volume=1000 + i * 10
        )
        bars.append(bar)
    return bars


def test_compute_derived_bars_5min():
    """Test 5-minute bar computation from 1-minute bars."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars_1m = create_test_bars(10, base_time)
    
    bars_5m = compute_derived_bars(bars_1m, interval=5)
    
    assert len(bars_5m) == 2  # 10 / 5 = 2
    
    # Check first 5m bar
    assert bars_5m[0].timestamp == base_time
    assert bars_5m[0].open == bars_1m[0].open
    assert bars_5m[0].close == bars_1m[4].close
    assert bars_5m[0].high == max(b.high for b in bars_1m[:5])
    assert bars_5m[0].low == min(b.low for b in bars_1m[:5])
    assert bars_5m[0].volume == sum(b.volume for b in bars_1m[:5])


def test_compute_derived_bars_15min():
    """Test 15-minute bar computation."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars_1m = create_test_bars(30, base_time)
    
    bars_15m = compute_derived_bars(bars_1m, interval=15)
    
    assert len(bars_15m) == 2  # 30 / 15 = 2


def test_compute_derived_bars_incomplete():
    """Test handling of incomplete bars at end."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars_1m = create_test_bars(12, base_time)  # 12 bars
    
    bars_5m = compute_derived_bars(bars_1m, interval=5)
    
    assert len(bars_5m) == 2  # Only complete bars: 10 / 5 = 2
    # Last 2 bars (incomplete) should be skipped


def test_compute_derived_bars_empty():
    """Test with empty input."""
    bars_5m = compute_derived_bars([], interval=5)
    
    assert len(bars_5m) == 0


def test_compute_derived_bars_invalid_interval():
    """Test with invalid interval."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars_1m = create_test_bars(10, base_time)
    
    with pytest.raises(ValueError):
        compute_derived_bars(bars_1m, interval=0)
    
    with pytest.raises(ValueError):
        compute_derived_bars(bars_1m, interval=-5)


def test_compute_derived_bars_with_gap():
    """Test derived bar computation with gap in source data."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars_1m = create_test_bars(4, base_time)
    
    # Add bar with gap
    bars_1m.append(BarData(
        symbol="AAPL",
        timestamp=base_time + timedelta(minutes=6),  # Gap at minute 4-5
        open=151.0,
        high=152.0,
        low=150.0,
        close=151.5,
        volume=1100
    ))
    
    bars_5m = compute_derived_bars(bars_1m, interval=5)
    
    # Should skip due to gap
    assert len(bars_5m) == 0


def test_compute_derived_bars_ohlc_relationship():
    """Test that OHLC relationship is maintained."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars_1m = create_test_bars(10, base_time)
    
    bars_5m = compute_derived_bars(bars_1m, interval=5)
    
    for bar in bars_5m:
        assert bar.low <= bar.open <= bar.high
        assert bar.low <= bar.close <= bar.high
        assert bar.low <= bar.high


def test_compute_all_derived_intervals():
    """Test computing multiple intervals at once."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars_1m = create_test_bars(30, base_time)
    
    all_derived = compute_all_derived_intervals(bars_1m, intervals=[5, 10, 15])
    
    assert len(all_derived) == 3
    assert 5 in all_derived
    assert 10 in all_derived
    assert 15 in all_derived
    
    assert len(all_derived[5]) == 6  # 30 / 5
    assert len(all_derived[10]) == 3  # 30 / 10
    assert len(all_derived[15]) == 2  # 30 / 15


def test_compute_all_derived_intervals_error_handling():
    """Test error handling in multi-interval computation."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars_1m = create_test_bars(10, base_time)
    
    # Include invalid interval
    all_derived = compute_all_derived_intervals(bars_1m, intervals=[5, 0, 10])
    
    # Should have results for valid intervals, empty for invalid
    assert 5 in all_derived
    assert 0 in all_derived
    assert 10 in all_derived
    assert len(all_derived[0]) == 0  # Invalid interval


def test_validate_derived_bars_valid():
    """Test validation with valid derived bars."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars_1m = create_test_bars(20, base_time)
    bars_5m = compute_derived_bars(bars_1m, interval=5)
    
    validation = validate_derived_bars(bars_5m, interval=5, source_1m_count=20)
    
    assert validation["valid"]
    assert validation["count_valid"]
    assert validation["timestamp_valid"]
    assert validation["ohlc_valid"]
    assert validation["expected_count"] == 4
    assert validation["actual_count"] == 4


def test_validate_derived_bars_empty():
    """Test validation with no derived bars."""
    validation = validate_derived_bars([], interval=5, source_1m_count=3)
    
    assert validation["valid"]  # Valid because insufficient source data
    assert validation["expected_count"] == 0
    assert validation["actual_count"] == 0


def test_validate_derived_bars_too_many():
    """Test validation when there are too many derived bars."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars_1m = create_test_bars(10, base_time)
    bars_5m = compute_derived_bars(bars_1m, interval=5)
    
    # Add extra bar
    bars_5m.append(BarData(
        symbol="AAPL",
        timestamp=base_time + timedelta(minutes=10),
        open=152.0,
        high=153.0,
        low=151.0,
        close=152.5,
        volume=5000
    ))
    
    validation = validate_derived_bars(bars_5m, interval=5, source_1m_count=10)
    
    assert not validation["count_valid"]
    assert validation["expected_count"] == 2
    assert validation["actual_count"] == 3


def test_validate_derived_bars_invalid_timestamps():
    """Test validation with invalid timestamp spacing."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars_5m = [
        BarData(
            symbol="AAPL",
            timestamp=base_time,
            open=150.0,
            high=151.0,
            low=149.0,
            close=150.5,
            volume=5000
        ),
        BarData(
            symbol="AAPL",
            timestamp=base_time + timedelta(minutes=6),  # Should be 5
            open=151.0,
            high=152.0,
            low=150.0,
            close=151.5,
            volume=5500
        ),
    ]
    
    validation = validate_derived_bars(bars_5m, interval=5, source_1m_count=10)
    
    assert not validation["timestamp_valid"]


def test_validate_derived_bars_invalid_ohlc():
    """Test validation with invalid OHLC relationship."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars_5m = [
        BarData(
            symbol="AAPL",
            timestamp=base_time,
            open=150.0,
            high=148.0,  # High < Open (invalid!)
            low=149.0,
            close=150.5,
            volume=5000
        ),
    ]
    
    validation = validate_derived_bars(bars_5m, interval=5, source_1m_count=5)
    
    assert not validation["ohlc_valid"]


def test_align_bars_to_interval():
    """Test aligning bars to interval boundaries."""
    session_start = datetime(2025, 1, 1, 9, 30)
    base_time = datetime(2025, 1, 1, 9, 31)  # Start at 9:31 (offset by 1)
    bars_1m = create_test_bars(10, base_time)
    
    aligned = align_bars_to_interval(bars_1m, interval=5, session_start=session_start)
    
    # Should skip first bar to align to 5-minute boundary
    # Next alignment after 9:31 is 9:35 (9:30 + 5min), which is 4 minutes away
    assert len(aligned) == len(bars_1m) - 4


def test_compute_derived_bars_volume_aggregation():
    """Test that volume is correctly aggregated."""
    base_time = datetime(2025, 1, 1, 9, 30)
    
    # Create bars with specific volumes
    bars_1m = []
    for i in range(5):
        bar = BarData(
            symbol="AAPL",
            timestamp=base_time + timedelta(minutes=i),
            open=150.0,
            high=151.0,
            low=149.0,
            close=150.5,
            volume=100 * (i + 1)  # 100, 200, 300, 400, 500
        )
        bars_1m.append(bar)
    
    bars_5m = compute_derived_bars(bars_1m, interval=5)
    
    assert len(bars_5m) == 1
    assert bars_5m[0].volume == 1500  # 100 + 200 + 300 + 400 + 500


def test_compute_derived_bars_price_extremes():
    """Test that high/low are correctly identified."""
    base_time = datetime(2025, 1, 1, 9, 30)
    
    bars_1m = [
        BarData("AAPL", base_time, 150, 151, 149, 150.5, 1000),
        BarData("AAPL", base_time + timedelta(minutes=1), 150.5, 153, 148, 152, 1100),  # Highest high, lowest low
        BarData("AAPL", base_time + timedelta(minutes=2), 152, 152.5, 150, 151, 1200),
        BarData("AAPL", base_time + timedelta(minutes=3), 151, 152, 149.5, 151.5, 1300),
        BarData("AAPL", base_time + timedelta(minutes=4), 151.5, 151.8, 150.5, 151, 1400),
    ]
    
    bars_5m = compute_derived_bars(bars_1m, interval=5)
    
    assert len(bars_5m) == 1
    assert bars_5m[0].high == 153  # Highest from all bars
    assert bars_5m[0].low == 148  # Lowest from all bars


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
