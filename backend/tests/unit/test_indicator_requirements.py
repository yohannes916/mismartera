"""Unit Tests for Indicator Requirement Analysis

Tests the _analyze_indicator_requirements method and related logic.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from app.threads.session_coordinator import (
    SessionCoordinator,
    ProvisioningRequirements
)
from app.indicators.base import IndicatorConfig, IndicatorType


class TestAnalyzeIndicatorRequirements:
    """Test _analyze_indicator_requirements method."""
    
    def test_analyze_trend_indicator(self):
        """Test analyzing trend indicator (SMA)."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._system_manager = Mock()
        
        indicator_config = IndicatorConfig(
            name="sma",
            type=IndicatorType.TREND,
            period=20,
            interval="5m",
            params={}
        )
        
        req = ProvisioningRequirements(
            operation_type="indicator",
            symbol="AAPL",
            source="config"
        )
        
        coordinator._analyze_indicator_requirements = SessionCoordinator._analyze_indicator_requirements.__get__(coordinator, SessionCoordinator)
        
        # Mock the analyzer
        with patch('app.threads.quality.requirement_analyzer.analyze_indicator_requirements') as mock_analyze:
            mock_analyze.return_value = Mock(
                required_intervals=["5m"],
                historical_bars=40,
                historical_days=2,
                reason="SMA(20) on 5m requires 40 bars"
            )
            
            coordinator._analyze_indicator_requirements(req, indicator_config=indicator_config)
        
        # Should set indicator requirements
        assert req.indicator_config == indicator_config
        assert req.needs_session is True
        assert req.needs_historical is True
        assert req.historical_days == 2
    
    def test_analyze_momentum_indicator(self):
        """Test analyzing momentum indicator (RSI)."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._system_manager = Mock()
        
        indicator_config = IndicatorConfig(
            name="rsi",
            type=IndicatorType.MOMENTUM,
            period=14,
            interval="1m",
            params={}
        )
        
        req = ProvisioningRequirements(
            operation_type="indicator",
            symbol="AAPL",
            source="scanner"
        )
        
        coordinator._analyze_indicator_requirements = SessionCoordinator._analyze_indicator_requirements.__get__(coordinator, SessionCoordinator)
        
        with patch('app.threads.quality.requirement_analyzer.analyze_indicator_requirements') as mock_analyze:
            mock_analyze.return_value = Mock(
                required_intervals=["1m"],
                historical_bars=28,
                historical_days=1,
                reason="RSI(14) requires 28 bars for warmup"
            )
            
            coordinator._analyze_indicator_requirements(req, indicator_config=indicator_config)
        
        assert req.indicator_config == indicator_config
        assert "1m" in req.required_intervals
    
    def test_analyze_volatility_indicator(self):
        """Test analyzing volatility indicator (Bollinger Bands)."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._system_manager = Mock()
        
        indicator_config = IndicatorConfig(
            name="bbands",
            type=IndicatorType.VOLATILITY,
            period=20,
            interval="5m",
            params={"num_std": 2.0}
        )
        
        req = ProvisioningRequirements(
            operation_type="indicator",
            symbol="AAPL",
            source="strategy"
        )
        
        coordinator._analyze_indicator_requirements = SessionCoordinator._analyze_indicator_requirements.__get__(coordinator, SessionCoordinator)
        
        with patch('app.threads.quality.requirement_analyzer.analyze_indicator_requirements') as mock_analyze:
            mock_analyze.return_value = Mock(
                required_intervals=["5m"],
                historical_bars=40,
                historical_days=2,
                reason="BBands(20) on 5m"
            )
            
            coordinator._analyze_indicator_requirements(req, indicator_config=indicator_config)
        
        assert req.indicator_config.params["num_std"] == 2.0


