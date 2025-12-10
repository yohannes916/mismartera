# Strategy Configuration Explained - December 9, 2025

## Overview

Explanation of the `strategies` configuration in `session_config.json`, based on the existing scanner framework pattern.

---

## Configuration Format

### Location in session_config.json

```json
{
  "session_data_config": {
    "symbols": ["AAPL", "GOOGL", "TSLA"],
    "streams": ["1m", "5m"],
    "strategies": [
      {
        "module": "strategies.examples.simple_ma_cross",
        "enabled": true,
        "config": {
          "symbols": ["AAPL"],
          "interval": "5m",
          "fast_period": 10,
          "slow_period": 20
        }
      },
      {
        "module": "strategies.production.my_strategy",
        "enabled": true,
        "config": {
          "symbols": ["AAPL", "GOOGL"],
          "interval": "5m",
          "min_quality": 95.0,
          "max_position_size": 100
        }
      },
      {
        "module": "strategies.examples.rsi_strategy",
        "enabled": false,
        "config": {
          "symbols": ["TSLA"],
          "interval": "1m",
          "rsi_period": 14,
          "oversold": 30,
          "overbought": 70
        }
      }
    ]
  }
}
```

---

## Field Explanations

### Top-Level Fields

#### `module` (required, string)

**Purpose**: Python module path to the strategy class

**Format**: `"strategies.subfolder.module_name"`

**Examples**:
- `"strategies.examples.simple_ma_cross"` → File: `strategies/examples/simple_ma_cross.py`
- `"strategies.production.my_strategy"` → File: `strategies/production/my_strategy.py`
- `"strategies.momentum_strategy"` → File: `strategies/momentum_strategy.py`

**Rules**:
- Must be a valid Python module path
- File must exist in `strategies/` directory
- Class name derived from file name (e.g., `simple_ma_cross.py` → `SimpleMaCrossStrategy`)
- Subfolders allowed for organization

**Similar to**: Scanner framework's `module` field

---

#### `enabled` (optional, boolean, default: true)

**Purpose**: Enable or disable strategy without removing from config

**Examples**:
```json
"enabled": true   // Strategy will be loaded and run
"enabled": false  // Strategy skipped (for testing/debugging)
```

**Use Cases**:
- Temporarily disable underperforming strategy
- A/B testing (enable one at a time)
- Development (disable production strategies)
- Quick toggle without editing config

**Similar to**: Scanner framework's `enabled` field

---

#### `config` (optional, object, default: {})

**Purpose**: Strategy-specific configuration passed to strategy instance

**Content**: Completely flexible - strategy defines what it needs

**Common Parameters**:

1. **Data Selection**:
   ```json
   "symbols": ["AAPL", "GOOGL"]     // Which symbols to trade
   "interval": "5m"                  // Which interval to use
   ```

2. **Strategy Parameters**:
   ```json
   "fast_period": 10                 // Fast MA period
   "slow_period": 20                 // Slow MA period
   "rsi_period": 14                  // RSI lookback
   "threshold": 0.02                 // 2% threshold
   ```

3. **Risk Management**:
   ```json
   "max_position_size": 100          // Max shares per trade
   "min_quality": 95.0               // Minimum data quality
   "stop_loss_pct": 0.02             // 2% stop loss
   ```

4. **Operating Parameters**:
   ```json
   "warmup_bars": 50                 // Bars needed before signals
   "min_volume": 1000000             // Minimum daily volume
   "trading_hours_only": true        // Only trade during market hours
   ```

**Access in Strategy**:
```python
class SimpleMaCrossStrategy(BaseStrategy):
    def setup(self, context):
        # Access via self.config
        self.fast_period = self.config.get('fast_period', 10)
        self.slow_period = self.config.get('slow_period', 20)
        self.symbols = self.config.get('symbols', [])
```

**Similar to**: Scanner framework's `config` field (completely flexible per scanner/strategy)

---

## Complete Example with Multiple Strategies

```json
{
  "mode": "backtest",
  "session_data_config": {
    "symbols": ["AAPL", "GOOGL", "TSLA", "MSFT"],
    "streams": ["1m", "5m", "15m"],
    
    "strategies": [
      {
        "module": "strategies.examples.simple_ma_cross",
        "enabled": true,
        "config": {
          "symbols": ["AAPL", "GOOGL"],
          "interval": "5m",
          "fast_period": 10,
          "slow_period": 20,
          "min_quality": 95.0
        }
      },
      {
        "module": "strategies.examples.rsi_strategy",
        "enabled": true,
        "config": {
          "symbols": ["TSLA"],
          "interval": "1m",
          "rsi_period": 14,
          "oversold": 30,
          "overbought": 70,
          "min_quality": 98.0
        }
      },
      {
        "module": "strategies.production.vwap_strategy",
        "enabled": false,
        "config": {
          "symbols": ["MSFT"],
          "interval": "15m",
          "vwap_deviation": 0.01,
          "volume_threshold": 1000000
        }
      }
    ]
  }
}
```

---

## Strategy Lifecycle

### 1. Loading (SystemManager → StrategyManager)

