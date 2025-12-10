"""Unit tests for StrategyManager."""
import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from app.strategies.manager import StrategyManager
from app.strategies.base import BaseStrategy
from app.models.strategy_config import StrategyConfig


# Test Fixtures
# =============================================================================

class DummyStrategy(BaseStrategy):
    """Dummy strategy for testing."""
    
    def get_subscriptions(self):
        return [("AAPL", "5m"), ("GOOGL", "5m")]
    
    def on_bars(self, symbol, interval):
        return []


@pytest.fixture
def mock_system_manager():
    """Create mock SystemManager."""
    mock = Mock()
    
    # Mock session_config
    mock.session_config = Mock()
    mock.session_config.session_data_config = Mock()
    mock.session_config.session_data_config.strategies = []
    
    # Mock mode
    mock.mode = Mock()
    mock.mode.value = "backtest"
    
    # Mock session_config.backtest_config
    mock.session_config.backtest_config = Mock()
    mock.session_config.backtest_config.speed_multiplier = 0
    
    # Mock get_session_data
    mock.get_session_data = Mock()
    
    # Mock get_time_manager
    mock.get_time_manager = Mock()
    
    return mock


@pytest.fixture
def strategy_manager(mock_system_manager):
    """Create StrategyManager."""
    return StrategyManager(mock_system_manager)


# Initialization Tests
# =============================================================================

def test_strategy_manager_initialization(strategy_manager, mock_system_manager):
    """Test StrategyManager initialization."""
    assert strategy_manager._system_manager is mock_system_manager
    assert strategy_manager._strategy_threads == []
    assert strategy_manager._subscriptions == {}
    assert strategy_manager._initialized is False
    assert strategy_manager._running is False


# Initialize Tests
# =============================================================================

def test_initialize_with_no_strategies(strategy_manager, mock_system_manager):
    """Test initialize() with no strategies configured."""
    # No strategies in config
    mock_system_manager.session_config.session_data_config.strategies = []
    
    result = strategy_manager.initialize()
    
    assert result is True
    assert strategy_manager._initialized is True
    assert len(strategy_manager._strategy_threads) == 0


def test_initialize_already_initialized(strategy_manager, caplog):
    """Test initialize() when already initialized."""
    strategy_manager._initialized = True
    
    with caplog.at_level('WARNING'):
        result = strategy_manager.initialize()
    
    assert result is True
    assert "already initialized" in caplog.text


def test_initialize_with_disabled_strategy(strategy_manager, mock_system_manager):
    """Test initialize() skips disabled strategies."""
    # Add disabled strategy to config
    strategy_config = StrategyConfig(
        module="strategies.test_strategy",
        enabled=False,
        config={}
    )
    mock_system_manager.session_config.session_data_config.strategies = [strategy_config]
    
    with patch.object(strategy_manager, '_load_strategy') as mock_load:
        result = strategy_manager.initialize()
    
    assert result is True
    mock_load.assert_not_called()


@patch('app.strategies.manager.importlib.import_module')
def test_initialize_loads_enabled_strategies(mock_import, strategy_manager, mock_system_manager):
    """Test initialize() loads enabled strategies."""
    # Create mock module
    mock_module = Mock()
    mock_module.DummyStrategy = DummyStrategy
    mock_import.return_value = mock_module
    
    # Add enabled strategy to config
    strategy_config = StrategyConfig(
        module="strategies.examples.dummy",
        enabled=True,
        config={}
    )
    mock_system_manager.session_config.session_data_config.strategies = [strategy_config]
    
    result = strategy_manager.initialize()
    
    assert result is True
    assert strategy_manager._initialized is True
    assert len(strategy_manager._strategy_threads) == 1


def test_initialize_build_subscription_map(strategy_manager, mock_system_manager):
    """Test that initialize() builds subscription map."""
    with patch.object(strategy_manager, '_load_strategy', return_value=True):
        with patch.object(strategy_manager, '_build_subscription_map') as mock_build:
            strategy_config = StrategyConfig(
                module="strategies.test",
                enabled=True,
                config={}
            )
            mock_system_manager.session_config.session_data_config.strategies = [strategy_config]
            
            strategy_manager.initialize()
            
            mock_build.assert_called_once()


