# Unified Interval Support Documentation

**Date**: December 7, 2025  
**Status**: ✅ IMPLEMENTED  
**Goal**: Document complete interval support across all timeframes

---

## **Supported Intervals**

### **✅ Seconds** (s)
```json
"streams": ["1s", "5s", "10s", "15s", "30s"]

"indicators": {
  "session": [
    {"name": "sma", "period": 20, "interval": "5s"}
  ]
}
```

**Base**: `1s` (must be streamed or loaded from parquet)  
**Derived**: `5s`, `10s`, `15s`, `30s` (aggregated from `1s`)

---

### **✅ Minutes** (m)
```json
"streams": ["1m", "5m", "15m", "30m", "60m", "90m", "120m"]

"indicators": {
  "session": [
    {"name": "sma", "period": 20, "interval": "5m"},
    {"name": "rsi", "period": 14, "interval": "15m"}
  ]
}
```

**Base**: `1m` (must be streamed or loaded from parquet)  
**Derived**: `5m`, `15m`, `30m`, `60m`, `90m`, `120m` (aggregated from `1m`)

**Note**: For "hourly" intervals, use minutes:
- ❌ `"1h"` - NOT SUPPORTED
- ✅ `"60m"` - USE THIS (1 hour = 60 minutes)
- ✅ `"120m"` - USE THIS (2 hours = 120 minutes)
- ✅ `"240m"` - USE THIS (4 hours = 240 minutes)

---

### **✅ Days** (d)
```json
"streams": ["1d", "5d"]

"indicators": {
  "historical": [
    {"name": "high_low", "period": 20, "interval": "1d", "unit": "days"},
    {"name": "avg_volume", "period": 10, "interval": "1d", "unit": "days"}
  ]
}
```

**Base**: `1d` (aggregated from `1m` bars)  
**Derived**: `5d`, `10d` (aggregated from `1d`)

**How Daily Bars Work**:
1. System streams/loads `1m` bars
2. Aggregates `1m` → `1d` (at end of trading day)
3. Can then aggregate `1d` → `5d` if needed

---

### **✅ Weeks** (w)
```json
"streams": ["1w", "2w", "4w"]

"indicators": {
  "historical": [
    {"name": "high_low", "period": 52, "interval": "1w", "unit": "weeks"},
    {"name": "high_low", "period": 4, "interval": "1w", "unit": "weeks"}
  ]
}
```

**Base**: `1d` (aggregated from `1m` bars first)  
**Intermediate**: `1w` (aggregated from `1d` bars)  
**Derived**: `2w`, `4w`, `8w` (aggregated from `1w`)

**How Weekly Bars Work**:
1. System streams/loads `1m` bars
2. Aggregates `1m` → `1d`
3. Aggregates `1d` → `1w` (at end of trading week)
4. Can then aggregate `1w` → `4w`, etc.

---

### **❌ Hours** (h) - NOT SUPPORTED

```json
// ❌ THIS WILL FAIL
"streams": ["1h", "2h", "4h"]

// ✅ USE THIS INSTEAD
"streams": ["60m", "120m", "240m"]
```

**Why Not Supported**:
- Clean break from old architecture
- Simplifies interval hierarchy
- Minutes work just as well (60m = 1h)

**Error Message**:
```
Invalid interval '1h': Supported: seconds (1s, 5s), minutes (1m, 5m, 15m),
days (1d), weeks (1w). NO hourly support - use minutes (60m, 120m, etc.)
```

---

## **Interval Hierarchy**

### **Aggregation Chain**:
```
1s (base)
  └─> 5s, 10s, 15s, 30s (derived from 1s)

1m (base)
  ├─> 5m, 15m, 30m, 60m, 120m (derived from 1m)
  └─> 1d (aggregated from 1m at EOD)
      └─> 1w (aggregated from 1d at EOW)
          └─> 4w, 8w (derived from 1w)
```

### **Base Determination Rules**:

**Requirement Analyzer Logic**:
1. If you request `5s` → requires `1s` base
2. If you request `5m` → requires `1m` base
3. If you request `1d` → requires `1m` base (aggregated)
4. If you request `1w` → requires `1d` base → which requires `1m`

