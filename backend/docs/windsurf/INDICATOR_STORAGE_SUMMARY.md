# Indicator Storage & Access Summary

**Date**: December 7, 2025  
**Status**: ✅ Fully Documented

---

## Quick Answer

### **Do we support Nd and Nw high/low?** ✅ YES

- ✅ **Nd (N days)**: `{"name": "high_low", "period": 20, "interval": "1d"}`
- ✅ **Nw (N weeks)**: `{"name": "high_low", "period": 4, "interval": "1w"}`
- ✅ **Nm (N minutes)**: `{"name": "high_low", "period": 30, "interval": "1m"}`
- ✅ **Any interval**: Same indicator, parameterized by interval!

### **Storage Location** ✅

All indicators stored in `SessionData`:
```python
session_data.get_symbol_data(symbol).indicators
```

**Two categories**:
1. **session.indicators** - Real-time (SMA, RSI, VWAP, etc.)
2. **historical.indicators** - Context (20-day high, avg volume, etc.)

### **AnalysisEngine Access** ✅

```python
# Simple access
sma_20 = session_data.get_indicator_value("AAPL", "sma_20_5m")

# Multi-value access
bb_upper = session_data.get_indicator_value("AAPL", "bbands_20_5m", "upper")

# 20-day high/low
day_20_high = session_data.get_indicator_value("AAPL", "high_low_20_1d", "high")

# 4-week high/low
week_4_high = session_data.get_indicator_value("AAPL", "high_low_4_1w", "high")
```

---

## Storage Structure

### **In SessionData**

```python
@dataclass
class SymbolSessionData:
    symbol: str
    base_interval: str
    bars: Dict[str, BarIntervalData]  # Existing
    indicators: Dict[str, IndicatorData]  # NEW!
```

### **Indicator Keys** (Naming Convention)

Format: `"{name}_{period}_{interval}"` or `"{name}_{interval}"`

**Examples**:
- `sma_20_5m` → SMA(20) on 5m bars
- `rsi_14_15m` → RSI(14) on 15m bars
- `vwap_1m` → VWAP on 1m bars
- `high_low_20_1d` → 20-day high/low
- `high_low_4_1w` → 4-week high/low
- `bbands_20_5m` → Bollinger Bands(20) on 5m

---

## Unified High/Low Implementation

### **ONE Indicator, Multiple Intervals**

```json
{
  "indicators": {
    "historical": [
      {
        "name": "high_low",
        "period": 3,
        "interval": "1d",
        "comment": "3-day high/low"
      },
      {
        "name": "high_low",
        "period": 20,
        "interval": "1d",
        "comment": "20-day high/low (Nd)"
      },
      {
        "name": "high_low",
        "period": 4,
        "interval": "1w",
        "comment": "4-week high/low (Nw)"
      },
      {
        "name": "high_low",
        "period": 13,
        "interval": "1w",
        "comment": "13-week (quarter) high/low"
      }
    ],
    "session": [
      {
        "name": "high_low",
        "period": 30,
        "interval": "15m",
        "comment": "30-period high/low on 15m bars (intraday S/R)"
      }
    ]
  }
}
```

**Result in SessionData**:
- `high_low_3_1d` → {high: X, low: Y}
- `high_low_20_1d` → {high: X, low: Y}
- `high_low_4_1w` → {high: X, low: Y}
- `high_low_13_1w` → {high: X, low: Y}
- `high_low_30_15m` → {high: X, low: Y}

---

## AnalysisEngine Access API

### **Core Methods**

```python
# 1. Get indicator value
value = session_data.get_indicator_value(symbol, indicator_key, field=None)

# 2. Get indicator object (full details)
indicator = session_data.get_indicator(symbol, indicator_key)

# 3. Check if ready (warmup complete)
ready = session_data.is_indicator_ready(symbol, indicator_key)

# 4. Get all indicators
all_indicators = session_data.get_all_indicators(symbol, type=None)
session_only = session_data.get_all_indicators(symbol, type="session")
historical_only = session_data.get_all_indicators(symbol, type="historical")
```

### **Usage Examples**

#### **Single-Value Indicator**
```python
# SMA(20) on 5m
sma_20 = session_data.get_indicator_value("AAPL", "sma_20_5m")
if sma_20:
    print(f"SMA(20): {sma_20}")
```

#### **Multi-Value Indicator**
```python
# Bollinger Bands
bb_upper = session_data.get_indicator_value("AAPL", "bbands_20_5m", "upper")
bb_middle = session_data.get_indicator_value("AAPL", "bbands_20_5m", "middle")
bb_lower = session_data.get_indicator_value("AAPL", "bbands_20_5m", "lower")
```

#### **Historical Context (20-day high/low)**
```python
# Get 20-day high/low
day_20_high = session_data.get_indicator_value("AAPL", "high_low_20_1d", "high")
day_20_low = session_data.get_indicator_value("AAPL", "high_low_20_1d", "low")

# Check breakout
if current_price > day_20_high:
    print("BREAKOUT above 20-day high!")
```

