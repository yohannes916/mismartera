# Symbol Data Structure - Session vs Historical

## Overview

Each symbol in `session_data.symbols` contains **both** current session data and historical data, matching the `SymbolSessionData` class structure.

---

## Structure

```json
{
  "session_data": {
    "_session_active": true,
    "_active_symbols": ["AAPL", "RIVN"],
    "symbols": {
      "AAPL": {
        "base_interval": "1m",
        "session": { /* Current trading day */ },
        "historical": { /* Past trading days */ }
      }
    }
  }
}
```

---

## 1. `base_interval`

**Maps to:** `SymbolSessionData.base_interval`

The base streaming interval for this symbol (either "1s" for second bars or "1m" for minute bars).

```python
# Source code (session_data.py line 38)
base_interval: str = "1m"
```

**Example:**
```json
"base_interval": "1m"
```

---

## 2. `session` Section (Current Day)

**Maps to:** Current session attributes in `SymbolSessionData`

Contains all data for the **current trading day** being streamed/generated.

### Structure

```json
"session": {
  "volume": 125000,
  "high": 185.50,
  "low": 183.25,
  "last_update": "2024-11-15T14:35:00",
  "bar_quality": 100.0,
  "bars_updated": true,
  "quotes_updated": false,
  "ticks_updated": false,
  "bar_counts": {
    "1m": 305,
    "5m": 61,
    "15m": 20
  },
  "time_range": {
    "first_bar": "09:30:00",
    "last_bar": "14:35:00"
  }
}
```

### Attribute Mapping

| JSON Attribute | Source Variable | Type | Notes |
|----------------|-----------------|------|-------|
| `volume` | `self.session_volume` | int | Total volume for current day |
| `high` | `self.session_high` | float | Highest price for current day |
| `low` | `self.session_low` | float | Lowest price for current day |
| `last_update` | `self.last_update` | datetime | Timestamp of last bar |
| `bar_quality` | `self.bar_quality` | float | Quality percentage (0-100) |
| `bars_updated` | `self.bars_updated` | bool | Flag: bars were updated this cycle |
| `quotes_updated` | `self.quotes_updated` | bool | Flag: quotes were updated this cycle |
| `ticks_updated` | `self.ticks_updated` | bool | Flag: ticks were updated this cycle |
| `bar_counts.{interval}` | `self.get_bar_count(interval)` | int | Number of bars per interval |
| `time_range.first_bar` | `self.bars_base[0].timestamp` | time | First bar timestamp (if exists) |
| `time_range.last_bar` | `self.last_update` | time | Last bar timestamp |

### Data Sources

**Current session data comes from:**
- `bars_base: Deque[BarData]` - Base interval bars (1s or 1m)
- `bars_derived: Dict[str, List[BarData]]` - Derived interval bars (5m, 15m, etc.)
- Real-time metrics updated as bars stream in

**Example source code:**
```python
# session_data.py lines 40-60
bars_base: Deque[BarData] = field(default_factory=deque)
bars_derived: Dict[str, List[BarData]] = field(default_factory=dict)
session_volume: int = 0
session_high: Optional[float] = None
session_low: Optional[float] = None
bar_quality: float = 0.0
bars_updated: bool = False
```

---

## 3. `historical` Section (Past Days)

**Maps to:** `SymbolSessionData.historical_bars`

Contains bar data for **past trading days** (trailing window for analysis).

### Structure

```json
"historical": {
  "loaded": true,
  "bar_counts_by_interval": {
    "1m": {
      "2024-11-14": 390,
      "2024-11-13": 390,
      "2024-11-12": 390,
      "total_dates": 20
    },
    "5m": {
      "2024-11-14": 78,
      "2024-11-13": 78,
      "2024-11-12": 78,
      "total_dates": 20
    },
    "15m": {
      "2024-11-14": 26,
      "2024-11-13": 26,
      "2024-11-12": 26,
      "total_dates": 20
    }
  },
  "date_range": {
    "start": "2024-10-15",
    "end": "2024-11-14"
  }
}
```

### Attribute Mapping

| JSON Attribute | Source Computation | Notes |
|----------------|-------------------|-------|
| `loaded` | `bool(self.historical_bars)` | True if any historical data exists |
| `bar_counts_by_interval.{interval}.{date}` | `len(self.historical_bars[interval][date])` | Count of bars for specific date and interval |
| `bar_counts_by_interval.{interval}.total_dates` | `len(self.historical_bars[interval])` | Number of dates with data for this interval |
| `date_range.start` | `min(self.historical_bars[interval].keys())` | Earliest date with historical data |
| `date_range.end` | `max(self.historical_bars[interval].keys())` | Latest date with historical data |