**Example**:
```json
// User requests: ["5m", "15m", "1d", "1w"]
// Analyzer determines:
{
  "base_interval": "1m",           // Smallest base needed
  "derived_intervals": [
    "5m",   // from 1m
    "15m",  // from 1m
    "1d",   // from 1m (end of day)
    "1w"    // from 1d (end of week)
  ]
}
```

---

## **Common Use Cases**

### **1. Intraday Trading** (Seconds/Minutes)
```json
{
  "streams": ["1m", "5m", "15m"],
  "indicators": {
    "session": [
      {"name": "sma", "period": 20, "interval": "5m"},
      {"name": "ema", "period": 9, "interval": "1m"},
      {"name": "rsi", "period": 14, "interval": "15m"},
      {"name": "vwap", "period": 0, "interval": "1m"}
    ]
  }
}
```

**System Determines**:
- Base: `1m`
- Derived: `5m`, `15m` (from `1m`)
- Indicators calculate on respective intervals

---

### **2. Swing Trading** (Days/Weeks)
```json
{
  "streams": ["1m", "1d", "1w"],
  "indicators": {
    "historical": [
      {"name": "high_low", "period": 20, "interval": "1d", "unit": "days"},
      {"name": "high_low", "period": 4, "interval": "1w", "unit": "weeks"},
      {"name": "avg_volume", "period": 10, "interval": "1d", "unit": "days"},
      {"name": "atr_daily", "period": 14, "interval": "1d", "unit": "days"}
    ]
  }
}
```

**System Determines**:
- Base: `1m`
- Derived: `1d` (from `1m`), `1w` (from `1d`)
- Historical indicators calculate on daily/weekly bars

---

### **3. Multi-Timeframe Analysis**
```json
{
  "streams": ["1m", "5m", "15m", "1d", "1w"],
  "indicators": {
    "session": [
      {"name": "ema", "period": 9, "interval": "1m"},
      {"name": "ema", "period": 21, "interval": "5m"},
      {"name": "rsi", "period": 14, "interval": "15m"}
    ],
    "historical": [
      {"name": "high_low", "period": 20, "interval": "1d", "unit": "days"},
      {"name": "high_low", "period": 52, "interval": "1w", "unit": "weeks"}
    ]
  }
}
```

**Access in AnalysisEngine**:
```python
# 1-minute trend
ema_9_1m = get_indicator_value(session_data, "AAPL", "ema_9_1m")

# 5-minute trend
ema_21_5m = get_indicator_value(session_data, "AAPL", "ema_21_5m")

# 15-minute momentum
rsi_14_15m = get_indicator_value(session_data, "AAPL", "rsi_14_15m")

# 20-day high/low
day_20_high = get_indicator_value(session_data, "AAPL", "high_low_20_1d", "high")
day_20_low = get_indicator_value(session_data, "AAPL", "high_low_20_1d", "low")

# 52-WEEK HIGH/LOW
week_52_high = get_indicator_value(session_data, "AAPL", "high_low_52_1w", "high")
week_52_low = get_indicator_value(session_data, "AAPL", "high_low_52_1w", "low")
```

---

## **Special Cases**

### **52-Week High/Low** ⭐

**Config**:
```json
{
  "streams": ["1m", "1d", "1w"],
  "historical": {
    "data": [
      {
        "trailing_days": 365,
        "intervals": ["1d", "1w"],
        "apply_to": "all"
      }
    ]
  },
  "indicators": {
    "historical": [
      {
        "name": "high_low",
        "period": 52,
        "unit": "weeks",
        "interval": "1w",
        "type": "historical"
      }
    ]
  }
}
```

**How It Works**:
1. System loads 365 days of `1d` bars (historical)
2. Aggregates `1d` → `1w` (52 weeks)
3. Calculates `high_low` indicator on 52 weeks
4. Stores as `high_low_52_1w` in SessionData

**Access**:
```python
week_52_high = get_indicator_value(session_data, "AAPL", "high_low_52_1w", "high")
week_52_low = get_indicator_value(session_data, "AAPL", "high_low_52_1w", "low")

# Check if ready (warmup complete)
if is_indicator_ready(session_data, "AAPL", "high_low_52_1w"):
    logger.info(f"52-week high: {week_52_high}, low: {week_52_low}")
```

---

### **Intraday "Hourly" Charts**

**Instead of**: `"1h", "2h", "4h"`  
**Use**: `"60m", "120m", "240m"`

