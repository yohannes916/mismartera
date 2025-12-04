# Quality Metric Restructuring - Nested Under Bar Intervals

**Date:** December 4, 2025  
**Status:** ✅ Complete

## Summary

Restructured the quality metric in system status JSON exports to be nested under each bar interval instead of at a top-level `quality` dictionary. This better reflects that quality is interval-specific and only applies to bar data (not ticks/quotes).

## Changes Made

### 1. Session Data Quality Structure

**Before (OLD):**
```json
{
  "session": {
    "volume": 19106.0,
    "high": 13.54,
    "low": 13.47,
    "quality": {
      "1m": 0.9345794392523363
    },
    "data": {
      "1m": {
        "count": 1,
        "data": [...]
      }
    }
  }
}
```

**After (NEW):**
```json
{
  "session": {
    "volume": 19106.0,
    "high": 13.54,
    "low": 13.47,
    "data": {
      "1m": {
        "count": 1,
        "quality": 0.9345794392523363,
        "data": [...]
      }
    }
  }
}
```

### 2. Historical Data Quality Structure

**Before (OLD):**
```json
{
  "historical": {
    "loaded": true,
    "data": {
      "1m": {
        "count": 1656,
        "date_range": {...},
        "data": [...]
      },
      "1d": {
        "count": 2,
        "date_range": {...},
        "data": [...]
      }
    },
    "quality": {
      "1m": 0.9345794392523363,
      "1d": 1.0
    }
  }
}
```

**After (NEW):**
```json
{
  "historical": {
    "loaded": true,
    "data": {
      "1m": {
        "count": 1656,
        "date_range": {...},
        "quality": 0.9345794392523363,
        "data": [...]
      },
      "1d": {
        "count": 2,
        "date_range": {...},
        "quality": 1.0,
        "data": [...]
      }
    }
  }
}
```

### 3. Delta Mode (Historical Intervals)

**Before (OLD):**
```json
{
  "historical": {
    "loaded": true,
    "intervals": {
      "1m": {
        "date_range": {...}
      }
    },
    "quality": {
      "1m": 0.9345794392523363
    }
  }
}
```

**After (NEW):**
```json
{
  "historical": {
    "loaded": true,
    "intervals": {
      "1m": {
        "date_range": {...},
        "quality": 0.9345794392523363
      }
    }
  }
}
```

## Code Changes

### File: `/app/managers/data_manager/session_data.py` (Primary)

#### 1. Removed Top-Level Quality from Session
- **Line 287-294:** Removed `"quality": self.bar_quality` from session dict

#### 2. Added Quality to Base Bars
- **Lines 368-370:** Added quality metric nested under base interval (1m or 1s)
```python
# Add quality metric if available for this interval
if self.base_interval in self.bar_quality:
    base_data["quality"] = self.bar_quality[self.base_interval]
```

#### 3. Added Quality to Derived Bars
- **Lines 408-410:** Added quality metric nested under each derived interval (5m, 15m, etc.)
```python
# Add quality metric if available for this interval
if interval in self.bar_quality:
    derived_data["quality"] = self.bar_quality[interval]
```

#### 4. Updated Historical Complete Mode
- **Line 426:** Removed `result["historical"]["quality"] = {}`
- **Lines 481-483:** Quality now nested under each interval's data structure
```python
# Add quality for this interval if available
if interval_key in self.bar_quality:
    historical_interval_data["quality"] = self.bar_quality[interval_key]
```

#### 5. Updated Historical Delta Mode
- **Line 489:** Removed `result["historical"]["quality"] = {}`
- **Lines 512-514:** Quality now nested in each interval's info
```python
# Add quality for this interval if available
if interval_key in self.bar_quality:
    interval_info["quality"] = self.bar_quality[interval_key]
```

#### 6. Fixed Bug in reset_session_metrics()
- **Line 259:** Fixed `self.bar_quality = 0.0` → `self.bar_quality = {}`
  - **Reason:** `bar_quality` is defined as `Dict[str, float]` in dataclass (line 52), not a float

### File: `/app/cli/system_status_impl.py` (Display)