def test_initialize_handles_load_failure(strategy_manager, mock_system_manager):
    """Test initialize() handles strategy load failure."""
    strategy_config = StrategyConfig(
        module="strategies.nonexistent",
        enabled=True,
        config={}
    )
    mock_system_manager.session_config.session_data_config.strategies = [strategy_config]
    
    result = strategy_manager.initialize()
    
    # Should fail
    assert result is False


# Load Strategy Tests
# =============================================================================

@patch('app.strategies.manager.importlib.import_module')
def test_load_strategy_success(mock_import, strategy_manager):
    """Test _load_strategy() successfully loads strategy."""
    # Create mock module
    mock_module = Mock()
    mock_module.DummyStrategy = DummyStrategy
    mock_import.return_value = mock_module
    
    config = StrategyConfig(
        module="strategies.examples.dummy",
        enabled=True,
        config={}
    )
    
    result = strategy_manager._load_strategy(config)
    
    assert result is True
    assert len(strategy_manager._strategy_threads) == 1


@patch('app.strategies.manager.importlib.import_module')
def test_load_strategy_module_not_found(mock_import, strategy_manager, caplog):
    """Test _load_strategy() handles module not found."""
    mock_import.side_effect = ModuleNotFoundError("Module not found")
    
    config = StrategyConfig(
        module="strategies.nonexistent",
        enabled=True,
        config={}
    )
    
    with caplog.at_level('ERROR'):
        result = strategy_manager._load_strategy(config)
    
    assert result is False
    assert "Failed to load" in caplog.text


@patch('app.strategies.manager.importlib.import_module')
def test_load_strategy_no_strategy_class(mock_import, strategy_manager, caplog):
    """Test _load_strategy() when no strategy class found."""
    # Module with no strategy class
    mock_module = Mock(spec=[])
    mock_import.return_value = mock_module
    
    config = StrategyConfig(
        module="strategies.examples.empty",
        enabled=True,
        config={}
    )
    
    with caplog.at_level('ERROR'):
        result = strategy_manager._load_strategy(config)
    
    assert result is False
    assert "No strategy class found" in caplog.text


# Find Strategy Class Tests
# =============================================================================

def test_find_strategy_class_exact_match(strategy_manager):
    """Test _find_strategy_class() finds exact name match."""
    # Create a mock module with the strategy class
    import types
    mock_module = types.ModuleType('test_module')
    mock_module.SimpleMaCrossStrategy = DummyStrategy
    
    strategy_class = strategy_manager._find_strategy_class(
        mock_module,
        "strategies.examples.simple_ma_cross"
    )
    
    assert strategy_class is DummyStrategy


def test_find_strategy_class_no_match(strategy_manager):
    """Test _find_strategy_class() returns None when no match."""
    mock_module = Mock(spec=[])
    
    with patch('builtins.dir', return_value=[]):
        strategy_class = strategy_manager._find_strategy_class(
            mock_module,
            "strategies.examples.nonexistent"
        )
    
    assert strategy_class is None


# Context Creation Tests
# =============================================================================

def test_create_context(strategy_manager, mock_system_manager):
    """Test _create_context() creates proper context."""
    mock_session_data = Mock()
    mock_time_manager = Mock()
    
    # Patch the global get_session_data function (SessionData is a singleton)
    with patch('app.strategies.manager.get_session_data', return_value=mock_session_data):
        mock_system_manager.get_time_manager.return_value = mock_time_manager
        mock_system_manager.mode.value = "backtest"
        
        context = strategy_manager._create_context()
        
        assert context.session_data is mock_session_data
        assert context.time_manager is mock_time_manager
        assert context.system_manager is mock_system_manager
        assert context.mode == "backtest"


# Mode Determination Tests
# =============================================================================

def test_determine_mode_live(strategy_manager, mock_system_manager):
    """Test _determine_mode() returns 'live' for live mode."""
    mock_system_manager.mode.value = "live"
    
    mode = strategy_manager._determine_mode()
    
    assert mode == "live"


def test_determine_mode_data_driven(strategy_manager, mock_system_manager):
    """Test _determine_mode() returns 'data-driven' for speed=0."""
    mock_system_manager.mode.value = "backtest"
    mock_system_manager.session_config.backtest_config.speed_multiplier = 0
    
    mode = strategy_manager._determine_mode()
    
    assert mode == "data-driven"


