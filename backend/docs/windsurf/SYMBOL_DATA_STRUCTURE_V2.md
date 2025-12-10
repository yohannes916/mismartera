# Symbol Data Structure V2 - CSV-Like Compact Format

## Overview

Each symbol contains actual data in a compact CSV-like array format for efficient streaming and transmission. Data is organized by type (ticks, quotes, bars) with different detail levels.

---

## Structure

```json
{
  "symbols": {
    "AAPL": {
      "session": {
        "volume": 125000,
        "high": 185.50,
        "low": 183.25,
        "quality": 100.0,
        "data": {
          "ticks": { /* count + last_updated only */ },
          "quotes": { /* count + last_updated + latest */ },
          "1m": { /* full bars with CSV array */ },
          "5m": { /* full bars with CSV array */ },
          "15m": { /* full bars with CSV array */ }
        }
      },
      "historical": {
        "1d": { /* daily bars + interval summaries */ }
      }
    }
  }
}
```

---

## 1. Session Section

### Top-Level Metrics

```json
"session": {
  "volume": 125000,
  "high": 185.50,
  "low": 183.25,
  "quality": 100.0,
  "data": { ... }
}
```

**Maps to:**
- `volume` → `self.session_volume`
- `high` → `self.session_high`
- `low` → `self.session_low`
- `quality` → `self.bar_quality` (percentage 0-100)

---

## 2. Data Section - Ticks (Summary + Latest)

**Goal:** Count and most recent tick

```json
"ticks": {
  "count": 45678,
  "latest": {
    "timestamp": "2024-11-15T14:35:22",
    "price": 184.36,
    "size": 100,
    "exchange": "NYSE"
  }
}
```

**Maps to:**
- `count` → `len(self.ticks)`
- `latest` → `self.ticks[-1]` serialized to dict (includes timestamp, price, size, exchange)

**Rationale:** Latest tick provides most recent trade information. Timestamp is included in the latest tick object, so no need for separate `last_updated` field.

---

## 3. Data Section - Quotes (Summary + Latest)

**Goal:** Count and most recent quote

```json
"quotes": {
  "count": 12345,
  "latest": {
    "timestamp": "2024-11-15T14:35:21",
    "bid": 184.35,
    "ask": 184.37,
    "bid_size": 200,
    "ask_size": 150
  }
}
```

**Maps to:**
- `count` → `len(self.quotes)`
- `latest` → `self.quotes[-1]` serialized to dict (includes timestamp)

**Rationale:** Latest quote provides current market state without streaming all quotes. Timestamp is included in the latest quote object, so no need for separate `last_updated` field.

---

## 4. Data Section - Bars (Full CSV Format)

**Goal:** Complete bar data in compact array format

### 4.1 Base Interval (Streamed)

```json
"1m": {
  "count": 305,
  "generated": false,
  "columns": ["timestamp", "open", "high", "low", "close", "volume"],
  "data": [
    ["09:30:00", 183.50, 183.75, 183.25, 183.60, 25000],
    ["09:31:00", 183.60, 183.80, 183.55, 183.70, 18000],
    ["09:32:00", 183.70, 183.90, 183.65, 183.85, 22000]
  ]
}
```

**Maps to:**
- `count` → `len(self.bars_base)` or `self.get_bar_count("1m")`
- `generated` → `false` (streamed from database/API, not computed)
- `columns` → Static schema
- `data` → `[[bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume] for bar in self.bars_base]`

### 4.2 Derived Intervals (Computed)

```json
"5m": {
  "count": 61,
  "generated": true,
  "columns": ["timestamp", "open", "high", "low", "close", "volume"],
  "data": [
    ["09:30:00", 183.50, 184.00, 183.25, 183.85, 120000],
    ["09:35:00", 183.85, 184.20, 183.75, 184.10, 115000]
  ]
}
```

**Maps to:**
- `count` → `self.get_bar_count("5m")`
- `generated` → `true` (computed from 1m bars by DataProcessor)
- `columns` → Static schema
- `data` → `[[bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume] for bar in self.bars_derived["5m"]]`

### Key Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `count` | int | Total number of bars in this interval |
| `generated` | bool | `false` = streamed base data, `true` = computed derived data |
| `columns` | array | Column names (schema) |
| `data` | array of arrays | Actual bar data in row format |

---

## 5. Historical Section - All Intervals with Full Data

**Goal:** Historical bars in same CSV format as session data, organized by interval

