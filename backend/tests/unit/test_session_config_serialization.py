"""
Test SessionConfig.to_dict() includes indicator configurations.
"""

import pytest
from app.models.session_config import SessionConfig


def test_session_config_to_dict_includes_indicators():
    """Verify session_config.to_dict() includes indicators section."""
    
    # Load example session config (has many indicators)
    config = SessionConfig.from_file("session_configs/example_session.json")
    
    # Convert to dict
    config_dict = config.to_dict()
    
    # Verify structure
    assert "session_data_config" in config_dict
    assert "indicators" in config_dict["session_data_config"]
    
    indicators = config_dict["session_data_config"]["indicators"]
    assert "session" in indicators
    assert "historical" in indicators
    
    # Verify session indicators
    session_indicators = indicators["session"]
    assert isinstance(session_indicators, list)
    assert len(session_indicators) > 0
    
    # Check first indicator structure
    first_indicator = session_indicators[0]
    assert "name" in first_indicator
    assert "period" in first_indicator
    assert "interval" in first_indicator
    assert "type" in first_indicator
    assert "params" in first_indicator
    
    # Verify historical indicators
    historical_indicators = indicators["historical"]
    assert isinstance(historical_indicators, list)
    assert len(historical_indicators) > 0
    
    # Check first historical indicator structure
    first_hist = historical_indicators[0]
    assert "name" in first_hist
    assert "period" in first_hist
    assert "unit" in first_hist
    assert "interval" in first_hist
    assert "type" in first_hist
    assert "params" in first_hist


def test_session_indicators_from_example_config():
    """Verify specific indicators from example_session.json are serialized."""
    
    config = SessionConfig.from_file("session_configs/example_session.json")
    config_dict = config.to_dict()
    
    session_indicators = config_dict["session_data_config"]["indicators"]["session"]
    
    # Find SMA indicator
    sma_indicators = [ind for ind in session_indicators if ind["name"] == "sma"]
    assert len(sma_indicators) > 0
    
    sma = sma_indicators[0]
    assert sma["period"] == 20
    assert sma["interval"] == "5m"
    assert sma["type"] == "trend"
    
    # Find RSI indicator
    rsi_indicators = [ind for ind in session_indicators if ind["name"] == "rsi"]
    assert len(rsi_indicators) > 0
    
    rsi = rsi_indicators[0]
    assert rsi["period"] == 14
    assert rsi["interval"] == "5m"
    assert rsi["type"] == "momentum"
    
    # Find VWAP indicator
    vwap_indicators = [ind for ind in session_indicators if ind["name"] == "vwap"]
    assert len(vwap_indicators) > 0
    
    vwap = vwap_indicators[0]
    assert vwap["period"] == 0  # VWAP doesn't use period
    assert vwap["interval"] == "1m"


def test_historical_indicators_from_example_config():
    """Verify historical indicators from example_session.json are serialized."""
    
    config = SessionConfig.from_file("session_configs/example_session.json")
    config_dict = config.to_dict()
    
    historical_indicators = config_dict["session_data_config"]["indicators"]["historical"]
    
    # Find avg_volume indicator
    avg_vol_indicators = [ind for ind in historical_indicators if ind["name"] == "avg_volume"]
    assert len(avg_vol_indicators) > 0
    
    avg_vol = avg_vol_indicators[0]
    assert avg_vol["period"] == 20
    assert avg_vol["unit"] == "days"
    assert avg_vol["interval"] == "1d"
    assert avg_vol["type"] == "historical"


def test_empty_indicators_serializes_correctly():
    """Verify config with no indicators serializes correctly."""
    
    # Create minimal config
    from app.models.session_config import (
        SessionConfig, BacktestConfig, SessionDataConfig,
        TradingConfig, APIConfig, IndicatorsConfig
    )
    
    config = SessionConfig(
        session_name="Test",
        exchange_group="US_EQUITY",
        asset_class="EQUITY",
        mode="backtest",
        backtest_config=BacktestConfig(
            start_date="2025-01-01",
            end_date="2025-01-02",
            speed_multiplier=1.0
        ),
        session_data_config=SessionDataConfig(
            symbols=["AAPL"],
            streams=["1m"],
            indicators=IndicatorsConfig()  # Empty
        ),
        trading_config=TradingConfig(
            max_buying_power=100000.0,
            max_per_trade=10000.0,
            max_per_symbol=20000.0,
            max_open_positions=5
        ),
        api_config=APIConfig(
            data_api="alpaca",
            trade_api="alpaca"
        )
    )
    
    # Convert to dict
    config_dict = config.to_dict()
    
    # Verify indicators section exists but is empty
    indicators = config_dict["session_data_config"]["indicators"]
    assert indicators["session"] == []
    assert indicators["historical"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
