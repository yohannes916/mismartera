"""Tests for IndicatorManager and SessionData integration."""
import pytest
from datetime import datetime, timedelta
from typing import List

from app.models.trading import BarData
from app.indicators import (
    IndicatorManager,
    IndicatorConfig,
    IndicatorType,
    IndicatorData,
    get_indicator_value,
    is_indicator_ready,
)
from app.managers.data_manager.session_data import SessionData, SymbolSessionData


def create_test_bars(
    count: int = 50,
    symbol: str = "AAPL",
    interval: str = "1m",
    base_price: float = 100.0
) -> List[BarData]:
    """Create test bars."""
    bars = []
    base_time = datetime(2025, 1, 2, 9, 30)
    
    for i in range(count):
        price = base_price + (i % 10 - 5) * 0.5
        bars.append(BarData(
            timestamp=base_time + timedelta(minutes=i),
            symbol=symbol,
            open=price,
            high=price + 0.5,
            low=price - 0.5,
            close=price + 0.3,
            volume=1000000 + i * 10000,
            interval=interval
        ))
    
    return bars


class TestIndicatorManager:
    """Test IndicatorManager functionality."""
    
    def test_init(self):
        """Test IndicatorManager initialization."""
        session_data = SessionData()
        manager = IndicatorManager(session_data)
        
        assert manager.session_data == session_data
        # No internal trackers - everything lives in session_data
    
    def test_register_symbol_indicators(self):
        """Test registering indicators for a symbol."""
        session_data = SessionData()
        manager = IndicatorManager(session_data)
        
        # Create symbol data
        symbol_data = session_data.register_symbol("AAPL")
        
        # Define indicators
        indicators = [
            IndicatorConfig("sma", IndicatorType.TREND, 20, "5m"),
            IndicatorConfig("rsi", IndicatorType.MOMENTUM, 14, "5m"),
            IndicatorConfig("bbands", IndicatorType.VOLATILITY, 20, "5m"),
        ]
        
        # Register
        manager.register_symbol_indicators(
            symbol="AAPL",
            indicators=indicators,
            historical_bars={}
        )
        
        # Verify registration - check session_data.indicators
        symbol_data = session_data.get_symbol_data("AAPL", internal=True)
        assert symbol_data is not None
        assert len(symbol_data.indicators) == 3
        
        # Verify each indicator has embedded config
        for ind_data in symbol_data.indicators.values():
            assert ind_data.config is not None
            assert ind_data.config.interval == "5m"
    
    def test_update_indicators_single(self):
        """Test updating indicators with new bars."""
        session_data = SessionData()
        manager = IndicatorManager(session_data)
        
        # Register symbol
        symbol_data = session_data.register_symbol("AAPL")
        
        # Register SMA indicator
        indicators = [
            IndicatorConfig("sma", IndicatorType.TREND, 20, "5m"),
        ]
        manager.register_symbol_indicators("AAPL", indicators, {})
        
        # Create bars
        bars = create_test_bars(25, "AAPL", "5m")
        
        # Update indicators
        manager.update_indicators("AAPL", "5m", bars)
        
        # Check SessionData
        sma_value = get_indicator_value(session_data, "AAPL", "sma_20_5m")
        assert sma_value is not None
        assert isinstance(sma_value, float)
    
    def test_update_indicators_multiple(self):
        """Test updating multiple indicators."""
        session_data = SessionData()
        manager = IndicatorManager(session_data)
        
        # Register symbol
        symbol_data = session_data.register_symbol("AAPL")
        
        # Register multiple indicators
        indicators = [
            IndicatorConfig("sma", IndicatorType.TREND, 20, "5m"),
            IndicatorConfig("ema", IndicatorType.TREND, 20, "5m"),
            IndicatorConfig("rsi", IndicatorType.MOMENTUM, 14, "5m"),
        ]
        manager.register_symbol_indicators("AAPL", indicators, {})
        
        # Create bars
        bars = create_test_bars(30, "AAPL", "5m")
        
        # Update indicators
        manager.update_indicators("AAPL", "5m", bars)
        
        # Check all indicators
        sma = get_indicator_value(session_data, "AAPL", "sma_20_5m")
        ema = get_indicator_value(session_data, "AAPL", "ema_20_5m")
        rsi = get_indicator_value(session_data, "AAPL", "rsi_14_5m")
        
        assert sma is not None
        assert ema is not None
        assert rsi is not None
    
    def test_update_indicators_warmup(self):
        """Test indicator warmup behavior."""
        session_data = SessionData()
        manager = IndicatorManager(session_data)
        
        # Register symbol
        symbol_data = session_data.register_symbol("AAPL")
        
        # Register indicator needing 20 bars
        indicators = [
            IndicatorConfig("sma", IndicatorType.TREND, 20, "5m"),
        ]
        manager.register_symbol_indicators("AAPL", indicators, {})
        
        # Start with insufficient bars
        bars = create_test_bars(10, "AAPL", "5m")
        manager.update_indicators("AAPL", "5m", bars)
        
        # Should not be ready
        assert not is_indicator_ready(session_data, "AAPL", "sma_20_5m")
        
        # Add more bars
        bars = create_test_bars(25, "AAPL", "5m")
        manager.update_indicators("AAPL", "5m", bars)
        
        # Should now be ready
        assert is_indicator_ready(session_data, "AAPL", "sma_20_5m")
    
    def test_update_indicators_multi_interval(self):
        """Test indicators on different intervals."""
        session_data = SessionData()
        manager = IndicatorManager(session_data)
        
        # Register symbol
        symbol_data = session_data.register_symbol("AAPL")
        
        # Register indicators on different intervals
        indicators = [
            IndicatorConfig("sma", IndicatorType.TREND, 20, "1m"),
            IndicatorConfig("sma", IndicatorType.TREND, 20, "5m"),
            IndicatorConfig("rsi", IndicatorType.MOMENTUM, 14, "1m"),
        ]
        manager.register_symbol_indicators("AAPL", indicators, {})
        
        # Update 1m bars
        bars_1m = create_test_bars(30, "AAPL", "1m")
        manager.update_indicators("AAPL", "1m", bars_1m)
        
        # Update 5m bars
        bars_5m = create_test_bars(25, "AAPL", "5m")
        manager.update_indicators("AAPL", "5m", bars_5m)
        
        # Check both intervals
        sma_1m = get_indicator_value(session_data, "AAPL", "sma_20_1m")
        sma_5m = get_indicator_value(session_data, "AAPL", "sma_20_5m")
        rsi_1m = get_indicator_value(session_data, "AAPL", "rsi_14_1m")
        
        assert sma_1m is not None
        assert sma_5m is not None
        assert rsi_1m is not None
    
    def test_historical_warmup(self):
        """Test indicator warmup with historical bars."""
        session_data = SessionData()
        manager = IndicatorManager(session_data)
        
        # Register symbol
        symbol_data = session_data.register_symbol("AAPL")
        
        # Create historical bars
        historical_bars = {
            "5m": create_test_bars(50, "AAPL", "5m")
        }
        
        # Register indicators with historical warmup
        indicators = [
            IndicatorConfig("sma", IndicatorType.TREND, 20, "5m"),
            IndicatorConfig("ema", IndicatorType.TREND, 20, "5m"),
        ]
        manager.register_symbol_indicators("AAPL", indicators, historical_bars)
        
        # Indicators should be ready immediately after warmup
        assert is_indicator_ready(session_data, "AAPL", "sma_20_5m")
        assert is_indicator_ready(session_data, "AAPL", "ema_20_5m")


