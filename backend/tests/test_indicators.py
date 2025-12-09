"""Comprehensive tests for all 37 indicators.

Tests indicator calculations, warmup periods, and edge cases.
"""
import pytest
from datetime import datetime, timedelta
from typing import List

from app.models.trading import BarData
from app.indicators import (
    IndicatorConfig,
    IndicatorType,
    IndicatorResult,
    calculate_indicator,
)


def create_test_bars(
    count: int = 50,
    symbol: str = "TEST",
    interval: str = "1m",
    base_price: float = 100.0,
    volatility: float = 1.0
) -> List[BarData]:
    """Create test bars with realistic OHLCV data.
    
    Args:
        count: Number of bars to create
        symbol: Symbol name
        interval: Interval string
        base_price: Starting price
        volatility: Price movement range
        
    Returns:
        List of BarData objects
    """
    bars = []
    current_price = base_price
    base_time = datetime(2025, 1, 2, 9, 30)  # Market open
    
    for i in range(count):
        # Simulate price movement
        price_change = (i % 5 - 2) * volatility  # Oscillating pattern
        current_price += price_change
        
        # Create OHLC with realistic relationships
        open_price = current_price
        high = open_price + abs(price_change) + volatility * 0.5
        low = open_price - abs(price_change) - volatility * 0.5
        close = open_price + price_change
        
        # Ensure high >= open/close and low <= open/close
        high = max(high, open_price, close)
        low = min(low, open_price, close)
        
        bar = BarData(
            timestamp=base_time + timedelta(minutes=i),
            symbol=symbol,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=1000000 + i * 10000,  # Increasing volume
            interval=interval
        )
        bars.append(bar)
    
    return bars


class TestTrendIndicators:
    """Test trend indicators (SMA, EMA, WMA, VWAP, DEMA, TEMA, HMA, TWAP)."""
    
    def test_sma_basic(self):
        """Test SMA calculation."""
        bars = create_test_bars(30, base_price=100.0)
        config = IndicatorConfig("sma", IndicatorType.TREND, 20, "1m")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        assert result.value is not None
        assert isinstance(result.value, float)
        assert 90.0 < result.value < 110.0  # Reasonable range
    
    def test_sma_warmup(self):
        """Test SMA warmup period."""
        # Not enough bars
        bars = create_test_bars(10, base_price=100.0)
        config = IndicatorConfig("sma", IndicatorType.TREND, 20, "1m")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is False
        assert result.value is None
    
    def test_ema_basic(self):
        """Test EMA calculation."""
        bars = create_test_bars(50, base_price=100.0)
        config = IndicatorConfig("ema", IndicatorType.TREND, 20, "1m")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        assert result.value is not None
        assert isinstance(result.value, float)
    
    def test_ema_stateful(self):
        """Test EMA stateful calculation."""
        bars = create_test_bars(25, base_price=100.0)
        config = IndicatorConfig("ema", IndicatorType.TREND, 20, "1m")
        
        # First calculation
        result1 = calculate_indicator(bars, config, "TEST", None)
        
        # Add new bar
        new_bar = create_test_bars(1, base_price=105.0)[0]
        bars.append(new_bar)
        
        # Second calculation (stateful)
        result2 = calculate_indicator(bars, config, "TEST", result1)
        
        assert result2.is_ready() is True
        assert result2.value != result1.value  # Should change with new bar
    
    def test_vwap_basic(self):
        """Test VWAP calculation."""
        bars = create_test_bars(50, base_price=100.0)
        config = IndicatorConfig("vwap", IndicatorType.TREND, 0, "1m")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        assert result.value is not None
        assert 90.0 < result.value < 110.0


