# Mode and Backtest Configuration Enhancement

## Overview

Added **mode selection** and **backtest window configuration** directly to session configuration files. The system now automatically applies the correct operation mode and backtest parameters when starting a session.

## New Configuration Fields

### 1. Mode (Required)

```json
"mode": "backtest"  // or "live"
```

**Description**: Specifies the operation mode for the session

**Valid Values**:
- `"live"` - Real-time live trading (or paper trading with live data)
- `"backtest"` - Historical simulation mode

**Validation**:
- ✅ Must be present
- ✅ Must be one of: "live" or "backtest"
- ✅ System will automatically switch to specified mode on startup

### 2. Backtest Configuration (Required for Backtest Mode)

```json
"backtest_config": {
  "start_date": "2024-11-01",
  "end_date": "2024-11-22",
  "speed_multiplier": 0.0
}
```

**Description**: Defines the backtest window and execution speed

**Fields**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `start_date` | string | Yes (for backtest) | Backtest start date (YYYY-MM-DD) |
| `end_date` | string | Yes (for backtest) | Backtest end date (YYYY-MM-DD) |
| `speed_multiplier` | number | No (default: 0.0) | Execution speed (0=max, 1.0=realtime, 2.0=2x) |

**Validation Rules**:
- ✅ Dates must be in YYYY-MM-DD format
- ✅ `start_date` must be before or equal to `end_date`
- ✅ `speed_multiplier` must be >= 0
- ✅ Required when `mode` is "backtest"
- ✅ Optional/ignored when `mode` is "live"

## Complete Configuration Examples

### Backtest Session

```json
{
  "session_name": "Example Trading Session",
  "mode": "backtest",
  "data_streams": [
    {
      "type": "bars",
      "symbol": "AAPL",
      "interval": "1m"
    },
    {
      "type": "ticks",
      "symbol": "AAPL"
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
  "backtest_config": {
    "start_date": "2024-11-01",
    "end_date": "2024-11-22",
    "speed_multiplier": 0.0
  },
  "metadata": {
    "created_by": "user",
    "description": "Backtest session for momentum strategy",
    "strategy": "momentum_scalping"
  }
}
```

### Live Session

```json
{
  "session_name": "Live Trading Session",
  "mode": "live",
  "data_streams": [
    {
      "type": "bars",
      "symbol": "SPY",
      "interval": "1m"
    },
    {
      "type": "ticks",
      "symbol": "SPY"
    },
    {
      "type": "quotes",
      "symbol": "SPY"
    }
  ],
  "trading_config": {
    "max_buying_power": 50000.0,
    "max_per_trade": 5000.0,
    "max_per_symbol": 10000.0,
    "max_open_positions": 3,
    "paper_trading": true
  },
  "api_config": {
    "data_api": "alpaca",
    "trade_api": "alpaca",
    "account_id": "paper_live_trading"
  },
  "metadata": {
    "created_by": "user",
    "description": "Live paper trading session for SPY",
    "strategy": "day_trading"
  }
}
```

**Note**: Live sessions don't need `backtest_config`

## How It Works

### Startup Sequence

```
1. Load session configuration file
   ↓
2. Parse mode field
   ↓
3. System automatically switches to specified mode
   ↓
4. If mode is "backtest":
   │  ├─ Parse backtest_config
   │  ├─ Validate dates and speed
   │  ├─ Set backtest window
   │  └─ Configure backtest speed
   ↓
5. Start data streams
   ↓
6. Transition to RUNNING
```

### Mode Switching

The system automatically switches modes when starting:

```python
# If config mode differs from current mode
if self._session_config.mode != self._mode.value:
    logger.info(f"Setting operation mode to: {self._session_config.mode}")
    self.set_mode(self._session_config.mode)
```

**Note**: Mode can only be changed when system is STOPPED

### Backtest Configuration

When in backtest mode, the system:

1. **Parses dates** from configuration
2. **Sets backtest window** via `data_manager.set_backtest_window()`
3. **Configures speed** via `data_manager.backtest_speed`
4. **Initializes time provider** with start date

## Success Output

### Backtest Mode
```
System started successfully!
  Session: Example Trading Session
  Mode: BACKTEST
  Backtest Window: 2024-11-01 to 2024-11-22
  Speed: 0.0x (0=max)
  Streams: 6 active
  Max Buying Power: $100,000.00
  Max Per Trade: $10,000.00
  Paper Trading: True
```

### Live Mode
```
System started successfully!
  Session: Live Trading Session
  Mode: LIVE
  Streams: 3 active
  Max Buying Power: $50,000.00
  Max Per Trade: $5,000.00
  Paper Trading: True
```

## Configuration Model Updates

### BacktestConfig Class

```python
@dataclass
class BacktestConfig:
    """Backtest configuration for historical simulation."""
    start_date: str  # YYYY-MM-DD format
    end_date: str    # YYYY-MM-DD format
    speed_multiplier: float = 0.0  # 0 = max speed
    
    def validate(self) -> None:
        """Validates date formats, range, and speed."""
```

### SessionConfig Class

```python
@dataclass
class SessionConfig:
    """Complete session configuration."""
    session_name: str
    mode: str  # "live" or "backtest" ← NEW
    data_streams: List[DataStreamConfig]
    trading_config: TradingConfig
    api_config: APIConfig
    backtest_config: Optional[BacktestConfig] = None  # ← NEW
    metadata: Optional[Dict[str, Any]] = None
```