class TestSessionDataAPI:
    """Test SessionData indicator API."""
    
    def test_get_indicator_value_single(self):
        """Test getting single-value indicator."""
        session_data = SessionData()
        symbol_data = session_data.register_symbol("AAPL")
        
        # Create indicator data directly in session_data (new pattern)
        symbol_data = session_data.get_symbol_data("AAPL", internal=True)
        symbol_data.indicators["sma_20_5m"] = IndicatorData(
            name="sma",
            type="session",
            interval="5m",
            current_value=150.5,
            last_updated=datetime.now(),
            valid=True
        )
        
        # Retrieve
        value = get_indicator_value(session_data, "AAPL", "sma_20_5m")
        assert value == 150.5
    
    def test_get_indicator_value_multi(self):
        """Test getting multi-value indicator."""
        session_data = SessionData()
        symbol_data = session_data.register_symbol("AAPL")
        
        # Create multi-value indicator data directly
        values = {"upper": 155.0, "middle": 150.0, "lower": 145.0}
        symbol_data = session_data.get_symbol_data("AAPL", internal=True)
        symbol_data.indicators["bbands_20_5m"] = IndicatorData(
            name="bbands",
            type="session",
            interval="5m",
            current_value=values,
            last_updated=datetime.now(),
            valid=True
        )
        
        # Retrieve individual values
        upper = get_indicator_value(session_data, "AAPL", "bbands_20_5m", "upper")
        middle = get_indicator_value(session_data, "AAPL", "bbands_20_5m", "middle")
        lower = get_indicator_value(session_data, "AAPL", "bbands_20_5m", "lower")
        
        assert upper == 155.0
        assert middle == 150.0
        assert lower == 145.0
    
    def test_is_indicator_ready(self):
        """Test checking indicator ready status."""
        session_data = SessionData()
        symbol_data = session_data.register_symbol("AAPL")
        
        # Not ready initially
        assert not is_indicator_ready(session_data, "AAPL", "sma_20_5m")
        
        # Create ready indicator
        symbol_data = session_data.get_symbol_data("AAPL", internal=True)
        symbol_data.indicators["sma_20_5m"] = IndicatorData(
            name="sma",
            type="session",
            interval="5m",
            current_value=150.0,
            last_updated=datetime.now(),
            valid=True
        )
        assert is_indicator_ready(session_data, "AAPL", "sma_20_5m")
        
        # Set as not ready
        symbol_data.indicators["sma_20_5m"].valid = False
        symbol_data.indicators["sma_20_5m"].current_value = None
        assert not is_indicator_ready(session_data, "AAPL", "sma_20_5m")
    
    def test_get_all_indicators(self):
        """Test getting all indicators for a symbol."""
        session_data = SessionData()
        symbol_data = session_data.register_symbol("AAPL")
        
        # Create multiple indicators directly
        symbol_data = session_data.get_symbol_data("AAPL", internal=True)
        for key, value in [("sma_20_5m", 150.0), ("rsi_14_5m", 55.3), ("ema_20_5m", 151.2)]:
            symbol_data.indicators[key] = IndicatorData(
                name=key.split("_")[0],
                type="session",
                interval="5m",
                current_value=value,
                last_updated=datetime.now(),
                valid=True
            )
        
        # Get all
        all_indicators = symbol_data.indicators
        
        assert "sma_20_5m" in all_indicators
        assert "rsi_14_5m" in all_indicators
        assert "ema_20_5m" in all_indicators
        assert len(all_indicators) == 3
    
    def test_missing_symbol(self):
        """Test accessing indicator for non-existent symbol."""
        session_data = SessionData()
        
        value = get_indicator_value(session_data, "MISSING", "sma_20_5m")
        assert value is None
    
    def test_missing_indicator(self):
        """Test accessing non-existent indicator."""
        session_data = SessionData()
        symbol_data = session_data.register_symbol("AAPL")
        
        value = get_indicator_value(session_data, "AAPL", "missing_indicator")
        assert value is None