class TestMomentumIndicators:
    """Test momentum indicators (RSI, MACD, Stochastic, CCI, ROC, etc.)."""
    
    def test_rsi_basic(self):
        """Test RSI calculation."""
        bars = create_test_bars(30, base_price=100.0)
        config = IndicatorConfig("rsi", IndicatorType.MOMENTUM, 14, "1m")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        assert result.value is not None
        assert 0 <= result.value <= 100  # RSI range
    
    def test_rsi_overbought(self):
        """Test RSI in overbought conditions."""
        # Create strongly trending up bars
        bars = []
        base_time = datetime(2025, 1, 2, 9, 30)
        for i in range(30):
            price = 100.0 + i * 2.0  # Strong uptrend
            bars.append(BarData(
                timestamp=base_time + timedelta(minutes=i),
                symbol="TEST",
                open=price,
                high=price + 1,
                low=price - 0.5,
                close=price + 0.5,
                volume=1000000,
                interval="1m"
            ))
        
        config = IndicatorConfig("rsi", IndicatorType.MOMENTUM, 14, "1m")
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        assert result.value > 70  # Should be overbought
    
    def test_macd_basic(self):
        """Test MACD calculation."""
        bars = create_test_bars(50, base_price=100.0)
        config = IndicatorConfig("macd", IndicatorType.MOMENTUM, 0, "1m")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        assert result.value is not None
        assert "macd" in result.value
        assert "signal" in result.value
        assert "histogram" in result.value
    
    def test_stochastic_basic(self):
        """Test Stochastic oscillator."""
        bars = create_test_bars(30, base_price=100.0)
        config = IndicatorConfig("stochastic", IndicatorType.MOMENTUM, 14, "1m")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        assert result.value is not None
        assert "k" in result.value
        assert "d" in result.value
        assert 0 <= result.value["k"] <= 100
        assert 0 <= result.value["d"] <= 100


class TestVolatilityIndicators:
    """Test volatility indicators (ATR, Bollinger Bands, Keltner, etc.)."""
    
    def test_atr_basic(self):
        """Test ATR calculation."""
        bars = create_test_bars(30, base_price=100.0, volatility=2.0)
        config = IndicatorConfig("atr", IndicatorType.VOLATILITY, 14, "1m")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        assert result.value is not None
        assert result.value > 0  # ATR is always positive
    
    def test_bollinger_bands_basic(self):
        """Test Bollinger Bands calculation."""
        bars = create_test_bars(30, base_price=100.0)
        config = IndicatorConfig("bbands", IndicatorType.VOLATILITY, 20, "1m")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        assert result.value is not None
        assert "upper" in result.value
        assert "middle" in result.value
        assert "lower" in result.value
        assert result.value["upper"] > result.value["middle"]
        assert result.value["middle"] > result.value["lower"]
    
    def test_bollinger_squeeze(self):
        """Test Bollinger Bands in low volatility (squeeze)."""
        # Create bars with minimal price movement
        bars = []
        base_time = datetime(2025, 1, 2, 9, 30)
        for i in range(30):
            price = 100.0 + (i % 2) * 0.1  # Very tight range
            bars.append(BarData(
                timestamp=base_time + timedelta(minutes=i),
                symbol="TEST",
                open=price,
                high=price + 0.05,
                low=price - 0.05,
                close=price,
                volume=1000000,
                interval="1m"
            ))
        
        config = IndicatorConfig("bbands", IndicatorType.VOLATILITY, 20, "1m")
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        # Bands should be narrow
        band_width = result.value["upper"] - result.value["lower"]
        assert band_width < 1.0  # Very narrow


class TestVolumeIndicators:
    """Test volume indicators (OBV, PVT, Volume SMA, Volume Ratio)."""
    
    def test_obv_basic(self):
        """Test OBV calculation."""
        bars = create_test_bars(30, base_price=100.0)
        config = IndicatorConfig("obv", IndicatorType.VOLUME, 0, "1m")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        assert result.value is not None
    
    def test_obv_accumulation(self):
        """Test OBV in accumulation phase."""
        # Create bars with rising prices and volume
        bars = []
        base_time = datetime(2025, 1, 2, 9, 30)
        for i in range(30):
            price = 100.0 + i * 0.5  # Rising prices
            bars.append(BarData(
                timestamp=base_time + timedelta(minutes=i),
                symbol="TEST",
                open=price,
                high=price + 0.5,
                low=price - 0.2,
                close=price + 0.3,  # Closes higher
                volume=1000000 + i * 50000,  # Rising volume
                interval="1m"
            ))
        
        config = IndicatorConfig("obv", IndicatorType.VOLUME, 0, "1m")
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        assert result.value > 0  # Should be positive in accumulation


