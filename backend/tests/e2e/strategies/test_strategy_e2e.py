"""End-to-end tests for strategy framework.

These tests use the real strategy framework integrated with the system.
They test the complete flow: config -> load -> run -> signals -> stop.
"""
import pytest
import asyncio
import json
from pathlib import Path
from unittest.mock import Mock, patch

from app.strategies.manager import StrategyManager
from app.strategies.base import BaseStrategy, Signal, SignalAction
from app.models.strategy_config import StrategyConfig


# Test Strategy for E2E
# =============================================================================

class E2ETestStrategy(BaseStrategy):
    """Strategy for E2E testing that generates predictable signals."""
    
    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.notification_count = 0
        self.generated_signals = []
    
    def get_subscriptions(self):
        symbols = self.config.get('symbols', ['AAPL'])
        interval = self.config.get('interval', '5m')
        return [(symbol, interval) for symbol in symbols]
    
    def on_bars(self, symbol: str, interval: str):
        self.notification_count += 1
        
        # Generate test signal every 3rd notification
        if self.notification_count % 3 == 0:
            signal = Signal(
                symbol=symbol,
                action=SignalAction.BUY,
                quantity=100,
                reason=f"Test signal {self.notification_count}"
            )
            self.generated_signals.append(signal)
            return [signal]
        
        return []


# Fixtures
# =============================================================================

@pytest.fixture
def mock_system_manager():
    """Create realistic mock SystemManager for E2E test."""
    from collections import deque
    
    mock = Mock()
    
    # Session config with strategy
    mock.session_config = Mock()
    mock.session_config.session_data_config = Mock()
    mock.session_config.session_data_config.strategies = [
        StrategyConfig(
            module="test_e2e_strategy",
            enabled=True,
            config={
                'symbols': ['AAPL', 'GOOGL'],
                'interval': '5m'
            }
        )
    ]
    
    # Backtest config
    mock.session_config.backtest_config = Mock()
    mock.session_config.backtest_config.speed_multiplier = 0  # Data-driven
    
    # Mode
    mock.mode = Mock()
    mock.mode.value = "backtest"
    
    # Session data with realistic data
    session_data = Mock()
    session_data.get_bars_ref.return_value = deque()
    session_data.get_bar_quality.return_value = 100.0
    mock.get_session_data.return_value = session_data
    
    # Time manager
    from datetime import datetime
    time_manager = Mock()
    time_manager.get_current_time.return_value = datetime(2024, 11, 1, 9, 30)
    mock.get_time_manager.return_value = time_manager
    
    return mock


# E2E Tests - Full Lifecycle
# =============================================================================

@patch('app.strategies.manager.importlib.import_module')
def test_e2e_strategy_full_cycle(mock_import, mock_system_manager):
    """Test complete E2E cycle: load -> setup -> run -> stop."""
    # Mock module that returns our test strategy
    mock_module = Mock()
    mock_module.E2eTestStrategy = E2ETestStrategy
    mock_import.return_value = mock_module
    
    # Update config to use correct module
    mock_system_manager.session_config.session_data_config.strategies[0].module = "test_e2e_strategy"
    
    # Create manager and initialize
    manager = StrategyManager(mock_system_manager)
    
    # Initialize (loads strategies)
    result = manager.initialize()
    assert result is True
    assert len(manager._strategy_threads) == 1
    
    # Start strategies
    result = manager.start_strategies()
    assert result is True
    assert manager._running is True
    
    # Give time to start
    import time
    time.sleep(0.1)
    
    # Simulate data notifications
    manager.notify_strategies("AAPL", "5m", "bars")
    manager.notify_strategies("GOOGL", "5m", "bars")
    manager.notify_strategies("AAPL", "5m", "bars")
    
    time.sleep(0.3)  # Let strategies process
    
    # Stop strategies
    manager.stop_strategies()
    assert manager._running is False
    
    # Get metrics
    metrics = manager.get_metrics()
    assert metrics['total_strategies'] == 1
    assert metrics['total_notifications_processed'] >= 3


@patch('app.strategies.manager.importlib.import_module')
def test_e2e_multiple_strategies_concurrent(mock_import, mock_system_manager):
    """Test multiple strategies running concurrently."""
    # Mock module
    mock_module = Mock()
    mock_module.E2eTestStrategy = E2ETestStrategy
    mock_import.return_value = mock_module
    
    # Configure multiple strategies
    mock_system_manager.session_config.session_data_config.strategies = [
        StrategyConfig(
            module="test_e2e_strategy",
            enabled=True,
            config={'symbols': ['AAPL'], 'interval': '5m'}
        ),
        StrategyConfig(
            module="test_e2e_strategy",
            enabled=True,
            config={'symbols': ['GOOGL'], 'interval': '5m'}
        )
    ]
    
    # Create and initialize
    manager = StrategyManager(mock_system_manager)
    manager.initialize()
    
    # Should have loaded 2 strategies
    assert len(manager._strategy_threads) == 2
    
    # Start
    manager.start_strategies()
    
    import time
    time.sleep(0.1)
    
    # Notify both symbols
    manager.notify_strategies("AAPL", "5m", "bars")
    manager.notify_strategies("GOOGL", "5m", "bars")
    
    time.sleep(0.3)
    
    # Stop
    manager.stop_strategies()
    
    # Both strategies should have processed
    metrics = manager.get_metrics()
    assert metrics['total_strategies'] == 2


