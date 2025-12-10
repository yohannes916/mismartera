# Indicator Implementation Status

## Issue Summary

The system status JSON was missing:
1. ✅ **FIXED**: `session_config` section (including indicator configurations)
2. ⚠️ **PARTIAL**: `indicators` values in symbol data (configuration shown but values not computed)

---

## What Was Fixed

### 1. Session Config Serialization ✅

**Problem**: The `SessionConfig.to_dict()` method wasn't serializing the `indicators` section from `session_data_config`.

**Fixed in**: `/app/models/session_config.py` (lines 646-668)

**Now includes**:
```json
{
  "session_config": {
    "session_data_config": {
      "indicators": {
        "session": [
          {"name": "sma", "period": 20, "interval": "5m", "type": "trend", "params": {}},
          {"name": "rsi", "period": 14, "interval": "5m", "type": "momentum", "params": {}}
        ],
        "historical": [
          {"name": "avg_volume", "period": 20, "unit": "days", "interval": "1d", "type": "historical"}
        ]
      }
    }
  }
}
```

---

## What's Still Needed

### 2. Indicator Value Calculation ⚠️

**Current Status**: Configuration loaded but values NOT computed

**Location**: `/app/threads/data_processor.py` lines 500-543

**Code Status**:
```python
def _calculate_realtime_indicators(self, symbol: str, interval: str):
    """Calculate real-time indicators for a symbol/interval.
    
    Implementation Status: DEFERRED
    Reason: Indicator configuration system not yet designed
    Priority: Can be added after Phase 4 core functionality complete
    """
    if not self._realtime_indicators:
        return  # ← Currently returns immediately (no calculation)
```

**What needs to happen**:

1. **Read indicator config** from `system_manager.session_config.session_data_config.indicators.session`
2. **Calculate indicator values** using the bars from `session_data`
3. **Store values** in `session_data.symbols[symbol].indicators` dict
4. **Update on each bar** as new data arrives

**Example of what the output should look like**:
```json
{
  "session_data": {
    "symbols": {
      "AAPL": {
        "indicators": {
          "sma_20_5m": 225.45,
          "ema_9_5m": 224.80,
          "rsi_14_5m": 62.3,
          "macd_5m": {
            "macd": 1.25,
            "signal": 0.95,
            "histogram": 0.30
          },
          "bbands_20_5m": {
            "upper": 228.50,
            "middle": 225.00,
            "lower": 221.50
          },
          "vwap_1m": 225.12
        }
      }
    }
  }
}
```

---

## Architecture Notes

### Indicator Types

**Session Indicators** (Real-time):
- Computed in **DataProcessor** thread
- Updated as bars arrive during session
- Examples: SMA, EMA, RSI, MACD, VWAP, Bollinger Bands
- Stored in: `session_data.symbols[symbol].indicators`

**Historical Indicators** (Context):
- Computed in **SessionCoordinator** during initialization
- Pre-calculated on trailing historical data
- Examples: 20-day avg volume, 52-week high/low, ATR
- Stored in: `session_data.symbols[symbol].historical.indicators`

### Where Calculation Happens

```
SessionCoordinator (Phase 3)
  ↓ Initializes session
  ↓ Loads historical data
  ↓ Computes historical indicators ← NOT YET IMPLEMENTED
  
DataProcessor (Phase 4)
  ↓ Receives new bars
  ↓ Generates derived bars (5m, 15m) ← WORKING
  ↓ Calculates session indicators ← NOT YET IMPLEMENTED
  ↓ Updates session_data
```

### Implementation Order

**Phase 6 - Indicator System** (Planned):

1. **Phase 6a**: Indicator calculation library
   - Technical indicators (SMA, EMA, RSI, MACD, etc.)
   - Volume indicators (OBV, Volume SMA, etc.)
   - Volatility indicators (ATR, Bollinger Bands, etc.)

2. **Phase 6b**: DataProcessor integration
   - Read indicator config from session_config
   - Calculate indicators after derived bars
   - Store in session_data.indicators

3. **Phase 6c**: SessionCoordinator integration
   - Calculate historical indicators during init
   - Store in session_data.historical.indicators

4. **Phase 6d**: IndicatorManager
   - Centralized indicator calculation
   - Caching and optimization
   - Dependency management

---

## Current Workaround

**For testing/debugging**, you can manually set indicator values:

```python
from app.managers.data_manager.session_data import get_session_data

session_data = get_session_data()
symbol_data = session_data.get_symbol_data("AAPL")

# Manually set indicator values
symbol_data.indicators["sma_20_5m"] = 225.45
symbol_data.indicators["rsi_14_5m"] = 62.3
symbol_data.indicators["vwap_1m"] = 225.12

# Will now appear in JSON export
```

---

## Testing the Fix

**Re-run the system and export status**:

```bash
# Start system
./start_cli.sh
system start session_configs/example_session.json

# Let it run for a bit
# ...

# Export system status
system export-status

# Check output
cat data/status/system_status_Example_Trading_Session_-_All_Indicator_Types_complete_*.json
```

**You should now see**:

1. ✅ `session_config` section with indicators configuration
2. ⚠️ `indicators: {}` still empty (because calculation not implemented)

**After Phase 6 implementation**:

1. ✅ `session_config` with configuration
2. ✅ `indicators: {"sma_20_5m": 225.45, ...}` with actual values

---

## Files Modified

### Fixed
- ✅ `/app/models/session_config.py` - Added indicators to `to_dict()` method

### Needs Implementation
- ⚠️ `/app/threads/data_processor.py` - Implement `_calculate_realtime_indicators()`
- ⚠️ `/app/threads/session_coordinator.py` - Implement historical indicator calculation
- ⚠️ `/app/services/indicators/` - Create indicator calculation library

---

## Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Config Loading | ✅ Working | Indicators loaded from JSON |
| Config Serialization | ✅ Fixed | Now appears in session_config |
| Value Calculation | ❌ Not Implemented | Marked as "DEFERRED" |
| Value Storage | ✅ Ready | Structure exists in session_data |
| Value Export | ✅ Working | Will show once calculated |

**Next Step**: Implement Phase 6 - Indicator calculation in DataProcessor and SessionCoordinator

---

**Status**: Partial Fix - Configuration now exported, but values not yet calculated
**Priority**: Medium (nice-to-have for monitoring, not critical for trading logic)
**Blocking**: None (can proceed with other features)