class TestIndicatorIntervalRequirements:
    """Test indicator requirements set correct intervals."""
    
    def test_single_interval_indicator(self):
        """Test indicator on single interval."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._system_manager = Mock()
        
        indicator_config = IndicatorConfig(
            name="vwap",
            type=IndicatorType.VOLUME,
            period=0,  # VWAP doesn't use period
            interval="1m",
            params={}
        )
        
        req = ProvisioningRequirements(
            operation_type="indicator",
            symbol="AAPL",
            source="config"
        )
        
        coordinator._analyze_indicator_requirements = SessionCoordinator._analyze_indicator_requirements.__get__(coordinator, SessionCoordinator)
        
        with patch('app.threads.quality.requirement_analyzer.analyze_indicator_requirements') as mock_analyze:
            mock_analyze.return_value = Mock(
                required_intervals=["1m"],
                historical_bars=0,
                historical_days=0,
                reason="VWAP on 1m"
            )
            
            coordinator._analyze_indicator_requirements(req, indicator_config=indicator_config)
        
        assert req.required_intervals == ["1m"]
    
    def test_multi_interval_indicator(self):
        """Test indicator requiring multiple intervals."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._system_manager = Mock()
        
        indicator_config = IndicatorConfig(
            name="custom",
            type=IndicatorType.TREND,
            period=20,
            interval="15m",
            params={}
        )
        
        req = ProvisioningRequirements(
            operation_type="indicator",
            symbol="AAPL",
            source="config"
        )
        
        coordinator._analyze_indicator_requirements = SessionCoordinator._analyze_indicator_requirements.__get__(coordinator, SessionCoordinator)
        
        with patch('app.threads.quality.requirement_analyzer.analyze_indicator_requirements') as mock_analyze:
            # Indicator might need base interval too
            mock_analyze.return_value = Mock(
                required_intervals=["1m", "15m"],
                historical_bars=60,
                historical_days=3,
                reason="Custom indicator on 15m"
            )
            
            coordinator._analyze_indicator_requirements(req, indicator_config=indicator_config)
        
        if len(req.required_intervals) > 1:
            # Should set base interval
            assert req.base_interval == req.required_intervals[0]


class TestIndicatorHistoricalRequirements:
    """Test indicator historical data requirements."""
    
    def test_indicator_with_warmup(self):
        """Test indicator requiring warmup period."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._system_manager = Mock()
        
        indicator_config = IndicatorConfig(
            name="ema",
            type=IndicatorType.TREND,
            period=50,
            interval="5m",
            params={}
        )
        
        req = ProvisioningRequirements(
            operation_type="indicator",
            symbol="AAPL",
            source="config"
        )
        
        coordinator._analyze_indicator_requirements = SessionCoordinator._analyze_indicator_requirements.__get__(coordinator, SessionCoordinator)
        
        with patch('app.threads.quality.requirement_analyzer.analyze_indicator_requirements') as mock_analyze:
            # EMA(50) needs warmup
            mock_analyze.return_value = Mock(
                required_intervals=["5m"],
                historical_bars=100,  # 2x period
                historical_days=5,
                reason="EMA(50) needs warmup"
            )
            
            coordinator._analyze_indicator_requirements(req, indicator_config=indicator_config)
        
        assert req.historical_bars == 100
        assert req.needs_historical is True
    
    def test_indicator_no_warmup(self):
        """Test indicator not requiring warmup (e.g., simple price)."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._system_manager = Mock()
        
        indicator_config = IndicatorConfig(
            name="high",
            type=IndicatorType.TREND,
            period=1,
            interval="1m",
            params={}
        )
        
        req = ProvisioningRequirements(
            operation_type="indicator",
            symbol="AAPL",
            source="scanner"
        )
        
        coordinator._analyze_indicator_requirements = SessionCoordinator._analyze_indicator_requirements.__get__(coordinator, SessionCoordinator)
        
        with patch('app.threads.quality.requirement_analyzer.analyze_indicator_requirements') as mock_analyze:
            # Simple indicator
            mock_analyze.return_value = Mock(
                required_intervals=["1m"],
                historical_bars=0,
                historical_days=0,
                reason="Simple high value"
            )
            
            coordinator._analyze_indicator_requirements(req, indicator_config=indicator_config)
        
        assert req.historical_days == 0
        assert req.needs_historical is False


class TestIndicatorReasonMessages:
    """Test indicator analysis sets helpful reason messages."""
    
    def test_reason_includes_indicator_name(self):
        """Test reason message includes indicator details."""
        coordinator = Mock(spec=SessionCoordinator)
        coordinator._system_manager = Mock()
        
        indicator_config = IndicatorConfig(
            name="macd",
            type=IndicatorType.MOMENTUM,
            period=12,
            interval="5m",
            params={"slow": 26, "signal": 9}
        )
        
        req = ProvisioningRequirements(
            operation_type="indicator",
            symbol="AAPL",
            source="config"
        )
        
        coordinator._analyze_indicator_requirements = SessionCoordinator._analyze_indicator_requirements.__get__(coordinator, SessionCoordinator)
        
        with patch('app.threads.quality.requirement_analyzer.analyze_indicator_requirements') as mock_analyze:
            mock_analyze.return_value = Mock(
                required_intervals=["5m"],
                historical_bars=52,
                historical_days=2,
                reason="MACD(12,26,9) on 5m requires 52 bars"
            )
            
            coordinator._analyze_indicator_requirements(req, indicator_config=indicator_config)
        
        # Should have descriptive reason
        assert req.reason != ""
        assert "MACD" in req.reason or "52" in req.reason