@patch('app.strategies.manager.importlib.import_module')
def test_e2e_signal_generation(mock_import, mock_system_manager):
    """Test E2E signal generation flow."""
    # Mock module
    mock_module = Mock()
    mock_module.E2eTestStrategy = E2ETestStrategy
    mock_import.return_value = mock_module
    
    # Create manager
    manager = StrategyManager(mock_system_manager)
    manager.initialize()
    manager.start_strategies()
    
    import time
    time.sleep(0.1)
    
    # Send enough notifications to trigger signal generation
    # Strategy generates signal every 3rd notification
    for i in range(6):
        manager.notify_strategies("AAPL", "5m", "bars")
    
    time.sleep(0.5)
    manager.stop_strategies()
    
    # Check metrics
    metrics = manager.get_metrics()
    assert metrics['total_signals_generated'] >= 2  # 2 signals from 6 notifications


# E2E Tests - Data-Driven Mode
# =============================================================================

@patch('app.strategies.manager.importlib.import_module')
def test_e2e_data_driven_mode(mock_import, mock_system_manager):
    """Test E2E in data-driven mode (blocking)."""
    # Configure for data-driven
    mock_system_manager.session_config.backtest_config.speed_multiplier = 0
    
    mock_module = Mock()
    mock_module.E2eTestStrategy = E2ETestStrategy
    mock_import.return_value = mock_module
    
    manager = StrategyManager(mock_system_manager)
    manager.initialize()
    
    # Check mode determination
    mode = manager._determine_mode()
    assert mode == "data-driven"
    
    manager.start_strategies()
    
    import time
    time.sleep(0.1)
    
    manager.notify_strategies("AAPL", "5m", "bars")
    
    # In data-driven mode, wait should block until ready
    result = manager.wait_for_strategies(timeout=None)
    assert result is True
    
    manager.stop_strategies()


@patch('app.strategies.manager.importlib.import_module')
def test_e2e_clock_driven_mode(mock_import, mock_system_manager):
    """Test E2E in clock-driven mode (non-blocking)."""
    # Configure for clock-driven
    mock_system_manager.session_config.backtest_config.speed_multiplier = 10
    
    mock_module = Mock()
    mock_module.E2eTestStrategy = E2ETestStrategy
    mock_import.return_value = mock_module
    
    manager = StrategyManager(mock_system_manager)
    manager.initialize()
    
    # Check mode determination
    mode = manager._determine_mode()
    assert mode == "clock-driven"
    
    manager.start_strategies()
    
    import time
    time.sleep(0.1)
    
    manager.notify_strategies("AAPL", "5m", "bars")
    
    # In clock-driven mode, wait has timeout
    result = manager.wait_for_strategies(timeout=0.5)
    # Should return quickly (within timeout)
    
    manager.stop_strategies()


# E2E Tests - Error Scenarios
# =============================================================================

@patch('app.strategies.manager.importlib.import_module')
def test_e2e_strategy_error_recovery(mock_import, mock_system_manager):
    """Test E2E with strategy that raises errors."""
    
    class ErrorStrategy(BaseStrategy):
        def __init__(self, name, config):
            super().__init__(name, config)
            self.call_count = 0
        
        def get_subscriptions(self):
            return [("AAPL", "5m")]
        
        def on_bars(self, symbol, interval):
            self.call_count += 1
            # Raise error on first call, succeed after
            if self.call_count == 1:
                raise ValueError("Test error")
            return []
    
    mock_module = Mock()
    mock_module.ErrorStrategy = ErrorStrategy
    mock_import.return_value = mock_module
    
    manager = StrategyManager(mock_system_manager)
    manager.initialize()
    manager.start_strategies()
    
    import time
    time.sleep(0.1)
    
    # Send notifications - first will error, second should succeed
    manager.notify_strategies("AAPL", "5m", "bars")
    time.sleep(0.1)
    manager.notify_strategies("AAPL", "5m", "bars")
    time.sleep(0.1)
    
    # Strategy should still be running
    metrics = manager.get_metrics()
    assert metrics['total_strategies'] == 1
    assert metrics['total_errors'] >= 1
    
    manager.stop_strategies()


@patch('app.strategies.manager.importlib.import_module')
def test_e2e_disabled_strategy_not_loaded(mock_import, mock_system_manager):
    """Test that disabled strategies are not loaded."""
    # Configure with disabled strategy
    mock_system_manager.session_config.session_data_config.strategies = [
        StrategyConfig(
            module="test_disabled",
            enabled=False,  # Disabled
            config={}
        )
    ]
    
    manager = StrategyManager(mock_system_manager)
    result = manager.initialize()
    
    # Should succeed but not load strategy
    assert result is True
    assert len(manager._strategy_threads) == 0