```json
"historical": {
  "loaded": true,
  "data": {
    "1m": {
      "count": 7800,
      "dates": ["2024-11-14", "2024-11-13", "2024-11-12"],
      "columns": ["timestamp", "open", "high", "low", "close", "volume"],
      "data": [
        ["2024-11-14T09:30:00", 182.50, 182.75, 182.40, 182.60, 25000],
        ["2024-11-14T09:31:00", 182.60, 182.80, 182.55, 182.70, 18000]
      ]
    },
    "5m": {
      "count": 1560,
      "dates": ["2024-11-14", "2024-11-13", "2024-11-12"],
      "columns": ["timestamp", "open", "high", "low", "close", "volume"],
      "data": [
        ["2024-11-14T09:30:00", 182.50, 183.00, 182.40, 182.85, 120000]
      ]
    },
    "1d": {
      "count": 20,
      "columns": ["date", "open", "high", "low", "close", "volume"],
      "data": [
        ["2024-11-14", 182.50, 186.20, 182.10, 185.30, 48500000],
        ["2024-11-13", 181.00, 183.50, 180.50, 182.80, 52300000]
      ]
    }
  }
}
```

### 5.1 Structure

**Maps to:** `self.historical_bars: Dict[str, Dict[date, List[BarData]]]`

Each interval (1m, 5m, 15m, 1d) has:
- `count` → Total number of historical bars across all dates
- `dates` → Array of dates with data (for display/filtering)
- `columns` → Column schema (same as session)
- `data` → CSV array of actual bars

### 5.2 Timestamp Format

- **Intraday bars (1m, 5m, 15m)**: Include date in timestamp (`"2024-11-14T09:30:00"`)
- **Daily bars (1d)**: Date only (`"2024-11-14"`)

### 5.3 Source Access

```python
# Get all historical 1m bars across all dates
all_bars = []
for date, bars in symbol_data.historical_bars["1m"].items():
    all_bars.extend(bars)
    
# Get bars for specific date
bars_for_date = symbol_data.historical_bars["1m"][date(2024, 11, 14)]

# Total count
total_1m = sum(len(bars) for bars in symbol_data.historical_bars["1m"].values())
```

### 5.4 Daily Bars Computation

Daily bars are **computed from intraday bars** (not stored separately):

```python
# Compute daily bar from all 1m bars for a date
intraday_bars = symbol_data.historical_bars["1m"][date]
daily_bar = {
    "date": date.isoformat(),
    "open": intraday_bars[0].open,
    "high": max(bar.high for bar in intraday_bars),
    "low": min(bar.low for bar in intraday_bars),
    "close": intraday_bars[-1].close,
    "volume": sum(bar.volume for bar in intraday_bars)
}
```

**Rationale:** Consistent CSV format across session and historical. All intervals include actual data, not just counts.

---

## 6. CSV-Like Format Benefits

### Compact Representation
```json
// Traditional (verbose)
{
  "bars": [
    {"timestamp": "09:30:00", "open": 183.50, "high": 183.75, ...},
    {"timestamp": "09:31:00", "open": 183.60, "high": 183.80, ...}
  ]
}

// CSV-like (compact)
{
  "columns": ["timestamp", "open", "high", "low", "close", "volume"],
  "data": [
    ["09:30:00", 183.50, 183.75, 183.25, 183.60, 25000],
    ["09:31:00", 183.60, 183.80, 183.55, 183.70, 18000]
  ]
}
```

**Savings:**
- ~60% smaller JSON size
- Faster parsing (array access vs key lookup)
- Easier streaming (append rows)
- Column schema defined once

### Streaming Friendly

```python
# Add new bar to data array
new_bar = [timestamp, open, high, low, close, volume]
json_data["data"].append(new_bar)

# In diff mode, only send new rows
if diff_mode:
    json_data["data"] = new_bars_since_last_update
```

---

## 7. Complete Example

```json
{
  "AAPL": {
    "session": {
      "volume": 125000,
      "high": 185.50,
      "low": 183.25,
      "quality": 100.0,
      "data": {
        "ticks": {
          "count": 45678,
          "last_updated": "2024-11-15T14:35:22"
        },
        "quotes": {
          "count": 12345,
          "latest": {
            "timestamp": "2024-11-15T14:35:21",
            "bid": 184.35,
            "ask": 184.37,
            "bid_size": 200,
            "ask_size": 150
          }
        },
        "1m": {
          "count": 305,
          "generated": false,
          "columns": ["timestamp", "open", "high", "low", "close", "volume"],
          "data": [
            ["09:30:00", 183.50, 183.75, 183.25, 183.60, 25000],
            ["09:31:00", 183.60, 183.80, 183.55, 183.70, 18000]
          ]
        },
        "5m": {
          "count": 61,
          "generated": true,
          "columns": ["timestamp", "open", "high", "low", "close", "volume"],
          "data": [
            ["09:30:00", 183.50, 184.00, 183.25, 183.85, 120000]
          ]
        }
      }
    },
    "historical": {
      "loaded": true,
      "data": {
        "1m": {
          "count": 7800,
          "dates": ["2024-11-14", "2024-11-13"],
          "columns": ["timestamp", "open", "high", "low", "close", "volume"],
          "data": [
            ["2024-11-14T09:30:00", 182.50, 182.75, 182.40, 182.60, 25000]
          ]
        },
        "5m": {
          "count": 1560,
          "dates": ["2024-11-14", "2024-11-13"],
          "columns": ["timestamp", "open", "high", "low", "close", "volume"],
          "data": [
            ["2024-11-14T09:30:00", 182.50, 183.00, 182.40, 182.85, 120000]
          ]
        },
        "1d": {
          "count": 20,
          "columns": ["date", "open", "high", "low", "close", "volume"],
          "data": [
            ["2024-11-14", 182.50, 186.20, 182.10, 185.30, 48500000]
          ]
        }
      }
    }
  }
}
```