def test_determine_mode_clock_driven(strategy_manager, mock_system_manager):
    """Test _determine_mode() returns 'clock-driven' for speed>0."""
    mock_system_manager.mode.value = "backtest"
    mock_system_manager.session_config.backtest_config.speed_multiplier = 10
    
    mode = strategy_manager._determine_mode()
    
    assert mode == "clock-driven"


# Subscription Map Tests
# =============================================================================

def test_build_subscription_map(strategy_manager):
    """Test _build_subscription_map() creates correct mapping."""
    # Create mock threads
    thread1 = Mock()
    thread1.strategy = Mock()
    thread1.strategy.get_subscriptions.return_value = [
        ("AAPL", "5m"),
        ("GOOGL", "5m")
    ]
    
    thread2 = Mock()
    thread2.strategy = Mock()
    thread2.strategy.get_subscriptions.return_value = [
        ("AAPL", "5m"),
        ("TSLA", "15m")
    ]
    
    strategy_manager._strategy_threads = [thread1, thread2]
    
    strategy_manager._build_subscription_map()
    
    # Check subscriptions
    assert ("AAPL", "5m") in strategy_manager._subscriptions
    assert ("GOOGL", "5m") in strategy_manager._subscriptions
    assert ("TSLA", "15m") in strategy_manager._subscriptions
    
    # AAPL 5m should have both threads
    assert len(strategy_manager._subscriptions[("AAPL", "5m")]) == 2
    
    # GOOGL 5m should have only thread1
    assert len(strategy_manager._subscriptions[("GOOGL", "5m")]) == 1
    
    # TSLA 15m should have only thread2
    assert len(strategy_manager._subscriptions[("TSLA", "15m")]) == 1


def test_get_subscribed_threads(strategy_manager):
    """Test get_subscribed_threads() returns correct threads."""
    thread1 = Mock()
    thread2 = Mock()
    
    strategy_manager._subscriptions = {
        ("AAPL", "5m"): [thread1, thread2],
        ("GOOGL", "5m"): [thread1]
    }
    
    # Get threads for AAPL 5m
    threads = strategy_manager.get_subscribed_threads("AAPL", "5m")
    assert len(threads) == 2
    
    # Get threads for GOOGL 5m
    threads = strategy_manager.get_subscribed_threads("GOOGL", "5m")
    assert len(threads) == 1
    
    # Get threads for non-existent subscription
    threads = strategy_manager.get_subscribed_threads("TSLA", "15m")
    assert len(threads) == 0


def test_get_all_subscriptions(strategy_manager):
    """Test get_all_subscriptions() returns all unique keys."""
    strategy_manager._subscriptions = {
        ("AAPL", "5m"): [Mock()],
        ("GOOGL", "5m"): [Mock()],
        ("TSLA", "15m"): [Mock()]
    }
    
    subscriptions = strategy_manager.get_all_subscriptions()
    
    assert len(subscriptions) == 3
    assert ("AAPL", "5m") in subscriptions
    assert ("GOOGL", "5m") in subscriptions
    assert ("TSLA", "15m") in subscriptions


# Notification Routing Tests
# =============================================================================

def test_notify_strategies(strategy_manager):
    """Test notify_strategies() routes to subscribed threads."""
    thread1 = Mock()
    thread2 = Mock()
    
    strategy_manager._subscriptions = {
        ("AAPL", "5m"): [thread1, thread2]
    }
    
    strategy_manager.notify_strategies("AAPL", "5m", "bars")
    
    thread1.notify.assert_called_once_with("AAPL", "5m", "bars")
    thread2.notify.assert_called_once_with("AAPL", "5m", "bars")


def test_notify_strategies_no_subscribers(strategy_manager):
    """Test notify_strategies() with no subscribers."""
    strategy_manager._subscriptions = {}
    
    # Should not raise error
    strategy_manager.notify_strategies("AAPL", "5m", "bars")


# Wait for Strategies Tests
# =============================================================================

def test_wait_for_strategies_data_driven(strategy_manager, mock_system_manager):
    """Test wait_for_strategies() in data-driven mode (infinite timeout)."""
    mock_system_manager.mode.value = "backtest"
    mock_system_manager.session_config.backtest_config.speed_multiplier = 0
    
    thread = Mock()
    subscription = Mock()
    subscription._overrun_count = 0
    thread.get_subscription.return_value = subscription
    subscription.wait_until_ready.return_value = True
    
    strategy_manager._strategy_threads = [thread]
    
    result = strategy_manager.wait_for_strategies()
    
    assert result is True
    subscription.wait_until_ready.assert_called_once_with(timeout=None)
    subscription.reset.assert_called_once()


