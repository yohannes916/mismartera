"""Unit tests for BaseStrategy and StrategyContext."""
import pytest
from unittest.mock import Mock, MagicMock
from collections import deque

from app.strategies.base import (
    BaseStrategy,
    StrategyContext,
    Signal,
    SignalAction
)


# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_session_data():
    """Mock SessionData."""
    mock = Mock()
    mock.get_bars_ref.return_value = deque([
        Mock(close=100.0, timestamp='2024-11-01 09:30:00'),
        Mock(close=101.0, timestamp='2024-11-01 09:35:00'),
        Mock(close=102.0, timestamp='2024-11-01 09:40:00'),
    ])
    mock.get_quality_metric.return_value = 100.0  # Changed to use correct SessionData method
    return mock


@pytest.fixture
def mock_time_manager():
    """Mock TimeManager."""
    mock = Mock()
    mock.get_current_time.return_value = Mock(
        date=Mock(return_value='2024-11-01'),
        time=Mock(return_value='09:45:00')
    )
    return mock


@pytest.fixture
def mock_system_manager():
    """Mock SystemManager."""
    return Mock()


@pytest.fixture
def strategy_context(mock_session_data, mock_time_manager, mock_system_manager):
    """Create StrategyContext."""
    return StrategyContext(
        session_data=mock_session_data,
        time_manager=mock_time_manager,
        system_manager=mock_system_manager,
        mode="backtest"
    )


class ConcreteStrategy(BaseStrategy):
    """Concrete strategy for testing."""
    
    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.setup_called = False
        self.teardown_called = False
        self.on_bars_calls = []
        self.symbol_added_calls = []
    
    def get_subscriptions(self):
        """Return test subscriptions."""
        symbols = self.config.get('symbols', ['AAPL'])
        interval = self.config.get('interval', '5m')
        return [(symbol, interval) for symbol in symbols]
    
    def on_bars(self, symbol: str, interval: str):
        """Record call."""
        self.on_bars_calls.append((symbol, interval))
        return []
    
    def setup(self, context):
        """Record setup call."""
        self.setup_called = True
        return super().setup(context)
    
    def teardown(self, context):
        """Record teardown call."""
        self.teardown_called = True
        super().teardown(context)
    
    def on_symbol_added(self, symbol: str):
        """Record symbol added call."""
        self.symbol_added_calls.append(symbol)
        super().on_symbol_added(symbol)


# SignalAction Tests
# =============================================================================

def test_signal_action_enum():
    """Test SignalAction enum values."""
    assert SignalAction.BUY.value == "BUY"
    assert SignalAction.SELL.value == "SELL"
    assert SignalAction.HOLD.value == "HOLD"
    assert SignalAction.CLOSE.value == "CLOSE"


# Signal Tests
# =============================================================================

def test_signal_creation():
    """Test Signal creation with required fields."""
    signal = Signal(
        symbol="AAPL",
        action=SignalAction.BUY
    )
    
    assert signal.symbol == "AAPL"
    assert signal.action == SignalAction.BUY
    assert signal.quantity is None
    assert signal.price is None
    assert signal.reason == ""
    assert signal.metadata == {}


def test_signal_with_all_fields():
    """Test Signal creation with all fields."""
    signal = Signal(
        symbol="AAPL",
        action=SignalAction.BUY,
        quantity=100,
        price=150.50,
        reason="MA crossover",
        metadata={'fast_ma': 151.0, 'slow_ma': 149.0}
    )
    
    assert signal.symbol == "AAPL"
    assert signal.action == SignalAction.BUY
    assert signal.quantity == 100
    assert signal.price == 150.50
    assert signal.reason == "MA crossover"
    assert signal.metadata['fast_ma'] == 151.0
    assert signal.metadata['slow_ma'] == 149.0


# StrategyContext Tests
# =============================================================================

def test_strategy_context_creation(strategy_context):
    """Test StrategyContext creation."""
    assert strategy_context.session_data is not None
    assert strategy_context.time_manager is not None
    assert strategy_context.system_manager is not None
    assert strategy_context.mode == "backtest"


def test_strategy_context_get_current_time(strategy_context):
    """Test StrategyContext.get_current_time()."""
    current_time = strategy_context.get_current_time()
    assert current_time is not None
    strategy_context.time_manager.get_current_time.assert_called_once()


