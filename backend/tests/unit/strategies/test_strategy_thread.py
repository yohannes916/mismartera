"""Unit tests for StrategyThread."""
import pytest
import time
import queue
from unittest.mock import Mock, MagicMock, patch

from app.strategies.thread import StrategyThread
from app.strategies.base import BaseStrategy, StrategyContext, Signal, SignalAction


# Test Fixtures
# =============================================================================

class MockStrategy(BaseStrategy):
    """Mock strategy for testing."""
    
    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.on_bars_calls = []
        self.signals_to_return = []
        self.processing_delay = 0.0
        self.should_raise = False
    
    def get_subscriptions(self):
        return [("AAPL", "5m")]
    
    def on_bars(self, symbol: str, interval: str):
        self.on_bars_calls.append((symbol, interval))
        
        if self.processing_delay > 0:
            time.sleep(self.processing_delay)
        
        if self.should_raise:
            raise ValueError("Test error")
        
        return self.signals_to_return


@pytest.fixture
def mock_context():
    """Create mock StrategyContext."""
    return Mock(spec=StrategyContext)


@pytest.fixture
def mock_strategy():
    """Create mock strategy."""
    strategy = MockStrategy(name="test_strategy", config={})
    strategy.setup = Mock(return_value=True)
    strategy.teardown = Mock()
    return strategy


@pytest.fixture
def strategy_thread(mock_strategy, mock_context):
    """Create StrategyThread."""
    return StrategyThread(
        strategy=mock_strategy,
        context=mock_context,
        mode="data-driven"
    )


# Initialization Tests
# =============================================================================

def test_strategy_thread_initialization(strategy_thread, mock_strategy):
    """Test StrategyThread initialization."""
    assert strategy_thread.strategy is mock_strategy
    assert strategy_thread.mode == "data-driven"
    assert strategy_thread.name == "Strategy-test_strategy"
    assert strategy_thread.daemon is True
    assert strategy_thread._stop_event.is_set() is False


def test_strategy_thread_queue_created(strategy_thread):
    """Test that notification queue is created."""
    assert strategy_thread._queue is not None
    assert strategy_thread._queue.empty()


def test_strategy_thread_subscription_created(strategy_thread):
    """Test that StreamSubscription is created."""
    assert strategy_thread._subscription is not None
    assert strategy_thread._subscription._mode == "data-driven"


def test_strategy_thread_metrics_initialized(strategy_thread):
    """Test that metrics are initialized to zero."""
    assert strategy_thread._notifications_processed == 0
    assert strategy_thread._signals_generated == 0
    assert strategy_thread._errors == 0
    assert strategy_thread._total_processing_time == 0.0
    assert strategy_thread._max_processing_time == 0.0


# Notification Tests
# =============================================================================

def test_notify_adds_to_queue(strategy_thread):
    """Test that notify() adds to queue."""
    assert strategy_thread._queue.qsize() == 0
    
    strategy_thread.notify("AAPL", "5m", "bars")
    
    assert strategy_thread._queue.qsize() == 1


def test_notify_multiple_items(strategy_thread):
    """Test notifying multiple items."""
    strategy_thread.notify("AAPL", "5m", "bars")
    strategy_thread.notify("GOOGL", "5m", "bars")
    strategy_thread.notify("AAPL", "15m", "bars")
    
    assert strategy_thread._queue.qsize() == 3


def test_notify_with_full_queue(strategy_thread):
    """Test notify() when queue is full."""
    # Replace the unlimited queue with a limited one for testing
    import queue as queue_module
    old_queue = strategy_thread._queue
    strategy_thread._queue = queue_module.Queue(maxsize=5)
    
    # Fill queue
    for i in range(5):
        strategy_thread._queue.put_nowait(("TEST", "5m", "bars"))
    
    initial_errors = strategy_thread._errors
    
    # Try to add one more - should silently drop and increment error count
    strategy_thread.notify("AAPL", "5m", "bars")
    
    # Error count should increase
    assert strategy_thread._errors == initial_errors + 1
    # Queue size should still be at max
    assert strategy_thread.get_queue_size() == 5
    
    # Restore original queue
    strategy_thread._queue = old_queue


def test_get_queue_size(strategy_thread):
    """Test get_queue_size()."""
    assert strategy_thread.get_queue_size() == 0
    
    strategy_thread.notify("AAPL", "5m", "bars")
    assert strategy_thread.get_queue_size() == 1
    
    strategy_thread.notify("GOOGL", "5m", "bars")
    assert strategy_thread.get_queue_size() == 2


# Processing Tests
# =============================================================================

def test_process_notification_calls_strategy(strategy_thread, mock_strategy):
    """Test that _process_notification calls strategy.on_bars()."""
    strategy_thread._process_notification(("AAPL", "5m", "bars"))
    
    assert len(mock_strategy.on_bars_calls) == 1
    assert mock_strategy.on_bars_calls[0] == ("AAPL", "5m")