class TestIndicatorIntegration:
    """Integration tests for complete indicator workflow."""
    
    def test_full_workflow(self):
        """Test complete workflow: register -> update -> access."""
        session_data = SessionData()
        manager = IndicatorManager(session_data)
        
        # 1. Register symbol
        symbol_data = session_data.register_symbol("AAPL")
        
        # 2. Register indicators
        indicators = [
            IndicatorConfig("sma", IndicatorType.TREND, 20, "5m"),
            IndicatorConfig("rsi", IndicatorType.MOMENTUM, 14, "5m"),
            IndicatorConfig("bbands", IndicatorType.VOLATILITY, 20, "5m"),
        ]
        manager.register_symbol_indicators("AAPL", indicators, {})
        
        # 3. Update with bars
        bars = create_test_bars(30, "AAPL", "5m")
        manager.update_indicators("AAPL", "5m", bars)
        
        # 4. Access indicators
        sma = get_indicator_value(session_data, "AAPL", "sma_20_5m")
        rsi = get_indicator_value(session_data, "AAPL", "rsi_14_5m")
        bb_upper = get_indicator_value(session_data, "AAPL", "bbands_20_5m", "upper")
        
        # 5. Verify
        assert sma is not None
        assert rsi is not None
        assert bb_upper is not None
        assert is_indicator_ready(session_data, "AAPL", "sma_20_5m")
    
    def test_multi_symbol_workflow(self):
        """Test workflow with multiple symbols."""
        session_data = SessionData()
        manager = IndicatorManager(session_data)
        
        symbols = ["AAPL", "TSLA", "NVDA"]
        indicators = [
            IndicatorConfig("sma", IndicatorType.TREND, 20, "5m"),
            IndicatorConfig("rsi", IndicatorType.MOMENTUM, 14, "5m"),
        ]
        
        # Register all symbols
        for symbol in symbols:
            session_data.register_symbol(symbol)
            manager.register_symbol_indicators(symbol, indicators, {})
        
        # Update all symbols
        for symbol in symbols:
            bars = create_test_bars(30, symbol, "5m", base_price=100.0 + ord(symbol[0]))
            manager.update_indicators(symbol, "5m", bars)
        
        # Verify all symbols
        for symbol in symbols:
            sma = get_indicator_value(session_data, symbol, "sma_20_5m")
            rsi = get_indicator_value(session_data, symbol, "rsi_14_5m")
            assert sma is not None
            assert rsi is not None
    
    def test_52_week_high_low(self):
        """Test 52-week high/low indicator."""
        session_data = SessionData()
        manager = IndicatorManager(session_data)
        
        # Register symbol
        symbol_data = session_data.register_symbol("SPY")
        
        # Register 52-week high/low
        indicators = [
            IndicatorConfig("high_low", IndicatorType.HISTORICAL, 52, "1w"),
        ]
        
        # Create 52+ weeks of data
        weekly_bars = create_test_bars(55, "SPY", "1w", base_price=400.0)
        
        # Add historical data
        historical_bars = {"1w": weekly_bars}
        manager.register_symbol_indicators("SPY", indicators, historical_bars)
        
        # Should be ready with historical data
        assert is_indicator_ready(session_data, "SPY", "high_low_52_1w")
        
        # Get values
        week_52_high = get_indicator_value(session_data, "SPY", "high_low_52_1w", "high")
        week_52_low = get_indicator_value(session_data, "SPY", "high_low_52_1w", "low")
        
        assert week_52_high is not None
        assert week_52_low is not None
        assert week_52_high >= week_52_low


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
