# Session Configuration System

## Overview

The system has been revised with **strict configuration requirements** for starting sessions. This ensures that all trading parameters, risk limits, data streams, and API settings are explicitly defined before any system operations begin.

## Key Changes

### 1. Mandatory Configuration File

**Before:**
```python
# Old behavior - could start without configuration
system_mgr.start()  # ❌ No configuration required
```

**After:**
```python
# New behavior - configuration file is MANDATORY
system_mgr.start("session_configs/my_session.json")  # ✅ Required
system_mgr.start(None)  # ❌ Raises ValueError
system_mgr.start("")    # ❌ Raises ValueError
```

### 2. No Default Fallbacks

**Strict Error Handling:**
- ❌ No default configuration files
- ❌ No fallback to example configs
- ❌ No optional parameters
- ✅ Clear error messages with exact failure reason

### 3. Stream Initialization Before RUNNING

**Critical Sequence:**
1. Load and validate configuration
2. Start all data streams
3. **Only then** transition to RUNNING state

This ensures data is flowing before any trading logic activates.

## Session Configuration File Format

### Complete Example

```json
{
  "session_name": "My Trading Session",
  "data_streams": [
    {
      "type": "bars",
      "symbol": "AAPL",
      "interval": "1m",
      "output_file": "./data/streams/aapl_bars.csv"
    },
    {
      "type": "ticks",
      "symbol": "TSLA",
      "output_file": "./data/streams/tsla_ticks.csv"
    },
    {
      "type": "quotes",
      "symbol": "MSFT",
      "output_file": "./data/streams/msft_quotes.csv"
    }
  ],
  "trading_config": {
    "max_buying_power": 100000.0,
    "max_per_trade": 10000.0,
    "max_per_symbol": 20000.0,
    "max_open_positions": 5,
    "paper_trading": true
  },
  "api_config": {
    "data_api": "alpaca",
    "trade_api": "alpaca",
    "account_id": "paper_account_123"
  },
  "metadata": {
    "created_by": "trader_name",
    "description": "Momentum scalping strategy",
    "strategy": "momentum_scalping",
    "notes": "Optional additional information"
  }
}
```

## Configuration Sections

### 1. Session Name
```json
"session_name": "My Trading Session"
```
- **Required**: Yes
- **Type**: String
- **Purpose**: Descriptive name for the session
- **Validation**: Cannot be empty

### 2. Data Streams
```json
"data_streams": [
  {
    "type": "bars",           // "bars", "ticks", or "quotes"
    "symbol": "AAPL",         // Stock symbol
    "interval": "1m",         // Required for bars: "1m", "5m", "15m", etc.
    "output_file": "./data/streams/aapl_bars.csv"  // Optional CSV output
  }
]
```

**Required**: Yes (at least one stream)

**Stream Types:**
- **`bars`** - OHLCV bar data (requires `interval`)
- **`ticks`** - Individual trades
- **`quotes`** - Bid/ask quotes

**Validation:**
- At least one stream must be configured
- Bar streams must specify an interval
- Symbol cannot be empty
- Type must be one of: "bars", "ticks", "quotes"

### 3. Trading Configuration
```json
"trading_config": {
  "max_buying_power": 100000.0,      // Total capital to use
  "max_per_trade": 10000.0,          // Maximum $ per single trade
  "max_per_symbol": 20000.0,         // Maximum position size per symbol
  "max_open_positions": 5,           // Max concurrent positions
  "paper_trading": true              // Paper (true) or live (false)
}
```

**Required**: Yes

**Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `max_buying_power` | float | Yes | Total available capital (USD) |
| `max_per_trade` | float | Yes | Maximum per trade (USD) |
| `max_per_symbol` | float | Yes | Maximum per symbol (USD) |
| `max_open_positions` | int | No (default: 10) | Max concurrent positions |
| `paper_trading` | bool | No (default: true) | Paper or live trading |

**Validation Rules:**
- All amounts must be positive
- `max_per_trade` ≤ `max_buying_power`
- `max_per_symbol` ≤ `max_buying_power`
- `max_open_positions` must be positive