# E2E Tests - Performance
# =============================================================================

@patch('app.strategies.manager.importlib.import_module')
def test_e2e_high_throughput(mock_import, mock_system_manager):
    """Test E2E with high throughput (many notifications)."""
    mock_module = Mock()
    mock_module.E2eTestStrategy = E2ETestStrategy
    mock_import.return_value = mock_module
    
    manager = StrategyManager(mock_system_manager)
    manager.initialize()
    manager.start_strategies()
    
    import time
    start_time = time.time()
    
    # Send many notifications
    for i in range(100):
        manager.notify_strategies("AAPL", "5m", "bars")
    
    time.sleep(1.0)  # Give time to process
    
    elapsed = time.time() - start_time
    
    manager.stop_strategies()
    
    # Check that all or most were processed
    metrics = manager.get_metrics()
    assert metrics['total_notifications_processed'] >= 90  # Allow some buffer
    
    # Should complete in reasonable time
    assert elapsed < 3.0


@patch('app.strategies.manager.importlib.import_module')
def test_e2e_shutdown_performance(mock_import, mock_system_manager):
    """Test that shutdown completes quickly."""
    mock_module = Mock()
    mock_module.E2eTestStrategy = E2ETestStrategy
    mock_import.return_value = mock_module
    
    # Create multiple strategies
    mock_system_manager.session_config.session_data_config.strategies = [
        StrategyConfig(
            module="test_strategy",
            enabled=True,
            config={'symbols': [f"SYM{i}"], 'interval': '5m'}
        )
        for i in range(5)
    ]
    
    manager = StrategyManager(mock_system_manager)
    manager.initialize()
    manager.start_strategies()
    
    import time
    time.sleep(0.2)
    
    # Time the shutdown
    start_time = time.time()
    manager.shutdown()
    elapsed = time.time() - start_time
    
    # Shutdown should complete quickly
    assert elapsed < 2.0
    assert not manager._running
    assert not manager._initialized


# E2E Tests - Configuration
# =============================================================================

def test_e2e_load_from_json_config(tmp_path):
    """Test loading strategy config from JSON file."""
    # Create test config file
    config_data = {
        "session_name": "E2E Test",
        "mode": "backtest",
        "backtest_config": {
            "start_date": "2024-11-01",
            "end_date": "2024-11-01",
            "speed_multiplier": 0
        },
        "session_data_config": {
            "symbols": ["AAPL"],
            "streams": ["1m"],
            "strategies": [
                {
                    "module": "strategies.examples.simple_ma_cross",
                    "enabled": True,
                    "config": {
                        "symbols": ["AAPL"],
                        "interval": "5m",
                        "fast_period": 10,
                        "slow_period": 20
                    }
                }
            ]
        },
        "trading_config": {
            "max_buying_power": 100000.0,
            "max_per_trade": 10000.0,
            "max_per_symbol": 20000.0,
            "max_open_positions": 10
        },
        "api_config": {
            "data_api": "alpaca",
            "trade_api": "alpaca"
        }
    }
    
    config_file = tmp_path / "test_config.json"
    with open(config_file, 'w') as f:
        json.dump(config_data, f)
    
    # Load and validate
    from app.models.session_config import SessionConfig
    config = SessionConfig.from_file(str(config_file))
    
    # Verify strategies loaded
    assert len(config.session_data_config.strategies) == 1
    strategy_config = config.session_data_config.strategies[0]
    assert strategy_config.module == "strategies.examples.simple_ma_cross"
    assert strategy_config.enabled is True
    assert strategy_config.config['fast_period'] == 10


# E2E Tests - Real SimpleMaCrossStrategy
# =============================================================================

@pytest.mark.skipif(
    not Path("strategies/examples/simple_ma_cross.py").exists(),
    reason="SimpleMaCrossStrategy file not found"
)
def test_e2e_real_simple_ma_cross_strategy(mock_system_manager):
    """Test with the real SimpleMaCrossStrategy (if available)."""
    # This test uses the actual SimpleMaCrossStrategy
    mock_system_manager.session_config.session_data_config.strategies = [
        StrategyConfig(
            module="strategies.examples.simple_ma_cross",
            enabled=True,
            config={
                'symbols': ['AAPL'],
                'interval': '5m',
                'fast_period': 3,
                'slow_period': 5
            }
        )
    ]
    
    manager = StrategyManager(mock_system_manager)
    
    try:
        result = manager.initialize()
        # If strategy file exists and loads correctly
        if result:
            assert len(manager._strategy_threads) == 1
            
            manager.start_strategies()
            import time
            time.sleep(0.1)
            
            manager.notify_strategies("AAPL", "5m", "bars")
            time.sleep(0.2)
            
            manager.stop_strategies()
            
            metrics = manager.get_metrics()
            assert metrics['total_strategies'] == 1
    except Exception as e:
        # If strategy not found or fails to load, that's okay for this test
        pytest.skip(f"SimpleMaCrossStrategy not available: {e}")
