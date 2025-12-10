# Unified Requirement Analysis

## Core Principle

**One Routine**: All indicator additions (session_config and adhoc) use the same `requirement_analyzer` to determine and provision required bars.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    REQUIREMENT ANALYZER                       │
│                  (Single Source of Truth)                     │
└────────────────────┬─────────────────────────────────────────┘
                     │
         ┌───────────┴────────────┐
         │                        │
         ▼                        ▼
┌──────────────────┐    ┌──────────────────────┐
│  session_config  │    │ Scanner add_indicator │
│   Indicators     │    │     (adhoc)          │
└──────────────────┘    └──────────────────────┘
         │                        │
         │                        │
         └───────────┬────────────┘
                     │
                     ▼
         ┌──────────────────────┐
         │  Provision Bars:     │
         │  - Historical (warmup)│
         │  - Session (live)    │
         └──────────────────────┘
```

---

## Unified Flow

### 1. Session Config Indicators

```python
# session_config.json
{
  "indicators": [
    {
      "name": "sma",
      "period": 20,
      "interval": "5m"
    }
  ]
}

# SessionCoordinator processes
for indicator_config in session_config.indicators:
    # Call requirement_analyzer
    requirements = requirement_analyzer.analyze_indicator_requirements(
        indicator_config=indicator_config,
        warmup_multiplier=2.0
    )
    
    # Provision bars
    for interval in requirements.required_intervals:
        add_historical_bars(symbol, interval, requirements.historical_days)
        add_session_bars(symbol, interval)
    
    # Register indicator
    indicator_manager.register(symbol, indicator_config)
```

---

### 2. Adhoc Scanner Indicators

```python
# Scanner code
context.session_data.add_indicator(
    "SPY",
    "sma",
    {
        "period": 20,
        "interval": "5m"
    }
)

# add_indicator() implementation
def add_indicator(symbol, indicator_type, config):
    # Create IndicatorConfig
    indicator_config = IndicatorConfig(
        name=indicator_type,
        period=config["period"],
        interval=config["interval"],
        params=config.get("params", {})
    )
    
    # SAME ROUTINE: Call requirement_analyzer
    requirements = requirement_analyzer.analyze_indicator_requirements(
        indicator_config=indicator_config,
        warmup_multiplier=2.0
    )
    
    # SAME ROUTINE: Provision bars
    for interval in requirements.required_intervals:
        add_historical_bars(symbol, interval, requirements.historical_days)
        add_session_bars(symbol, interval)
    
    # SAME ROUTINE: Register indicator
    indicator_manager.register(symbol, indicator_config)
```

---

## requirement_analyzer API

### Input

```python
from app.indicators import IndicatorConfig

indicator_config = IndicatorConfig(
    name="sma",
    period=20,
    interval="5m",
    params={}
)
```

### Analysis

```python
requirements = requirement_analyzer.analyze_indicator_requirements(
    indicator_config=indicator_config,
    warmup_multiplier=2.0  # 2x period for warmup
)
```

### Output

```python
class IndicatorRequirements:
    required_intervals: List[str]  # ["5m"]
    historical_days: int           # 40 (for SMA(20) warmup)
    base_interval: str             # "5m"
    derived_intervals: List[str]   # [] (none for this example)
```

---

## Examples

### Example 1: Simple SMA

```python
# Indicator
add_indicator("SPY", "sma", {"period": 20, "interval": "1d"})

# requirement_analyzer determines:
requirements = {
    "required_intervals": ["1d"],
    "historical_days": 40,  # 2x 20 periods
    "base_interval": "1d"
}

# Auto-provisions:
add_historical_bars("SPY", "1d", days=40)
add_session_bars("SPY", "1d")
```

---

### Example 2: RSI with Sub-Interval

```python
# Indicator
add_indicator("SPY", "rsi", {"period": 14, "interval": "5m"})

# requirement_analyzer determines:
# RSI needs price changes, so needs consecutive bars
requirements = {
    "required_intervals": ["5m"],
    "historical_days": 28,  # 2x 14 periods (converted to days)
    "base_interval": "5m"
}

# Auto-provisions:
add_historical_bars("SPY", "5m", days=28)
add_session_bars("SPY", "5m")
```

---

### Example 3: MACD (Multiple Components)

```python
# Indicator
add_indicator("SPY", "macd", {
    "fast_period": 12,
    "slow_period": 26,
    "signal_period": 9,
    "interval": "1d"
})