#### **Multi-Timeframe High/Low**
```python
# 3-day, 20-day, 4-week levels
day_3_high = session_data.get_indicator_value("AAPL", "high_low_3_1d", "high")
day_20_high = session_data.get_indicator_value("AAPL", "high_low_20_1d", "high")
week_4_high = session_data.get_indicator_value("AAPL", "high_low_4_1w", "high")

# Multi-timeframe analysis
if current_price > day_3_high and current_price > day_20_high:
    print("Strong breakout across multiple timeframes!")
```

#### **Check Readiness**
```python
# Before using indicator, check if warmup complete
if session_data.is_indicator_ready("AAPL", "sma_20_5m"):
    sma = session_data.get_indicator_value("AAPL", "sma_20_5m")
    # Use sma...
else:
    print("SMA(20) still warming up...")
```

---

## Complete Strategy Example

### **Multi-Timeframe Momentum Strategy**

```python
def analyze_momentum(self, symbol: str):
    """Multi-timeframe momentum analysis using SessionData API."""
    
    # Check all indicators ready
    required_indicators = [
        "sma_20_5m",
        "rsi_14_5m",
        "vwap_1m",
        "high_low_20_1d",
        "high_low_4_1w",
        "avg_volume_5_1d"
    ]
    
    for ind_key in required_indicators:
        if not self.session_data.is_indicator_ready(symbol, ind_key):
            logger.warning(f"{symbol}: Waiting for {ind_key}")
            return
    
    # Get current price
    bars = self.session_data.get_bars(symbol, "5m", limit=1)
    current_price = bars[0].close
    
    # Get session indicators
    sma_20 = self.session_data.get_indicator_value(symbol, "sma_20_5m")
    rsi_14 = self.session_data.get_indicator_value(symbol, "rsi_14_5m")
    vwap = self.session_data.get_indicator_value(symbol, "vwap_1m")
    
    # Get historical context
    day_20_high = self.session_data.get_indicator_value(symbol, "high_low_20_1d", "high")
    day_20_low = self.session_data.get_indicator_value(symbol, "high_low_20_1d", "low")
    week_4_high = self.session_data.get_indicator_value(symbol, "high_low_4_1w", "high")
    avg_vol = self.session_data.get_indicator_value(symbol, "avg_volume_5_1d")
    
    # Analysis
    signals = []
    
    # Trend signal
    if current_price > sma_20:
        signals.append("Above SMA(20)")
    
    # Momentum signal
    if rsi_14 < 30:
        signals.append("RSI oversold")
    elif rsi_14 > 70:
        signals.append("RSI overbought")
    
    # VWAP signal
    if current_price > vwap:
        signals.append("Above VWAP")
    
    # Breakout signals
    if current_price > day_20_high:
        signals.append("Breaking 20-day high")
    
    if current_price > week_4_high:
        signals.append("Breaking 4-week high - STRONG!")
    
    # Volume confirmation
    current_vol = bars[0].volume
    if current_vol > avg_vol * 1.5:
        signals.append("High volume (1.5x average)")
    
    # Decision
    if len([s for s in signals if "Breaking" in s]) >= 1 and len(signals) >= 3:
        logger.info(f"{symbol}: STRONG BUY - {signals}")
    elif len(signals) >= 2:
        logger.info(f"{symbol}: Buy signal - {signals}")
```

---

## Documentation Files

### **For Developers**
1. **`SESSION_DATA_INDICATOR_API.md`** - Complete API reference
2. **`INDICATOR_IMPLEMENTATION_PLAN.md`** - Implementation guide
3. **`INDICATOR_STORAGE_SUMMARY.md`** - This file (quick reference)

### **For Users**
1. **`INDICATOR_REFERENCE.md`** - All 37 indicators documented
   - Formulas, interpretation, config examples
   - Nd and Nw high/low clarified
   - Strategy combinations

---

## Key Takeaways

### **1. Unified High/Low** ✅
- ONE indicator: `high_low`
- Works on ANY interval: 1m, 5m, 15m, 1d, 1w
- Nd = `interval: "1d"`, Nw = `interval: "1w"`

### **2. Storage in SessionData** ✅
- All indicators in `SymbolSessionData.indicators`
- Keys: `"{name}_{period}_{interval}"`
- Two categories: session and historical

### **3. Simple Access API** ✅
- `get_indicator_value()` - Direct value access
- `is_indicator_ready()` - Check warmup
- `get_all_indicators()` - Get all for symbol

### **4. AnalysisEngine Ready** ✅
- Fast access (no computation)
- Simple API (2-3 line usage)
- Well documented (examples provided)

---

## **Status**: ✅ FULLY DOCUMENTED

All indicator storage and access patterns documented and ready for implementation in Phase 3!
