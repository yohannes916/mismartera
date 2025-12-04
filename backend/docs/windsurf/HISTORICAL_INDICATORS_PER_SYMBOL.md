# Historical Indicators - Per-Symbol Implementation

## Summary

Changed historical indicators from global storage to **per-symbol storage**, matching the JSON export structure where each symbol has its own data.

## Changes Made

### 1. **SymbolSessionData Structure**
**File:** `/app/managers/data_manager/session_data.py`

Added `historical_indicators` field to `SymbolSessionData`:
```python
@dataclass
class SymbolSessionData:
    # ... existing fields ...
    
    # Historical indicators for this symbol
    # Structure: {indicator_key: value}
    # Example: {"avg_volume_2d": 12345678.9, "max_price_5d": 150.25}
    historical_indicators: Dict[str, Any] = field(default_factory=dict)
```

### 2. **JSON Export Structure**
**File:** `/app/managers/data_manager/session_data.py`

Indicators now export at root level of each symbol, alongside `session` and `historical`:

```json
{
  "symbols": {
    "RIVN": {
      "session": { "volume": 123, "high": 15.50, ... },
      "historical": { "loaded": true, "data": {...} },
      "avg_volume_2d": 12345678.9,
      "max_price_5d": 150.25
    }
  }
}
```

**NOT** nested under `historical.indicators` or separate `historical_indicators` section.

### 3. **API Methods Updated**
**File:** `/app/managers/data_manager/session_data.py`

All indicator methods now require `symbol` parameter:

```python
# OLD (Global)
session_data.set_historical_indicator("avg_volume_2d", 12345678.9)
avg_vol = session_data.get_historical_indicator("avg_volume_2d")
all_indicators = session_data.get_all_historical_indicators()

# NEW (Per-Symbol)
session_data.set_historical_indicator("RIVN", "avg_volume_2d", 12345678.9)
avg_vol = session_data.get_historical_indicator("RIVN", "avg_volume_2d")
all_indicators = session_data.get_all_historical_indicators("RIVN")
```

### 4. **Indicator Calculation Per Symbol**
**File:** `/app/threads/session_coordinator.py`

Updated `_calculate_historical_indicators()` to calculate per symbol:

```python
# Calculate indicators for each symbol
for symbol in symbols:
    for indicator_name, indicator_config in indicators.items():
        # Calculate for this symbol
        result = self._calculate_trailing_average(
            symbol,  # ← Added symbol parameter
            indicator_name,
            indicator_config
        )
        
        # Store per symbol
        self.session_data.set_historical_indicator(symbol, storage_key, result)
```

### 5. **Updated Calculation Methods**

All calculation methods now accept `symbol` parameter:

- `_calculate_trailing_average(symbol, indicator_name, config)`
- `_calculate_trailing_max(symbol, indicator_name, config)`
- `_calculate_trailing_min(symbol, indicator_name, config)`
- `_calculate_daily_average(symbol, field, period_days, skip_early_close)`

The `_calculate_daily_average()` now only processes data for the specified symbol instead of aggregating across all symbols.

### 6. **Removed Global Storage**

Removed from `SessionData.__init__()`:
```python
# ❌ REMOVED
self._historical_indicators: Dict[str, any] = {}
```

Removed from `SessionData.to_json()`:
```python
# ❌ REMOVED
if complete and self._historical_indicators:
    result["historical_indicators"] = self._historical_indicators.copy()
```

## Benefits

1. **Per-Symbol Analysis**: Each symbol has its own indicators
2. **Multi-Symbol Support**: Different symbols can have different indicator values
3. **Clean JSON Structure**: Indicators at root level alongside session/historical data
4. **Consistent Architecture**: Matches the per-symbol data structure throughout the system

## Example Configuration

```json
{
  "historical": {
    "indicators": {
      "avg_volume": {
        "type": "trailing_average",
        "period": "2d",
        "granularity": "daily",
        "field": "volume"
      }
    }
  }
}
```

## Example JSON Output

```json
{
  "symbols": {
    "RIVN": {
      "session": {
        "volume": 1234567,
        "high": 15.50,
        "low": 14.80,
        "quality": 100.0,
        "data": { ... }
      },
      "historical": {
        "loaded": true,
        "data": {
          "1d": { ... }
        }
      },
      "avg_volume_2d": 12345678.9
    },
    "AAPL": {
      "session": { ... },
      "historical": { ... },
      "avg_volume_2d": 98765432.1
    }
  }
}
```

## Analysis Engine Access

```python
# In analysis engine
from app.managers.data_manager.session_data import get_session_data

session_data = get_session_data()

# Get indicator for specific symbol
rivn_avg_vol = session_data.get_historical_indicator("RIVN", "avg_volume_2d")
aapl_avg_vol = session_data.get_historical_indicator("AAPL", "avg_volume_2d")

# Get all indicators for a symbol
rivn_indicators = session_data.get_all_historical_indicators("RIVN")
# {'avg_volume_2d': 12345678.9, 'max_price_5d': 150.25}
```

## Migration Notes

- No migration needed for configs (format unchanged)
- Code accessing indicators must now provide symbol parameter
- JSON exports will have new structure (indicators at symbol root level)

## Status

✅ **Complete** - All changes implemented and tested