# requirement_analyzer determines:
# MACD uses EMA(12), EMA(26), then EMA(9) of difference
# Needs longest period for warmup
requirements = {
    "required_intervals": ["1d"],
    "historical_days": 52,  # 2x 26 (slowest component)
    "base_interval": "1d"
}

# Auto-provisions:
add_historical_bars("SPY", "1d", days=52)
add_session_bars("SPY", "1d")
```

---

## Benefits

### 1. Consistency

```
✅ Same logic for session_config and adhoc
✅ Same warmup calculation (2x period)
✅ Same bar provisioning routine
✅ No duplicate code
```

### 2. Correctness

```
✅ requirement_analyzer knows indicator internals
✅ Automatically provisions correct intervals
✅ Calculates proper warmup periods
✅ Handles complex indicators (MACD, Bollinger Bands)
```

### 3. Simplicity

```
Scanner developer doesn't need to:
❌ Know what bars an indicator needs
❌ Calculate warmup periods
❌ Manually provision bars
❌ Worry about derived intervals

Scanner developer just calls:
✅ add_indicator(symbol, type, config)
   → Everything provisioned automatically!
```

---

## Comparison: Before vs After

### Before (Manual Bar Provisioning)

```python
# Scanner has to know indicator internals ❌
def setup(self, context):
    for symbol in universe:
        # Manually add bars
        context.session_data.add_historical_bars(symbol, "1d", days=40)
        context.session_data.add_session_bars(symbol, "1d")
        
        # Then add indicator
        context.session_data.add_indicator(symbol, "sma", {
            "period": 20,
            "interval": "1d"
        })

# Problems:
# - Scanner must calculate 40 days (2x 20)
# - Scanner must know SMA uses 1d bars
# - Easy to get wrong
# - Duplicate logic everywhere
```

### After (Automatic Provisioning)

```python
# Scanner just specifies what indicator it needs ✅
def setup(self, context):
    for symbol in universe:
        # Just add indicator - bars provisioned automatically!
        context.session_data.add_indicator(symbol, "sma", {
            "period": 20,
            "interval": "1d"
        })

# Benefits:
# - requirement_analyzer calculates days (40)
# - requirement_analyzer knows SMA uses 1d bars
# - Same logic as session_config
# - Scanner code is simple
```

---

## Implementation in add_indicator()

```python
def add_indicator(self, symbol: str, indicator_type: str, config: dict) -> bool:
    """Add indicator with automatic bar provisioning."""
    from app.threads.quality.requirement_analyzer import requirement_analyzer
    
    # 1. Create IndicatorConfig
    indicator_config = IndicatorConfig(
        name=indicator_type,
        period=config.get("period", 0),
        interval=config["interval"],
        params=config.get("params", {})
    )
    
    # 2. UNIFIED: Use requirement_analyzer
    requirements = requirement_analyzer.analyze_indicator_requirements(
        indicator_config=indicator_config,
        warmup_multiplier=2.0
    )
    
    # 3. UNIFIED: Provision bars automatically
    for interval in requirements.required_intervals:
        if requirements.historical_days > 0:
            self.add_historical_bars(
                symbol=symbol,
                interval=interval,
                days=requirements.historical_days
            )
        
        self.add_session_bars(
            symbol=symbol,
            interval=interval
        )
    
    # 4. Register indicator
    self._indicator_manager.register_symbol_indicators(
        symbol=symbol,
        indicators=[indicator_config]
    )
    
    return True
```

---

## Summary

### Unified Routine

✅ **One Function**: `requirement_analyzer.analyze_indicator_requirements()`  
✅ **One Logic**: Used by session_config AND adhoc  
✅ **One Truth**: requirement_analyzer knows all indicators  
✅ **One Result**: Correct bars always provisioned  

### Scanner Simplification

**Before**:
```python
add_historical_bars(symbol, interval, days)  # Manual
add_session_bars(symbol, interval)            # Manual
add_indicator(symbol, type, config)           # Then indicator
```

**After**:
```python
add_indicator(symbol, type, config)  # Bars automatic!
```

### Key Insight

> **Scanner developers don't need to know indicator internals.**  
> **requirement_analyzer handles all the complexity.**  
> **Same unified routine for everyone.**

This is the clean, correct architecture! 🎯