def test_process_notification_updates_metrics(strategy_thread, mock_strategy):
    """Test that _process_notification updates metrics."""
    assert strategy_thread._notifications_processed == 0
    
    strategy_thread._process_notification(("AAPL", "5m", "bars"))
    
    assert strategy_thread._notifications_processed == 1
    assert strategy_thread._total_processing_time > 0
    assert strategy_thread._max_processing_time > 0


def test_process_notification_with_signals(strategy_thread, mock_strategy):
    """Test processing notification that generates signals."""
    mock_strategy.signals_to_return = [
        Signal(symbol="AAPL", action=SignalAction.BUY),
        Signal(symbol="AAPL", action=SignalAction.SELL)
    ]
    
    strategy_thread._process_notification(("AAPL", "5m", "bars"))
    
    assert strategy_thread._signals_generated == 2


def test_process_notification_handles_error(strategy_thread, mock_strategy, caplog):
    """Test that errors in strategy are caught and logged."""
    mock_strategy.should_raise = True
    
    with caplog.at_level('ERROR'):
        strategy_thread._process_notification(("AAPL", "5m", "bars"))
    
    assert "Error processing" in caplog.text
    assert strategy_thread._errors == 1


def test_process_notification_signals_ready(strategy_thread):
    """Test that _process_notification signals ready."""
    # Mock the subscription
    strategy_thread._subscription.signal_ready = Mock()
    
    strategy_thread._process_notification(("AAPL", "5m", "bars"))
    
    strategy_thread._subscription.signal_ready.assert_called_once()


def test_process_notification_signals_ready_even_on_error(strategy_thread, mock_strategy):
    """Test that signal_ready is called even if strategy raises error."""
    mock_strategy.should_raise = True
    strategy_thread._subscription.signal_ready = Mock()
    
    strategy_thread._process_notification(("AAPL", "5m", "bars"))
    
    # Should still signal ready to not block system
    strategy_thread._subscription.signal_ready.assert_called_once()


# Thread Lifecycle Tests
# =============================================================================

def test_stop_sets_stop_event(strategy_thread):
    """Test that stop() sets stop event."""
    assert not strategy_thread._stop_event.is_set()
    
    strategy_thread.stop()
    
    assert strategy_thread._stop_event.is_set()


def test_stop_adds_sentinel_to_queue(strategy_thread):
    """Test that stop() adds sentinel to queue."""
    strategy_thread.stop()
    
    # Sentinel should be in queue
    item = strategy_thread._queue.get(timeout=1.0)
    assert item is None


def test_thread_exits_on_sentinel(strategy_thread, mock_strategy):
    """Test that thread exits when it receives sentinel."""
    # Start thread
    strategy_thread.start()
    
    # Give it time to start
    time.sleep(0.1)
    
    # Stop thread
    strategy_thread.stop()
    
    # Wait for exit
    strategy_thread.join(timeout=2.0)
    
    # Should have exited
    assert not strategy_thread.is_alive()


def test_thread_processes_queue_items(strategy_thread, mock_strategy):
    """Test that thread processes items from queue."""
    # Add notifications
    strategy_thread.notify("AAPL", "5m", "bars")
    strategy_thread.notify("GOOGL", "5m", "bars")
    
    # Start thread
    strategy_thread.start()
    
    # Give it time to process
    time.sleep(0.2)
    
    # Stop thread
    strategy_thread.stop()
    strategy_thread.join(timeout=2.0)
    
    # Should have processed both notifications
    assert len(mock_strategy.on_bars_calls) == 2


def test_thread_handles_timeout(strategy_thread, mock_strategy):
    """Test that thread continues after queue timeout."""
    # Start thread
    strategy_thread.start()
    
    # Give it time to hit timeout
    time.sleep(1.5)
    
    # Stop thread
    strategy_thread.stop()
    strategy_thread.join(timeout=2.0)
    
    # Should have exited cleanly
    assert not strategy_thread.is_alive()


# Subscription Tests
# =============================================================================

def test_get_subscription_returns_subscription(strategy_thread):
    """Test get_subscription() returns StreamSubscription."""
    subscription = strategy_thread.get_subscription()
    
    assert subscription is not None
    assert subscription is strategy_thread._subscription


# Metrics Tests
# =============================================================================

def test_get_metrics_initial_state(strategy_thread):
    """Test get_metrics() returns initial state."""
    metrics = strategy_thread.get_metrics()
    
    assert metrics['strategy_name'] == 'test_strategy'
    assert metrics['running'] is False
    assert metrics['mode'] == 'data-driven'
    assert metrics['notifications_processed'] == 0
    assert metrics['signals_generated'] == 0
    assert metrics['errors'] == 0
    assert metrics['queue_size'] == 0
    assert metrics['avg_processing_time_ms'] == 0.0
    assert metrics['max_processing_time_ms'] == 0.0


