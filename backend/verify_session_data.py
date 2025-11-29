#!/usr/bin/env python3
"""
Quick verification script for SessionData without pytest dependency.
"""

import time
from app.data.session_data import SessionData


class MockBar:
    """Simple bar object for testing."""
    def __init__(self, timestamp, open, high, low, close, volume):
        self.timestamp = timestamp
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


def test_zero_copy():
    """Test zero-copy behavior."""
    print("Testing zero-copy behavior...")
    session_data = SessionData()
    bar1 = MockBar("2025-01-01 09:30", 100, 101, 99, 100.5, 1000)
    bar2 = MockBar("2025-01-01 09:31", 100.5, 102, 100, 101.5, 1200)
    
    session_data.append_bar("AAPL", "1m", bar1)
    session_data.append_bar("AAPL", "1m", bar2)
    
    bars_ref1 = session_data.get_bars("AAPL", "1m")
    bars_ref2 = session_data.get_bars("AAPL", "1m")
    
    # Verify same object reference
    assert bars_ref1 is bars_ref2, "FAILED: get_bars returns different objects"
    assert id(bars_ref1) == id(bars_ref2), "FAILED: Different memory addresses"
    assert bars_ref1[0] is bar1, "FAILED: Bar not same object"
    
    print("✓ Zero-copy verified: Same object references")


def test_performance():
    """Test append and get performance."""
    print("\nTesting performance...")
    session_data = SessionData()
    bar = MockBar("2025-01-01 09:30", 100, 101, 99, 100.5, 1000)
    
    # Warm up
    for _ in range(100):
        session_data.append_bar("AAPL", "1m", bar)
    
    # Test append
    iterations = 10000
    start = time.perf_counter()
    for _ in range(iterations):
        session_data.append_bar("AAPL", "1m", bar)
    duration = time.perf_counter() - start
    append_time_us = (duration / iterations) * 1_000_000
    
    print(f"✓ Append performance: {append_time_us:.3f} μs/operation")
    assert append_time_us < 10.0, f"Append too slow: {append_time_us:.3f} μs"
    
    # Test get_bars
    iterations = 100000
    start = time.perf_counter()
    for _ in range(iterations):
        bars = session_data.get_bars("AAPL", "1m")
    duration = time.perf_counter() - start
    get_time_us = (duration / iterations) * 1_000_000
    
    print(f"✓ Get bars performance: {get_time_us:.3f} μs/operation")
    assert get_time_us < 10.0, f"get_bars too slow: {get_time_us:.3f} μs"


def test_basic_api():
    """Test basic API methods."""
    print("\nTesting basic API...")
    session_data = SessionData()
    
    # Bars
    bar = MockBar("2025-01-01 09:30", 100, 101, 99, 100.5, 1000)
    session_data.append_bar("AAPL", "1m", bar)
    assert session_data.get_bar_count("AAPL", "1m") == 1
    print("✓ Bar operations work")
    
    # Historical indicators
    session_data.set_historical_indicator("high_52w", 245.67)
    assert session_data.get_historical_indicator("high_52w") == 245.67
    assert session_data.has_historical_indicator("high_52w")
    print("✓ Historical indicator operations work")
    
    # Real-time indicators
    session_data.set_realtime_indicator("AAPL", "rsi", 65.4)
    assert session_data.get_realtime_indicator("AAPL", "rsi") == 65.4
    print("✓ Real-time indicator operations work")
    
    # Quality metrics
    session_data.set_quality_metric("AAPL", "1m", 98.5)
    assert session_data.get_quality_metric("AAPL", "1m") == 98.5
    assert session_data.get_quality_metric("RIVN", "1m") == 100.0  # Default
    print("✓ Quality metric operations work")
    
    # Clear
    session_data.clear()
    assert session_data.get_bar_count("AAPL", "1m") == 0
    print("✓ Clear operation works")


def test_stats():
    """Test statistics."""
    print("\nTesting statistics...")
    session_data = SessionData()
    
    session_data.append_bar("AAPL", "1m", MockBar("2025-01-01 09:30", 100, 101, 99, 100.5, 1000))
    session_data.append_bar("AAPL", "1m", MockBar("2025-01-01 09:31", 100.5, 102, 100, 101.5, 1200))
    session_data.append_bar("RIVN", "1m", MockBar("2025-01-01 09:30", 50, 51, 49, 50.5, 2000))
    session_data.set_historical_indicator("high_52w", 245.67)
    
    stats = session_data.get_stats()
    assert "AAPL" in stats["symbols"]
    assert "RIVN" in stats["symbols"]
    assert stats["bar_counts"]["AAPL"]["1m"] == 2
    assert stats["bar_counts"]["RIVN"]["1m"] == 1
    
    repr_str = repr(session_data)
    assert "SessionData" in repr_str
    
    print("✓ Statistics and repr work")
    print(f"  Stats: {stats}")
    print(f"  Repr: {repr_str}")


if __name__ == "__main__":
    print("=" * 60)
    print("SessionData Verification")
    print("=" * 60)
    
    try:
        test_zero_copy()
        test_performance()
        test_basic_api()
        test_stats()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nSessionData is ready for use!")
        print("- Zero-copy behavior verified")
        print("- Performance targets met (<10μs)")
        print("- All API methods working correctly")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
