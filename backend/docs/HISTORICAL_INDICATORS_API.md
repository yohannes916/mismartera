# Historical Indicators API

## Overview

Historical indicators are calculated once before each session starts and stored in `SessionData` for access by the analysis engine.

## Configuration

**File:** `session_configs/example_session.json`

```json
{
  "session_data_config": {
    "historical": {
      "indicators": {
        "avg_volume": {
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
        },
        "max_price": {
          "type": "trailing_max",
          "period": "5d",
          "field": "close"
        }
      }
    }
  }
}
```

## Storage Keys

Indicators are stored with **auto-generated descriptive keys** that include the period:

| Config Name | Period | Storage Key | Description |
|-------------|--------|-------------|-------------|
| `avg_volume` | `2d` | **`avg_volume_2d`** | 2-day average volume |
| `avg_volume_long` | `10d` | **`avg_volume_long_10d`** | 10-day average volume |
| `max_price` | `5d` | **`max_price_5d`** | 5-day max close price |

This allows multiple indicators with the same base name but different periods.

## Analysis Engine Access

### Method 1: Get Specific Indicator

**Note:** Indicators are stored per-symbol, so you must specify the symbol when retrieving.

```python
from app.managers.data_manager.session_data import get_session_data

session_data = get_session_data()

# Get specific indicator by symbol and name
rivn_avg_vol_2d = session_data.get_historical_indicator("RIVN", "avg_volume_2d")
aapl_avg_vol_10d = session_data.get_historical_indicator("AAPL", "avg_volume_10d")

# Get all indicators for a symbol
rivn_indicators = session_data.get_all_historical_indicators("RIVN")
# Returns: {'avg_volume_2d': 12345678.9, 'max_price_5d': 150.25}
```

### Method 2: Get All Indicators for Symbol

```python
# Get all indicators for a specific symbol
rivn_indicators = session_data.get_all_historical_indicators("RIVN")

# Access by key
avg_vol = rivn_indicators.get("avg_volume_2d", 0.0)
max_price = indicators.get("max_price_5d", 0.0)

# Iterate all
for name, value in indicators.items():
    print(f"{name}: {value}")
```

## Indicator Types

### 1. Trailing Average (`trailing_average`)

**Daily Granularity:**
```json
{
  "type": "trailing_average",
  "period": "10d",
  "granularity": "daily",
  "field": "volume"
}
```
- Returns: Single float value
- Example: `12345678.9`

**Intraday Granularity:**
```json
{
  "type": "trailing_average",
  "period": "5d",
  "granularity": "minute",
  "field": "volume"
}
```
- Returns: List of 390 float values (one per minute of trading day)
- Example: `[1000.5, 1050.2, ..., 1200.8]` (390 values)

### 2. Trailing Max (`trailing_max`)

```json
{
  "type": "trailing_max",
  "period": "5d",
  "field": "close"
}
```
- Returns: Single float value (maximum)

### 3. Trailing Min (`trailing_min`)

```json
{
  "type": "trailing_min",
  "period": "5d",
  "field": "low"
}
```
- Returns: Single float value (minimum)

## Supported Fields

- `volume` - Trading volume
- `close` - Closing price
- `open` - Opening price
- `high` - High price
- `low` - Low price

## Example: Multiple Volume Indicators

**Config:**
```json
{
  "indicators": {
    "avg_volume_short": {
      "type": "trailing_average",
      "period": "2d",
      "granularity": "daily",
      "field": "volume"
    },
    "avg_volume_med": {
      "type": "trailing_average",
      "period": "5d",
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

**Analysis Engine:**
```python
# Access different periods for a symbol
vol_2d = session_data.get_historical_indicator("RIVN", "avg_volume_short_2d")
vol_5d = session_data.get_historical_indicator("RIVN", "avg_volume_med_5d")
vol_10d = session_data.get_historical_indicator("RIVN", "avg_volume_long_10d")

# Compare short vs long term
if vol_2d > vol_10d * 1.5:
    print("RIVN: Recent volume spike detected!")
```

## JSON Export

Indicators are exported **per-symbol** nested under the `historical` section:

```json
{
  "session_data": {
    "symbols": {
      "RIVN": {
        "session": {
          "volume": 1234567,
          "high": 15.50,
          "low": 14.80,
          "quality": {
            "1m": 100.0,
            "5m": 98.5
          }
        },
        "historical": {
          "loaded": true,
          "quality": {
            "1m": 100.0,
            "1d": 100.0
          },
          "data": {
            "1m": [...],
            "1d": [...]
          },
          "avg_volume_2d": 12345678.90,
          "avg_volume_long_10d": 10234567.80,
          "max_price_5d": 150.25
        }
      },
      "AAPL": {
        "session": {
          "quality": { "1m": 100.0 }
        },
        "historical": {
          "quality": { "1m": 100.0, "1d": 100.0 },
          "avg_volume_2d": 98765432.10,
          "max_price_5d": 180.45
        }
      }
    }
  }
}
```

**Note:** 
- Indicators are nested under `historical` section
- Quality is per-interval (not a single value) in both `session` and `historical`

## Implementation Details

- **Calculation:** Once per session before streaming starts, calculated per symbol
- **Storage:** In-memory in `SymbolSessionData.historical_indicators` dict (per-symbol)
- **Thread-safe:** All access methods use locks
- **Persistence:** Not persisted, recalculated each session
- **Data Source:** Uses 1d historical bars loaded from parquet for each symbol

## Notes

1. Indicators are calculated **before** the session starts (Phase 2.2)
2. They use **historical bars only** (not current session bars)
3. Storage keys are auto-generated to include the period
4. Multiple indicators with same base name but different periods are supported
5. Returns `None` if indicator not found (safe to use with `.get()`)
