#!/usr/bin/env python3
"""
Verification script for new SessionConfig structure.
Tests loading, validation, and serialization.
"""

import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

# Now we can import - but wrap in try/except for missing dependencies
try:
    from app.models.session_config import (
        SessionConfig, BacktestConfig, SessionDataConfig,
        HistoricalConfig, HistoricalDataConfig, GapFillerConfig,
        TradingConfig, APIConfig
    )
except ImportError as e:
    print(f"Import error: {e}")
    print("This script needs to run with the full environment.")
    print("Try: PYTHONPATH=. python3 verify_session_config.py")
    sys.exit(1)


def test_load_example_config():
    """Test loading example_session.json"""
    print("Testing config loading from JSON...")
    
    config_path = Path("session_configs/example_session.json")
    with open(config_path, 'r') as f:
        data = json.load(f)
    
    config = SessionConfig.from_dict(data)
    
    # Validate structure
    assert config.session_name == "Example Trading Session"
    assert config.mode == "backtest"
    assert config.exchange_group == "US_EQUITY"
    assert config.asset_class == "EQUITY"
    
    print("✓ Basic fields loaded correctly")
    
    # Validate backtest_config
    assert config.backtest_config is not None
    assert config.backtest_config.start_date == "2025-07-02"
    assert config.backtest_config.end_date == "2025-07-07"
    assert config.backtest_config.speed_multiplier == 360.0
    assert config.backtest_config.prefetch_days == 3
    
    print("✓ Backtest config loaded correctly")
    
    # Validate session_data_config
    assert config.session_data_config.symbols == ["RIVN", "AAPL"]
    assert "1m" in config.session_data_config.streams
    assert "quotes" in config.session_data_config.streams
    
    print("✓ Symbols and streams loaded correctly")
    
    # Validate historical config
    hist = config.session_data_config.historical
    assert hist.enable_quality is True
    assert len(hist.data) == 2
    assert hist.data[0].trailing_days == 3
    assert hist.data[0].intervals == ["1m"]
    assert hist.data[1].trailing_days == 10
    assert hist.data[1].intervals == ["1d"]
    
    print("✓ Historical data config loaded correctly")
    
    # Validate indicators
    assert "avg_volume" in hist.indicators
    assert "avg_volume_intraday" in hist.indicators
    assert "high_52w" in hist.indicators
    assert "low_52w" in hist.indicators
    assert hist.indicators["avg_volume"]["type"] == "trailing_average"
    
    print("✓ Historical indicators loaded correctly")
    
    # Validate gap_filler
    gf = config.session_data_config.gap_filler
    assert gf.max_retries == 5
    assert gf.retry_interval_seconds == 60
    assert gf.enable_session_quality is True
    
    print("✓ Gap filler config loaded correctly")
    
    # Validate trading_config
    assert config.trading_config.max_buying_power == 100000.0
    assert config.trading_config.max_per_trade == 10000.0
    assert config.trading_config.max_per_symbol == 20000.0
    assert config.trading_config.max_open_positions == 5
    
    print("✓ Trading config loaded correctly")
    
    # Validate api_config
    assert config.api_config.data_api == "alpaca"
    assert config.api_config.trade_api == "alpaca"
    
    print("✓ API config loaded correctly")
    
    # Validate metadata
    assert config.metadata is not None
    assert config.metadata["version"] == "2.0"
    
    print("✓ Metadata loaded correctly")


