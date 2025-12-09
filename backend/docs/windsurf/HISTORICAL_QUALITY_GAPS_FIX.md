# Historical Quality & Gaps Fix - Implementation Complete

## Overview
Fixed historical data quality calculation and gap detection to work properly for both initial session load and mid-session symbol additions.

**Date**: December 7, 2025  
**Status**: ✅ **COMPLETE** - All changes implemented

---

## Problems Identified

### 1. **Historical Quality Not Displayed**
- Quality was calculated via `session_data.set_quality()` but stored in session bars, not historical
- `HistoricalBarIntervalData.quality` was always 0.0
- Display showed `quality: 0.0` because it read from the wrong location

### 2. **Historical Gaps Not Calculated**
- No gap detection was performed on historical bars
- `HistoricalBarIntervalData.gaps` was always empty list
- Display had no gap information to show

### 3. **Inefficient Mid-Session Symbol Loading**
- `_manage_historical_data()` accepted `symbols` parameter but didn't use it
- Always cleared ALL historical data (even for existing symbols)
- Always loaded ALL symbols from config (not just new ones)
- Wasted time reloading existing data

---

## Solution Implemented (Option A)

### Architecture
Created a **shared method** that both code paths use:
- **Initial Load**: `_calculate_historical_quality()` for all symbols at startup
- **Mid-Session Add**: `_process_pending_symbols()` for new symbols only

### Changes Made

#### 1. **SessionData** (`session_data.py`)
```python
def clear_symbol_historical(self, symbol: str) -> None:
    """Clear historical bars for a specific symbol."""
    # Targeted clear instead of clearing all symbols
```

#### 2. **Session Coordinator** (`session_coordinator.py`)

**A. Fixed `_manage_historical_data()`**
```python
def _manage_historical_data(self, symbols: Optional[List[str]] = None):
    # If symbols specified (mid-session), clear only those
    if symbols:
        for symbol in symbols:
            self.session_data.clear_symbol_historical(symbol)
    else:
        # Initial load: clear all
        self.session_data.clear_session_bars()
        self.session_data.clear_historical_bars()
    
    # Pass symbols_filter to config loader
    for hist_data_config in historical_config.data:
        self._load_historical_data_config(
            hist_config=hist_data_config,
            current_date=current_date,
            symbols_filter=symbols_to_process  # NEW
        )
```

**B. Updated `_load_historical_data_config()`**
```python
def _load_historical_data_config(
    self,
    hist_config,
    current_date: date,
    symbols_filter: Optional[List[str]] = None  # NEW
):
    # Resolve symbols from config
    config_symbols = self._resolve_symbols(hist_config.apply_to)
    
    # Apply filter if provided (for mid-session adds)
    if symbols_filter:
        symbols = [s for s in config_symbols if s in symbols_filter]
    else:
        symbols = config_symbols
```

**C. Created Shared Method `_calculate_quality_and_gaps_for_symbol()`**
```python
def _calculate_quality_and_gaps_for_symbol(self, symbol: str, intervals: Optional[List[str]] = None):
    """Calculate quality and detect gaps for historical bars of a symbol.
    
    This is a shared method used by both:
    - _calculate_historical_quality() (initial load, all symbols)
    - _process_pending_symbols() (mid-session add, specific symbols)
    
    For each interval:
    1. Calculate quality percentage
    2. Detect gaps in the data
    3. Store quality in HistoricalBarIntervalData.quality  # FIXED
    4. Store gaps in HistoricalBarIntervalData.gaps        # NEW
    """
    for interval in intervals:
        quality = self._calculate_bar_quality(symbol, interval)
        
        # Get HistoricalBarIntervalData
        hist_interval_data = symbol_data.historical.bars.get(interval_key)
        
        # Store quality DIRECTLY in historical data
        hist_interval_data.quality = quality  # FIXED
        
        # Detect gaps for each date
        all_gaps = []
        for hist_date, bars in hist_interval_data.data_by_date.items():
            date_gaps = detect_gaps(
                symbol=symbol,
                session_start=session_start,
                current_time=session_end,
                existing_bars=bars,
                interval_minutes=interval_minutes
            )
            all_gaps.extend(date_gaps)
        
        # Store gaps in historical data
        hist_interval_data.gaps = all_gaps  # NEW
```

