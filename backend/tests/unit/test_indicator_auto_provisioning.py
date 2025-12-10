"""Unit tests for indicator auto-provisioning.

Tests the analyze_indicator_requirements() function that automatically
determines what bar intervals and historical data are needed for indicators.
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import date, timedelta
from app.threads.quality.requirement_analyzer import (
    analyze_indicator_requirements,
    IndicatorRequirements
)
from app.indicators import IndicatorConfig, IndicatorType


@pytest.fixture
def mock_time_manager():
    """Mock TimeManager with realistic date navigation."""
    time_manager = Mock()
    
    # Mock get_current_time() to return a fixed date
    time_manager.get_current_time.return_value = Mock(date=lambda: date(2025, 12, 9))
    
    # Mock get_previous_trading_date() to walk back ~1.4 days per trading day
    # (accounts for weekends)
    def mock_previous_trading_date(session, from_date, n, exchange="NYSE"):
        # Approximate: 5 trading days = 7 calendar days
        calendar_days_back = int(n * 1.4)
        return from_date - timedelta(days=calendar_days_back)
    
    time_manager.get_previous_trading_date = Mock(side_effect=mock_previous_trading_date)
    
    # Mock get_trading_session() to return regular market hours
    def mock_trading_session(session, date, exchange="NYSE"):
        from datetime import time as dt_time
        trading_session = Mock()
        trading_session.is_trading_day = True
        trading_session.regular_open = dt_time(9, 30)
        trading_session.regular_close = dt_time(16, 0)
        return trading_session
    
    time_manager.get_trading_session = Mock(side_effect=mock_trading_session)
    
    return time_manager


@pytest.fixture
def mock_session():
    """Mock database session."""
    return Mock()


def analyze_with_mocks(config, warmup_multiplier=2.0):
    """Helper to analyze indicator requirements with default mocks.
    
    This simplifies tests by providing default mock implementations
    of SystemManager and TimeManager.
    """
    # Create mock TimeManager
    time_manager = Mock()
    
    # Mock get_current_time() to return a fixed date
    time_manager.get_current_time.return_value = Mock(date=lambda: date(2025, 12, 9))
    
    # Mock get_previous_trading_date() - conservative estimate
    def mock_previous(session, from_date, n, exchange="NYSE"):
        return from_date - timedelta(days=int(n * 1.4))
    time_manager.get_previous_trading_date = Mock(side_effect=mock_previous)
    
    # Mock get_trading_session() - regular hours
    def mock_session_fn(session, date, exchange="NYSE"):
        from datetime import time as dt_time
        ts = Mock()
        ts.is_trading_day = True
        ts.regular_open = dt_time(9, 30)
        ts.regular_close = dt_time(16, 0)
        return ts
    time_manager.get_trading_session = Mock(side_effect=mock_session_fn)
    
    # Create mock SystemManager that provides TimeManager
    system_manager = Mock()
    system_manager.get_time_manager.return_value = time_manager
    
    return analyze_indicator_requirements(
        config,
        system_manager=system_manager,
        warmup_multiplier=warmup_multiplier
    )


class TestIndicatorAutoProvisioning:
    """Test indicator requirement analysis."""
    
    def test_simple_sma_on_daily(self):
        """Test SMA on daily bars (base interval)."""
        config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=20,
            interval="1d"
        )
        
        reqs = analyze_with_mocks(config, warmup_multiplier=2.0)
        
        assert reqs.indicator_key == "sma_20_1d"
        assert reqs.required_intervals == ["1d"]  # Only needs daily
        assert reqs.historical_bars == 40  # 20 * 2.0
        assert reqs.historical_days >= 40  # At least 40 calendar days
        assert "SMA(20)" in reqs.reason
        assert "1d" in reqs.reason
    
    def test_sma_on_derived_interval(self):
        """Test SMA on 5m bars (derived interval)."""
        config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=20,
            interval="5m"
        )
        
        reqs = analyze_with_mocks(config, warmup_multiplier=2.0)
        
        assert reqs.indicator_key == "sma_20_5m"
        assert reqs.required_intervals == ["1m", "5m"]  # Needs base + derived
        assert "1m" in reqs.required_intervals  # Base comes first
        assert reqs.historical_bars == 40  # 20 * 2.0
        assert reqs.historical_days >= 1  # At least 1 day
    
    def test_rsi_with_extra_warmup(self):
        """Test RSI which needs extra warmup bars."""
        config = IndicatorConfig(
            name="rsi",
            type=IndicatorType.MOMENTUM,
            period=14,
            interval="1d"
        )
        
        reqs = analyze_with_mocks(config, warmup_multiplier=2.0)
        
        assert reqs.indicator_key == "rsi_14_1d"
        # RSI needs period + 1 = 15, then * 2.0 = 30
        assert reqs.historical_bars == 30
        assert "RSI(14)" in reqs.reason
    
    def test_macd_special_warmup(self):
        """Test MACD which has special warmup requirements."""
        config = IndicatorConfig(
            name="macd",
            type=IndicatorType.MOMENTUM,
            period=12,  # Fast period (convention)
            interval="1d",
            params={"fast": 12, "slow": 26, "signal": 9}
        )
        
        reqs = analyze_with_mocks(config, warmup_multiplier=2.0)
        
        assert reqs.indicator_key == "macd_12_1d"
        # MACD needs 26 bars (slow EMA), then * 2.0 = 52
        assert reqs.historical_bars == 52
    
    def test_intraday_indicator(self):
        """Test indicator on 1-minute bars."""
        config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=20,
            interval="1m"
        )
        
        reqs = analyze_with_mocks(config, warmup_multiplier=2.0)
        
        assert reqs.indicator_key == "sma_20_1m"
        assert reqs.required_intervals == ["1m"]  # 1m is base
        assert reqs.historical_bars == 40
        # 40 1-minute bars is a tiny fraction of a day
        assert reqs.historical_days >= 1
    
    def test_high_frequency_indicator(self):
        """Test indicator on 5-second bars."""
        config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=200,
            interval="5s"
        )
        
        reqs = analyze_with_mocks(config, warmup_multiplier=2.0)
        
        assert reqs.indicator_key == "sma_200_5s"
        assert reqs.required_intervals == ["1s", "5s"]  # Needs 1s base
        assert reqs.historical_bars == 400  # 200 * 2.0
        # 400 5-second bars = 2000 seconds = 33 minutes
        assert reqs.historical_days >= 1
    
    def test_weekly_indicator(self):
        """Test indicator on weekly bars."""
        config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=10,
            interval="1w"
        )
        
        reqs = analyze_with_mocks(config, warmup_multiplier=2.0)
        
        assert reqs.indicator_key == "sma_10_1w"
        assert reqs.required_intervals == ["1w"]  # 1w is base
        assert reqs.historical_bars == 20  # 10 * 2.0
        # 20 weeks = ~140 days
        assert reqs.historical_days >= 140
    
    def test_52_week_high(self):
        """Test 52-week high/low indicator."""
        config = IndicatorConfig(
            name="high_low",
            type=IndicatorType.VOLATILITY,
            period=52,
            interval="1w"
        )
        
        reqs = analyze_with_mocks(config, warmup_multiplier=2.0)
        
        assert reqs.indicator_key == "high_low_52_1w"
        assert reqs.required_intervals == ["1w"]
        assert reqs.historical_bars == 104  # 52 * 2.0
        # 104 weeks = ~728 days = ~2 years
        assert reqs.historical_days >= 700
    
    def test_custom_warmup_multiplier(self):
        """Test with custom warmup multiplier."""
        config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=20,
            interval="1d"
        )
        
        # Conservative multiplier
        reqs = analyze_with_mocks(config, warmup_multiplier=3.0)
        assert reqs.historical_bars == 60  # 20 * 3.0
        
        # Minimal multiplier
        reqs = analyze_with_mocks(config, warmup_multiplier=1.0)
        assert reqs.historical_bars == 20  # 20 * 1.0
    
    def test_zero_period_indicator(self):
        """Test indicator with no period (like VWAP)."""
        config = IndicatorConfig(
            name="vwap",
            type=IndicatorType.TREND,
            period=0,  # VWAP doesn't have a period
            interval="1m"
        )
        
        reqs = analyze_with_mocks(config, warmup_multiplier=2.0)
        
        assert reqs.indicator_key == "vwap_1m"
        assert reqs.required_intervals == ["1m"]
        # warmup_bars() returns max(1, period) = 1
        assert reqs.historical_bars == 2  # 1 * 2.0
    
    def test_multi_hour_timeframe(self):
        """Test indicator on 4-hour bars (240 minutes)."""
        config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=10,
            interval="240m"  # 4 hours
        )
        
        reqs = analyze_with_mocks(config, warmup_multiplier=2.0)
        
        assert reqs.indicator_key == "sma_10_240m"
        assert reqs.required_intervals == ["1m", "240m"]  # Needs 1m base
        assert reqs.historical_bars == 20
        # 20 4-hour bars = 80 hours of trading
        assert reqs.historical_days >= 10  # ~12 trading days = 17+ calendar days


class TestCalendarDayEstimation:
    """Test calendar day estimation logic."""
    
    def test_daily_bars_estimation(self):
        """Test estimation for daily bars."""
        config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=20,
            interval="1d"
        )
        
        reqs = analyze_with_mocks(config, warmup_multiplier=2.0)
        
        # 40 trading days ~= 60 calendar days (1.5x factor)
        assert 55 <= reqs.historical_days <= 65
    
    def test_intraday_bars_estimation(self):
        """Test estimation for intraday bars."""
        config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=390,  # Full trading day of 1m bars
            interval="1m"
        )
        
        reqs = analyze_with_mocks(config, warmup_multiplier=1.0)
        
        # 390 1-minute bars = 1 trading day = 1-2 calendar days
        assert 1 <= reqs.historical_days <= 3
    
    def test_weekly_bars_estimation(self):
        """Test estimation for weekly bars."""
        config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=52,  # 1 year
            interval="1w"
        )
        
        reqs = analyze_with_mocks(config, warmup_multiplier=1.0)
        
        # 52 weeks = ~364 days, but with 10% buffer
        assert 360 <= reqs.historical_days <= 410


class TestMultiIntervalProvisioning:
    """Test multi-interval provisioning scenarios."""
    
    def test_derived_from_minute_base(self):
        """Test that 5m, 15m, 30m all derive from 1m."""
        intervals = ["5m", "15m", "30m", "60m"]
        
        for interval in intervals:
            config = IndicatorConfig(
                name="sma",
                type=IndicatorType.TREND,
                period=10,
                interval=interval
            )
            
            reqs = analyze_with_mocks(config)
            
            # All should require 1m base + their interval
            assert "1m" in reqs.required_intervals
            assert interval in reqs.required_intervals
            assert reqs.required_intervals[0] == "1m"  # Base comes first
    
    def test_derived_from_second_base(self):
        """Test that 5s, 10s, 30s all derive from 1s."""
        intervals = ["5s", "10s", "30s"]
        
        for interval in intervals:
            config = IndicatorConfig(
                name="sma",
                type=IndicatorType.TREND,
                period=10,
                interval=interval
            )
            
            reqs = analyze_with_mocks(config)
            
            # All should require 1s base + their interval
            assert "1s" in reqs.required_intervals
            assert interval in reqs.required_intervals
            assert reqs.required_intervals[0] == "1s"  # Base comes first
    
    def test_base_intervals_no_derivation(self):
        """Test that base intervals don't require derivation."""
        base_intervals = ["1s", "1m", "1d", "1w"]
        
        for interval in base_intervals:
            config = IndicatorConfig(
                name="sma",
                type=IndicatorType.TREND,
                period=10,
                interval=interval
            )
            
            reqs = analyze_with_mocks(config)
            
            # Base intervals only require themselves
            assert reqs.required_intervals == [interval]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
