# Dropped Attributes from SYSTEM_JSON_EXAMPLE.json

These attributes were removed because they don't map to actual source code variables.

## Dropped from `system_manager`

1. ❌ **`performance.uptime_seconds`** - No `_start_time` attribute exists yet (needs to be added)
2. ❌ **`performance.memory_usage_mb`** - Not stored, would need to be computed on-demand via psutil

## Dropped from `threads.session_coordinator`

1. ❌ **`iterations`** - No `_iteration_count` or equivalent counter in source
2. ❌ **`performance.avg_cycle_ms`** - Not tracked directly (would need MetricTracker)
3. ❌ **`performance.last_cycle_ms`** - Not tracked directly (would need MetricTracker)

**Note:** These are tracked in system-level `PerformanceMetrics.iterations`, but not in the thread itself.

## Dropped from `threads.data_processor`

1. ❌ **`cycles_completed`** - No `_cycles_completed` counter in source
2. ❌ **`performance.avg_cycle_ms`** - Not tracked in thread (tracked in system PerformanceMetrics)
3. ❌ **`performance.last_computation_ms`** - Not tracked in thread

**Kept:**
- ✅ `derived_intervals` - Maps to `self._derived_intervals` (populated from coordinator)

## Dropped from `threads.data_quality_manager`

1. ❌ **`checks_completed`** - No counter in source
2. ❌ **`performance.avg_check_ms`** - Not tracked
3. ❌ **`performance.last_check_ms`** - Not tracked

## Dropped from `threads.analysis_engine`

1. ❌ **`performance.avg_analysis_ms`** - Tracked in PerformanceMetrics, not in thread
2. ❌ **`performance.last_analysis_ms`** - Not tracked in thread

**Kept:**
- ✅ `signals_generated` - Maps to `self._signals_generated`

## Dropped from `session_data.session`

1. ❌ **`time`** - Time is available from TimeManager's current_time, not stored in SessionData
2. ❌ **`ended`** - Not a stored attribute (only `_session_active` exists)

**Replaced with:**
- ✅ `time_manager` section with TradingSession data (date, open/close times, holiday info)

## Dropped from `session_data.symbols.{SYMBOL}`

1. ❌ **`performance.last_update_ms`** - Not tracked per symbol
2. ❌ **`performance.total_updates`** - Not tracked per symbol
3. ❌ **`current_bars.{interval}.data`** - Too verbose for example JSON (actual bars not shown)

**Restructured (Not Dropped):**
- ✅ **Split into `session` and `historical` sections** - Matches `SymbolSessionData` structure
- ✅ `session`: Current day data (volume, high, low, bar_counts, quality, update flags)
- ✅ `historical`: Past days data from `self.historical_bars: Dict[str, Dict[date, List[BarData]]]`

**Kept:**
- ✅ All core attributes: volume, high, low, bar_counts, bar_quality
- ✅ time_range (first_bar, last_bar)
- ✅ bars_updated, quotes_updated, ticks_updated flags
- ✅ base_interval (1s or 1m)
- ✅ Historical bars with counts per date per interval

## Added (Previously Missing)

### SystemManager
1. ✅ **`_mode`** - Now stored directly (performance optimization)
2. ✅ **`_start_time`** - For uptime calculation (needs to be added to source)

### Threads
1. ✅ **`_state`** - Added to SessionCoordinator (needs to be added to source)
2. ✅ **`_state`** - Added to DataProcessor (needs to be added to source)
3. ✅ **`_state`** - Added to DataQualityManager
4. ✅ **`_state`** - Added to AnalysisEngine

### Root Level
1. ✅ **`performance_metrics`** - Complete PerformanceMetrics object with all counters/trackers

### SessionData
1. ✅ **`time_manager`** - TradingSession info (date, open/close times, holiday, early_close)

## Summary

**Total Dropped:** 18 attributes  
**Total Added:** 7 attributes + PerformanceMetrics object  

**Reason:** All remaining attributes now map directly to source code variables or are computed from them.
