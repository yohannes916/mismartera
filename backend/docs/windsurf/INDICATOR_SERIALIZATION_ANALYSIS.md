# Indicator Serialization Analysis

**Issue**: Indicator values and metadata not appearing in system status JSON export

## Investigation Summary

### 1. Configuration Status ✅
- **Session Config**: Contains 14+ indicators (SMA, EMA, VWAP, RSI, MACD, Stochastic, etc.)
- **Location**: `session_config.session_data_config.indicators.session[]`
- **Sample**: Lines 8207-8316 in the exported JSON show full indicator config

### 2. Expected JSON Structure
Two indicator sections should appear per symbol:

```json
{
  "symbols": {
    "AAPL": {
      "indicators": {
        "sma_20_5m": {
          "name": "sma",
          "type": "trend",
          "interval": "5m",
          "value": 225.43,
          "last_updated": "2025-07-02T12:39:00",
          "valid": true
        }
      },
      "historical": {
        "loaded": true,
        "indicators": {
          // Historical pre-calculated indicators
        }
      }
    }
  }
}
```

### 3. Actual JSON Output ❌
```json
{
  "symbols": {
    "AAPL": {
      "indicators": {},  // EMPTY!
      "historical": {
        "loaded": true
        // No indicators section!
      }
    }
  }
}
```

## Root Cause Analysis

### Issue #1: Indicators Dict is Empty
**Location**: `session_data.py` lines 334-356

The serialization loop iterates over `self.indicators.items()`:
```python
for key, indicator_data in self.indicators.items():
    if hasattr(indicator_data, 'current_value'):
        # Serialize IndicatorData object
        result["indicators"][key] = {...}
```

**Problem**: If `self.indicators` is empty, loop never executes.

**Possible Causes**:
1. Indicators never registered
2. Indicators registered but then cleared
3. Export happens before registration completes

### Issue #2: Missing New Metadata in Serialization
**Yesterday's Changes**: Added `config` and `state` fields to `IndicatorData`

**Current Serialization** (lines 345-352):
```python
result["indicators"][key] = {
    "name": indicator_data.name,
    "type": indicator_type,
    "interval": indicator_data.interval,
    "value": indicator_data.current_value,
    "last_updated": indicator_data.last_updated.isoformat() if indicator_data.last_updated else None,
    "valid": indicator_data.valid
}
```

**Missing Fields**:
- ❌ `config` - Full IndicatorConfig with params, warmup requirements, etc.
- ❌ `state` - Last IndicatorResult for stateful indicators (EMA, VWAP, OBV)
- ❌ `historical_values` - Value history for charting/analysis

### Issue #3: Historical Indicators Not Serialized
**Location**: `session_data.py` lines 463-464

```python
if self.historical.indicators:
    result["historical"]["indicators"] = self.historical.indicators.copy()
```

This does a shallow copy - if indicators contain `IndicatorData` objects, they need proper serialization like session indicators.

## Registration Flow Review

### SessionCoordinator Flow
```
1. _parse_indicator_configs() -> Parse from session config
   ├─ session indicators → self._indicator_configs['session']
   └─ historical indicators → self._indicator_configs['historical']

2. register_symbol() -> For each symbol
   └─ _register_symbol_indicators()
      └─ indicator_manager.register_symbol_indicators()
         └─ symbol_data.indicators[key] = IndicatorData(...)
```

### IndicatorManager Registration (manager.py lines 75-90)
```python
for config in indicators:
    key = config.make_key()
    
    # Registration = Create structure with embedded config
    symbol_data.indicators[key] = IndicatorData(
        name=config.name,
        type="session",
        interval=config.interval,
        current_value=None,
        last_updated=None,
        valid=False,
        config=config,  # ✅ Config stored
        state=None      # ✅ State stored
    )
```

**Config and state ARE being stored during registration!**

## Next Steps to Debug

1. **Verify Registration**: Check if `register_symbol_indicators()` is actually being called
2. **Check Timing**: Verify export doesn't happen before indicator registration
3. **Add Logging**: Log `len(self.indicators)` in `to_json()` to see if dict is populated
4. **Import Check**: Verify `IndicatorData` type is accessible (though duck typing should work)

## Fixes Needed

### Fix #1: Ensure Indicators are Registered
- Verify `calculate_indicators=True` is passed during symbol registration
- Add defensive logging in IndicatorManager.register_symbol_indicators()

### Fix #2: Serialize New Metadata
Update `SymbolSessionData.to_json()` lines 345-352:

```python
result["indicators"][key] = {
    "name": indicator_data.name,
    "type": indicator_type,
    "interval": indicator_data.interval,
    "value": indicator_data.current_value,
    "last_updated": indicator_data.last_updated.isoformat() if indicator_data.last_updated else None,
    "valid": indicator_data.valid,
    
    # NEW: Add metadata serialization
    "config": self._serialize_indicator_config(indicator_data.config) if indicator_data.config else None,
    "state": self._serialize_indicator_state(indicator_data.state) if indicator_data.state else None,
    "historical_values": indicator_data.historical_values if indicator_data.historical_values else None
}
```

### Fix #3: Serialize Historical Indicators Properly  
Update lines 463-464 to serialize `IndicatorData` objects instead of shallow copy:

```python
if self.historical.indicators:
    result["historical"]["indicators"] = {}
    for key, ind_data in self.historical.indicators.items():
        result["historical"]["indicators"][key] = self._serialize_indicator(ind_data)
```

## Files to Modify

1. `/app/managers/data_manager/session_data.py`
   - Add helper methods for indicator serialization
   - Update `to_json()` to include config/state/historical_values
   - Fix historical indicators serialization

2. `/app/indicators/manager.py`
   - Add logging to verify registration is called
   - Verify indicators dict is populated

3. `/app/threads/session_coordinator.py`
   - Verify `calculate_indicators=True` in all registration calls
