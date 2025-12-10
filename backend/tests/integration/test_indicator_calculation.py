"""
Integration test for indicator calculation in DataProcessor.

This test verifies that indicators are calculated and stored correctly
when bars are processed.
"""

import pytest
from datetime import datetime, date
from app.indicators import IndicatorConfig, IndicatorType, BarData
from app.managers.data_manager.session_data import SessionData, SymbolSessionData
from app.indicators.manager import IndicatorManager


@pytest.fixture
def session_data():
    """Create SessionData instance."""
    return SessionData()


@pytest.fixture
def indicator_manager(session_data):
    """Create IndicatorManager instance."""
    return IndicatorManager(session_data)


def create_bar(timestamp: datetime, close: float, volume: int = 1000) -> BarData:
    """Helper to create a bar."""
    return BarData(
        timestamp=timestamp,
        open=close - 0.10,
        high=close + 0.10,
        low=close - 0.20,
        close=close,
        volume=volume
    )


def test_indicator_manager_calculates_sma(session_data, indicator_manager):
    """Test that IndicatorManager correctly calculates SMA."""
    symbol = "TEST"
    
    # Register symbol
    symbol_data = session_data.register_symbol(symbol)
    
    # Create SMA indicator config
    sma_config = IndicatorConfig(
        name="sma",
        type=IndicatorType.TREND,
        period=3,
        interval="1m",
        params={}
    )
    
    # Register indicator
    indicator_manager.register_symbol_indicators(
        symbol=symbol,
        indicators=[sma_config],
        historical_bars=None
    )
    
    # Create 5 bars (SMA needs 3, so after 3rd bar it should be valid)
    base_time = datetime(2025, 1, 1, 9, 30)
    bars = []
    closes = [100.0, 101.0, 102.0, 103.0, 104.0]
    
    for i, close_price in enumerate(closes):
        bar = create_bar(base_time.replace(minute=30+i), close_price)
        bars.append(bar)
        
        # Update indicators after each bar
        indicator_manager.update_indicators(
            symbol=symbol,
            interval="1m",
            bars=bars  # Pass all bars (warmup)
        )
    
    # Check indicator was stored in session_data
    assert "sma_3_1m" in symbol_data.indicators
    
    indicator_data = symbol_data.indicators["sma_3_1m"]
    assert indicator_data.name == "sma"
    assert indicator_data.interval == "1m"
    assert indicator_data.valid is True
    
    # SMA of last 3 bars: (102 + 103 + 104) / 3 = 103.0
    assert indicator_data.current_value == pytest.approx(103.0, rel=0.01)


def test_indicator_manager_calculates_ema(session_data, indicator_manager):
    """Test that IndicatorManager correctly calculates EMA."""
    symbol = "TEST"
    
    # Register symbol
    symbol_data = session_data.register_symbol(symbol)
    
    # Create EMA indicator config
    ema_config = IndicatorConfig(
        name="ema",
        type=IndicatorType.TREND,
        period=3,
        interval="1m",
        params={}
    )
    
    # Register indicator
    indicator_manager.register_symbol_indicators(
        symbol=symbol,
        indicators=[ema_config],
        historical_bars=None
    )
    
    # Create bars
    base_time = datetime(2025, 1, 1, 9, 30)
    bars = []
    closes = [100.0, 102.0, 104.0, 106.0, 108.0]
    
    for i, close_price in enumerate(closes):
        bar = create_bar(base_time.replace(minute=30+i), close_price)
        bars.append(bar)
        
        # Update indicators
        indicator_manager.update_indicators(
            symbol=symbol,
            interval="1m",
            bars=bars
        )
    
    # Check EMA was stored
    assert "ema_3_1m" in symbol_data.indicators
    
    indicator_data = symbol_data.indicators["ema_3_1m"]
    assert indicator_data.name == "ema"
    assert indicator_data.valid is True
    
    # EMA should be between recent values
    assert 100.0 < indicator_data.current_value < 108.0