def test_wait_for_strategies_clock_driven(strategy_manager, mock_system_manager):
    """Test wait_for_strategies() in clock-driven mode (with timeout)."""
    mock_system_manager.mode.value = "backtest"
    mock_system_manager.session_config.backtest_config.speed_multiplier = 10
    
    thread = Mock()
    subscription = Mock()
    subscription._overrun_count = 0
    thread.get_subscription.return_value = subscription
    subscription.wait_until_ready.return_value = True
    
    strategy_manager._strategy_threads = [thread]
    
    result = strategy_manager.wait_for_strategies(timeout=0.1)
    
    assert result is True
    subscription.wait_until_ready.assert_called_once_with(timeout=0.1)


def test_wait_for_strategies_timeout(strategy_manager, mock_system_manager, caplog):
    """Test wait_for_strategies() handles timeout."""
    mock_system_manager.mode.value = "backtest"
    mock_system_manager.session_config.backtest_config.speed_multiplier = 10
    
    thread = Mock()
    thread.strategy = Mock()
    thread.strategy.name = "slow_strategy"
    subscription = Mock()
    subscription._overrun_count = 5
    thread.get_subscription.return_value = subscription
    subscription.wait_until_ready.return_value = False  # Timeout
    
    strategy_manager._strategy_threads = [thread]
    
    with caplog.at_level('WARNING'):
        result = strategy_manager.wait_for_strategies(timeout=0.1)
    
    assert result is False
    assert "timeout" in caplog.text
    assert "slow_strategy" in caplog.text


# Start/Stop Tests
# =============================================================================

def test_start_strategies_not_initialized(strategy_manager, caplog):
    """Test start_strategies() when not initialized."""
    with caplog.at_level('ERROR'):
        result = strategy_manager.start_strategies()
    
    assert result is False
    assert "not initialized" in caplog.text


def test_start_strategies_already_running(strategy_manager, caplog):
    """Test start_strategies() when already running."""
    strategy_manager._initialized = True
    strategy_manager._running = True
    
    with caplog.at_level('WARNING'):
        result = strategy_manager.start_strategies()
    
    assert result is True
    assert "already running" in caplog.text


def test_start_strategies_success(strategy_manager):
    """Test start_strategies() success."""
    strategy_manager._initialized = True
    
    # Create mock thread
    thread = Mock()
    thread.strategy = Mock()
    thread.strategy.name = "test_strategy"
    thread.strategy.setup.return_value = True
    
    strategy_manager._strategy_threads = [thread]
    
    result = strategy_manager.start_strategies()
    
    assert result is True
    assert strategy_manager._running is True
    thread.strategy.setup.assert_called_once()
    thread.start.assert_called_once()


def test_start_strategies_setup_failure(strategy_manager, caplog):
    """Test start_strategies() when setup fails."""
    strategy_manager._initialized = True
    
    thread = Mock()
    thread.strategy = Mock()
    thread.strategy.name = "test_strategy"
    thread.strategy.setup.return_value = False  # Setup failed
    
    strategy_manager._strategy_threads = [thread]
    
    with caplog.at_level('ERROR'):
        result = strategy_manager.start_strategies()
    
    assert result is False
    assert "setup failed" in caplog.text


def test_stop_strategies_not_running(strategy_manager):
    """Test stop_strategies() when not running."""
    strategy_manager._running = False
    
    # Should not raise error
    strategy_manager.stop_strategies()


def test_stop_strategies_success(strategy_manager):
    """Test stop_strategies() success."""
    strategy_manager._running = True
    
    thread = Mock()
    thread.strategy = Mock()
    thread.strategy.name = "test_strategy"
    thread.is_alive.return_value = False
    
    strategy_manager._strategy_threads = [thread]
    
    strategy_manager.stop_strategies()
    
    assert strategy_manager._running is False
    thread.stop.assert_called_once()
    thread.join.assert_called_once()
    thread.strategy.teardown.assert_called_once()


# Shutdown Tests
# =============================================================================

def test_shutdown_stops_if_running(strategy_manager):
    """Test shutdown() stops strategies if running."""
    strategy_manager._running = True
    strategy_manager._strategy_threads = [Mock()]
    
    with patch.object(strategy_manager, 'stop_strategies') as mock_stop:
        strategy_manager.shutdown()
        mock_stop.assert_called_once()