### 4. API Configuration
```json
"api_config": {
  "data_api": "alpaca",              // Data provider
  "trade_api": "alpaca",             // Trading API
  "account_id": "paper_account_123"  // Optional account ID
}
```

**Required**: Yes

**Fields:**
| Field | Type | Required | Valid Values |
|-------|------|----------|--------------|
| `data_api` | string | Yes | "alpaca", "schwab" |
| `trade_api` | string | Yes | "alpaca", "schwab" |
| `account_id` | string | No | Any string |

### 5. Backtest Configuration (Backtest Mode Only)
```json
"backtest_config": {
  "start_date": "2025-07-02",
  "end_date": "2025-07-03",
  "speed_multiplier": 60.0
}
```

**Required**: Yes (only in backtest mode)

**Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `start_date` | string | Yes | Start date (YYYY-MM-DD) |
| `end_date` | string | Yes | End date (YYYY-MM-DD) |
| `speed_multiplier` | float | No (default: 0.0) | Speed multiplier (0=max, >0=realtime multiplier) |

**Speed Multiplier:**
- `0.0` - Maximum speed (no delay)
- `1.0` - Real-time speed (1 second = 1 second)
- `60.0` - 60x speed (1 second = 1 minute)
- `360.0` - 360x speed (1 second = 6 minutes)

### 6. Historical Configuration
```json
"session_data_config": {
  "historical": {
    "enable_quality": true,
    "data": [
      {
        "trailing_days": 3,
        "intervals": ["1m"],
        "apply_to": "all"
      },
      {
        "trailing_days": 10,
        "intervals": ["1d"],
        "apply_to": "all"
      }
    ],
    "indicators": {
      "avg_volume": {
        "type": "trailing_average",
        "period": "10d",
        "granularity": "daily",
        "field": "volume"
      },
      "max_price": {
        "type": "trailing_max",
        "period": "5d",
        "field": "close"
      }
    }
  }
}
```

**Required**: No

**Historical Data:**
- Loads historical bars before each session starts
- Different `trailing_days` per interval type (1m, 1d, etc.)
- `apply_to`: "all" or list of specific symbols

**Historical Indicators:**

Indicators are calculated once before each session and stored with auto-generated names that include the period.

**Indicator Types:**

| Type | Description | Returns |
|------|-------------|---------|
| `trailing_average` | Average over period | Single value (daily) or 390 values (minute) |
| `trailing_max` | Maximum over period | Single value |
| `trailing_min` | Minimum over period | Single value |

**Supported Fields:** `volume`, `close`, `open`, `high`, `low`

**Storage Keys:**
Indicators are stored with descriptive keys that include the period:
- Config name: `avg_volume`, Period: `10d` → Storage key: **`avg_volume_10d`**
- Config name: `max_price`, Period: `5d` → Storage key: **`max_price_5d`**

**Access in Analysis Engine:**
```python
from app.managers.data_manager.session_data import get_session_data

session_data = get_session_data()

# Get specific indicator
avg_vol_10d = session_data.get_historical_indicator("avg_volume_10d")
max_price_5d = session_data.get_historical_indicator("max_price_5d")

# Get all indicators
all_indicators = session_data.get_all_historical_indicators()
# {'avg_volume_10d': 12345678.9, 'max_price_5d': 150.25}
```

**Multiple Periods Example:**
```json
{
  "indicators": {
    "avg_volume_short": {
      "type": "trailing_average",
      "period": "2d",
      "granularity": "daily",
      "field": "volume"
    },
    "avg_volume_long": {
      "type": "trailing_average",
      "period": "10d",
      "granularity": "daily",
      "field": "volume"
    }
  }
}
```
Storage keys: `avg_volume_short_2d`, `avg_volume_long_10d`

**Granularity Options:**
- `daily`: Single value (average across all days)
- `minute`: Array of 390 values (one per minute of trading day)

See `/docs/HISTORICAL_INDICATORS_API.md` for complete documentation.

