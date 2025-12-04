# JSON Attribute Mapping - Source Variables

This document maps every attribute in `SYSTEM_JSON_EXAMPLE.json` to its actual source variable in the codebase.

## Legend

- ✅ **Direct mapping** - Attribute maps to a source variable
- 🔄 **Computed** - Value is computed/derived, not stored directly
- ❌ **Missing** - Source doesn't exist yet, needs to be added
- 📝 **Renamed** - JSON name differs from source name (for clarity)

---

## 1. `system_manager` Object

**Source:** `/app/managers/system_manager/api.py` - `SystemManager` class

| JSON Attribute | Source Variable | Status | Notes |
|----------------|-----------------|--------|-------|
| `state` | `self._state` | ✅ | Type: `SystemState` enum (STOPPED, RUNNING) |
| `mode` | `self.mode` (property) | ✅ | Property returns `self._session_config.mode` (SINGLE SOURCE) |
| `timezone` | `self.timezone` | ✅ | Type: `str`, derived from exchange_group + asset_class |
| `backtest_window.start_date` | 🔄 Computed | 🔄 | From `self.backtest_start_date` property (parses from config) |
| `backtest_window.end_date` | 🔄 Computed | 🔄 | From `self.backtest_end_date` property (parses from config) |
| `performance.uptime_seconds` | 🔄 Computed | ❌ | Need to add: `self._start_time` (datetime), compute delta |
| `performance.memory_usage_mb` | 🔄 Computed | ❌ | Compute via `psutil.Process().memory_info().rss / 1024 / 1024` |

### Recommendations:
- **`mode` already exists**: Property at line 186 and 762 (DUPLICATE - need to fix)
- **Add `self._start_time`**: Set when `start()` is called, for uptime calculation
- **Note**: Line 186-194 returns `str`, line 762-767 returns `OperationMode` enum (duplicate definition!)

---

## 2. `threads.session_coordinator` Object

**Source:** `/app/threads/session_coordinator.py` - `SessionCoordinator` class

| JSON Attribute | Source Variable | Status | Notes |
|----------------|-----------------|--------|-------|
| `thread_info.name` | `self.name` | ✅ | From `threading.Thread` base class |
| `thread_info.is_alive` | `self.is_alive()` | ✅ | Method from `threading.Thread` |
| `thread_info.daemon` | `self.daemon` | ✅ | From `threading.Thread` base class |
| `state` | 🔄 Computed | ❌ | Need to add: `self._state` (e.g., "running", "paused", "stopped") |
| `current_session_date` | 🔄 Computed | 🔄 | Get from `session_data.get_current_session_date()` |
| `session_active` | `self._session_active` | ✅ | Type: `bool` |
| `iterations` | 🔄 Computed | ❌ | Need to add: `self._iteration_count` (increment each cycle) |
| `performance.avg_cycle_ms` | 🔄 Computed | ❌ | Track via performance metrics (need moving average) |
| `performance.last_cycle_ms` | 🔄 Computed | ❌ | Track last cycle duration |

### Recommendations:
- **Add `self._state`**: Track coordinator state explicitly
- **Add `self._iteration_count`**: Increment in main loop
- **Add performance tracking**: Use `self.metrics` (PerformanceMetrics) to track cycle times

---

## 3. `threads.data_upkeep` Object

**Note:** This thread doesn't exist in current codebase. It's been replaced by `DataProcessor`.

**Should be:** `threads.data_processor`

**Source:** `/app/threads/data_processor.py` - `DataProcessor` class

| JSON Attribute | Source Variable | Status | Notes |
|----------------|-----------------|--------|-------|
| `thread_info.name` | `self.name` | ✅ | From `threading.Thread` base class |
| `thread_info.is_alive` | `self.is_alive()` | ✅ | Method from `threading.Thread` |
| `thread_info.daemon` | `self.daemon` | ✅ | From `threading.Thread` base class |
| `state` | 🔄 Computed | ❌ | Need to add: `self._state` |
| `cycles_completed` | 🔄 Computed | ❌ | Need to add: `self._cycles_completed` |
| `derived_intervals` | 🔄 Computed | 🔄 | From session config: `session_config.session_data_config.data_upkeep.derived_intervals` |
| `performance.avg_cycle_ms` | 🔄 Computed | ❌ | Track cycle times |
| `performance.last_computation_ms` | 🔄 Computed | ❌ | Track last computation duration |

