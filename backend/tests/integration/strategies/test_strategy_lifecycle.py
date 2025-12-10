"""Integration tests for strategy lifecycle (load, setup, run, teardown)."""
import pytest
import time
from unittest.mock import Mock, patch
from collections import deque

from app.strategies.manager import StrategyManager
from app.strategies.thread import StrategyThread
from app.strategies.base import BaseStrategy, StrategyContext
from app.models.strategy_config import StrategyConfig


# Test Strategy
# =============================================================================

class TestLifecycleStrategy(BaseStrategy):
    """Test strategy that tracks lifecycle events."""
    
    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.events = []
    
    def setup(self, context):
        self.events.append('setup')
        return super().setup(context)
    
    def teardown(self, context):
        self.events.append('teardown')
        super().teardown(context)
    
    def get_subscriptions(self):
        return [("AAPL", "5m")]
    
    def on_bars(self, symbol, interval):
        self.events.append(f'on_bars:{symbol}:{interval}')
        return []


# Fixtures
# =============================================================================

@pytest.fixture
def mock_system_manager():
    """Create mock SystemManager with realistic structure."""
    mock = Mock()
    
    # Session config
    mock.session_config = Mock()
    mock.session_config.session_data_config = Mock()
    mock.session_config.session_data_config.strategies = []
    mock.session_config.backtest_config = Mock()
    mock.session_config.backtest_config.speed_multiplier = 0
    
    # Mode
    mock.mode = Mock()
    mock.mode.value = "backtest"
    
    # Session data
    session_data = Mock()
    session_data.get_bars_ref.return_value = deque()
    session_data.get_bar_quality.return_value = 100.0
    mock.get_session_data.return_value = session_data
    
    # Time manager
    time_manager = Mock()
    time_manager.get_current_time.return_value = Mock()
    mock.get_time_manager.return_value = time_manager
    
    return mock


@pytest.fixture
def strategy_config():
    """Create strategy config."""
    return StrategyConfig(
        module="test_module",
        enabled=True,
        config={}
    )


# Lifecycle Tests
# =============================================================================

def test_strategy_full_lifecycle(mock_system_manager, strategy_config):
    """Test complete strategy lifecycle: load -> setup -> run -> teardown."""
    # Create manager
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    # Create strategy and thread manually (simulating load)
    strategy = TestLifecycleStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager._build_subscription_map()
    
    # 1. Setup
    assert 'setup' not in strategy.events
    result = manager.start_strategies()
    assert result is True
    assert 'setup' in strategy.events
    
    # 2. Run - send notification
    time.sleep(0.1)  # Let thread start
    thread.notify("AAPL", "5m", "bars")
    time.sleep(0.2)  # Let it process
    
    assert 'on_bars:AAPL:5m' in strategy.events
    
    # 3. Teardown
    manager.stop_strategies()
    assert 'teardown' in strategy.events


def test_strategy_setup_failure(mock_system_manager):
    """Test strategy lifecycle when setup fails."""
    
    class FailingSetupStrategy(TestLifecycleStrategy):
        def setup(self, context):
            self.events.append('setup_failed')
            return False  # Fail setup
    
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = FailingSetupStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    
    # Setup should fail
    result = manager.start_strategies()
    assert result is False
    assert 'setup_failed' in strategy.events
    assert 'on_bars:AAPL:5m' not in strategy.events


def test_strategy_multiple_notifications(mock_system_manager):
    """Test strategy processes multiple notifications."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = TestLifecycleStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager._build_subscription_map()
    manager.start_strategies()
    
    time.sleep(0.1)
    
    # Send multiple notifications
    thread.notify("AAPL", "5m", "bars")
    thread.notify("AAPL", "5m", "bars")
    thread.notify("AAPL", "5m", "bars")
    
    time.sleep(0.3)
    manager.stop_strategies()
    
    # Should have processed all 3
    on_bars_count = sum(1 for e in strategy.events if e.startswith('on_bars'))
    assert on_bars_count == 3


def test_strategy_graceful_shutdown(mock_system_manager):
    """Test strategy shuts down gracefully."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = TestLifecycleStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager.start_strategies()
    
    time.sleep(0.1)
    
    # Add notification that won't be processed
    thread.notify("AAPL", "5m", "bars")
    
    # Stop immediately
    manager.stop_strategies()
    
    # Should have called teardown
    assert 'teardown' in strategy.events
    
    # Thread should have exited
    assert not thread.is_alive()


# Context Integration Tests
# =============================================================================

def test_strategy_uses_context_services(mock_system_manager):
    """Test strategy can use context services."""
    
    class ContextUsingStrategy(BaseStrategy):
        def __init__(self, name, config):
            super().__init__(name, config)
            self.used_services = []
        
        def get_subscriptions(self):
            return [("AAPL", "5m")]
        
        def on_bars(self, symbol, interval):
            # Use context services
            current_time = self.context.get_current_time()
            self.used_services.append('get_current_time')
            
            bars = self.context.get_bars(symbol, interval)
            self.used_services.append('get_bars')
            
            quality = self.context.get_bar_quality(symbol, interval)
            self.used_services.append('get_bar_quality')
            
            return []
    
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = ContextUsingStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager.start_strategies()
    
    time.sleep(0.1)
    
    thread.notify("AAPL", "5m", "bars")
    time.sleep(0.2)
    
    manager.stop_strategies()
    
    # Should have used all services
    assert 'get_current_time' in strategy.used_services
    assert 'get_bars' in strategy.used_services
    assert 'get_bar_quality' in strategy.used_services


