"""Integration tests for strategy subscription routing."""
import pytest
import time
from unittest.mock import Mock
from collections import deque

from app.strategies.manager import StrategyManager
from app.strategies.thread import StrategyThread
from app.strategies.base import BaseStrategy, Signal, SignalAction


# Test Strategies
# =============================================================================

class SingleSubStrategy(BaseStrategy):
    """Strategy with single subscription."""
    
    def __init__(self, name, config):
        super().__init__(name, config)
        self.notifications = []
    
    def get_subscriptions(self):
        return [("AAPL", "5m")]
    
    def on_bars(self, symbol, interval):
        self.notifications.append((symbol, interval))
        return []


class MultiSubStrategy(BaseStrategy):
    """Strategy with multiple subscriptions."""
    
    def __init__(self, name, config):
        super().__init__(name, config)
        self.notifications = []
    
    def get_subscriptions(self):
        return [
            ("AAPL", "5m"),
            ("GOOGL", "5m"),
            ("TSLA", "15m")
        ]
    
    def on_bars(self, symbol, interval):
        self.notifications.append((symbol, interval))
        return []


class OverlappingStrategy1(BaseStrategy):
    """First strategy with overlapping subscriptions."""
    
    def __init__(self, name, config):
        super().__init__(name, config)
        self.notifications = []
    
    def get_subscriptions(self):
        return [("AAPL", "5m"), ("GOOGL", "5m")]
    
    def on_bars(self, symbol, interval):
        self.notifications.append((symbol, interval))
        return []


class OverlappingStrategy2(BaseStrategy):
    """Second strategy with overlapping subscriptions."""
    
    def __init__(self, name, config):
        super().__init__(name, config)
        self.notifications = []
    
    def get_subscriptions(self):
        return [("AAPL", "5m"), ("TSLA", "15m")]
    
    def on_bars(self, symbol, interval):
        self.notifications.append((symbol, interval))
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


# Subscription Map Tests
# =============================================================================

def test_single_strategy_single_subscription(mock_system_manager):
    """Test subscription map with single strategy, single subscription."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = SingleSubStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager._build_subscription_map()
    
    # Check subscription map
    subscriptions = manager.get_all_subscriptions()
    assert len(subscriptions) == 1
    assert ("AAPL", "5m") in subscriptions
    
    # Check thread mapping
    threads = manager.get_subscribed_threads("AAPL", "5m")
    assert len(threads) == 1
    assert threads[0] is thread


def test_single_strategy_multiple_subscriptions(mock_system_manager):
    """Test subscription map with single strategy, multiple subscriptions."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = MultiSubStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager._build_subscription_map()
    
    # Check all subscriptions mapped
    subscriptions = manager.get_all_subscriptions()
    assert len(subscriptions) == 3
    assert ("AAPL", "5m") in subscriptions
    assert ("GOOGL", "5m") in subscriptions
    assert ("TSLA", "15m") in subscriptions


def test_multiple_strategies_overlapping_subscriptions(mock_system_manager):
    """Test subscription map with overlapping subscriptions."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy1 = OverlappingStrategy1(name="s1", config={})
    strategy2 = OverlappingStrategy2(name="s2", config={})
    
    context = manager._create_context()
    mode = manager._determine_mode()
    
    thread1 = StrategyThread(strategy1, context, mode)
    thread2 = StrategyThread(strategy2, context, mode)
    
    manager._strategy_threads = [thread1, thread2]
    manager._build_subscription_map()
    
    # AAPL 5m should have both threads
    threads = manager.get_subscribed_threads("AAPL", "5m")
    assert len(threads) == 2
    assert thread1 in threads
    assert thread2 in threads
    
    # GOOGL 5m should have only thread1
    threads = manager.get_subscribed_threads("GOOGL", "5m")
    assert len(threads) == 1
    assert thread1 in threads
    
    # TSLA 15m should have only thread2
    threads = manager.get_subscribed_threads("TSLA", "15m")
    assert len(threads) == 1
    assert thread2 in threads


def test_get_subscribed_threads_no_match(mock_system_manager):
    """Test get_subscribed_threads with no match."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = SingleSubStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager._build_subscription_map()
    
    # Query non-existent subscription
    threads = manager.get_subscribed_threads("MSFT", "5m")
    assert len(threads) == 0


# Notification Routing Tests
# =============================================================================

def test_notify_routes_to_correct_strategy(mock_system_manager):
    """Test notify_strategies routes to correct strategy."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = SingleSubStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager._build_subscription_map()
    manager.start_strategies()
    
    time.sleep(0.1)
    
    # Notify via manager
    manager.notify_strategies("AAPL", "5m", "bars")
    
    time.sleep(0.2)
    manager.stop_strategies()
    
    # Strategy should have received notification
    assert ("AAPL", "5m") in strategy.notifications


def test_notify_routes_to_multiple_strategies(mock_system_manager):
    """Test notify_strategies routes to all subscribed strategies."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy1 = OverlappingStrategy1(name="s1", config={})
    strategy2 = OverlappingStrategy2(name="s2", config={})
    
    context = manager._create_context()
    mode = manager._determine_mode()
    
    thread1 = StrategyThread(strategy1, context, mode)
    thread2 = StrategyThread(strategy2, context, mode)
    
    manager._strategy_threads = [thread1, thread2]
    manager._build_subscription_map()
    manager.start_strategies()
    
    time.sleep(0.1)
    
    # Notify AAPL 5m (both subscribed)
    manager.notify_strategies("AAPL", "5m", "bars")
    
    time.sleep(0.2)
    manager.stop_strategies()
    
    # Both strategies should have received notification
    assert ("AAPL", "5m") in strategy1.notifications
    assert ("AAPL", "5m") in strategy2.notifications


