#!/usr/bin/env python3
"""
Quick verification script for PerformanceMetrics without pytest dependency.
"""

import time
from app.monitoring.performance_metrics import PerformanceMetrics, MetricTracker, MetricStats


def test_metric_stats():
    """Test MetricStats running statistics."""
    print("Testing MetricStats...")
    
    stats = MetricStats()
    
    # Record values
    stats.record(1.0)
    stats.record(2.0)
    stats.record(3.0)
    
    assert stats.count == 3
    assert stats.min_value == 1.0
    assert stats.max_value == 3.0
    assert stats.avg_value == 2.0  # (1+2+3)/3
    
    # Record more
    stats.record(0.5)
    assert stats.min_value == 0.5
    assert stats.count == 4
    
    # Reset
    stats.reset()
    assert stats.count == 0
    assert stats.avg_value == 0.0
    
    print("✓ MetricStats running statistics work")


def test_metric_tracker():
    """Test MetricTracker."""
    print("\nTesting MetricTracker...")
    
    tracker = MetricTracker('test_metric')
    
    # Record values
    tracker.record(0.001)  # 1ms
    tracker.record(0.002)  # 2ms
    tracker.record(0.003)  # 3ms
    
    stats = tracker.get_stats()
    assert stats['count'] == 3
    assert stats['min'] == 0.001
    assert stats['max'] == 0.003
    assert abs(stats['avg'] - 0.002) < 1e-9
    
    # Reset
    tracker.reset()
    stats = tracker.get_stats()
    assert stats['count'] == 0
    
    print("✓ MetricTracker works")


def test_timer_utilities():
    """Test timer utilities."""
    print("\nTesting timer utilities...")
    
    metrics = PerformanceMetrics()
    
    # Test timer
    start = metrics.start_timer()
    time.sleep(0.01)  # 10ms
    elapsed = metrics.elapsed_time(start)
    
    assert 0.009 < elapsed < 0.015, f"Expected ~0.01s, got {elapsed:.6f}s"
    
    print(f"✓ Timer utilities work (measured: {elapsed*1000:.2f}ms)")


def test_recording_methods():
    """Test all recording methods."""
    print("\nTesting recording methods...")
    
    metrics = PerformanceMetrics()
    
    # Analysis engine
    start = metrics.start_timer()
    time.sleep(0.001)
    metrics.record_analysis_engine(start)
    assert metrics.analysis_engine.stats.count == 1
    
    # Data processor
    start = metrics.start_timer()
    time.sleep(0.001)
    metrics.record_data_processor(start)
    assert metrics.data_processor.stats.count == 1
    
    # Initial load
    metrics.record_initial_load(1.23)
    assert metrics.data_loading_initial == 1.23
    
    # Subsequent load
    start = metrics.start_timer()
    time.sleep(0.001)
    metrics.record_subsequent_load(start)
    assert metrics.data_loading_subsequent.stats.count == 1
    
    # Session gap
    start = metrics.start_timer()
    time.sleep(0.001)
    metrics.record_session_gap(start)
    assert metrics.session_gap.stats.count == 1
    
    # Session duration
    start = metrics.start_timer()
    time.sleep(0.001)
    metrics.record_session_duration(start)
    assert metrics.session_duration.stats.count == 1
    
    # Trading days
    metrics.increment_trading_days()
    metrics.increment_trading_days()
    assert metrics.backtest_trading_days == 2
    
    print("✓ All recording methods work")


def test_backtest_timing():
    """Test backtest timing."""
    print("\nTesting backtest timing...")
    
    metrics = PerformanceMetrics()
    
    # Start backtest
    metrics.start_backtest()
    assert metrics.backtest_start_time is not None
    assert metrics.backtest_trading_days == 0
    
    time.sleep(0.01)
    
    # Simulate some work
    metrics.increment_trading_days()
    metrics.increment_trading_days()
    
    # End backtest
    metrics.end_backtest()
    assert metrics.backtest_end_time is not None
    
    # Get summary
    summary = metrics.get_backtest_summary()
    assert summary['trading_days'] == 2
    assert summary['total_time'] is not None
    assert summary['total_time'] > 0.009
    assert summary['avg_per_day'] is not None
    
    print(f"✓ Backtest timing works (total: {summary['total_time']:.4f}s)")


def test_session_report():
    """Test session report formatting."""
    print("\nTesting session report...")
    
    metrics = PerformanceMetrics()
    
    # Record some data
    for _ in range(5):
        start = metrics.start_timer()
        time.sleep(0.001)
        metrics.record_analysis_engine(start)
    
    for _ in range(3):
        start = metrics.start_timer()
        time.sleep(0.001)
        metrics.record_data_processor(start)
    
    # Get report
    report = metrics.format_report('session')
    
    assert "Performance Metrics (Session)" in report
    assert "Analysis Engine:" in report
    assert "Cycles: 5" in report
    assert "Data Processor:" in report
    assert "Items: 3" in report
    
    print("✓ Session report formatting works")
    print("\nSample report:")
    print(report)


