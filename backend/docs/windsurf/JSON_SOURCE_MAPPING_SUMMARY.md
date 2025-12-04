# JSON to Source Code Mapping - Quick Reference

## Overview

This document provides a quick visual reference for mapping JSON attributes to their source code locations.

---

## 🗂️ File Structure

```
JSON Structure                          Source File
├── system_manager                   → /app/managers/system_manager/api.py (SystemManager)
│   ├── state                        → self._state
│   ├── mode                         → self.mode (property, line 186 & 762 - DUPLICATE!)
│   ├── timezone                     → self.timezone
│   ├── backtest_window.start_date   → self.backtest_start_date (property)
│   ├── backtest_window.end_date     → self.backtest_end_date (property)
│   └── performance
│       ├── uptime_seconds           → (ADD) current_time - self._start_time
│       └── memory_usage_mb          → (COMPUTE) psutil
│
├── threads                          → /app/threads/*.py
│   ├── session_coordinator          → session_coordinator.py (SessionCoordinator)
│   │   ├── thread_info.name         → self.name (Thread base class)
│   │   ├── thread_info.is_alive     → self.is_alive() (Thread base class)
│   │   ├── thread_info.daemon       → self.daemon (Thread base class)
│   │   ├── state                    → self._state (ADD)
│   │   ├── current_session_date     → session_data.get_current_session_date()
│   │   ├── session_active           → self._session_active
│   │   ├── iterations               → self._iteration_count (ADD)
│   │   └── performance
│   │       ├── avg_cycle_ms         → (ADD) track with deque
│   │       └── last_cycle_ms        → self._last_cycle_ms (ADD)
│   │
│   ├── data_processor               → data_processor.py (DataProcessor)
│   │   ├── thread_info.*            → (same as above)
│   │   ├── state                    → self._state (ADD)
│   │   ├── cycles_completed         → self._cycles_completed (ADD)
│   │   ├── derived_intervals        → session_config...derived_intervals
│   │   └── performance
│   │       ├── avg_cycle_ms         → (ADD) track with deque
│   │       └── last_computation_ms  → self._last_computation_ms (ADD)
│   │
│   ├── data_quality_manager         → data_quality_manager.py (DataQualityManager)
│   │   └── ... (similar pattern)
│   │
│   └── analysis_engine              → analysis_engine.py (AnalysisEngine)
│       └── ... (similar pattern)
│
└── session_data                     → /app/managers/data_manager/session_data.py
    ├── session                      → SessionData class
    │   ├── date                     → self._session_date (ADD)
    │   ├── time                     → self._session_time (ADD) or time_manager
    │   ├── active                   → self._session_active
    │   ├── ended                    → self._session_ended (ADD)
    │   └── symbol_count             → len(self._active_symbols)
    │
    └── symbols.{SYMBOL}             → SymbolSessionData class
        ├── symbol                   → self.symbol
        ├── volume                   → self.session_volume
        ├── high                     → self.session_high
        ├── low                      → self.session_low
        ├── vwap                     → self.vwap (ADD)
        ├── bar_counts
        │   ├── 1m                   → self.get_bar_count("1m")
        │   ├── 5m                   → self.get_bar_count("5m")
        │   └── 15m                  → self.get_bar_count("15m")
        ├── bar_quality              → self.bar_quality
        ├── bars_updated             → self.bars_updated
        ├── time_range
        │   ├── first_bar            → self.first_bar_ts (ADD)
        │   └── last_bar             → self.last_update
        ├── current_bars             → (SERIALIZE from self.bars_base / bars_derived)
        │   ├── {interval}.columns   → Static array
        │   └── {interval}.data      → Array of [timestamp, OHLCV]
        ├── historical_summary
        │   ├── loaded               → self.historical_loaded (ADD)
        │   ├── bar_counts.*         → Count from self.historical_bars
        │   └── date_range           → Min/max dates from historical_bars
        └── performance
            ├── last_update_ms       → self._last_update_duration_ms (ADD)
            └── total_updates        → self._update_count (ADD)
```

---

## 📊 Status Legend

| Symbol | Meaning | Action Required |
|--------|---------|-----------------|
| ✅ | Direct mapping exists | None - use as-is |
| 🔄 | Computed/derived value | Create helper method |
| ❌ | Missing from source | Add new attribute |
| 📝 | Name differs (JSON vs source) | Map in serialization |

---

## 🔧 Attributes to Add

### SystemManager
```python
class SystemManager:
    def __init__(self):
        # Note: mode property already exists (line 186 & 762) - duplicated!
        self._start_time: Optional[datetime] = None   # ❌ ADD
```

### SessionCoordinator
```python
class SessionCoordinator(threading.Thread):
    def __init__(self):
        self._state: str = "stopped"                  # ❌ ADD
        self._iteration_count: int = 0                # ❌ ADD
        self._cycle_times: deque = deque(maxlen=100)  # ❌ ADD
        self._last_cycle_ms: float = 0.0              # ❌ ADD
```