### 7. Metadata (Optional)
```json
"metadata": {
  "created_by": "user_name",
  "description": "Description of strategy",
  "strategy": "strategy_name",
  "notes": "Additional information"
}
```

**Required**: No

**Purpose**: Store additional context about the session

## Usage

### CLI Command

```bash
# Start system with configuration
system start session_configs/example_session.json

# With relative path
system start ./my_config.json

# With absolute path
system start /home/user/trading/configs/session.json
```

### Python API

```python
from app.managers.system_manager import get_system_manager

system_mgr = get_system_manager()

# Start with configuration (async)
system_mgr.start("session_configs/my_session.json")

# Access session configuration
if system_mgr.session_config:
    print(f"Session: {system_mgr.session_config.session_name}")
    print(f"Streams: {len(system_mgr.session_config.data_streams)}")
    print(f"Max Buying Power: ${system_mgr.session_config.trading_config.max_buying_power:,.2f}")

# Stop system (stops all streams)
system_mgr.stop()
```

## Error Handling

### Missing Configuration File

```bash
system start nonexistent.json
```
**Error:**
```
✗ Configuration file not found
Configuration file not found: nonexistent.json
Absolute path: /home/user/mismartera/backend/nonexistent.json
Please provide a valid path to a session configuration file.
```

### Empty or Null Path

```python
system_mgr.start(None)
system_mgr.start("")
```
**Error:**
```
ValueError: Configuration file path is mandatory.
You must provide a valid path to a session configuration file.
```

### Invalid JSON

```bash
system start invalid.json
```
**Error:**
```
✗ Configuration validation error
Configuration file contains invalid JSON: invalid.json
Error: Expecting property name enclosed in double quotes
```

### Validation Errors

```json
{
  "session_name": "",
  "trading_config": {
    "max_buying_power": 100000,
    "max_per_trade": 150000  // ❌ Exceeds max_buying_power
  }
}
```
**Error:**
```
✗ Configuration validation error
Configuration validation failed: session.json
Error: max_per_trade cannot exceed max_buying_power
```

### Stream Startup Failure

If any stream fails to start:
1. Error is logged with details
2. All previously started streams are stopped
3. System remains in STOPPED state
4. Clear error message displayed

## Startup Sequence

```
1. system start <config_file>
   ↓
2. Validate file path (strict)
   ↓
3. Load JSON file
   ↓
4. Parse and validate configuration
   ↓
5. Initialize managers if needed
   ↓
6. Apply API configuration
   ↓
7. Start each data stream sequentially
   │  ├─ Stream 1: ✓
   │  ├─ Stream 2: ✓
   │  └─ Stream 3: ✓
   ↓
8. Transition to RUNNING state ← Only after all streams started
   ↓
9. Display success summary
```

**Critical:** State transition to RUNNING happens **only after** all streams are successfully started.

## Stop Sequence

```
1. system stop
   ↓
2. Stop all active data streams
   ↓
3. Clear session configuration
   ↓
4. Transition to STOPPED state
   ↓
5. Display confirmation
```

## Configuration Templates

### Minimal Configuration

```json
{
  "session_name": "Minimal Session",
  "data_streams": [
    {
      "type": "bars",
      "symbol": "AAPL",
      "interval": "1m"
    }
  ],
  "trading_config": {
    "max_buying_power": 10000.0,
    "max_per_trade": 1000.0,
    "max_per_symbol": 2000.0
  },
  "api_config": {
    "data_api": "alpaca",
    "trade_api": "alpaca"
  }
}
```

### Multi-Symbol Strategy