def test_validation():
    """Test validation rules."""
    print("\nTesting validation rules...")
    
    # Test missing required field
    try:
        config = SessionConfig.from_dict({
            "mode": "backtest"
        })
        assert False, "Should have raised ValueError for missing session_name"
    except ValueError as e:
        assert "session_name" in str(e).lower()
        print(f"✓ Missing session_name validation: {e}")
    
    # Test invalid mode
    try:
        config = SessionConfig.from_dict({
            "session_name": "Test",
            "mode": "invalid_mode",
            "exchange_group": "US_EQUITY",
            "asset_class": "EQUITY",
            "session_data_config": {
                "symbols": ["AAPL"],
                "streams": ["1m"]
            },
            "trading_config": {
                "max_buying_power": 100000.0,
                "max_per_trade": 10000.0,
                "max_per_symbol": 20000.0,
                "max_open_positions": 5
            },
            "api_config": {
                "data_api": "alpaca",
                "trade_api": "alpaca"
            }
        })
        assert False, "Should have raised ValueError for invalid mode"
    except ValueError as e:
        assert "Invalid mode" in str(e)
        print(f"✓ Invalid mode validation: {e}")
    
    # Test backtest mode requires backtest_config
    try:
        config = SessionConfig.from_dict({
            "session_name": "Test",
            "mode": "backtest",
            "exchange_group": "US_EQUITY",
            "asset_class": "EQUITY",
            "session_data_config": {
                "symbols": ["AAPL"],
                "streams": ["1m"]
            },
            "trading_config": {
                "max_buying_power": 100000.0,
                "max_per_trade": 10000.0,
                "max_per_symbol": 20000.0,
                "max_open_positions": 5
            },
            "api_config": {
                "data_api": "alpaca",
                "trade_api": "alpaca"
            }
        })
        assert False, "Should have raised ValueError for missing backtest_config"
    except ValueError as e:
        assert "backtest_config" in str(e).lower()
        print(f"✓ Missing backtest_config validation: {e}")
    
    # Test empty symbols
    try:
        config = SessionConfig.from_dict({
            "session_name": "Test",
            "mode": "live",
            "exchange_group": "US_EQUITY",
            "asset_class": "EQUITY",
            "session_data_config": {
                "symbols": [],
                "streams": ["1m"]
            },
            "trading_config": {
                "max_buying_power": 100000.0,
                "max_per_trade": 10000.0,
                "max_per_symbol": 20000.0,
                "max_open_positions": 5
            },
            "api_config": {
                "data_api": "alpaca",
                "trade_api": "alpaca"
            }
        })
        assert False, "Should have raised ValueError for empty symbols"
    except ValueError as e:
        assert "symbols" in str(e).lower()
        print(f"✓ Empty symbols validation: {e}")
    
    # Test invalid interval
    try:
        config = SessionConfig.from_dict({
            "session_name": "Test",
            "mode": "live",
            "exchange_group": "US_EQUITY",
            "asset_class": "EQUITY",
            "session_data_config": {
                "symbols": ["AAPL"],
                "streams": ["invalid_interval"]
            },
            "trading_config": {
                "max_buying_power": 100000.0,
                "max_per_trade": 10000.0,
                "max_per_symbol": 20000.0,
                "max_open_positions": 5
            },
            "api_config": {
                "data_api": "alpaca",
                "trade_api": "alpaca"
            }
        })
        assert False, "Should have raised ValueError for invalid stream"
    except ValueError as e:
        assert "Invalid stream" in str(e)
        print(f"✓ Invalid stream validation: {e}")


def test_serialization():
    """Test config serialization (to_dict)."""
    print("\nTesting serialization...")
    
    config_path = Path("session_configs/example_session.json")
    with open(config_path, 'r') as f:
        original_data = json.load(f)
    
    config = SessionConfig.from_dict(original_data)
    serialized = config.to_dict()
    
    # Check key fields
    assert serialized["session_name"] == original_data["session_name"]
    assert serialized["mode"] == original_data["mode"]
    assert serialized["backtest_config"]["start_date"] == original_data["backtest_config"]["start_date"]
    assert serialized["session_data_config"]["symbols"] == original_data["session_data_config"]["symbols"]
    
    print("✓ Serialization matches original structure")
    
    # Test round-trip
    config2 = SessionConfig.from_dict(serialized)
    assert config2.session_name == config.session_name
    assert config2.mode == config.mode
    
    print("✓ Round-trip serialization successful")


def test_defaults():
    """Test default values."""
    print("\nTesting default values...")
    
    # Minimal config (live mode doesn't require backtest_config)
    config = SessionConfig.from_dict({
        "session_name": "Minimal Test",
        "mode": "live",
        "exchange_group": "US_EQUITY",
        "asset_class": "EQUITY",
        "session_data_config": {
            "symbols": ["AAPL"],
            "streams": ["1m"]
        },
        "trading_config": {
            "max_buying_power": 100000.0,
            "max_per_trade": 10000.0,
            "max_per_symbol": 20000.0,
            "max_open_positions": 5
        },
        "api_config": {
            "data_api": "alpaca",
            "trade_api": "alpaca"
        }
    })
    
    # Check defaults
    assert config.session_data_config.historical.enable_quality is True
    assert config.session_data_config.gap_filler.max_retries == 5
    assert config.session_data_config.gap_filler.retry_interval_seconds == 60
    assert config.session_data_config.gap_filler.enable_session_quality is True
    assert len(config.session_data_config.historical.data) == 0
    assert len(config.session_data_config.historical.indicators) == 0
    
    print("✓ Default values applied correctly")


if __name__ == "__main__":
    print("=" * 60)
    print("SessionConfig Verification")
    print("=" * 60)
    
    try:
        test_load_example_config()
        test_validation()
        test_serialization()
        test_defaults()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nSessionConfig is ready for use!")
        print("- Config loading works")
        print("- Validation rules enforced")
        print("- Serialization functional")
        print("- Defaults applied correctly")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
