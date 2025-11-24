"""Unit tests for gap detection module."""
import pytest
from datetime import datetime, timedelta
from app.managers.data_manager.gap_detection import (
    detect_gaps,
    calculate_bar_quality,
    generate_expected_timestamps,
    group_consecutive_timestamps,
    merge_overlapping_gaps,
    get_gap_summary,
    GapInfo
)
from app.models.trading import BarData


def create_test_bar(symbol: str, timestamp: datetime, price: float = 150.0) -> BarData:
    """Helper to create a test bar."""
    return BarData(
        symbol=symbol,
        timestamp=timestamp,
        open=price,
        high=price + 1.0,
        low=price - 1.0,
        close=price + 0.5,
        volume=1000
    )


def test_generate_expected_timestamps():
    """Test generating expected timestamps for a time range."""
    start = datetime(2025, 1, 1, 9, 30)
    end = datetime(2025, 1, 1, 9, 35)  # 5 minutes
    
    timestamps = generate_expected_timestamps(start, end)
    
    assert len(timestamps) == 5
    assert datetime(2025, 1, 1, 9, 30) in timestamps
    assert datetime(2025, 1, 1, 9, 34) in timestamps
    assert datetime(2025, 1, 1, 9, 35) not in timestamps  # Exclusive end


def test_group_consecutive_timestamps():
    """Test grouping consecutive missing timestamps."""
    missing = {
        datetime(2025, 1, 1, 9, 31),  # Gap 1
        datetime(2025, 1, 1, 9, 33),  # Gap 2 start
        datetime(2025, 1, 1, 9, 34),  # Gap 2 continue
        datetime(2025, 1, 1, 9, 35),  # Gap 2 end
    }
    
    gaps = group_consecutive_timestamps(missing)
    
    assert len(gaps) == 2
    assert gaps[0] == (datetime(2025, 1, 1, 9, 31), datetime(2025, 1, 1, 9, 31))
    assert gaps[1] == (datetime(2025, 1, 1, 9, 33), datetime(2025, 1, 1, 9, 35))


def test_detect_gaps_no_gaps():
    """Test gap detection with perfect data (no gaps)."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars = [create_test_bar("AAPL", base_time + timedelta(minutes=i)) for i in range(10)]
    
    gaps = detect_gaps(
        symbol="AAPL",
        session_start=base_time,
        current_time=base_time + timedelta(minutes=10),
        existing_bars=bars
    )
    
    assert len(gaps) == 0


def test_detect_gaps_single_gap():
    """Test gap detection with one missing bar."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars = [
        create_test_bar("AAPL", base_time),
        # Missing 9:31
        create_test_bar("AAPL", base_time + timedelta(minutes=2)),
        create_test_bar("AAPL", base_time + timedelta(minutes=3)),
    ]
    
    gaps = detect_gaps(
        symbol="AAPL",
        session_start=base_time,
        current_time=base_time + timedelta(minutes=4),
        existing_bars=bars
    )
    
    assert len(gaps) == 1
    assert gaps[0].symbol == "AAPL"
    assert gaps[0].start_time == base_time + timedelta(minutes=1)
    assert gaps[0].bar_count == 1