#### Updated Quality Display Logic
- **Lines 361-365:** Updated to access `bar_quality` as dict and display base interval quality
```python
# Display quality for base interval (bar_quality is now Dict[str, float])
if symbol_data.bar_quality and symbol_data.base_interval in symbol_data.bar_quality:
    quality_value = symbol_data.bar_quality[symbol_data.base_interval]
    quality_color = "green" if quality_value >= 95 else "yellow" if quality_value >= 80 else "red"
    session_table.add_row(f"  │  └─ Bar Quality ({symbol_data.base_interval})", f"[{quality_color}]{quality_value:.1f}%[/{quality_color}]")
```

### File: `/app/cli/session_data_display.py` (Display & CSV Export)

#### Updated 7 Locations to Handle Dict Quality
1. **Lines 100-104:** Compact display - overall quality calculation
2. **Lines 163-167:** Detailed display - overall quality calculation
3. **Lines 213-216:** Compact display - per-symbol quality display
4. **Lines 299-302:** Detailed display - per-symbol quality display
5. **Lines 734-738:** CSV export - overall quality calculation
6. **Lines 777-778:** CSV export - per-symbol quality export

All changes follow the pattern:
```python
# bar_quality is now Dict[str, float], get quality for base interval
base_quality = symbol_data.bar_quality.get(symbol_data.base_interval, 0.0)
quality_color = "green" if base_quality >= 95 else "yellow" if base_quality >= 80 else "red"
```

## Benefits

1. **Logical Grouping:** Quality is now co-located with the bar data it describes
2. **Interval-Specific:** Each interval has its own quality metric
3. **No Redundancy:** Eliminates separate top-level quality dictionary
4. **Cleaner Structure:** Follows the principle that quality only applies to bars (not ticks/quotes)
5. **Easier Parsing:** Consumers can access quality directly from each interval object

## Backward Compatibility

⚠️ **Breaking Change:** This is a structural change to the JSON export format.

Any code parsing the system status JSON that looks for `session.quality` or `historical.quality` will need to be updated to access quality from within each interval:

**Update your code from:**
```python
quality_1m = data["session"]["quality"]["1m"]
```

**To:**
```python
quality_1m = data["session"]["data"]["1m"]["quality"]
```

## Testing

Test by running:
```bash
./start_cli.sh
system@mismartera: system start
system@mismartera: system export-status
```

Then verify the JSON structure in `data/status/system_status_*.json`:
- Session data: Each interval under `session.data` should have `quality` field
- Historical data: Each interval under `historical.data` should have `quality` field
- No top-level `quality` dictionaries should exist

## Related Files

### Core Implementation
- `/app/managers/data_manager/session_data.py` - Primary changes to JSON export structure

### Display & User Interaction
- `/app/cli/system_status_impl.py` - System status display (updated for dict quality)
- `/app/cli/session_data_display.py` - Session data display and CSV export (updated 7 locations)

### Export Infrastructure
- `/app/managers/system_manager/api.py` - Calls `session_data.to_json()`
- `/app/cli/system_commands.py` - `export_status_command()` entry point

### Output
- `/data/status/system_status_*.json` - JSON export files

## Implementation Notes

- Quality is only added if it exists in `self.bar_quality` dictionary
- Works for both complete mode (full data) and delta mode (incremental)
- Maintains the same dataclass definition: `bar_quality: Dict[str, float]`
- Bug fix: `reset_session_metrics()` now correctly resets to `{}` not `0.0`
- Display code consistently uses `symbol_data.base_interval` to get the correct quality metric
- CSV export includes quality for the base interval only (default behavior)

## Summary of Changes

### 3 Files Modified:
1. **session_data.py** - 6 changes (export structure + bug fix)
2. **system_status_impl.py** - 1 change (display logic)
3. **session_data_display.py** - 7 changes (display + CSV export)

### Total Changes: 14 locations
- ✅ JSON export structure updated (session, historical complete, historical delta)
- ✅ Bug fix in reset method
- ✅ CLI display updated
- ✅ CSV export updated
- ✅ All syntax validated
