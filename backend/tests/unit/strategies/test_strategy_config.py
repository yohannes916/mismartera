"""Unit tests for StrategyConfig."""
import pytest

from app.models.strategy_config import StrategyConfig


# Basic Creation Tests
# =============================================================================

def test_strategy_config_creation():
    """Test StrategyConfig creation with required fields."""
    config = StrategyConfig(
        module="strategies.examples.simple_ma_cross",
        enabled=True
    )
    
    assert config.module == "strategies.examples.simple_ma_cross"
    assert config.enabled is True
    assert config.config == {}


def test_strategy_config_with_config_dict():
    """Test StrategyConfig with config dictionary."""
    config = StrategyConfig(
        module="strategies.examples.simple_ma_cross",
        enabled=True,
        config={
            'symbols': ['AAPL'],
            'interval': '5m',
            'fast_period': 10
        }
    )
    
    assert config.config['symbols'] == ['AAPL']
    assert config.config['interval'] == '5m'
    assert config.config['fast_period'] == 10


def test_strategy_config_disabled():
    """Test StrategyConfig with enabled=False."""
    config = StrategyConfig(
        module="strategies.examples.simple_ma_cross",
        enabled=False
    )
    
    assert config.enabled is False


def test_strategy_config_default_enabled():
    """Test StrategyConfig defaults enabled to True."""
    config = StrategyConfig(
        module="strategies.examples.simple_ma_cross"
    )
    
    assert config.enabled is True


# Validation Tests
# =============================================================================

def test_validate_success():
    """Test validate() with valid config."""
    config = StrategyConfig(
        module="strategies.examples.simple_ma_cross",
        enabled=True
    )
    
    # Should not raise
    config.validate()


def test_validate_empty_module():
    """Test validate() with empty module."""
    config = StrategyConfig(
        module="",
        enabled=True
    )
    
    with pytest.raises(ValueError, match="module path is required"):
        config.validate()


def test_validate_none_module():
    """Test validate() with None module."""
    # Dataclasses allow None, but validate() should catch it
    config = StrategyConfig(
        module=None,
        enabled=True
    )
    
    with pytest.raises((ValueError, AttributeError)):  # Either is acceptable
        config.validate()


def test_validate_invalid_module_path():
    """Test validate() with invalid module path."""
    config = StrategyConfig(
        module="strategies.examples.my-strategy",  # Hyphens not valid
        enabled=True
    )
    
    with pytest.raises(ValueError, match="Invalid module path"):
        config.validate()


def test_validate_module_with_dots():
    """Test validate() accepts module with dots."""
    config = StrategyConfig(
        module="strategies.examples.simple_ma_cross",
        enabled=True
    )
    
    # Should not raise
    config.validate()


def test_validate_module_with_underscores():
    """Test validate() accepts module with underscores."""
    config = StrategyConfig(
        module="strategies.production.my_custom_strategy",
        enabled=True
    )
    
    # Should not raise
    config.validate()


def test_validate_single_level_module():
    """Test validate() accepts single level module."""
    config = StrategyConfig(
        module="simple_strategy",
        enabled=True
    )
    
    # Should not raise
    config.validate()


# Edge Cases
# =============================================================================

def test_strategy_config_empty_config_dict():
    """Test StrategyConfig with empty config dict."""
    config = StrategyConfig(
        module="strategies.test",
        enabled=True,
        config={}
    )
    
    assert config.config == {}


def test_strategy_config_nested_config():
    """Test StrategyConfig with nested config."""
    config = StrategyConfig(
        module="strategies.test",
        enabled=True,
        config={
            'symbols': ['AAPL', 'GOOGL'],
            'params': {
                'fast': 10,
                'slow': 20
            }
        }
    )
    
    assert config.config['params']['fast'] == 10
    assert config.config['params']['slow'] == 20


def test_strategy_config_various_types_in_config():
    """Test StrategyConfig with various types in config."""
    config = StrategyConfig(
        module="strategies.test",
        enabled=True,
        config={
            'string': 'value',
            'int': 42,
            'float': 3.14,
            'bool': True,
            'list': [1, 2, 3],
            'dict': {'key': 'value'}
        }
    )
    
    assert config.config['string'] == 'value'
    assert config.config['int'] == 42
    assert config.config['float'] == 3.14
    assert config.config['bool'] is True
    assert config.config['list'] == [1, 2, 3]
    assert config.config['dict'] == {'key': 'value'}


