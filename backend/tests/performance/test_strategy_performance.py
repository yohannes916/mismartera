"""Performance tests for strategy framework.

These tests measure:
- Throughput (notifications/sec)
- Latency (notification -> signal time)
- Memory usage
- CPU usage
- Backpressure detection
"""
import pytest
import time
import psutil
import os
from unittest.mock import Mock
from collections import deque

from app.strategies.manager import StrategyManager
from app.strategies.thread import StrategyThread
from app.strategies.base import BaseStrategy


# Test Strategies
# =============================================================================

class FastStrategy(BaseStrategy):
    """Fast strategy that processes quickly."""
    
    def __init__(self, name, config):
        super().__init__(name, config)
        self.processed_count = 0
    
    def get_subscriptions(self):
        return [("AAPL", "5m")]
    
    def on_bars(self, symbol, interval):
        self.processed_count += 1
        return []


class SlowStrategy(BaseStrategy):
    """Slow strategy that simulates heavy processing."""
    
    def __init__(self, name, config):
        super().__init__(name, config)
        self.processed_count = 0
    
    def get_subscriptions(self):
        return [("AAPL", "5m")]
    
    def on_bars(self, symbol, interval):
        time.sleep(0.01)  # 10ms processing time
        self.processed_count += 1
        return []


# Fixtures
# =============================================================================

@pytest.fixture
def mock_system_manager():
    """Create mock SystemManager."""
    mock = Mock()
    mock.session_config = Mock()
    mock.session_config.session_data_config = Mock()
    mock.session_config.session_data_config.strategies = []
    mock.session_config.backtest_config = Mock()
    mock.session_config.backtest_config.speed_multiplier = 0
    mock.mode = Mock()
    mock.mode.value = "backtest"
    
    session_data = Mock()
    session_data.get_bars_ref.return_value = deque()
    session_data.get_bar_quality.return_value = 100.0
    mock.get_session_data.return_value = session_data
    
    time_manager = Mock()
    mock.get_time_manager.return_value = time_manager
    
    return mock


# Throughput Tests
# =============================================================================

def test_throughput_single_strategy(mock_system_manager, benchmark):
    """Benchmark throughput with single strategy."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = FastStrategy(name="fast", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager._build_subscription_map()
    manager.start_strategies()
    
    time.sleep(0.1)  # Let thread start
    
    def send_notifications():
        """Send 1000 notifications."""
        for i in range(1000):
            manager.notify_strategies("AAPL", "5m", "bars")
    
    # Benchmark notification sending
    result = benchmark(send_notifications)
    
    time.sleep(1.0)  # Let strategies process
    manager.stop_strategies()
    
    # Calculate throughput
    metrics = manager.get_metrics()
    processed = metrics['total_notifications_processed']
    print(f"\nProcessed: {processed}/1000 notifications")
    print(f"Throughput: {processed} notifications/sec")


def test_throughput_multiple_strategies(mock_system_manager):
    """Test throughput with multiple strategies."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    # Create 5 fast strategies
    context = manager._create_context()
    mode = manager._determine_mode()
    
    for i in range(5):
        strategy = FastStrategy(name=f"fast{i}", config={})
        thread = StrategyThread(strategy, context, mode)
        manager._strategy_threads.append(thread)
    
    manager._build_subscription_map()
    manager.start_strategies()
    
    time.sleep(0.1)
    
    start_time = time.time()
    
    # Send 1000 notifications
    for i in range(1000):
        manager.notify_strategies("AAPL", "5m", "bars")
    
    elapsed = time.time() - start_time
    
    time.sleep(1.0)  # Let strategies process
    manager.stop_strategies()
    
    # Calculate throughput
    throughput = 1000 / elapsed
    print(f"\nNotification throughput: {throughput:.0f} notifications/sec")
    
    metrics = manager.get_metrics()
    total_processed = metrics['total_notifications_processed']
    print(f"Total processed (all strategies): {total_processed}")
    
    # Should handle high throughput
    assert throughput > 100  # At least 100 notifications/sec


# Latency Tests
# =============================================================================