### Data Source

**Historical data stored in:**
```python
# session_data.py lines 67-72
historical_bars: Dict[str, Dict[date, List[BarData]]] = field(
    default_factory=lambda: defaultdict(dict)
)
```

**Structure:** `Dict[interval, Dict[date, List[BarData]]]`

**Example access:**
```python
# Get all 1m bars for Nov 14, 2024
bars = symbol_data.historical_bars["1m"][date(2024, 11, 14)]
# bars = [BarData, BarData, ...] (390 bars for full trading day)

# Get all 5m bars for Nov 14, 2024
bars_5m = symbol_data.historical_bars["5m"][date(2024, 11, 14)]
# bars_5m = [BarData, BarData, ...] (78 bars for full trading day)
```

### Why Show Sample Dates?

The JSON shows **3 recent dates** as examples (not all 20 dates):
- Demonstrates the structure
- Shows typical bar counts per date
- Keeps JSON readable
- `total_dates` provides full count

---

## Data Flow

### Initialization (Load Historical)
```
Database (Parquet)
    ↓
Load historical bars
    ↓
symbol_data.historical_bars[interval][date] = [bars...]
```

### During Session (Stream Current)
```
Stream Coordinator
    ↓
1m bars → symbol_data.bars_base
    ↓
Data Processor
    ↓
Compute 5m, 15m → symbol_data.bars_derived[interval]
    ↓
Update metrics → session_volume, session_high, etc.
```

### Session Roll (Move to Historical)
```
End of trading day
    ↓
symbol_data.bars_base → symbol_data.historical_bars["1m"][date]
symbol_data.bars_derived["5m"] → symbol_data.historical_bars["5m"][date]
    ↓
Clear bars_base, bars_derived
Reset session_volume, session_high, etc.
```

---

## Use Cases

### Analysis Engine - Current Day
```python
# Get latest bar for AAPL
latest = symbol_data.get_latest_bar("1m")

# Get last 20 bars for 5m analysis
bars_5m = symbol_data.get_last_n_bars(20, "5m")

# Check session metrics
volume = symbol_data.session_volume
high = symbol_data.session_high
```

### Analysis Engine - Historical
```python
# Get yesterday's bars
yesterday = current_date - timedelta(days=1)
historical_1m = symbol_data.historical_bars["1m"][yesterday]

# Compare today vs yesterday volume
today_vol = symbol_data.session_volume
yesterday_vol = sum(bar.volume for bar in historical_1m)
```

### Data Quality - Validation
```python
# Check current session quality
quality = symbol_data.bar_quality  # Should be 100%

# Verify historical data loaded
if not symbol_data.historical_bars:
    logger.warning("No historical data loaded!")

# Check historical completeness
for interval in ["1m", "5m", "15m"]:
    dates = symbol_data.historical_bars[interval].keys()
    logger.info(f"{interval}: {len(dates)} dates loaded")
```

---

## JSON Generation

### Method Signature (Proposed)
```python
def to_json(self, include_historical: bool = True) -> dict:
    """Convert SymbolSessionData to JSON.
    
    Args:
        include_historical: Include historical bars summary (default True)
    
    Returns:
        Dictionary with session and historical sections
    """
```

### Implementation Pattern
```python
def to_json(self, include_historical: bool = True) -> dict:
    result = {
        "base_interval": self.base_interval,
        "session": {
            "volume": self.session_volume,
            "high": self.session_high,
            "low": self.session_low,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "bar_quality": self.bar_quality,
            "bars_updated": self.bars_updated,
            "quotes_updated": self.quotes_updated,
            "ticks_updated": self.ticks_updated,
            "bar_counts": {
                interval: self.get_bar_count(interval)
                for interval in ["1m", "5m", "15m"]
                if self.get_bar_count(interval) > 0
            },
            "time_range": {
                "first_bar": self.bars_base[0].timestamp.time().isoformat() if self.bars_base else None,
                "last_bar": self.last_update.time().isoformat() if self.last_update else None
            }
        }
    }
    
    if include_historical and self.historical_bars:
        result["historical"] = {
            "loaded": True,
            "bar_counts_by_interval": {},
            "date_range": {}
        }
        # ... compute historical summary
    
    return result
```

---

## Summary

✅ **Session data** = Current trading day (streaming/live)  
✅ **Historical data** = Past trading days (loaded from database)  
✅ **Both stored in same object** (`SymbolSessionData`)  
✅ **JSON structure mirrors source code** (1:1 mapping)  
✅ **Complete visibility** into current + historical state  

This design enables:
- Technical indicators using historical bars
- Day-over-day comparisons
- Trailing window calculations
- Complete state inspection via JSON