**D. Added Helper Method `_get_historical_quality()`**
```python
def _get_historical_quality(self, symbol: str, interval: str) -> Optional[float]:
    """Get quality for historical bars from HistoricalBarIntervalData."""
    hist_interval_data = symbol_data.historical.bars.get(interval_key)
    if hist_interval_data:
        return hist_interval_data.quality
    return None
```

**E. Updated `_calculate_historical_quality()`**
```python
def _calculate_historical_quality(self):
    # Use shared method for quality and gap calculation
    for symbol in self.session_config.session_data_config.symbols:
        self._calculate_quality_and_gaps_for_symbol(symbol, base_intervals)
        
        # Propagate base quality to derived intervals
        for interval in base_intervals:
            quality = self._get_historical_quality(symbol, interval)  # NEW
            if quality is not None:
                self._propagate_quality_to_derived_historical(symbol, interval, quality)
```

**F. Updated `_process_pending_symbols()`**
```python
def _process_pending_symbols(self):
    # Load symbols using existing methods
    self._validate_and_mark_streams(symbols=pending)
    self._manage_historical_data(symbols=pending)
    
    # NEW: Calculate quality and gaps for newly loaded symbols
    base_intervals = ["1m", "1s", "1d"]
    for symbol in pending:
        self._calculate_quality_and_gaps_for_symbol(symbol, base_intervals)
        
        # Propagate base quality to derived intervals
        for interval in base_intervals:
            quality = self._get_historical_quality(symbol, interval)
            if quality is not None:
                self._propagate_quality_to_derived_historical(symbol, interval, quality)
    
    self._load_backtest_queues(symbols=pending)
```

---

## Benefits

### ✅ **Correct Data Storage**
- Quality stored in `HistoricalBarIntervalData.quality` (not session bars)
- Gaps stored in `HistoricalBarIntervalData.gaps` (new feature)
- Display now reads from the correct location

### ✅ **No Code Duplication**
- Single shared method `_calculate_quality_and_gaps_for_symbol()`
- Used by both initial load and mid-session adds
- Easy to maintain and test

### ✅ **Efficient Mid-Session Adds**
- Only clears historical for new symbols (not all)
- Only loads historical for new symbols (not all)
- No wasted reloading of existing data

### ✅ **Complete Information**
- Quality calculated for historical data
- Gaps detected for historical data
- Both displayed in CLI output

---

## Data Flow

### Initial Session Load
```
system start
  → _manage_historical_data(symbols=None)
    → Clear ALL data
    → Load ALL symbols from config
    → _load_historical_data_config(symbols_filter=None)
  
  → _calculate_historical_quality()
    → For each symbol:
      → _calculate_quality_and_gaps_for_symbol(symbol, ["1m", "1d"])
        → Calculate quality → store in HistoricalBarIntervalData.quality
        → Detect gaps → store in HistoricalBarIntervalData.gaps
```

### Mid-Session Symbol Add
```
add_symbol("TSLA")
  → Marks as pending
  
streaming_loop
  → _process_pending_symbols()
    → _manage_historical_data(symbols=["TSLA"])
      → Clear ONLY TSLA historical
      → Load ONLY TSLA from config
      → _load_historical_data_config(symbols_filter=["TSLA"])
    
    → For symbol "TSLA":
      → _calculate_quality_and_gaps_for_symbol("TSLA", ["1m", "1d"])
        → Calculate quality → store in HistoricalBarIntervalData.quality
        → Detect gaps → store in HistoricalBarIntervalData.gaps
```

---

## Export Structure

Historical data now exports with quality and gaps:

```json
{
  "session_data": {
    "symbols": {
      "RIVN": {
        "historical": {
          "loaded": true,
          "bars": {
            "1m": {
              "count": 1656,
              "quality": 85.5,           // ✅ Now calculated!
              "date_range": {
                "start_date": "2025-06-27",
                "end_date": "2025-07-01",
                "days": 3
              },
              "gaps": {                   // ✅ Now detected!
                "gap_count": 2,
                "missing_bars": 15,
                "ranges": [
                  {
                    "start_time": "09:45:00",
                    "end_time": "09:55:00",
                    "bar_count": 10
                  }
                ]
              }
            }
          }
        }
      }
    }
  }
}
```