def test_detect_gaps_multiple_gaps():
    """Test gap detection with multiple gaps."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars = [
        create_test_bar("AAPL", base_time),
        # Missing 9:31
        create_test_bar("AAPL", base_time + timedelta(minutes=2)),
        # Missing 9:33, 9:34
        create_test_bar("AAPL", base_time + timedelta(minutes=5)),
    ]
    
    gaps = detect_gaps(
        symbol="AAPL",
        session_start=base_time,
        current_time=base_time + timedelta(minutes=6),
        existing_bars=bars
    )
    
    assert len(gaps) == 2
    assert gaps[0].bar_count == 1  # 9:31
    assert gaps[1].bar_count == 2  # 9:33, 9:34


def test_calculate_bar_quality_perfect():
    """Test bar quality calculation with perfect data."""
    session_start = datetime(2025, 1, 1, 9, 30)
    current_time = datetime(2025, 1, 1, 10, 30)  # 60 minutes
    actual_count = 60
    
    quality = calculate_bar_quality(session_start, current_time, actual_count)
    
    assert quality == 100.0


def test_calculate_bar_quality_missing_bars():
    """Test bar quality calculation with missing bars."""
    session_start = datetime(2025, 1, 1, 9, 30)
    current_time = datetime(2025, 1, 1, 10, 30)  # 60 minutes
    actual_count = 58  # 2 bars missing
    
    quality = calculate_bar_quality(session_start, current_time, actual_count)
    
    assert quality == pytest.approx(96.67, rel=0.1)


def test_calculate_bar_quality_no_time_elapsed():
    """Test bar quality when no time has elapsed."""
    session_start = datetime(2025, 1, 1, 9, 30)
    current_time = datetime(2025, 1, 1, 9, 30)
    actual_count = 0
    
    quality = calculate_bar_quality(session_start, current_time, actual_count)
    
    assert quality == 100.0


def test_merge_overlapping_gaps():
    """Test merging overlapping gaps."""
    gaps = [
        GapInfo(
            symbol="AAPL",
            start_time=datetime(2025, 1, 1, 9, 31),
            end_time=datetime(2025, 1, 1, 9, 33),
            bar_count=2
        ),
        GapInfo(
            symbol="AAPL",
            start_time=datetime(2025, 1, 1, 9, 32),  # Overlaps with first
            end_time=datetime(2025, 1, 1, 9, 35),
            bar_count=3
        ),
    ]
    
    merged = merge_overlapping_gaps(gaps)
    
    assert len(merged) == 1
    assert merged[0].start_time == datetime(2025, 1, 1, 9, 31)
    assert merged[0].end_time == datetime(2025, 1, 1, 9, 35)


def test_get_gap_summary_no_gaps():
    """Test gap summary with no gaps."""
    summary = get_gap_summary([])
    
    assert summary["gap_count"] == 0
    assert summary["total_missing_bars"] == 0
    assert summary["quality"] == 100.0


def test_get_gap_summary_with_gaps():
    """Test gap summary with gaps."""
    gaps = [
        GapInfo("AAPL", datetime(2025, 1, 1, 9, 31), datetime(2025, 1, 1, 9, 32), 1),
        GapInfo("AAPL", datetime(2025, 1, 1, 9, 35), datetime(2025, 1, 1, 9, 38), 3),
    ]
    
    summary = get_gap_summary(gaps)
    
    assert summary["gap_count"] == 2
    assert summary["total_missing_bars"] == 4
    assert summary["largest_gap"] == 3
    assert summary["average_gap_size"] == 2.0


def test_gap_info_str():
    """Test GapInfo string representation."""
    gap = GapInfo(
        symbol="AAPL",
        start_time=datetime(2025, 1, 1, 9, 31),
        end_time=datetime(2025, 1, 1, 9, 33),
        bar_count=2,
        retry_count=1
    )
    
    gap_str = str(gap)
    
    assert "AAPL" in gap_str
    assert "2 bars" in gap_str
    assert "retries=1" in gap_str


def test_detect_gaps_large_dataset():
    """Test gap detection with large dataset."""
    base_time = datetime(2025, 1, 1, 9, 30)
    
    # Create 390 bars (full trading day) with some gaps
    bars = []
    for i in range(390):
        if i % 50 == 25:  # Skip every 50th bar starting at 25
            continue
        bars.append(create_test_bar("AAPL", base_time + timedelta(minutes=i)))
    
    gaps = detect_gaps(
        symbol="AAPL",
        session_start=base_time,
        current_time=base_time + timedelta(minutes=390),
        existing_bars=bars
    )
    
    assert len(gaps) == 7  # 390 / 50 = 7 full cycles, each with 1 gap
    assert all(gap.bar_count == 1 for gap in gaps)


def test_gap_detection_with_different_intervals():
    """Test gap detection with 5-minute intervals."""
    base_time = datetime(2025, 1, 1, 9, 30)
    bars = [
        create_test_bar("AAPL", base_time),
        # Missing 9:35
        create_test_bar("AAPL", base_time + timedelta(minutes=10)),
    ]
    
    gaps = detect_gaps(
        symbol="AAPL",
        session_start=base_time,
        current_time=base_time + timedelta(minutes=15),
        existing_bars=bars,
        interval_minutes=5
    )
    
    assert len(gaps) == 1
    assert gaps[0].bar_count == 1  # One 5-minute bar missing


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