# Module Path Format Tests
# =============================================================================

def test_validate_module_path_numbers():
    """Test module path can contain numbers."""
    config = StrategyConfig(
        module="strategies.strategy2.version3",
        enabled=True
    )
    
    # Should not raise
    config.validate()


def test_validate_module_path_special_chars_fail():
    """Test module path rejects special characters."""
    invalid_paths = [
        "strategies/examples/test",  # Slashes
        "strategies.examples.test!",  # Exclamation
        "strategies.examples.test@",  # At sign
        "strategies.examples.test#",  # Hash
        "strategies.examples.test-name",  # Hyphen
    ]
    
    for path in invalid_paths:
        config = StrategyConfig(module=path, enabled=True)
        with pytest.raises(ValueError, match="Invalid module path"):
            config.validate()


def test_validate_module_path_leading_dot():
    """Test module path with leading dot."""
    config = StrategyConfig(
        module=".strategies.test",
        enabled=True
    )
    
    # Leading dot should fail (empty part)
    with pytest.raises(ValueError, match="Invalid module path"):
        config.validate()


def test_validate_module_path_trailing_dot():
    """Test module path with trailing dot."""
    config = StrategyConfig(
        module="strategies.test.",
        enabled=True
    )
    
    # Trailing dot should fail (empty part)
    with pytest.raises(ValueError, match="Invalid module path"):
        config.validate()


def test_validate_module_path_double_dot():
    """Test module path with double dot."""
    config = StrategyConfig(
        module="strategies..test",
        enabled=True
    )
    
    # Double dot should fail (empty part)
    with pytest.raises(ValueError, match="Invalid module path"):
        config.validate()


# Real-World Examples
# =============================================================================

def test_example_simple_ma_cross_config():
    """Test realistic config for SimpleMaCrossStrategy."""
    config = StrategyConfig(
        module="strategies.examples.simple_ma_cross",
        enabled=True,
        config={
            'symbols': ['AAPL', 'GOOGL'],
            'interval': '5m',
            'fast_period': 10,
            'slow_period': 20,
            'min_quality': 95.0
        }
    )
    
    config.validate()
    assert config.module == "strategies.examples.simple_ma_cross"


def test_example_rsi_strategy_config():
    """Test realistic config for RSI strategy."""
    config = StrategyConfig(
        module="strategies.production.rsi_strategy",
        enabled=True,
        config={
            'symbols': ['SPY', 'QQQ'],
            'interval': '15m',
            'rsi_period': 14,
            'overbought': 70,
            'oversold': 30
        }
    )
    
    config.validate()


def test_example_disabled_strategy():
    """Test disabled strategy config."""
    config = StrategyConfig(
        module="strategies.experimental.new_strategy",
        enabled=False,
        config={}
    )
    
    config.validate()
    assert config.enabled is False


# Serialization Tests (if using dataclasses)
# =============================================================================

def test_strategy_config_repr():
    """Test StrategyConfig string representation."""
    config = StrategyConfig(
        module="strategies.test",
        enabled=True,
        config={'key': 'value'}
    )
    
    repr_str = repr(config)
    assert 'StrategyConfig' in repr_str
    assert 'strategies.test' in repr_str


def test_strategy_config_equality():
    """Test StrategyConfig equality."""
    config1 = StrategyConfig(
        module="strategies.test",
        enabled=True,
        config={'key': 'value'}
    )
    
    config2 = StrategyConfig(
        module="strategies.test",
        enabled=True,
        config={'key': 'value'}
    )
    
    assert config1 == config2


def test_strategy_config_inequality():
    """Test StrategyConfig inequality."""
    config1 = StrategyConfig(
        module="strategies.test1",
        enabled=True
    )
    
    config2 = StrategyConfig(
        module="strategies.test2",
        enabled=True
    )
    
    assert config1 != config2