---

## Display Output

Historical data now shows quality and gaps:

```
Historical│
  1m   │ 1,656 bars | Jun 27-Jul 01 (3d) | Q: 85.5% | 2 gaps (15 missing)
  1d   │ 2 bars | Jun 30-Jul 01 (2d) | Q: 100%
```

Instead of:

```
Historical│
  1m   │ 1,656 bars | Jun 27-Jul 01 (3 days)  // Missing quality & gaps
  1d   │ 2 bars | Jun 30-Jul 01 (2 days)      // Missing quality & gaps
```

---

## Additional Fix: Daily Bars (1d)

### Problem
Daily bars (1d) were not showing quality and gaps because:
1. **Interval key mismatch**: Code used `"1440m"` but bars stored as `"1d"`
2. **Wrong quality calculation**: Tried to calculate "how many 1440-min bars fit in 390-min day" (nonsense)
3. **Wrong gap detection**: Tried to detect minute gaps within a day (each day has only 1 bar)

### Solution
Added special handling for daily intervals:

**Quality Calculation (daily):**
```python
if interval.endswith('d'):
    # Quality = (actual trading days / expected trading days) * 100
    dates_with_bars = sorted(hist_interval_data.data_by_date.keys())
    start_date = dates_with_bars[0]
    end_date = dates_with_bars[-1]
    
    expected_days = time_manager.count_trading_days(
        db_session, start_date, end_date, exchange
    )
    actual_days = len(dates_with_bars)
    quality = (actual_days / expected_days) * 100.0
```

**Gap Detection (daily):**
```python
if interval.endswith('d'):
    # For daily bars, gaps = missing trading days
    dates_with_bars = sorted(hist_interval_data.data_by_date.keys())
    expected_days = time_manager.count_trading_days(...)
    actual_days = len(dates_with_bars)
    missing_days = expected_days - actual_days
    
    if missing_days > 0:
        gap = GapInfo(
            symbol=symbol,
            start_time=datetime.combine(start_date, time(0, 0)),
            end_time=datetime.combine(end_date, time(23, 59)),
            bar_count=missing_days  # missing trading days
        )
```

**Interval Key Fix:**
```python
# For daily bars, use "1d" key, not "1440m"
if interval.endswith('d'):
    interval_key = "1d"
else:
    interval_key = f"{interval_minutes}m"
```

## Testing

To verify the fix:

```bash
system start
data session 0
```

Expected output:
- Historical section shows quality percentages (not 0.0) **for all intervals including 1d**
- Historical section shows gaps if present **for all intervals including 1d**
- Quality color-coded (green ≥95%, yellow 80-95%, red <80%)
- Daily bars show quality based on trading days coverage
- Daily gaps represent missing trading days (not missing minute bars)

---

## Files Modified

1. **`/app/managers/data_manager/session_data.py`**
   - Added `clear_symbol_historical()` method

2. **`/app/threads/session_coordinator.py`**
   - Fixed `_manage_historical_data()` - targeted clearing
   - Updated `_load_historical_data_config()` - symbols_filter parameter
   - Added `_get_historical_quality()` - helper method
   - Added `_calculate_quality_and_gaps_for_symbol()` - shared method
   - Updated `_calculate_historical_quality()` - uses shared method
   - Updated `_process_pending_symbols()` - calculates quality/gaps

3. **`/app/cli/session_data_display.py`**
   - Already updated to display historical quality and gaps (previous fix)

---

## Summary

✅ Historical quality is now calculated and stored correctly  
✅ Historical gaps are now detected and stored  
✅ Mid-session symbol adds are now efficient (no unnecessary reloading)  
✅ Display shows complete information (quality + gaps)  
✅ No code duplication (shared method for both paths)  

**All changes follow TimeManager architecture rules** - no hardcoded times or manual date calculations.