### Recommendations:
- **Rename in JSON**: `data_upkeep` → `data_processor` (matches actual thread name)
- **Add performance tracking**: Similar to SessionCoordinator

---

## 4. `threads.stream_coordinator` Object

**Note:** This doesn't exist as a separate thread. Streaming is handled within `SessionCoordinator`.

**Options:**
1. Remove this section (streaming is part of SessionCoordinator)
2. Extract queue stats from SessionCoordinator
3. Add a separate BacktestStreamCoordinator class if needed

**If using SessionCoordinator's queue data:**

**Source:** `/app/threads/session_coordinator.py` - `SessionCoordinator._bar_queues`

| JSON Attribute | Source Variable | Status | Notes |
|----------------|-----------------|--------|-------|
| `thread_info.*` | N/A | ❌ | Part of SessionCoordinator, not separate thread |
| `state` | N/A | ❌ | Same as SessionCoordinator state |
| `items_yielded` | 🔄 Computed | ❌ | Need to add: `self._items_yielded` counter |
| `queue_stats.{SYMBOL}.{TYPE}.size` | `len(self._bar_queues[(symbol, interval)])` | 🔄 | Computed from `_bar_queues` dict |
| `queue_stats.{SYMBOL}.{TYPE}.oldest` | `self._bar_queues[(symbol, interval)][0].timestamp` | 🔄 | First item timestamp in deque |
| `queue_stats.{SYMBOL}.{TYPE}.newest` | `self._bar_queues[(symbol, interval)][-1].timestamp` | 🔄 | Last item timestamp in deque |
| `performance.avg_yield_ms` | 🔄 Computed | ❌ | Track time to yield each item |
| `performance.stale_items_skipped` | 🔄 Computed | ❌ | Need counter for stale items |

### Recommendations:
- **Remove from JSON**: Merge into SessionCoordinator section
- **Or add method**: `SessionCoordinator.get_queue_stats()` that returns this data

---

## 5. `session_data.system` Object

**RECOMMENDATION: REMOVE THIS SECTION FROM JSON** ❌

This duplicates the `system_manager` section and violates single source of truth.

| JSON Attribute | Source Variable | Status | Notes |
|----------------|-----------------|--------|-------|
| `state` | `system_manager._state` | ❌ DUPLICATE | Already in `system_manager.state` |
| `mode` | `system_manager.mode` | ❌ DUPLICATE | Already in `system_manager.mode` |

### Why Remove:
- **Duplicate data**: Same info already in `system_manager` section
- **Single source of truth**: SystemManager owns system state/mode
- **SessionData doesn't own this**: SessionData is for market data, not system state

---

## 6. `session_data.session` Object

**Source:** `/app/managers/data_manager/session_data.py` - `SessionData` class

| JSON Attribute | Source Variable | Status | Notes |
|----------------|-----------------|--------|-------|
| `date` | 🔄 Computed | ❌ | Need to add: `self._session_date` (date) |
| `time` | 🔄 Computed | ❌ | Need to add: `self._session_time` (time) or get from TimeManager |
| `active` | `self._session_active` | ✅ | Type: `bool` |
| `ended` | 🔄 Computed | ❌ | Need to add: `self._session_ended` (bool) |
| `symbol_count` | `len(self._active_symbols)` | ✅ | Computed from set size |

### Recommendations:
- **Add `self._session_date`**: Track current session date
- **Add `self._session_time`**: Track current session time (updated during streaming)
- **Add `self._session_ended`**: Flag when session completes
- **Or get from TimeManager**: `time_manager.get_current_time()` for time

---

## 7. `session_data.symbols.{SYMBOL}` Object

**Source:** `/app/managers/data_manager/session_data.py` - `SymbolSessionData` class

### Structure Overview