def test_latency_notification_to_processing(mock_system_manager):
    """Test latency from notification to processing."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = FastStrategy(name="fast", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager._build_subscription_map()
    manager.start_strategies()
    
    time.sleep(0.1)
    
    latencies = []
    
    for i in range(100):
        start = time.time()
        manager.notify_strategies("AAPL", "5m", "bars")
        
        # Wait for processing
        time.sleep(0.01)
        
        # Approximate latency (actual latency would need timing in strategy)
        latencies.append((time.time() - start) * 1000)  # Convert to ms
    
    manager.stop_strategies()
    
    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
    
    print(f"\nLatency stats (ms):")
    print(f"  Average: {avg_latency:.2f}")
    print(f"  Max: {max_latency:.2f}")
    print(f"  P95: {p95_latency:.2f}")
    
    # Latency should be reasonable (includes 10ms sleep, so expect ~10-15ms)
    assert avg_latency < 20.0  # Average < 20ms (includes sleep time)


def test_latency_with_slow_strategy(mock_system_manager):
    """Test latency with slow strategy (simulating heavy processing)."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = SlowStrategy(name="slow", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager._build_subscription_map()
    manager.start_strategies()
    
    time.sleep(0.1)
    
    # Send 10 notifications
    start_time = time.time()
    for i in range(10):
        manager.notify_strategies("AAPL", "5m", "bars")
    
    time.sleep(0.5)  # Let process
    elapsed = time.time() - start_time
    
    manager.stop_strategies()
    
    # Get processing metrics
    metrics = manager.get_metrics()
    avg_processing_time = metrics['strategies'][0]['avg_processing_time_ms']
    
    print(f"\nSlow strategy stats:")
    print(f"  Avg processing time: {avg_processing_time:.2f}ms")
    print(f"  Total elapsed: {elapsed:.2f}s")
    
    # Should track slow processing
    assert avg_processing_time >= 10.0  # At least 10ms per notification


# Memory Tests
# =============================================================================

