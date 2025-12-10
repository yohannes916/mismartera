"""Unit tests for SimpleMaCrossStrategy."""
import pytest
from unittest.mock import Mock
from collections import deque
from datetime import datetime

from strategies.examples.simple_ma_cross import SimpleMaCrossStrategy
from app.strategies.base import StrategyContext, Signal, SignalAction


# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_context():
    """Create mock StrategyContext."""
    context = Mock(spec=StrategyContext)
    context.get_bars = Mock()  # Changed from get_bars_ref
    context.get_bar_quality = Mock(return_value=100.0)
    return context


def create_bars(closes):
    """Helper to create mock bars."""
    bars = deque()
    for i, close in enumerate(closes):
        bar = Mock()
        bar.close = close
        bar.timestamp = f"2024-11-01 09:{30+i}:00"
        bars.append(bar)
    return bars


# Initialization Tests
# =============================================================================

def test_initialization():
    """Test strategy initialization."""
    config = {
        'symbols': ['AAPL', 'GOOGL'],
        'interval': '5m',
        'fast_period': 10,
        'slow_period': 20
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    
    assert strategy.name == "test"
    assert strategy.config == config


def test_setup_success(mock_context):
    """Test strategy setup success."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 10,
        'slow_period': 20
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    result = strategy.setup(mock_context)
    
    assert result is True
    assert strategy.context is mock_context
    assert strategy.symbols == ['AAPL']
    assert strategy.interval == '5m'
    assert strategy.fast_period == 10
    assert strategy.slow_period == 20


def test_setup_no_symbols(mock_context, caplog):
    """Test setup fails with no symbols."""
    config = {
        'symbols': [],
        'interval': '5m'
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    
    with caplog.at_level('ERROR'):
        result = strategy.setup(mock_context)
    
    assert result is False
    assert "No symbols configured" in caplog.text


def test_setup_invalid_periods(mock_context, caplog):
    """Test setup fails with fast >= slow period."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 20,
        'slow_period': 10  # Invalid: slow < fast
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    
    with caplog.at_level('ERROR'):
        result = strategy.setup(mock_context)
    
    assert result is False
    assert "fast_period must be < slow_period" in caplog.text


def test_setup_zero_periods(mock_context, caplog):
    """Test setup fails with zero periods."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 0,
        'slow_period': 20
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    
    with caplog.at_level('ERROR'):
        result = strategy.setup(mock_context)
    
    assert result is False
    assert "Periods must be positive" in caplog.text


# Subscription Tests
# =============================================================================

def test_get_subscriptions():
    """Test get_subscriptions returns correct format."""
    config = {
        'symbols': ['AAPL', 'GOOGL', 'TSLA'],
        'interval': '5m'
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    subscriptions = strategy.get_subscriptions()
    
    assert len(subscriptions) == 3
    assert ('AAPL', '5m') in subscriptions
    assert ('GOOGL', '5m') in subscriptions
    assert ('TSLA', '5m') in subscriptions


def test_get_subscriptions_single_symbol():
    """Test get_subscriptions with single symbol."""
    config = {
        'symbols': ['AAPL'],
        'interval': '15m'
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    subscriptions = strategy.get_subscriptions()
    
    assert len(subscriptions) == 1
    assert subscriptions[0] == ('AAPL', '15m')


# MA Calculation Tests
# =============================================================================

def test_calculate_ma():
    """Test MA calculation."""
    strategy = SimpleMaCrossStrategy(name="test", config={})
    bars = create_bars([100, 101, 102, 103, 104])
    
    ma = strategy._calculate_ma(bars, period=5)
    
    # Average of [100, 101, 102, 103, 104] = 102
    assert ma == 102.0


def test_calculate_ma_with_offset():
    """Test MA calculation with offset."""
    strategy = SimpleMaCrossStrategy(name="test", config={})
    bars = create_bars([100, 101, 102, 103, 104, 105])
    
    # Offset=1 means skip the last bar
    # Average of [100, 101, 102, 103, 104] = 102
    ma = strategy._calculate_ma(bars, period=5, offset=1)
    
    assert ma == 102.0


def test_calculate_ma_insufficient_data():
    """Test MA calculation with insufficient data."""
    strategy = SimpleMaCrossStrategy(name="test", config={})
    bars = create_bars([100, 101, 102])
    
    # Need 5 bars, only have 3
    ma = strategy._calculate_ma(bars, period=5)
    
    assert ma is None


def test_calculate_ma_exact_period():
    """Test MA calculation with exact period bars."""
    strategy = SimpleMaCrossStrategy(name="test", config={})
    bars = create_bars([100, 102, 104, 106, 108])
    
    ma = strategy._calculate_ma(bars, period=5)
    
    # Average of [100, 102, 104, 106, 108] = 104
    assert ma == 104.0


# Signal Generation Tests
# =============================================================================

def test_on_bars_insufficient_data(mock_context):
    """Test on_bars with insufficient data."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 10,
        'slow_period': 20
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    strategy.setup(mock_context)
    
    # Only 15 bars (need 20 for slow MA)
    bars = create_bars([100 + i for i in range(15)])
    mock_context.get_bars.return_value = bars
    
    signals = strategy.on_bars("AAPL", "5m")
    
    assert signals == []


def test_on_bars_bullish_crossover(mock_context):
    """Test bullish crossover signal generation."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 3,
        'slow_period': 5
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    strategy.setup(mock_context)
    
    # Create bullish crossover: flat prices then spike
    # Previous: fast=100, slow=100 (equal)
    # Current: fast=103.33 (avg of 100,100,110), slow=102 (avg of 100,100,100,100,110)
    # Fast crosses above slow!
    bars = create_bars([100, 100, 100, 100, 100, 100, 110])
    mock_context.get_bars.return_value = bars
    
    signals = strategy.on_bars("AAPL", "5m")
    
    # Should generate BUY signal
    assert len(signals) == 1
    assert signals[0].symbol == "AAPL"
    assert signals[0].action == SignalAction.BUY


def test_on_bars_bearish_crossover(mock_context):
    """Test bearish crossover signal generation."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 3,
        'slow_period': 5
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    strategy.setup(mock_context)
    
    # Create bearish crossover: flat prices then drop
    # Previous: fast=110, slow=110 (equal)
    # Current: fast=103.33 (avg of 110,110,90), slow=106 (avg of 110,110,110,110,90)
    # Fast crosses below slow!
    bars = create_bars([110, 110, 110, 110, 110, 110, 90])
    mock_context.get_bars.return_value = bars
    
    signals = strategy.on_bars("AAPL", "5m")
    
    # Should generate SELL signal
    assert len(signals) == 1
    assert signals[0].symbol == "AAPL"
    assert signals[0].action == SignalAction.SELL


def test_on_bars_no_crossover(mock_context):
    """Test no signal when no crossover."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 3,
        'slow_period': 5
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    strategy.setup(mock_context)
    
    # Flat prices - no crossover
    bars = create_bars([100] * 10)
    mock_context.get_bars.return_value = bars
    
    signals = strategy.on_bars("AAPL", "5m")
    
    assert signals == []


def test_on_bars_duplicate_signal_suppression(mock_context):
    """Test that duplicate signals are suppressed."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 3,
        'slow_period': 5
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    strategy.setup(mock_context)
    
    # First crossover - generate signal (use working crossover data)
    bars = create_bars([100, 100, 100, 100, 100, 100, 110])
    mock_context.get_bars.return_value = bars
    
    signals1 = strategy.on_bars("AAPL", "5m")
    assert len(signals1) == 1
    assert signals1[0].action == SignalAction.BUY
    
    # Call again with same data - should not generate duplicate
    signals2 = strategy.on_bars("AAPL", "5m")
    assert signals2 == []


# Quality Check Tests
# =============================================================================

def test_on_bars_low_quality(mock_context, caplog):
    """Test on_bars skips processing with low quality."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 3,
        'slow_period': 5,
        'min_quality': 95.0
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    strategy.setup(mock_context)
    
    # Set low quality
    mock_context.get_bar_quality.return_value = 90.0
    
    bars = create_bars([100] * 10)
    mock_context.get_bars.return_value = bars
    
    with caplog.at_level('WARNING'):
        signals = strategy.on_bars("AAPL", "5m")
    
    assert signals == []
    assert "Skipping" in caplog.text
    assert "quality" in caplog.text


def test_on_bars_sufficient_quality(mock_context):
    """Test on_bars processes with sufficient quality."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 3,
        'slow_period': 5,
        'min_quality': 95.0
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    strategy.setup(mock_context)
    
    # Set sufficient quality
    mock_context.get_bar_quality.return_value = 98.0
    
    bars = create_bars([100] * 10)
    mock_context.get_bars.return_value = bars
    
    # Should process (even if no signals generated)
    signals = strategy.on_bars("AAPL", "5m")
    
    # Quality check should pass
    mock_context.get_bar_quality.assert_called_once_with("AAPL", "5m")


# Wrong Symbol/Interval Tests
# =============================================================================

def test_on_bars_wrong_symbol(mock_context):
    """Test on_bars ignores wrong symbol."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m'
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    strategy.setup(mock_context)
    
    # Call with GOOGL (not subscribed)
    signals = strategy.on_bars("GOOGL", "5m")
    
    assert signals == []


def test_on_bars_wrong_interval(mock_context):
    """Test on_bars ignores wrong interval."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m'
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    strategy.setup(mock_context)
    
    # Call with 15m (not subscribed)
    signals = strategy.on_bars("AAPL", "15m")
    
    assert signals == []


# Signal Metadata Tests
# =============================================================================

def test_signal_contains_metadata(mock_context):
    """Test that generated signals contain metadata."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 3,
        'slow_period': 5
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    strategy.setup(mock_context)
    
    # Generate crossover (use working crossover data)
    bars = create_bars([100, 100, 100, 100, 100, 100, 110])
    mock_context.get_bars.return_value = bars
    
    signals = strategy.on_bars("AAPL", "5m")
    
    assert len(signals) == 1
    signal = signals[0]
    
    # Check metadata
    assert 'fast_ma' in signal.metadata
    assert 'slow_ma' in signal.metadata
    assert 'interval' in signal.metadata
    assert signal.metadata['interval'] == '5m'


def test_signal_has_reason(mock_context):
    """Test that signals have descriptive reason."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 3,
        'slow_period': 5
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    strategy.setup(mock_context)
    
    # Generate crossover (use working crossover data)
    bars = create_bars([100, 100, 100, 100, 100, 100, 110])
    mock_context.get_bars.return_value = bars
    
    signals = strategy.on_bars("AAPL", "5m")
    
    assert len(signals) == 1
    assert signals[0].reason != ""
    assert "crossed" in signals[0].reason.lower()


# Edge Cases
# =============================================================================

def test_on_bars_exact_minimum_bars(mock_context):
    """Test on_bars with exact minimum bars needed."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 3,
        'slow_period': 5
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    strategy.setup(mock_context)
    
    # Need 5 bars for slow MA + 1 for previous = 6 minimum
    bars = create_bars([100, 101, 102, 103, 104, 105])
    mock_context.get_bars.return_value = bars
    
    # Should be able to calculate (though may not generate signal)
    signals = strategy.on_bars("AAPL", "5m")
    
    # Just verify it doesn't crash
    assert isinstance(signals, list)


def test_on_bars_many_bars(mock_context):
    """Test on_bars with many bars."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 10,
        'slow_period': 20
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    strategy.setup(mock_context)
    
    # Create 100 bars
    bars = create_bars([100 + i * 0.1 for i in range(100)])
    mock_context.get_bars.return_value = bars
    
    # Should handle large dataset
    signals = strategy.on_bars("AAPL", "5m")
    
    assert isinstance(signals, list)


# Configuration Default Tests
# =============================================================================

def test_default_min_quality():
    """Test default min_quality is 95.0."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 10,
        'slow_period': 20
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    strategy.setup(Mock())
    
    assert strategy.min_quality == 95.0


def test_custom_min_quality():
    """Test custom min_quality."""
    config = {
        'symbols': ['AAPL'],
        'interval': '5m',
        'fast_period': 10,
        'slow_period': 20,
        'min_quality': 98.0
    }
    
    strategy = SimpleMaCrossStrategy(name="test", config=config)
    strategy.setup(Mock())
    
    assert strategy.min_quality == 98.0