def test_get_metrics_after_processing(strategy_thread, mock_strategy):
    """Test get_metrics() after processing notifications."""
    # Process some notifications
    strategy_thread.notify("AAPL", "5m", "bars")
    strategy_thread.notify("GOOGL", "5m", "bars")
    
    strategy_thread.start()
    time.sleep(0.2)
    strategy_thread.stop()
    strategy_thread.join(timeout=2.0)
    
    metrics = strategy_thread.get_metrics()
    
    assert metrics['notifications_processed'] == 2
    assert metrics['avg_processing_time_ms'] > 0
    assert metrics['max_processing_time_ms'] > 0


def test_get_metrics_with_signals(strategy_thread, mock_strategy):
    """Test get_metrics() tracks signals generated."""
    mock_strategy.signals_to_return = [
        Signal(symbol="AAPL", action=SignalAction.BUY)
    ]
    
    strategy_thread.notify("AAPL", "5m", "bars")
    strategy_thread.start()
    time.sleep(0.2)
    strategy_thread.stop()
    strategy_thread.join(timeout=2.0)
    
    metrics = strategy_thread.get_metrics()
    
    assert metrics['signals_generated'] >= 1


def test_get_metrics_with_errors(strategy_thread, mock_strategy):
    """Test get_metrics() tracks errors."""
    mock_strategy.should_raise = True
    
    strategy_thread.notify("AAPL", "5m", "bars")
    strategy_thread.start()
    time.sleep(0.2)
    strategy_thread.stop()
    strategy_thread.join(timeout=2.0)
    
    metrics = strategy_thread.get_metrics()
    
    assert metrics['errors'] >= 1


# Performance Tests
# =============================================================================

def test_processing_time_tracked(strategy_thread, mock_strategy):
    """Test that processing time is tracked accurately."""
    # Set delay in mock strategy
    mock_strategy.processing_delay = 0.1
    
    strategy_thread._process_notification(("AAPL", "5m", "bars"))
    
    # Should have tracked the time
    assert strategy_thread._total_processing_time >= 0.1
    assert strategy_thread._max_processing_time >= 0.1


def test_max_processing_time_updated(strategy_thread, mock_strategy):
    """Test that max_processing_time tracks maximum."""
    # First call - fast
    mock_strategy.processing_delay = 0.01
    strategy_thread._process_notification(("AAPL", "5m", "bars"))
    max1 = strategy_thread._max_processing_time
    
    # Second call - slower
    mock_strategy.processing_delay = 0.05
    strategy_thread._process_notification(("GOOGL", "5m", "bars"))
    max2 = strategy_thread._max_processing_time
    
    assert max2 > max1
    assert max2 >= 0.05


# Mode Tests
# =============================================================================

def test_data_driven_mode(mock_strategy, mock_context):
    """Test thread created with data-driven mode."""
    thread = StrategyThread(
        strategy=mock_strategy,
        context=mock_context,
        mode="data-driven"
    )
    
    assert thread.mode == "data-driven"
    assert thread._subscription._mode == "data-driven"


def test_clock_driven_mode(mock_strategy, mock_context):
    """Test thread created with clock-driven mode."""
    thread = StrategyThread(
        strategy=mock_strategy,
        context=mock_context,
        mode="clock-driven"
    )
    
    assert thread.mode == "clock-driven"
    assert thread._subscription._mode == "clock-driven"


def test_live_mode(mock_strategy, mock_context):
    """Test thread created with live mode."""
    thread = StrategyThread(
        strategy=mock_strategy,
        context=mock_context,
        mode="live"
    )
    
    assert thread.mode == "live"
    assert thread._subscription._mode == "live"


# Edge Cases
# =============================================================================

def test_join_timeout(strategy_thread):
    """Test join() with timeout."""
    # Start thread
    strategy_thread.start()
    
    # Try to join with short timeout (shouldn't exit yet)
    strategy_thread.join(timeout=0.1)
    
    # Should still be alive
    assert strategy_thread.is_alive()
    
    # Stop and join properly
    strategy_thread.stop()
    strategy_thread.join(timeout=2.0)


def test_multiple_stop_calls(strategy_thread):
    """Test calling stop() multiple times."""
    strategy_thread.stop()
    strategy_thread.stop()
    strategy_thread.stop()
    
    # Should not raise error
    assert strategy_thread._stop_event.is_set()


def test_notify_after_stop(strategy_thread, caplog):
    """Test notifying after thread stopped."""
    strategy_thread.stop()
    
    # Should still add to queue (thread may not have exited yet)
    strategy_thread.notify("AAPL", "5m", "bars")
    
    # Queue should have sentinel + notification
    assert strategy_thread._queue.qsize() >= 1


# Cleanup Tests
# =============================================================================

def test_thread_cleanup(strategy_thread, mock_strategy):
    """Test that thread cleans up properly on exit."""
    strategy_thread.start()
    time.sleep(0.1)
    
    strategy_thread.stop()
    strategy_thread.join(timeout=2.0)
    
    assert not strategy_thread.is_alive()
    assert strategy_thread._stop_event.is_set()