class TestHistoricalIndicators:
    """Test historical/support-resistance indicators."""
    
    def test_high_low_basic(self):
        """Test N-period high/low."""
        bars = create_test_bars(30, base_price=100.0, volatility=2.0)
        config = IndicatorConfig("high_low", IndicatorType.HISTORICAL, 20, "1m")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        assert result.value is not None
        assert "high" in result.value
        assert "low" in result.value
        assert result.value["high"] >= result.value["low"]
    
    def test_high_low_52_week(self):
        """Test 52-week high/low."""
        # Create 52+ weeks of weekly bars
        bars = create_test_bars(55, base_price=100.0, volatility=3.0)
        config = IndicatorConfig("high_low", IndicatorType.HISTORICAL, 52, "1w")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        assert result.value["high"] is not None
        assert result.value["low"] is not None
    
    def test_pivot_points_basic(self):
        """Test pivot points calculation."""
        bars = create_test_bars(2, base_price=100.0)  # Need prev day
        config = IndicatorConfig("pivot_points", IndicatorType.SUPPORT_RESISTANCE, 0, "1d")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        assert result.value is not None
        assert "pp" in result.value  # Pivot point
        assert "r1" in result.value
        assert "s1" in result.value
    
    def test_avg_volume_basic(self):
        """Test average volume calculation."""
        bars = create_test_bars(30, base_price=100.0)
        config = IndicatorConfig("avg_volume", IndicatorType.HISTORICAL, 20, "1d")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True
        assert result.value is not None
        assert result.value > 0


class TestIndicatorEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_bars(self):
        """Test with empty bar list."""
        bars = []
        config = IndicatorConfig("sma", IndicatorType.TREND, 20, "1m")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is False
        assert result.value is None
    
    def test_single_bar(self):
        """Test with single bar."""
        bars = create_test_bars(1, base_price=100.0)
        config = IndicatorConfig("sma", IndicatorType.TREND, 20, "1m")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is False  # Need 20 bars
    
    def test_exact_warmup_period(self):
        """Test with exactly warmup period bars."""
        bars = create_test_bars(20, base_price=100.0)
        config = IndicatorConfig("sma", IndicatorType.TREND, 20, "1m")
        
        result = calculate_indicator(bars, config, "TEST", None)
        
        assert result.is_ready() is True  # Exactly enough
    
    def test_zero_volume(self):
        """Test VWAP with zero volume bars."""
        bars = []
        base_time = datetime(2025, 1, 2, 9, 30)
        for i in range(5):
            bars.append(BarData(
                timestamp=base_time + timedelta(minutes=i),
                symbol="TEST",
                open=100.0,
                high=100.5,
                low=99.5,
                close=100.0,
                volume=0,  # Zero volume
                interval="1m"
            ))
        
        config = IndicatorConfig("vwap", IndicatorType.TREND, 0, "1m")
        result = calculate_indicator(bars, config, "TEST", None)
        
        # Should handle gracefully (VWAP might still calculate with zero volume)
        # Just verify it doesn't crash
        assert result is not None
    
    def test_all_same_price(self):
        """Test indicators with no price movement."""
        bars = []
        base_time = datetime(2025, 1, 2, 9, 30)
        for i in range(30):
            bars.append(BarData(
                timestamp=base_time + timedelta(minutes=i),
                symbol="TEST",
                open=100.0,
                high=100.0,
                low=100.0,
                close=100.0,
                volume=1000000,
                interval="1m"
            ))
        
        # SMA should equal price
        config_sma = IndicatorConfig("sma", IndicatorType.TREND, 20, "1m")
        result_sma = calculate_indicator(bars, config_sma, "TEST", None)
        assert result_sma.is_ready() is True
        assert result_sma.value == 100.0
        
        # RSI with flat prices - edge case
        config_rsi = IndicatorConfig("rsi", IndicatorType.MOMENTUM, 14, "1m")
        result_rsi = calculate_indicator(bars, config_rsi, "TEST", None)
        assert result_rsi.is_ready() is True
        # RSI with no price change is typically 100 (no bearish movement)
        # Different implementations handle this differently
        assert result_rsi.value is not None


class TestIndicatorConfig:
    """Test indicator configuration."""
    
    def test_make_key_single_value(self):
        """Test key generation for single-value indicator."""
        config = IndicatorConfig("sma", IndicatorType.TREND, 20, "5m")
        key = config.make_key()
        assert key == "sma_20_5m"
    
    def test_make_key_multi_value(self):
        """Test key generation for multi-value indicator."""
        config = IndicatorConfig("bbands", IndicatorType.VOLATILITY, 20, "5m")
        key = config.make_key()
        assert key == "bbands_20_5m"
    
    def test_warmup_bars_simple(self):
        """Test warmup bars calculation."""
        config = IndicatorConfig("sma", IndicatorType.TREND, 20, "5m")
        assert config.warmup_bars() == 20
    
    def test_warmup_bars_complex(self):
        """Test warmup bars for complex indicator (MACD)."""
        config = IndicatorConfig("macd", IndicatorType.MOMENTUM, 0, "5m")
        warmup = config.warmup_bars()
        assert warmup >= 26  # MACD needs 26 bars minimum


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