### DataProcessor
```python
class DataProcessor(threading.Thread):
    def __init__(self):
        self._state: str = "stopped"                  # ❌ ADD
        self._cycles_completed: int = 0               # ❌ ADD
        self._cycle_times: deque = deque(maxlen=100)  # ❌ ADD
        self._last_computation_ms: float = 0.0        # ❌ ADD
```

### SessionData
```python
class SessionData:
    def __init__(self):
        self._session_date: Optional[date] = None     # ❌ ADD
        self._session_time: Optional[time] = None     # ❌ ADD
        self._session_ended: bool = False             # ❌ ADD
```

### SymbolSessionData
```python
@dataclass
class SymbolSessionData:
    vwap: Optional[float] = None                      # ❌ ADD
    first_bar_ts: Optional[datetime] = None           # ❌ ADD
    historical_loaded: bool = False                   # ❌ ADD
    _update_count: int = 0                            # ❌ ADD
    _last_update_duration_ms: float = 0.0             # ❌ ADD
```

---

## 📝 Name Mapping (JSON ≠ Source)

| JSON Path | Source Variable | Note |
|-----------|----------------|------|
| `symbols.{SYMBOL}.volume` | `session_volume` | Simplified in JSON |
| `symbols.{SYMBOL}.high` | `session_high` | Simplified in JSON |
| `symbols.{SYMBOL}.low` | `session_low` | Simplified in JSON |
| `symbols.{SYMBOL}.time_range.last_bar` | `last_update` | More descriptive in JSON |
| `system_manager.state` | `_state` | Drop underscore in JSON |

---

## 🚫 Not From Source (Computed/Generated)

1. **`_metadata`** - Generated during serialization
   - `generated_at` - Current timestamp
   - `complete` - Function parameter
   - `debug` - Function parameter
   - `diff_mode` - Computed from `complete`
   - `changed_paths` - From DiffTracker

2. **`current_bars.{interval}.columns`** - Static array

3. **`backtest_window`** - Aggregated object

4. **`thread_info`** - Aggregated from Thread base class

---

## 🎯 Thread Name Corrections

| Original JSON | Should Be | File |
|--------------|-----------|------|
| ❌ `data_upkeep` | ✅ `data_processor` | `data_processor.py` |
| ❌ `stream_coordinator` | ✅ (remove - part of SessionCoordinator) | N/A |

---

## 🔍 Data Flow Example

### Getting Symbol Volume

```
JSON Request: system_manager.to_json()
     ↓
SystemManager.to_json() calls SessionData.to_json()
     ↓
SessionData.to_json() iterates symbols
     ↓
For each symbol: SymbolSessionData.to_json()
     ↓
Reads: self.session_volume
     ↓
JSON Output: {"symbols": {"AAPL": {"volume": 125000}}}
```

### Computing Performance Metrics

```
Thread main loop:
     ↓
Start: start_time = time.perf_counter()
     ↓
... do work ...
     ↓
End: duration_ms = (time.perf_counter() - start_time) * 1000
     ↓
Store: self._last_cycle_ms = duration_ms
Store: self._cycle_times.append(duration_ms)
     ↓
On to_json(): avg = sum(self._cycle_times) / len(self._cycle_times)
```

---

## 📦 Bar Data Serialization

### Source: SymbolSessionData
```python
# Base bars (1m)
self.bars_base: Deque[BarData]

# Derived bars (5m, 15m, etc.)
self.bars_derived: Dict[str, List[BarData]] = {
    "5m": [BarData(...), BarData(...)],
    "15m": [BarData(...), BarData(...)]
}
```

### JSON Output (efficient array format)
```json
{
  "current_bars": {
    "1m": {
      "columns": ["timestamp", "open", "high", "low", "close", "volume"],
      "data": [
        ["09:30:00", 183.50, 183.75, 183.25, 183.60, 25000],
        ["09:31:00", 183.60, 183.80, 183.55, 183.70, 18000]
      ]
    }
  }
}
```

### Serialization Process
```python
def _serialize_bars(self, interval: str) -> dict:
    if interval == "1m" or interval == self.base_interval:
        bars = self.bars_base
    else:
        bars = self.bars_derived.get(interval, [])
    
    return {
        "columns": ["timestamp", "open", "high", "low", "close", "volume"],
        "data": [
            [
                bar.timestamp.strftime("%H:%M:%S"),
                float(bar.open),
                float(bar.high),
                float(bar.low),
                float(bar.close),
                int(bar.volume)
            ]
            for bar in bars
        ]
    }
```

---

## ✅ Implementation Checklist

- [ ] Add missing attributes to **SystemManager (2):**
  - `_start_time` - For uptime calculation
  - Memory usage tracking
  - **Note**: `mode` property already exists (but duplicated at line 186 & 762) attributes to DataProcessor
- [ ] Add missing attributes to DataQualityManager
- [ ] Add missing attributes to AnalysisEngine
- [ ] Add missing attributes to SessionData
- [ ] Add missing attributes to SymbolSessionData
- [ ] Implement DiffTracker base class
- [ ] Implement to_json() for all classes
- [ ] Update JSON example with correct thread names
- [ ] Add CLI command `system json`
- [ ] Add tests for serialization
- [ ] Add tests for diff tracking
- [ ] Document API usage