## Validation

### Mode Validation
```python
valid_modes = ["live", "backtest"]
if self.mode not in valid_modes:
    raise ValueError(f"Invalid mode: {self.mode}")
```

### Backtest Config Validation
```python
# Backtest mode requires backtest_config
if self.mode == "backtest" and not self.backtest_config:
    raise ValueError("backtest_config is required when mode is 'backtest'")

# If backtest_config present, validate it
if self.backtest_config:
    self.backtest_config.validate()
```

### Date Format Validation
```python
# Dates must be YYYY-MM-DD
datetime.strptime(self.start_date, "%Y-%m-%d")
datetime.strptime(self.end_date, "%Y-%m-%d")

# Start must be before or equal to end
if start > end:
    raise ValueError("start_date must be before or equal to end_date")
```

### Speed Validation
```python
if self.speed_multiplier < 0:
    raise ValueError("speed_multiplier must be >= 0 (0 = max speed)")
```

## Usage Examples

### CLI

```bash
# Start backtest session
system start session_configs/example_session.json

# Start live session
system start session_configs/live_session_example.json
```

### Python API

```python
# The system will automatically apply mode and backtest config
await system_mgr.start("session_configs/example_session.json")

# Access configuration
if system_mgr.session_config:
    print(f"Mode: {system_mgr.session_config.mode}")
    if system_mgr.session_config.backtest_config:
        print(f"Window: {system_mgr.session_config.backtest_config.start_date} to "
              f"{system_mgr.session_config.backtest_config.end_date}")
```

## Speed Multiplier Guide

| Value | Behavior | Use Case |
|-------|----------|----------|
| 0.0 | Maximum speed (no delays) | Fast backtests, historical analysis |
| 1.0 | Real-time (matches live speed) | Strategy testing with realistic timing |
| 2.0 | 2x speed | Faster than realtime but with timing |
| 0.5 | Half speed (slow motion) | Detailed observation, debugging |

## Error Handling

### Missing Mode
```
ValueError: Missing required field: mode
```

### Invalid Mode
```
ValueError: Invalid mode: invalid. Must be one of ['live', 'backtest']
```

### Missing Backtest Config (Backtest Mode)
```
ValueError: backtest_config is required when mode is 'backtest'
```

### Invalid Date Format
```
ValueError: Invalid start_date format: 2024-13-01. Use YYYY-MM-DD
```

### Invalid Date Range
```
ValueError: start_date (2024-11-22) must be before or equal to end_date (2024-11-01)
```

### Invalid Speed
```
ValueError: speed_multiplier must be >= 0 (0 = max speed)
```

## Files Modified

### 1. Session Configuration Model
**File**: `app/models/session_config.py`

**Added**:
- `BacktestConfig` dataclass with validation
- `mode` field to `SessionConfig`
- `backtest_config` field to `SessionConfig`
- Mode and backtest config validation
- Date parsing and validation logic

### 2. System Manager
**File**: `app/managers/system_manager.py`

**Updated**:
- Parses `mode` from configuration
- Automatically switches mode on startup
- Parses and applies `backtest_config`
- Sets backtest window and speed
- Enhanced success message with mode and backtest info

### 3. Example Configurations
**Files**:
- `session_configs/example_session.json` - Updated with mode and backtest_config
- `session_configs/live_session_example.json` - New live session example

## Benefits

1. ✅ **Declarative Mode** - Mode specified in config, not command line
2. ✅ **Self-Contained** - All session parameters in one file
3. ✅ **Version Control** - Backtest windows tracked with strategy
4. ✅ **Reproducibility** - Exact configuration for reproducible backtests
5. ✅ **Validation** - Date formats and ranges validated
6. ✅ **Flexibility** - Easy to create multiple backtest periods
7. ✅ **Clarity** - Clear distinction between live and backtest sessions
8. ✅ **Speed Control** - Backtest speed configurable per session

## Migration

### Old Approach (Manual)
```bash
# Had to manually set mode first
system mode backtest
system start session_configs/config.json
```

### New Approach (Automatic)
```bash
# Mode and backtest config applied automatically
system start session_configs/example_session.json
```

## Best Practices

### 1. Create Separate Configs for Live vs Backtest
```
session_configs/
├── live/
│   └── day_trading.json
└── backtest/
    ├── 2024_q4.json
    └── 2024_november.json
```

### 2. Name Configs Descriptively
```json
"session_name": "Backtest_Momentum_2024_Q4"
```

### 3. Document Backtest Windows
```json
"metadata": {
  "description": "Q4 2024 backtest for momentum strategy",
  "notes": "Testing 60-day window with max speed"
}
```

### 4. Use Consistent Date Ranges
```json
// Trading days in November 2024
"start_date": "2024-11-01",
"end_date": "2024-11-30"
```

## Summary

✅ **Mode selection** now in configuration file  
✅ **Backtest window** defined in config  
✅ **Backtest speed** configurable per session  
✅ **Automatic mode switching** on startup  
✅ **Date validation** with clear error messages  
✅ **Self-contained configurations** for reproducibility  
✅ **Separate live and backtest** examples provided  

Sessions now fully define their operational parameters including mode and backtest settings!