```json
{
  "session_name": "Tech Stocks Momentum",
  "data_streams": [
    {"type": "bars", "symbol": "AAPL", "interval": "1m"},
    {"type": "bars", "symbol": "MSFT", "interval": "1m"},
    {"type": "bars", "symbol": "GOOGL", "interval": "1m"},
    {"type": "ticks", "symbol": "AAPL"},
    {"type": "quotes", "symbol": "AAPL"}
  ],
  "trading_config": {
    "max_buying_power": 100000.0,
    "max_per_trade": 5000.0,
    "max_per_symbol": 15000.0,
    "max_open_positions": 3,
    "paper_trading": true
  },
  "api_config": {
    "data_api": "alpaca",
    "trade_api": "alpaca",
    "account_id": "paper_tech_momentum"
  },
  "metadata": {
    "strategy": "momentum",
    "description": "Tech stocks momentum strategy with 1-minute bars",
    "created_by": "trader_1"
  }
}
```

### High-Frequency Scalping

```json
{
  "session_name": "HFT Scalping Session",
  "data_streams": [
    {"type": "ticks", "symbol": "SPY", "output_file": "./data/streams/spy_ticks.csv"},
    {"type": "quotes", "symbol": "SPY", "output_file": "./data/streams/spy_quotes.csv"}
  ],
  "trading_config": {
    "max_buying_power": 50000.0,
    "max_per_trade": 2000.0,
    "max_per_symbol": 10000.0,
    "max_open_positions": 10,
    "paper_trading": true
  },
  "api_config": {
    "data_api": "alpaca",
    "trade_api": "alpaca"
  },
  "metadata": {
    "strategy": "hft_scalping",
    "description": "High-frequency tick-level scalping on SPY"
  }
}
```

## Best Practices

### 1. Organize Configurations

```
project/
├── session_configs/
│   ├── production/
│   │   ├── live_trading.json
│   │   └── conservative.json
│   ├── paper/
│   │   ├── aggressive.json
│   │   └── moderate.json
│   └── backtest/
│       ├── 2024_q4.json
│       └── test_strategy.json
```

### 2. Use Descriptive Names

```json
"session_name": "SPY_Momentum_Paper_Conservative_2024"
```

### 3. Document in Metadata

```json
"metadata": {
  "created_by": "john_doe",
  "created_date": "2024-11-22",
  "strategy": "momentum_scalping",
  "description": "Paper trading session for testing momentum strategy on tech stocks",
  "risk_level": "low",
  "expected_trades_per_day": 20,
  "notes": "Testing with reduced position sizes"
}
```

### 4. Version Control Configurations

```bash
git add session_configs/
git commit -m "Add new momentum strategy configuration"
```

### 5. Test Before Live Trading

Always test configurations in paper trading mode before using with live capital:

```json
"trading_config": {
  "paper_trading": true  // ← Always start with paper
}
```

## Files Created/Modified

### New Files
1. **`app/models/session_config.py`** - Configuration data models
2. **`session_configs/example_session.json`** - Example configuration
3. **`SESSION_CONFIG_SYSTEM.md`** - This documentation

### Modified Files
1. **`app/managers/system_manager.py`** - Revised start() method
2. **`app/cli/system_commands.py`** - Updated start_command
3. **`app/cli/interactive.py`** - Updated CLI handler
4. **`app/cli/command_registry.py`** - Updated system start usage

## Migration Guide

### If You Have Existing Code

**Old Code:**
```python
system_mgr.start()
```

**New Code:**
```python
system_mgr.start("session_configs/my_session.json")
```

### Creating Your First Configuration

1. Copy the example:
```bash
cp session_configs/example_session.json session_configs/my_session.json
```

2. Edit to match your needs:
```bash
vim session_configs/my_session.json
```

3. Test it:
```bash
system start session_configs/my_session.json
```

## Summary

✅ **Mandatory configuration file** - No defaults or fallbacks  
✅ **Strict validation** - Clear error messages for all failures  
✅ **Streams before RUNNING** - Critical sequence enforcement  
✅ **Risk management** - Explicit position limits and buying power  
✅ **Multi-symbol support** - Configure multiple data streams  
✅ **API flexibility** - Choose data and trading providers  
✅ **Async architecture** - Proper async/support  
✅ **Metadata support** - Track strategy info and notes  

The system now requires explicit, validated configuration for all sessions, ensuring safer and more predictable trading operations.