def test_strategy_context_get_bars(strategy_context, mock_session_data):
    """Test StrategyContext.get_bars()."""
    bars = strategy_context.get_bars("AAPL", "5m")
    
    assert bars is not None
    assert len(bars) == 3
    mock_session_data.get_bars_ref.assert_called_once_with("AAPL", "5m")


def test_strategy_context_get_bar_quality(strategy_context, mock_session_data):
    """Test StrategyContext.get_bar_quality()."""
    mock_session_data.get_quality_metric.return_value = 100.0
    quality = strategy_context.get_bar_quality("AAPL", "5m")
    
    assert quality == 100.0
    mock_session_data.get_quality_metric.assert_called_once_with("AAPL", "5m")


# BaseStrategy Tests - Initialization
# =============================================================================

def test_base_strategy_initialization():
    """Test BaseStrategy initialization."""
    strategy = ConcreteStrategy(
        name="test_strategy",
        config={'symbols': ['AAPL'], 'interval': '5m'}
    )
    
    assert strategy.name == "test_strategy"
    assert strategy.config == {'symbols': ['AAPL'], 'interval': '5m'}
    assert strategy.context is None


def test_base_strategy_empty_config():
    """Test BaseStrategy with empty config."""
    strategy = ConcreteStrategy(name="test", config={})
    
    assert strategy.name == "test"
    assert strategy.config == {}


# BaseStrategy Tests - Lifecycle
# =============================================================================

def test_base_strategy_setup(strategy_context):
    """Test BaseStrategy.setup() lifecycle."""
    strategy = ConcreteStrategy(name="test", config={})
    
    assert strategy.context is None
    assert not strategy.setup_called
    
    result = strategy.setup(strategy_context)
    
    assert result is True
    assert strategy.context is strategy_context
    assert strategy.setup_called


def test_base_strategy_teardown(strategy_context):
    """Test BaseStrategy.teardown() lifecycle."""
    strategy = ConcreteStrategy(name="test", config={})
    strategy.setup(strategy_context)
    
    assert not strategy.teardown_called
    
    strategy.teardown(strategy_context)
    
    assert strategy.teardown_called


# BaseStrategy Tests - Abstract Methods
# =============================================================================

def test_base_strategy_get_subscriptions():
    """Test get_subscriptions() returns correct format."""
    strategy = ConcreteStrategy(
        name="test",
        config={'symbols': ['AAPL', 'GOOGL'], 'interval': '5m'}
    )
    
    subscriptions = strategy.get_subscriptions()
    
    assert len(subscriptions) == 2
    assert ('AAPL', '5m') in subscriptions
    assert ('GOOGL', '5m') in subscriptions


def test_base_strategy_on_bars():
    """Test on_bars() is called correctly."""
    strategy = ConcreteStrategy(name="test", config={})
    
    assert len(strategy.on_bars_calls) == 0
    
    signals = strategy.on_bars("AAPL", "5m")
    
    assert len(strategy.on_bars_calls) == 1
    assert strategy.on_bars_calls[0] == ("AAPL", "5m")
    assert signals == []


# BaseStrategy Tests - Optional Hooks
# =============================================================================

def test_base_strategy_on_symbol_added():
    """Test on_symbol_added() hook."""
    strategy = ConcreteStrategy(name="test", config={})
    
    assert len(strategy.symbol_added_calls) == 0
    
    strategy.on_symbol_added("TSLA")
    
    assert len(strategy.symbol_added_calls) == 1
    assert strategy.symbol_added_calls[0] == "TSLA"


def test_base_strategy_on_quality_update(strategy_context, caplog):
    """Test on_quality_update() hook."""
    strategy = ConcreteStrategy(name="test", config={})
    strategy.setup(strategy_context)
    
    # Should log warning for quality < 95%
    with caplog.at_level('WARNING'):
        strategy.on_quality_update("AAPL", "5m", 90.0)
    
    assert "Low quality" in caplog.text
    assert "AAPL" in caplog.text
    assert "90.0%" in caplog.text


def test_base_strategy_on_quality_update_no_warning(strategy_context, caplog):
    """Test on_quality_update() with good quality."""
    strategy = ConcreteStrategy(name="test", config={})
    strategy.setup(strategy_context)
    
    # Should NOT log warning for quality >= 95%
    with caplog.at_level('WARNING'):
        strategy.on_quality_update("AAPL", "5m", 98.0)
    
    assert "Low quality" not in caplog.text