```json
{
  "streams": ["1m", "60m", "240m"],
  "indicators": {
    "session": [
      {"name": "sma", "period": 20, "interval": "60m"},
      {"name": "rsi", "period": 14, "interval": "240m"}
    ]
  }
}
```

**Result**:
- `sma_20_60m` = 20-period SMA on 1-hour bars
- `rsi_14_240m` = 14-period RSI on 4-hour bars

---

## **Validation**

### **What Gets Validated**:
1. **Format**: Must match `^\d+[smdw]$` (e.g., "5m", "1d", "52w")
2. **No Hourly**: Rejects `1h`, `2h`, etc.
3. **Positive Numbers**: Must be > 0
4. **Reasonable**: No validation on size, but 52w is fine, 1000w would work too

### **Where Validation Happens**:
- `requirement_analyzer.parse_interval()` - Main validation
- `session_config.py` - Config loading validation
- `indicator_config.py` - Indicator interval validation

### **Error Examples**:

**Invalid Format**:
```json
"interval": "5h"  // ❌ Error: NO hourly support
"interval": "abc"  // ❌ Error: Invalid format
"interval": "m5"   // ❌ Error: Number must come first
```

**Valid Formats**:
```json
"interval": "1s"    // ✅ OK
"interval": "5m"    // ✅ OK
"interval": "60m"   // ✅ OK (not 1h!)
"interval": "1d"    // ✅ OK
"interval": "52w"   // ✅ OK (52-week)
"interval": "quotes" // ✅ OK (special case)
```

---

## **Implementation Details**

### **Requirement Analyzer**:

**File**: `app/threads/quality/requirement_analyzer.py`

**Supported Types**:
```python
class IntervalType(Enum):
    SECOND = "second"  # 1s, 5s, 10s
    MINUTE = "minute"  # 1m, 5m, 15m, 60m
    DAY = "day"        # 1d, 5d
    WEEK = "week"      # 1w, 4w, 52w
    QUOTE = "quote"    # quotes
    # NO HOUR TYPE!
```

**Parsing**:
```python
# Regex: ^\d+[smdw]$ (no 'h'!)
match = re.match(r'^(\d+)([smdw])$', interval_lower)
```

**Base Determination**:
```python
if interval_type == IntervalType.SECOND:
    return "1s"
elif interval_type == IntervalType.MINUTE:
    return "1m"
elif interval_type == IntervalType.DAY:
    return "1m"  # Days aggregated from 1m
elif interval_type == IntervalType.WEEK:
    return "1d"  # Weeks aggregated from 1d (which comes from 1m)
```

---

## **Indicator Keys**

### **Naming Convention**:
- With period: `{name}_{period}_{interval}`
- Without period: `{name}_{interval}`

### **Examples**:
```python
"sma_20_5m"        # SMA(20) on 5-minute bars
"rsi_14_15m"       # RSI(14) on 15-minute bars
"vwap_1m"          # VWAP on 1-minute bars (no period)
"high_low_20_1d"   # 20-day high/low
"high_low_52_1w"   # 52-WEEK high/low ⭐
```

---

## **Summary**

### **✅ Fully Supported**:
- Seconds: `1s`, `5s`, `10s`, `15s`, `30s`
- Minutes: `1m`, `5m`, `15m`, `30m`, `60m`, `120m`, `240m`
- Days: `1d`, `5d`, `10d`
- Weeks: `1w`, `2w`, `4w`, `52w`

### **❌ Not Supported**:
- Hours: `1h`, `2h`, `4h` (use `60m`, `120m`, `240m` instead)

### **Special Cases**:
- 52-week high/low: `{"name": "high_low", "period": 52, "interval": "1w"}`
- "Hourly" charts: Use `60m`, `120m`, `240m`
- Quotes: `"quotes"` (special non-bar interval)

### **Access Pattern**:
```python
# Any interval works the same way
value = get_indicator_value(session_data, symbol, indicator_key)

# Examples
sma_5s = get_indicator_value(session_data, "AAPL", "sma_20_5s")
rsi_15m = get_indicator_value(session_data, "AAPL", "rsi_14_15m")
high_52w = get_indicator_value(session_data, "AAPL", "high_low_52_1w", "high")
```

---

## **Status: ✅ COMPLETE**

All intervals (s, m, d, w) fully supported. No hourly intervals by design.