```json
{
  "AAPL": {
    "base_interval": "1m",
    "session": { /* Current session data */ },
    "historical": { /* Historical bars data */ }
  }
}
```

### 7.1 Top-level Attributes

| JSON Attribute | Source Variable | Status | Notes |
|----------------|-----------------|--------|-------|
| `base_interval` | `self.base_interval` | ✅ | Type: `str` ("1s" or "1m") |

### 7.2 `session` Section (Current Day)

Maps to current session data attributes in `SymbolSessionData`:

| JSON Attribute | Source Variable | Status | Notes |
|----------------|-----------------|--------|-------|
| `volume` | `self.session_volume` | ✅ | Type: `int` |
| `high` | `self.session_high` | ✅ | Type: `float` |
| `low` | `self.session_low` | ✅ | Type: `float` |
| `last_update` | `self.last_update` | ✅ | Type: `datetime` |
| `bar_quality` | `self.bar_quality` | ✅ | Type: `float` (0-100) |
| `bars_updated` | `self.bars_updated` | ✅ | Type: `bool` |
| `quotes_updated` | `self.quotes_updated` | ✅ | Type: `bool` |
| `ticks_updated` | `self.ticks_updated` | ✅ | Type: `bool` |
| `bar_counts.1m` | `self.get_bar_count("1m")` | ✅ | Method call |
| `bar_counts.5m` | `self.get_bar_count("5m")` | ✅ | Method call |
| `bar_counts.15m` | `self.get_bar_count("15m")` | ✅ | Method call |
| `time_range.first_bar` | `self.bars_base[0].timestamp` | 🔄 | If bars_base not empty |
| `time_range.last_bar` | `self.last_update` | ✅ | Same as last_update |

### 7.3 `historical` Section (Past Days)

Maps to `self.historical_bars: Dict[str, Dict[date, List[BarData]]]`:

| JSON Attribute | Source Variable | Status | Notes |
|----------------|-----------------|--------|-------|
| `loaded` | `bool(self.historical_bars)` | 🔄 | True if any historical data exists |
| `bar_counts_by_interval.{interval}.{date}` | `len(self.historical_bars[interval][date])` | ✅ | Count bars per date per interval |
| `bar_counts_by_interval.{interval}.total_dates` | `len(self.historical_bars[interval])` | 🔄 | Number of dates with data |
| `date_range.start` | `min(self.historical_bars[interval].keys())` | 🔄 | Earliest date with data |
| `date_range.end` | `max(self.historical_bars[interval].keys())` | 🔄 | Latest date with data |

### Recommendations:
- ✅ **Current structure correctly maps both session and historical data**
- **Note:** `historical_bars` structure: `Dict[interval, Dict[date, List[BarData]]]`
- **Example:** `historical_bars["1m"][date(2024,11,14)]` = list of 390 bars

---

## 8. `_metadata` Object

**Source:** Generated during `to_json()` call

| JSON Attribute | Source | Status | Notes |
|----------------|--------|--------|-------|
| `generated_at` | `time_manager.get_current_time().isoformat()` | 🔄 | Computed at call time |
| `complete` | Function parameter | 🔄 | From `complete` flag |
| `debug` | Function parameter | 🔄 | From `debug` flag |
| `diff_mode` | `not complete` | 🔄 | Inverse of `complete` flag |
| `changed_paths` | DiffTracker output | 🔄 | List of paths that changed since last call |

**Note:** This is metadata about the JSON itself, not source data.

---

## Summary of Changes Needed

### SystemManager (`/app/managers/system_manager/api.py`)
```python
class SystemManager:
    def __init__(self):
        # ... existing ...
        self._mode: Optional[str] = None  # ✅ ADD: "backtest" or "live"
        self._start_time: Optional[datetime] = None  # ✅ ADD: For uptime calculation
    
    def start(self, config_file: str):
        # ... existing ...
        self._mode = config.mode
        self._start_time = self.get_time_manager().get_current_time()  # ✅ ADD
```