def test_backtest_report():
    """Test backtest report formatting."""
    print("\nTesting backtest report...")
    
    metrics = PerformanceMetrics()
    
    # Simulate full backtest
    metrics.start_backtest()
    metrics.record_initial_load(1.23)
    
    for _ in range(3):  # 3 trading days
        metrics.increment_trading_days()
        
        # Session gap
        start = metrics.start_timer()
        time.sleep(0.001)
        metrics.record_session_gap(start)
        
        # Session work
        start = metrics.start_timer()
        time.sleep(0.005)
        metrics.record_session_duration(start)
        
        # Subsequent load
        if metrics.backtest_trading_days > 1:
            start = metrics.start_timer()
            time.sleep(0.002)
            metrics.record_subsequent_load(start)
    
    metrics.end_backtest()
    
    # Get report
    report = metrics.format_report('backtest')
    
    assert "Performance Metrics Summary:" in report
    assert "Data Loading (All Symbols):" in report
    assert "Initial Load: 1.23 s" in report
    assert "Subsequent Load:" in report
    assert "Session Lifecycle:" in report
    assert "Sessions: 3" in report
    assert "Backtest Summary:" in report
    assert "Trading Days: 3" in report
    
    print("✓ Backtest report formatting works")
    print("\nSample report:")
    print(report)


def test_reset_operations():
    """Test reset operations."""
    print("\nTesting reset operations...")
    
    metrics = PerformanceMetrics()
    
    # Record some data
    start = metrics.start_timer()
    time.sleep(0.001)
    metrics.record_analysis_engine(start)
    
    start = metrics.start_timer()
    time.sleep(0.001)
    metrics.record_data_processor(start)
    
    metrics.record_initial_load(1.23)
    metrics.increment_trading_days()
    
    # Reset session metrics
    metrics.reset_session_metrics()
    assert metrics.analysis_engine.stats.count == 0
    assert metrics.data_processor.stats.count == 0
    assert metrics.data_loading_initial == 1.23  # NOT reset
    assert metrics.backtest_trading_days == 1  # NOT reset
    
    # Reset all
    metrics.reset_all()
    assert metrics.data_loading_initial is None
    assert metrics.backtest_trading_days == 0
    
    print("✓ Reset operations work correctly")


def test_minimal_overhead():
    """Test that metrics have minimal overhead."""
    print("\nTesting overhead...")
    
    metrics = PerformanceMetrics()
    
    # Measure overhead of recording
    iterations = 10000
    start_time = time.perf_counter()
    for _ in range(iterations):
        start = metrics.start_timer()
        metrics.record_analysis_engine(start)
    total_time = time.perf_counter() - start_time
    
    overhead_per_op = (total_time / iterations) * 1_000_000  # microseconds
    
    print(f"✓ Overhead per operation: {overhead_per_op:.3f} μs")
    assert overhead_per_op < 10.0, f"Overhead too high: {overhead_per_op:.3f} μs"


def test_invalid_report_type():
    """Test invalid report type error."""
    print("\nTesting error handling...")
    
    metrics = PerformanceMetrics()
    
    try:
        metrics.format_report('invalid')
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Invalid report_type" in str(e)
        print(f"✓ Invalid report type correctly rejected: {e}")


def test_repr():
    """Test string representation."""
    print("\nTesting repr...")
    
    metrics = PerformanceMetrics()
    metrics.increment_trading_days()
    
    start = metrics.start_timer()
    time.sleep(0.001)
    metrics.record_analysis_engine(start)
    
    repr_str = repr(metrics)
    assert "PerformanceMetrics" in repr_str
    assert "trading_days=1" in repr_str
    
    print(f"✓ Repr works: {repr_str}")


if __name__ == "__main__":
    print("=" * 60)
    print("PerformanceMetrics Verification")
    print("=" * 60)
    
    try:
        test_metric_stats()
        test_metric_tracker()
        test_timer_utilities()
        test_recording_methods()
        test_backtest_timing()
        test_session_report()
        test_backtest_report()
        test_reset_operations()
        test_minimal_overhead()
        test_invalid_report_type()
        test_repr()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nPerformanceMetrics is ready for use!")
        print("- Running statistics working correctly")
        print("- Minimal overhead (<10μs per operation)")
        print("- Report formatting matches specification")
        print("- Reset operations correct")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