---

## 8. Implementation Pattern

### JSON Generation Method

```python
def to_json(self, include_data: bool = True, max_bars: int = 100) -> dict:
    """Convert SymbolSessionData to compact JSON format.
    
    Args:
        include_data: Include actual bar data (default True)
        max_bars: Maximum bars per interval to include (default 100, most recent)
    
    Returns:
        Dictionary with session and historical sections
    """
    result = {
        "session": {
            "volume": self.session_volume,
            "high": self.session_high,
            "low": self.session_low,
            "quality": self.bar_quality,
            "data": {}
        }
    }
    
    # Ticks (count + latest)
    if self.ticks:
        result["session"]["data"]["ticks"] = {
            "count": len(self.ticks),
            "latest": {
                "timestamp": self.ticks[-1].timestamp.isoformat(),
                "price": self.ticks[-1].price,
                "size": self.ticks[-1].size,
                "exchange": self.ticks[-1].exchange
            }
        }
    
    # Quotes (count + latest, timestamp included in latest)
    if self.quotes:
        result["session"]["data"]["quotes"] = {
            "count": len(self.quotes),
            "latest": {
                "timestamp": self.quotes[-1].timestamp.isoformat(),
                "bid": self.quotes[-1].bid,
                "ask": self.quotes[-1].ask,
                "bid_size": self.quotes[-1].bid_size,
                "ask_size": self.quotes[-1].ask_size
            }
        }
    
    # Bars (CSV format)
    if include_data:
        # Base interval
        bars = list(self.bars_base)[-max_bars:]
        if bars:
            result["session"]["data"][self.base_interval] = {
                "count": len(self.bars_base),
                "generated": False,
                "columns": ["timestamp", "open", "high", "low", "close", "volume"],
                "data": [
                    [
                        bar.timestamp.time().isoformat(),
                        bar.open,
                        bar.high,
                        bar.low,
                        bar.close,
                        bar.volume
                    ]
                    for bar in bars
                ]
            }
        
        # Derived intervals
        for interval, bars_list in self.bars_derived.items():
            if bars_list:
                bars = bars_list[-max_bars:]
                result["session"]["data"][interval] = {
                    "count": len(bars_list),
                    "generated": True,
                    "columns": ["timestamp", "open", "high", "low", "close", "volume"],
                    "data": [
                        [
                            bar.timestamp.time().isoformat(),
                            bar.open,
                            bar.high,
                            bar.low,
                            bar.close,
                            bar.volume
                        ]
                        for bar in bars
                    ]
                }
    
    # Historical data
    if self.historical_bars:
        result["historical"] = self._generate_historical_json()
    
    return result
```

---

## 9. Use Cases

### Frontend Display
```javascript
// Easy to render as table
const columns = data.session.data["1m"].columns;
const rows = data.session.data["1m"].data;

// Create table
rows.forEach(row => {
  const rowData = {};
  columns.forEach((col, i) => {
    rowData[col] = row[i];
  });
  // rowData = {timestamp: "09:30:00", open: 183.50, ...}
});
```

### Data Export
```python
# Convert to pandas DataFrame
import pandas as pd

columns = json_data["session"]["data"]["1m"]["columns"]
data = json_data["session"]["data"]["1m"]["data"]
df = pd.DataFrame(data, columns=columns)
```

### Streaming Updates
```python
# Only send new bars (diff mode)
last_sent_count = 300
current_count = json_data["session"]["data"]["1m"]["count"]
new_bars = current_count - last_sent_count

if new_bars > 0:
    json_data["session"]["data"]["1m"]["data"] = \
        json_data["session"]["data"]["1m"]["data"][-new_bars:]
```

---

## Summary

✅ **Ticks:** Count + last_updated (minimal)  
✅ **Quotes:** Count + last_updated + latest quote (summary)  
✅ **Bars:** Full data in CSV array format (complete)  
✅ **Generated flag:** Distinguishes streamed vs computed data  
✅ **Compact format:** ~60% smaller than traditional JSON  
✅ **Streaming friendly:** Easy to append and diff  
✅ **Historical:** Daily summaries + intraday counts  

This structure balances completeness, compactness, and usability for both monitoring and analysis.