```python
# StrategyManager reads config
strategies_config = session_config.session_data_config.strategies

for strategy_config in strategies_config:
    if not strategy_config.enabled:
        continue  # Skip disabled
    
    # Load module: "strategies.examples.simple_ma_cross"
    module = importlib.import_module(strategy_config.module)
    
    # Find strategy class: SimpleMaCrossStrategy
    strategy_class = find_strategy_class(module)
    
    # Instantiate with config
    strategy = strategy_class(
        name="simple_ma_cross",
        config=strategy_config.config  # Pass the config dict
    )
```

### 2. Initialization (strategy.setup)

```python
# Strategy receives config in setup
def setup(self, context: StrategyContext) -> bool:
    # Extract parameters from config
    self.symbols = self.config.get('symbols', [])
    self.interval = self.config.get('interval', '5m')
    self.fast_period = self.config.get('fast_period', 10)
    self.slow_period = self.config.get('slow_period', 20)
    
    # Validate parameters
    if self.fast_period >= self.slow_period:
        logger.error("fast_period must be < slow_period")
        return False
    
    return True
```

### 3. Runtime (strategy.on_bars)

```python
def on_bars(self, symbol: str, interval: str) -> List[Signal]:
    # Use config parameters
    if symbol not in self.config.get('symbols', []):
        return []  # Not subscribed to this symbol
    
    if interval != self.config.get('interval', '5m'):
        return []  # Not subscribed to this interval
    
    # Generate signals using config parameters
    fast_ma = calculate_ma(bars, self.fast_period)
    slow_ma = calculate_ma(bars, self.slow_period)
    
    # ...
```

---

## Config vs Code Relationship

### What Goes in Config?

✅ **Parameters that change between runs**:
- Symbol lists (different universes)
- Periods/thresholds (parameter tuning)
- Risk limits (position sizing)
- Quality requirements (data filtering)

✅ **Operational flags**:
- `enabled` (turn on/off)
- Mode-specific parameters
- Testing vs production settings

### What Goes in Code?

✅ **Strategy logic**:
- How to calculate indicators
- Signal generation rules
- Entry/exit logic

✅ **Default parameters**:
```python
self.fast_period = self.config.get('fast_period', 10)  # Default: 10
```

✅ **Parameter validation**:
```python
if self.fast_period <= 0:
    raise ValueError("fast_period must be positive")
```

---

## Comparison: Scanners vs Strategies

### Scanner Config

```json
{
  "module": "scanners.examples.gap_scanner",
  "enabled": true,
  "pre_session": true,
  "regular_session": [
    {
      "start_time": "10:30",
      "end_time": "15:30",
      "interval": "30m"
    }
  ],
  "config": {
    "universe": "data/universes/sp500.txt",
    "min_gap_pct": 2.0
  }
}
```

### Strategy Config

```json
{
  "module": "strategies.examples.simple_ma_cross",
  "enabled": true,
  "config": {
    "symbols": ["AAPL"],
    "interval": "5m",
    "fast_period": 10,
    "slow_period": 20
  }
}
```

### Key Differences

| Feature | Scanner | Strategy |
|---------|---------|----------|
| **Timing** | Scheduled (pre_session, regular_session) | Event-driven (on every bar) |
| **Purpose** | Find symbols | Generate signals |
| **Output** | List of symbols | Trading signals |
| **Config** | Schedules + parameters | Subscriptions + parameters |

### Similarities

| Feature | Both |
|---------|------|
| **Module-based** | Load from Python modules |
| **Enabled flag** | Can disable without deleting |
| **Flexible config** | Strategy/scanner-specific parameters |
| **Organized** | Subfolders allowed |

---

## Validation Rules

### Module Path

```python
# Must be valid Python identifier path
"strategies.examples.simple_ma_cross"  # ✅ Valid
"strategies.my-strategy"               # ❌ Invalid (hyphen)
"strategies.123_strategy"              # ❌ Invalid (starts with number)
```

### Enabled Flag

```python
"enabled": true   # ✅ Valid (boolean)
"enabled": false  # ✅ Valid (boolean)
"enabled": "yes"  # ❌ Invalid (string)
"enabled": 1      # ❌ Invalid (number)
```

### Config Object

```python
"config": {}                           # ✅ Valid (empty)
"config": {"symbols": ["AAPL"]}       # ✅ Valid (with data)
"config": null                         # ❌ Invalid (must be object)
"config": []                           # ❌ Invalid (must be object)
```

---

## Advanced: Config Inheritance

### Use Case: Multiple strategies with similar config

**Option 1: Explicit (Recommended)**
```json
{
  "strategies": [
    {
      "module": "strategies.ma_cross",
      "config": {
        "symbols": ["AAPL"],
        "interval": "5m",
        "fast_period": 10,
        "slow_period": 20
      }
    },
    {
      "module": "strategies.ma_cross",
      "config": {
        "symbols": ["GOOGL"],
        "interval": "5m",
        "fast_period": 10,
        "slow_period": 20
      }
    }
  ]
}
```