### SessionCoordinator (`/app/threads/session_coordinator.py`)
```python
class SessionCoordinator(threading.Thread):
    def __init__(self, ...):
        # ... existing ...
        self._state: str = "stopped"  # ✅ ADD: "running", "paused", "stopped"
        self._iteration_count: int = 0  # ✅ ADD: Cycle counter
        self._items_yielded: int = 0  # ✅ ADD: Items streamed counter
        self._cycle_times: deque = deque(maxlen=100)  # ✅ ADD: For avg calculation
        self._last_cycle_ms: float = 0.0  # ✅ ADD: Last cycle duration
```

### DataProcessor (`/app/threads/data_processor.py`)
```python
class DataProcessor(threading.Thread):
    def __init__(self, ...):
        # ... existing ...
        self._state: str = "stopped"  # ✅ ADD
        self._cycles_completed: int = 0  # ✅ ADD
        self._cycle_times: deque = deque(maxlen=100)  # ✅ ADD
        self._last_computation_ms: float = 0.0  # ✅ ADD
```

### SessionData (`/app/managers/data_manager/session_data.py`)
```python
class SessionData:
    def __init__(self):
        # ... existing ...
        self._session_date: Optional[date] = None  # ✅ ADD
        self._session_time: Optional[time] = None  # ✅ ADD
        self._session_ended: bool = False  # ✅ ADD
```

### SymbolSessionData (`/app/managers/data_manager/session_data.py`)
```python
@dataclass
class SymbolSessionData:
    # ... existing ...
    vwap: Optional[float] = None  # ✅ ADD: Volume-weighted average price
    first_bar_ts: Optional[datetime] = None  # ✅ ADD: First bar timestamp
    historical_loaded: bool = False  # ✅ ADD: Historical data loaded flag
    _update_count: int = 0  # ✅ ADD: Performance tracking
    _last_update_duration_ms: float = 0.0  # ✅ ADD: Performance tracking
```

---

## JSON Naming vs Source Naming

### Attributes with Different Names (for clarity in JSON):

1. **SymbolSessionData:**
   - Source: `session_volume` → JSON: `volume` ✅ (simpler)
   - Source: `session_high` → JSON: `high` ✅ (simpler)
   - Source: `session_low` → JSON: `low` ✅ (simpler)
   - Source: `last_update` → JSON: `time_range.last_bar` 📝 (more descriptive)

2. **SystemManager:**
   - Source: `_state` → JSON: `state` ✅ (drop underscore)
   - Source: `timezone` → JSON: `timezone` ✅ (same)

### Recommendations:
Keep JSON names simple and descriptive. The mapping layer will handle conversion between source and JSON naming.

---

## Attributes Not From Source (4 items as requested)

1. **`_metadata`** - Generated at serialization time, not from any source object
2. **`current_bars.{interval}.columns`** - Static array, not from source
3. **`backtest_window`** - Computed object aggregating start/end dates
4. **`thread_info`** - Aggregated from multiple Thread base class properties

---

## Implementation Priority

### High Priority (Core functionality):
1. Add missing state tracking to threads
2. Add session date/time to SessionData
3. Add performance counters (iterations, cycles)

### Medium Priority (Metrics):
4. Add cycle time tracking for performance metrics
5. Add uptime tracking to SystemManager
6. Add VWAP to SymbolSessionData

### Low Priority (Debug/optimization):
7. Add memory usage tracking
8. Add stale items counter
9. Add detailed queue statistics

---

## Thread Names in JSON

### Current JSON vs Actual Threads:

| JSON Name | Actual Thread | Status |
|-----------|--------------|---------|
| `session_coordinator` | `SessionCoordinator` | ✅ Correct |
| `data_upkeep` | `DataProcessor` | ❌ **Should be `data_processor`** |
| `stream_coordinator` | Part of SessionCoordinator | ❌ **Should remove or merge** |

### Recommendation:
Update JSON example to use actual thread names:
- `session_coordinator` ✅
- `data_processor` ✅ (rename from `data_upkeep`)
- `data_quality_manager` ✅ (add if needed)
- `analysis_engine` ✅ (add if needed)

Remove `stream_coordinator` (not a separate thread) or merge into `session_coordinator`.