# BaseStrategy Tests - Helper Methods
# =============================================================================

def test_base_strategy_log_signal(strategy_context, caplog):
    """Test log_signal() helper."""
    strategy = ConcreteStrategy(name="test", config={})
    strategy.setup(strategy_context)
    
    signal = Signal(
        symbol="AAPL",
        action=SignalAction.BUY,
        quantity=100,
        reason="Test signal"
    )
    
    with caplog.at_level('INFO'):
        strategy.log_signal(signal)
    
    assert "SIGNAL" in caplog.text
    assert "BUY" in caplog.text
    assert "AAPL" in caplog.text
    assert "qty=100" in caplog.text
    assert "reason=Test signal" in caplog.text


# BaseStrategy Tests - Edge Cases
# =============================================================================

def test_base_strategy_multiple_setup_calls(strategy_context):
    """Test calling setup() multiple times."""
    strategy = ConcreteStrategy(name="test", config={})
    
    # First setup
    result1 = strategy.setup(strategy_context)
    assert result1 is True
    context1 = strategy.context
    
    # Second setup (should replace context)
    result2 = strategy.setup(strategy_context)
    assert result2 is True
    assert strategy.context is context1  # Same reference


def test_base_strategy_teardown_without_setup(strategy_context):
    """Test calling teardown() without setup()."""
    strategy = ConcreteStrategy(name="test", config={})
    
    # Should not raise error
    strategy.teardown(strategy_context)
    assert strategy.teardown_called


def test_base_strategy_on_bars_multiple_calls():
    """Test multiple on_bars() calls."""
    strategy = ConcreteStrategy(name="test", config={})
    
    strategy.on_bars("AAPL", "5m")
    strategy.on_bars("GOOGL", "5m")
    strategy.on_bars("AAPL", "15m")
    
    assert len(strategy.on_bars_calls) == 3
    assert strategy.on_bars_calls[0] == ("AAPL", "5m")
    assert strategy.on_bars_calls[1] == ("GOOGL", "5m")
    assert strategy.on_bars_calls[2] == ("AAPL", "15m")


# BaseStrategy Tests - Configuration
# =============================================================================

def test_base_strategy_config_access():
    """Test accessing config values."""
    config = {
        'symbols': ['AAPL', 'GOOGL'],
        'interval': '5m',
        'fast_period': 10,
        'slow_period': 20
    }
    strategy = ConcreteStrategy(name="test", config=config)
    
    assert strategy.config['symbols'] == ['AAPL', 'GOOGL']
    assert strategy.config['interval'] == '5m'
    assert strategy.config['fast_period'] == 10
    assert strategy.config['slow_period'] == 20


def test_base_strategy_config_get_with_default():
    """Test config.get() with defaults."""
    strategy = ConcreteStrategy(name="test", config={})
    
    # Should use defaults from get_subscriptions
    subscriptions = strategy.get_subscriptions()
    assert len(subscriptions) == 1
    assert subscriptions[0] == ('AAPL', '5m')


# Integration with Context
# =============================================================================

def test_strategy_uses_context_services(strategy_context):
    """Test strategy can use all context services."""
    strategy = ConcreteStrategy(name="test", config={})
    strategy.setup(strategy_context)
    
    # Get current time
    current_time = strategy.context.get_current_time()
    assert current_time is not None
    
    # Get bars
    bars = strategy.context.get_bars("AAPL", "5m")
    assert len(bars) == 3
    
    # Get quality
    quality = strategy.context.get_bar_quality("AAPL", "5m")
    assert quality == 100.0


# Module Exports
# =============================================================================

def test_module_exports():
    """Test that all required classes are exported."""
    from app.strategies import base
    
    assert hasattr(base, 'BaseStrategy')
    assert hasattr(base, 'StrategyContext')
    assert hasattr(base, 'Signal')
    assert hasattr(base, 'SignalAction')
    
    # Check __all__
    assert 'BaseStrategy' in base.__all__
    assert 'StrategyContext' in base.__all__
    assert 'Signal' in base.__all__
    assert 'SignalAction' in base.__all__