# Multiple Strategies Tests
# =============================================================================

def test_multiple_strategies_independent(mock_system_manager):
    """Test multiple strategies run independently."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    # Create two strategies
    strategy1 = TestLifecycleStrategy(name="strategy1", config={})
    strategy2 = TestLifecycleStrategy(name="strategy2", config={})
    
    context = manager._create_context()
    mode = manager._determine_mode()
    
    thread1 = StrategyThread(strategy1, context, mode)
    thread2 = StrategyThread(strategy2, context, mode)
    
    manager._strategy_threads = [thread1, thread2]
    manager._build_subscription_map()
    
    manager.start_strategies()
    time.sleep(0.1)
    
    # Notify both
    thread1.notify("AAPL", "5m", "bars")
    thread2.notify("AAPL", "5m", "bars")
    
    time.sleep(0.3)
    manager.stop_strategies()
    
    # Both should have processed
    assert 'on_bars:AAPL:5m' in strategy1.events
    assert 'on_bars:AAPL:5m' in strategy2.events
    
    # Both should have been torn down
    assert 'teardown' in strategy1.events
    assert 'teardown' in strategy2.events


def test_multiple_strategies_different_subscriptions(mock_system_manager):
    """Test strategies with different subscriptions."""
    
    class Strategy1(BaseStrategy):
        def get_subscriptions(self):
            return [("AAPL", "5m")]
        
        def on_bars(self, symbol, interval):
            return []
    
    class Strategy2(BaseStrategy):
        def get_subscriptions(self):
            return [("GOOGL", "15m")]
        
        def on_bars(self, symbol, interval):
            return []
    
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy1 = Strategy1(name="s1", config={})
    strategy2 = Strategy2(name="s2", config={})
    
    context = manager._create_context()
    mode = manager._determine_mode()
    
    thread1 = StrategyThread(strategy1, context, mode)
    thread2 = StrategyThread(strategy2, context, mode)
    
    manager._strategy_threads = [thread1, thread2]
    manager._build_subscription_map()
    
    # Check subscription map
    subscriptions = manager.get_all_subscriptions()
    assert ("AAPL", "5m") in subscriptions
    assert ("GOOGL", "15m") in subscriptions


# Error Handling Tests
# =============================================================================

def test_strategy_error_doesnt_crash_system(mock_system_manager):
    """Test that error in one strategy doesn't crash system."""
    
    class ErrorStrategy(BaseStrategy):
        def get_subscriptions(self):
            return [("AAPL", "5m")]
        
        def on_bars(self, symbol, interval):
            raise ValueError("Test error")
    
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = ErrorStrategy(name="error_strategy", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager.start_strategies()
    
    time.sleep(0.1)
    
    # Send notification that will cause error
    thread.notify("AAPL", "5m", "bars")
    time.sleep(0.2)
    
    # Thread should still be alive
    assert thread.is_alive()
    
    # Can still stop cleanly
    manager.stop_strategies()
    assert not thread.is_alive()


# State Tracking Tests
# =============================================================================

def test_manager_tracks_running_state(mock_system_manager):
    """Test that StrategyManager tracks running state."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = TestLifecycleStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    
    assert manager._running is False
    
    manager.start_strategies()
    assert manager._running is True
    
    manager.stop_strategies()
    assert manager._running is False


def test_manager_tracks_initialized_state(mock_system_manager):
    """Test that StrategyManager tracks initialized state."""
    manager = StrategyManager(mock_system_manager)
    
    assert manager._initialized is False
    
    result = manager.initialize()
    assert result is True
    assert manager._initialized is True
    
    manager.shutdown()
    assert manager._initialized is False


# Metrics Integration Tests
# =============================================================================

def test_metrics_tracked_during_lifecycle(mock_system_manager):
    """Test that metrics are tracked throughout lifecycle."""
    manager = StrategyManager(mock_system_manager)
    manager._initialized = True
    
    strategy = TestLifecycleStrategy(name="test", config={})
    context = manager._create_context()
    mode = manager._determine_mode()
    thread = StrategyThread(strategy, context, mode)
    
    manager._strategy_threads = [thread]
    manager.start_strategies()
    
    time.sleep(0.1)
    
    # Send notifications
    for i in range(5):
        thread.notify("AAPL", "5m", "bars")
    
    time.sleep(0.5)
    manager.stop_strategies()
    
    # Get metrics
    metrics = manager.get_metrics()
    
    assert metrics['total_strategies'] == 1
    assert metrics['total_notifications_processed'] >= 5
    assert metrics['strategies'][0]['strategy_name'] == 'test'