**Option 2: Strategy determines from session symbols**
```json
{
  "symbols": ["AAPL", "GOOGL", "TSLA"],
  "strategies": [
    {
      "module": "strategies.ma_cross",
      "config": {
        "symbols": "all",  // Strategy reads from session_data_config.symbols
        "interval": "5m",
        "fast_period": 10,
        "slow_period": 20
      }
    }
  ]
}
```

```python
# In strategy
def get_subscriptions(self):
    symbol_config = self.config.get('symbols')
    
    if symbol_config == "all":
        # Subscribe to all session symbols
        symbols = self.context.session_data.get_symbols()
    else:
        symbols = symbol_config
    
    interval = self.config.get('interval', '5m')
    return [(s, interval) for s in symbols]
```

---

## Error Handling

### Missing Module

```python
# Config
"module": "strategies.nonexistent"

# Error
ModuleNotFoundError: No module named 'strategies.nonexistent'
```

### Invalid Config Parameter

```python
# Strategy validates in setup()
def setup(self, context):
    if 'symbols' not in self.config:
        logger.error("Missing required config: 'symbols'")
        return False  # Setup fails, strategy not started
```

### Strategy Errors

```python
# During setup
if not strategy.setup(context):
    logger.error(f"Strategy {name} setup failed - not starting")
    # Strategy excluded from active list

# During on_bars
try:
    signals = strategy.on_bars(symbol, interval)
except Exception as e:
    logger.error(f"Strategy {name} error: {e}")
    # Log, increment error counter, continue
```

---

## Best Practices

### 1. Use Defaults in Code

```python
# ✅ Good - provides defaults
self.fast_period = self.config.get('fast_period', 10)
self.slow_period = self.config.get('slow_period', 20)

# ❌ Bad - crashes if not in config
self.fast_period = self.config['fast_period']
```

### 2. Validate in setup()

```python
def setup(self, context):
    # Validate required fields
    if 'symbols' not in self.config:
        logger.error("Missing required config: 'symbols'")
        return False
    
    # Validate parameter ranges
    if self.config.get('fast_period', 0) <= 0:
        logger.error("fast_period must be positive")
        return False
    
    return True
```

### 3. Document Config in Docstring

```python
class SimpleMaCrossStrategy(BaseStrategy):
    """Simple moving average crossover strategy.
    
    Config Parameters:
        symbols (List[str]): Symbols to trade
        interval (str): Bar interval (e.g., "5m")
        fast_period (int): Fast MA period (default: 10)
        slow_period (int): Slow MA period (default: 20)
        min_quality (float): Minimum data quality % (default: 95.0)
    
    Example Config:
        {
            "symbols": ["AAPL", "GOOGL"],
            "interval": "5m",
            "fast_period": 10,
            "slow_period": 20,
            "min_quality": 95.0
        }
    """
```

### 4. Keep Config Flat

```python
# ✅ Good - flat structure
"config": {
    "fast_period": 10,
    "slow_period": 20,
    "min_quality": 95.0
}

# ❌ Avoid - nested complexity
"config": {
    "ma_params": {
        "fast": {
            "period": 10,
            "type": "simple"
        },
        "slow": {
            "period": 20,
            "type": "simple"
        }
    }
}
```

---

## Summary

### Strategy Config Structure

```json
{
  "module": "strategies.path.to.strategy",  // Required: Module path
  "enabled": true,                          // Optional: Enable/disable
  "config": {                               // Optional: Strategy parameters
    "symbols": ["AAPL"],
    "interval": "5m",
    "parameter1": value1,
    "parameter2": value2
  }
}
```

### Key Points

1. ✅ **Module-based**: Load from Python files
2. ✅ **Flexible config**: Strategy defines what it needs
3. ✅ **Enable/disable**: Quick toggle
4. ✅ **Organized**: Use subfolders
5. ✅ **Validated**: Errors caught in setup()
6. ✅ **Similar to scanners**: Consistent pattern

### Config Principles

- **Config**: What changes (symbols, parameters)
- **Code**: How it works (logic, calculations)
- **Defaults**: Always provide in code
- **Validation**: Check in setup()
- **Documentation**: Explain in docstring

---

## Existing Pause Feature

### Location

`app/threads/session_coordinator.py` lines 638-680

### API

```python
def pause_backtest():
    """Pause backtest streaming/time advancement."""
    self._stream_paused.clear()

def resume_backtest():
    """Resume backtest streaming/time advancement."""
    self._stream_paused.set()

def is_paused() -> bool:
    """Check if backtest is currently paused."""
    return not self._stream_paused.is_set()
```

### Usage in Streaming Loop

```python
# Line 2238-2241 in session_coordinator.py
if self.mode == "backtest":
    # Wait until resume signal
    self._stream_paused.wait()
```

### When Used

1. **Scanner execution** - Clock paused while scanner runs
2. **Mid-session symbol insertion** - Clock paused during symbol registration

### Behavior

- ✅ Clock frozen at current time
- ✅ No new bars arrive
- ✅ Strategies idle (waiting on queues)
- ✅ Safe to modify SessionData
- ✅ Thread-safe (Event-based)

**Already implemented and working!**