def test_notify_only_subscribed_strategies(mock_system_manager):
    """Test notify_strategies only routes to subscribed strategies."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy1 = OverlappingStrategy1(name="s1", config={})
    strategy2 = OverlappingStrategy2(name="s2", config={})
    
    context = manager._create_context()
    mode = manager._determine_mode()
    
    thread1 = StrategyThread(strategy1, context, mode)
    thread2 = StrategyThread(strategy2, context, mode)
    
    manager._strategy_threads = [thread1, thread2]
    manager._build_subscription_map()
    manager.start_strategies()
    
    time.sleep(0.1)
    
    # Notify GOOGL 5m (only strategy1 subscribed)
    manager.notify_strategies("GOOGL", "5m", "bars")
    
    time.sleep(0.2)
    manager.stop_strategies()
    
    # Only strategy1 should have received notification
    assert ("GOOGL", "5m") in strategy1.notifications
    assert ("GOOGL", "5m") not in strategy2.notifications


def test_notify_no_subscribers(mock_system_manager):
    """Test notify_strategies with no subscribers."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = SingleSubStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager._build_subscription_map()
    manager.start_strategies()
    
    time.sleep(0.1)
    
    # Notify symbol not subscribed to
    manager.notify_strategies("MSFT", "5m", "bars")
    
    time.sleep(0.2)
    manager.stop_strategies()
    
    # Strategy should not have received notification
    assert ("MSFT", "5m") not in strategy.notifications


# Multiple Notification Tests
# =============================================================================

def test_multiple_notifications_same_subscription(mock_system_manager):
    """Test multiple notifications to same subscription."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = SingleSubStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager._build_subscription_map()
    manager.start_strategies()
    
    time.sleep(0.1)
    
    # Send multiple notifications
    for i in range(5):
        manager.notify_strategies("AAPL", "5m", "bars")
    
    time.sleep(0.5)
    manager.stop_strategies()
    
    # Strategy should have received all notifications
    assert len(strategy.notifications) == 5
    assert all(n == ("AAPL", "5m") for n in strategy.notifications)


def test_multiple_notifications_different_subscriptions(mock_system_manager):
    """Test multiple notifications to different subscriptions."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = MultiSubStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager._build_subscription_map()
    manager.start_strategies()
    
    time.sleep(0.1)
    
    # Send notifications to different subscriptions
    manager.notify_strategies("AAPL", "5m", "bars")
    manager.notify_strategies("GOOGL", "5m", "bars")
    manager.notify_strategies("TSLA", "15m", "bars")
    
    time.sleep(0.3)
    manager.stop_strategies()
    
    # Strategy should have received all
    assert ("AAPL", "5m") in strategy.notifications
    assert ("GOOGL", "5m") in strategy.notifications
    assert ("TSLA", "15m") in strategy.notifications


# Subscription Rebuild Tests
# =============================================================================

def test_rebuild_subscriptions_after_symbol_added(mock_system_manager):
    """Test rebuilding subscription map after symbol added."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = SingleSubStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager._build_subscription_map()
    
    # Initial subscriptions
    initial_subs = manager.get_all_subscriptions()
    assert len(initial_subs) == 1
    
    # Simulate symbol added (strategy updates subscriptions)
    # Note: In real scenario, strategy.on_symbol_added() might update subscriptions
    manager.notify_symbol_added("GOOGL")
    
    # Subscription map should be rebuilt (same in this case since strategy doesn't change)
    new_subs = manager.get_all_subscriptions()
    assert len(new_subs) == 1


# Performance Tests
# =============================================================================

def test_subscription_routing_performance(mock_system_manager):
    """Test that subscription routing is efficient."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    # Create 10 strategies with various subscriptions
    strategies = []
    threads = []
    context = manager._create_context()
    mode = manager._determine_mode()
    
    for i in range(10):
        strategy = MultiSubStrategy(name=f"s{i}", config={})
        thread = StrategyThread(strategy, context, mode)
        strategies.append(strategy)
        threads.append(thread)
    
    manager._strategy_threads = threads
    
    # Build subscription map (should be fast)
    import time as time_module
    start = time_module.time()
    manager._build_subscription_map()
    elapsed = time_module.time() - start
    
    # Should complete in < 100ms
    assert elapsed < 0.1
    
    # Should have all subscriptions
    all_subs = manager.get_all_subscriptions()
    assert len(all_subs) >= 3  # At least the 3 unique subscriptions


def test_notification_routing_overhead(mock_system_manager):
    """Test notification routing has minimal overhead."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = SingleSubStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager._build_subscription_map()
    manager.start_strategies()
    
    time.sleep(0.1)
    
    # Time multiple notifications
    import time as time_module
    start = time_module.time()
    
    for i in range(100):
        manager.notify_strategies("AAPL", "5m", "bars")
    
    elapsed = time_module.time() - start
    
    manager.stop_strategies()
    
    # 100 notifications should complete quickly (< 100ms for routing only)
    # Note: Actual processing happens async in threads
    assert elapsed < 0.1