def test_indicator_warmup_period(session_data, indicator_manager):
    """Test that indicators respect warmup period."""
    symbol = "TEST"
    
    # Register symbol
    symbol_data = session_data.register_symbol(symbol)
    
    # Create SMA(20) - needs 20 bars
    sma_config = IndicatorConfig(
        name="sma",
        type=IndicatorType.TREND,
        period=20,
        interval="1m",
        params={}
    )
    
    # Register indicator
    indicator_manager.register_symbol_indicators(
        symbol=symbol,
        indicators=[sma_config],
        historical_bars=None
    )
    
    # Create only 10 bars (not enough)
    base_time = datetime(2025, 1, 1, 9, 30)
    bars = []
    
    for i in range(10):
        bar = create_bar(base_time.replace(minute=30+i), 100.0 + i)
        bars.append(bar)
    
    # Update indicators
    indicator_manager.update_indicators(
        symbol=symbol,
        interval="1m",
        bars=bars
    )
    
    # Check indicator exists but is NOT valid (warmup incomplete)
    assert "sma_20_1m" in symbol_data.indicators
    indicator_data = symbol_data.indicators["sma_20_1m"]
    
    assert indicator_data.valid is False
    assert indicator_data.current_value is None
    
    # Now add 10 more bars (total 20)
    for i in range(10, 20):
        bar = create_bar(base_time.replace(minute=30+i), 100.0 + i)
        bars.append(bar)
    
    # Update indicators
    indicator_manager.update_indicators(
        symbol=symbol,
        interval="1m",
        bars=bars
    )
    
    # Now it should be valid
    indicator_data = symbol_data.indicators["sma_20_1m"]
    assert indicator_data.valid is True
    assert indicator_data.current_value is not None


def test_multiple_indicators_same_interval(session_data, indicator_manager):
    """Test multiple indicators on same interval."""
    symbol = "TEST"
    
    # Register symbol
    symbol_data = session_data.register_symbol(symbol)
    
    # Create multiple indicators
    indicators = [
        IndicatorConfig(name="sma", type=IndicatorType.TREND, period=5, interval="1m", params={}),
        IndicatorConfig(name="ema", type=IndicatorType.TREND, period=5, interval="1m", params={}),
        IndicatorConfig(name="rsi", type=IndicatorType.MOMENTUM, period=5, interval="1m", params={}),
    ]
    
    # Register indicators
    indicator_manager.register_symbol_indicators(
        symbol=symbol,
        indicators=indicators,
        historical_bars=None
    )
    
    # Create bars
    base_time = datetime(2025, 1, 1, 9, 30)
    bars = []
    
    for i in range(10):
        bar = create_bar(base_time.replace(minute=30+i), 100.0 + i * 0.5)
        bars.append(bar)
    
    # Update all indicators
    indicator_manager.update_indicators(
        symbol=symbol,
        interval="1m",
        bars=bars
    )
    
    # Check all indicators were calculated
    assert "sma_5_1m" in symbol_data.indicators
    assert "ema_5_1m" in symbol_data.indicators
    assert "rsi_5_1m" in symbol_data.indicators
    
    # All should be valid
    assert symbol_data.indicators["sma_5_1m"].valid is True
    assert symbol_data.indicators["ema_5_1m"].valid is True
    assert symbol_data.indicators["rsi_5_1m"].valid is True


def test_indicator_serialization(session_data, indicator_manager):
    """Test that indicators serialize properly to JSON."""
    symbol = "TEST"
    
    # Register symbol
    symbol_data = session_data.register_symbol(symbol)
    
    # Create indicator
    sma_config = IndicatorConfig(
        name="sma",
        type=IndicatorType.TREND,
        period=3,
        interval="1m",
        params={}
    )
    
    # Register indicator
    indicator_manager.register_symbol_indicators(
        symbol=symbol,
        indicators=[sma_config],
        historical_bars=None
    )
    
    # Create bars and calculate
    base_time = datetime(2025, 1, 1, 9, 30)
    bars = [
        create_bar(base_time, 100.0),
        create_bar(base_time.replace(minute=31), 101.0),
        create_bar(base_time.replace(minute=32), 102.0),
    ]
    
    indicator_manager.update_indicators(symbol=symbol, interval="1m", bars=bars)
    
    # Serialize to JSON
    json_data = symbol_data.to_json(complete=True)
    
    # Check indicators section exists and has data
    assert "indicators" in json_data
    assert "sma_3_1m" in json_data["indicators"]
    
    indicator_json = json_data["indicators"]["sma_3_1m"]
    
    # Check structure
    assert "name" in indicator_json
    assert "type" in indicator_json
    assert "interval" in indicator_json
    assert "value" in indicator_json
    assert "valid" in indicator_json
    assert "last_updated" in indicator_json
    
    # Check values
    assert indicator_json["name"] == "sma"
    assert indicator_json["type"] == "trend"
    assert indicator_json["interval"] == "1m"
    assert indicator_json["valid"] is True
    assert indicator_json["value"] == pytest.approx(101.0, rel=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