def test_shutdown_clears_data(strategy_manager):
    """Test shutdown() clears data structures."""
    strategy_manager._initialized = True
    strategy_manager._strategy_threads = [Mock()]
    strategy_manager._subscriptions = {("AAPL", "5m"): [Mock()]}
    
    strategy_manager.shutdown()
    
    assert len(strategy_manager._strategy_threads) == 0
    assert len(strategy_manager._subscriptions) == 0
    assert strategy_manager._initialized is False


# Performance Metrics Tests
# =============================================================================

def test_get_metrics_no_strategies(strategy_manager):
    """Test get_metrics() with no strategies."""
    metrics = strategy_manager.get_metrics()
    
    assert metrics['total_strategies'] == 0
    assert metrics['active_strategies'] == 0
    assert metrics['total_subscriptions'] == 0
    assert metrics['strategies'] == []


def test_get_metrics_with_strategies(strategy_manager):
    """Test get_metrics() with strategies."""
    thread1 = Mock()
    thread1.get_metrics.return_value = {
        'strategy_name': 'strategy1',
        'running': True,
        'notifications_processed': 100,
        'signals_generated': 10,
        'errors': 0,
        'avg_processing_time_ms': 5.0
    }
    
    thread2 = Mock()
    thread2.get_metrics.return_value = {
        'strategy_name': 'strategy2',
        'running': True,
        'notifications_processed': 50,
        'signals_generated': 5,
        'errors': 1,
        'avg_processing_time_ms': 10.0
    }
    
    strategy_manager._strategy_threads = [thread1, thread2]
    strategy_manager._subscriptions = {("AAPL", "5m"): [thread1, thread2]}
    
    metrics = strategy_manager.get_metrics()
    
    assert metrics['total_strategies'] == 2
    assert metrics['active_strategies'] == 2
    assert metrics['total_subscriptions'] == 1
    assert metrics['total_notifications_processed'] == 150
    assert metrics['total_signals_generated'] == 15
    assert metrics['total_errors'] == 1
    assert metrics['slowest_strategy'] == 'strategy2'
    assert metrics['slowest_avg_time_ms'] == 10.0


# Symbol Added Tests
# =============================================================================

def test_notify_symbol_added(strategy_manager, caplog):
    """Test notify_symbol_added() notifies all strategies."""
    thread1 = Mock()
    thread1.strategy = Mock()
    thread1.strategy.name = "strategy1"
    thread1.strategy.get_subscriptions.return_value = [("AAPL", "5m")]  # Fix mock
    
    thread2 = Mock()
    thread2.strategy = Mock()
    thread2.strategy.name = "strategy2"
    thread2.strategy.get_subscriptions.return_value = [("GOOGL", "5m")]  # Fix mock
    
    strategy_manager._strategy_threads = [thread1, thread2]
    
    with caplog.at_level('INFO'):
        strategy_manager.notify_symbol_added("TSLA")
    
    thread1.strategy.on_symbol_added.assert_called_once_with("TSLA")
    thread2.strategy.on_symbol_added.assert_called_once_with("TSLA")
    assert "TSLA" in caplog.text


def test_notify_symbol_added_rebuilds_subscriptions(strategy_manager):
    """Test notify_symbol_added() rebuilds subscription map."""
    thread = Mock()
    thread.strategy = Mock()
    strategy_manager._strategy_threads = [thread]
    
    with patch.object(strategy_manager, '_build_subscription_map') as mock_build:
        strategy_manager.notify_symbol_added("TSLA")
        mock_build.assert_called_once()


def test_notify_symbol_added_handles_error(strategy_manager, caplog):
    """Test notify_symbol_added() handles strategy errors."""
    thread = Mock()
    thread.strategy = Mock()
    thread.strategy.name = "test_strategy"
    thread.strategy.get_subscriptions.return_value = [("AAPL", "5m")]  # Fix mock
    thread.strategy.on_symbol_added.side_effect = Exception("Test error")
    
    strategy_manager._strategy_threads = [thread]
    
    with caplog.at_level('ERROR'):
        strategy_manager.notify_symbol_added("TSLA")
    
    assert "Error notifying" in caplog.text
    assert "test_strategy" in caplog.text