def test_memory_usage_baseline(mock_system_manager):
    """Test baseline memory usage."""
    process = psutil.Process(os.getpid())
    
    # Baseline memory
    baseline_mem = process.memory_info().rss / 1024 / 1024  # MB
    
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    # Create strategy
    strategy = FastStrategy(name="fast", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager.start_strategies()
    
    time.sleep(0.1)
    
    # Memory after startup
    after_mem = process.memory_info().rss / 1024 / 1024  # MB
    
    manager.stop_strategies()
    
    memory_increase = after_mem - baseline_mem
    
    print(f"\nMemory usage:")
    print(f"  Baseline: {baseline_mem:.2f} MB")
    print(f"  After: {after_mem:.2f} MB")
    print(f"  Increase: {memory_increase:.2f} MB")
    
    # Memory increase should be reasonable
    assert memory_increase < 50.0  # Less than 50MB increase


def test_memory_usage_under_load(mock_system_manager):
    """Test memory usage under load."""
    process = psutil.Process(os.getpid())
    
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = FastStrategy(name="fast", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager.start_strategies()
    
    time.sleep(0.1)
    
    mem_before = process.memory_info().rss / 1024 / 1024
    
    # Send many notifications
    for i in range(10000):
        manager.notify_strategies("AAPL", "5m", "bars")
    
    time.sleep(1.0)
    
    mem_after = process.memory_info().rss / 1024 / 1024
    
    manager.stop_strategies()
    
    mem_delta = mem_after - mem_before
    
    print(f"\nMemory under load:")
    print(f"  Before: {mem_before:.2f} MB")
    print(f"  After: {mem_after:.2f} MB")
    print(f"  Delta: {mem_delta:.2f} MB")
    
    # Should not have significant memory leak
    assert mem_delta < 100.0  # Less than 100MB increase


# Scalability Tests
# =============================================================================

def test_scalability_many_strategies(mock_system_manager):
    """Test scalability with many strategies."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    # Create 20 strategies
    context = manager._create_context()
    mode = manager._determine_mode()
    
    for i in range(20):
        strategy = FastStrategy(name=f"s{i}", config={})
        thread = StrategyThread(strategy, context, mode)
        manager._strategy_threads.append(thread)
    
    manager._build_subscription_map()
    
    start_time = time.time()
    result = manager.start_strategies()
    startup_time = time.time() - start_time
    
    assert result is True
    
    time.sleep(0.1)
    
    # Send notifications
    for i in range(100):
        manager.notify_strategies("AAPL", "5m", "bars")
    
    time.sleep(0.5)
    
    manager.stop_strategies()
    
    print(f"\nScalability (20 strategies):")
    print(f"  Startup time: {startup_time:.3f}s")
    
    metrics = manager.get_metrics()
    print(f"  Total processed: {metrics['total_notifications_processed']}")
    
    # Should handle many strategies
    assert startup_time < 2.0


def test_scalability_many_subscriptions(mock_system_manager):
    """Test scalability with many subscriptions."""
    
    class ManySubsStrategy(BaseStrategy):
        def get_subscriptions(self):
            # Subscribe to 50 different symbols
            return [(f"SYM{i}", "5m") for i in range(50)]
        
        def on_bars(self, symbol, interval):
            return []
    
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = ManySubsStrategy(name="many_subs", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    
    start_time = time.time()
    manager._build_subscription_map()
    build_time = time.time() - start_time
    
    subscriptions = manager.get_all_subscriptions()
    
    print(f"\nSubscription scalability:")
    print(f"  Subscriptions: {len(subscriptions)}")
    print(f"  Build time: {build_time * 1000:.2f}ms")
    
    # Should handle many subscriptions efficiently
    assert len(subscriptions) == 50
    assert build_time < 0.1  # Less than 100ms


# Backpressure Tests
# =============================================================================

def test_backpressure_detection_data_driven(mock_system_manager):
    """Test backpressure detection in data-driven mode."""
    # Configure for data-driven
    mock_system_manager.session_config.backtest_config.speed_multiplier = 0
    
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    # Use slow strategy
    strategy = SlowStrategy(name="slow", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager.start_strategies()
    
    time.sleep(0.1)
    
    # Send notifications faster than strategy can process
    for i in range(50):
        manager.notify_strategies("AAPL", "5m", "bars")
    
    # Check queue size (backpressure indicator)
    queue_size = thread.get_queue_size()
    
    print(f"\nBackpressure (data-driven):")
    print(f"  Queue size: {queue_size}")
    
    time.sleep(1.0)
    manager.stop_strategies()
    
    # Queue should have built up (backpressure)
    # Note: In data-driven mode, this actually demonstrates blocking


def test_backpressure_detection_clock_driven(mock_system_manager):
    """Test backpressure detection in clock-driven mode."""
    # Configure for clock-driven
    mock_system_manager.session_config.backtest_config.speed_multiplier = 10
    
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = SlowStrategy(name="slow", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager.start_strategies()
    
    time.sleep(0.1)
    
    # Send many notifications quickly
    for i in range(100):
        manager.notify_strategies("AAPL", "5m", "bars")
    
    # Wait with timeout
    result = manager.wait_for_strategies(timeout=0.1)
    
    time.sleep(0.5)
    manager.stop_strategies()
    
    metrics = manager.get_metrics()
    
    print(f"\nBackpressure (clock-driven):")
    print(f"  Wait result: {result}")
    print(f"  Overruns: {metrics['strategies'][0].get('overruns', 0)}")
    
    # In clock-driven mode, should detect overruns


# Performance Summary
# =============================================================================

def test_performance_summary(mock_system_manager):
    """Generate comprehensive performance summary."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = FastStrategy(name="fast", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager._build_subscription_map()
    
    # Startup
    start_startup = time.time()
    manager.start_strategies()
    startup_time = time.time() - start_startup
    
    time.sleep(0.1)
    
    # Throughput test
    start_throughput = time.time()
    for i in range(1000):
        manager.notify_strategies("AAPL", "5m", "bars")
    throughput_time = time.time() - start_throughput
    
    time.sleep(0.5)
    
    # Shutdown
    start_shutdown = time.time()
    manager.stop_strategies()
    shutdown_time = time.time() - start_shutdown
    
    metrics = manager.get_metrics()
    
    print("\n" + "="*60)
    print("PERFORMANCE SUMMARY")
    print("="*60)
    print(f"Startup time:           {startup_time*1000:.2f}ms")
    print(f"Shutdown time:          {shutdown_time*1000:.2f}ms")
    print(f"Throughput:             {1000/throughput_time:.0f} notifications/sec")
    print(f"Notifications sent:     1000")
    print(f"Notifications processed: {metrics['total_notifications_processed']}")
    print(f"Avg processing time:    {metrics['strategies'][0]['avg_processing_time_ms']:.2f}ms")
    print(f"Max processing time:    {metrics['strategies'][0]['max_processing_time_ms']:.2f}ms")
    print("="*60)


if __name__ == "__main__":
    # Can run individual performance tests
    pytest.main([__file__, "-v", "-s"])
