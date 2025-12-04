# SessionData Tree Structure: Proposed Architecture

## Complete Hierarchy (Single Source of Truth)

```
SessionData (Singleton)
│
├─ _session_active: bool                          ← Session state
├─ _current_session_date: Optional[date]          ← Current date
├─ _lock: threading.RLock()                       ← Thread safety
├─ _data_arrival_event: threading.Event()         ← Notification
│
├─ _active_streams: Dict[Tuple[str, str], bool]   ← Stream lifecycle tracking
│   └─ Example: {("AAPL", "bars"): True, ("AAPL", "ticks"): True}
│
└─ _symbols: Dict[str, SymbolSessionData]         ← ★ SINGLE SOURCE OF TRUTH ★
    │
    ├─ "AAPL": SymbolSessionData
    │   │
    │   ├─ IDENTITY
    │   │   ├─ symbol: "AAPL"
    │   │   ├─ base_interval: "1m"                ← "1s" or "1m"
    │   │   ├─ derived_intervals: ["5m", "15m"]   ← ✨ NEW: Self-describing!
    │   │   └─ is_loaded: True                    ← ✨ NEW: Loading status
    │   │
    │   ├─ BARS (Current Session)
    │   │   ├─ bars_base: Deque[BarData]          ← Base bars (1s or 1m)
    │   │   │   ├─ BarData(timestamp=09:30:00, open=150.0, ...)
    │   │   │   ├─ BarData(timestamp=09:31:00, open=150.5, ...)
    │   │   │   └─ ...
    │   │   │
    │   │   ├─ bars_derived: Dict[str, List[BarData]]  ← Computed bars
    │   │   │   ├─ "5m": [BarData(...), BarData(...), ...]
    │   │   │   └─ "15m": [BarData(...), BarData(...), ...]
    │   │   │
    │   │   └─ _latest_bar: Optional[BarData]     ← Cached for O(1) access
    │   │
    │   ├─ QUALITY & GAPS
    │   │   ├─ bar_quality: Dict[str, float]      ← Per-interval quality
    │   │   │   ├─ "1m": 98.5
    │   │   │   ├─ "5m": 98.5
    │   │   │   └─ "15m": 99.2
    │   │   │
    │   │   └─ bar_gaps: Dict[str, List[GapInfo]] ← ✨ NEW: Gap details stored!
    │   │       ├─ "1m": [
    │   │       │   GapInfo(symbol="AAPL", start=09:45, end=09:47, count=3),
    │   │       │   GapInfo(symbol="AAPL", start=10:15, end=10:17, count=3)
    │   │       │ ]
    │   │       ├─ "5m": [GapInfo(...)]
    │   │       └─ "15m": []
    │   │
    │   ├─ SESSION METRICS
    │   │   ├─ session_volume: 19106
    │   │   ├─ session_high: 13.54
    │   │   ├─ session_low: 13.47
    │   │   └─ last_update: datetime(2025-07-02 11:52:00)
    │   │
    │   ├─ UPDATE FLAGS
    │   │   ├─ bars_updated: True                 ← Triggers processing
    │   │   ├─ quotes_updated: False
    │   │   └─ ticks_updated: False
    │   │
    │   ├─ HISTORICAL DATA (Trailing Days)
    │   │   ├─ historical_bars: Dict[str, Dict[date, List[BarData]]]
    │   │   │   ├─ "1m": {
    │   │   │   │   date(2025-06-30): [BarData(...), BarData(...), ...],
    │   │   │   │   date(2025-07-01): [BarData(...), BarData(...), ...]
    │   │   │   │ }
    │   │   │   └─ "1d": {
    │   │   │       date(2025-06-30): [BarData(...)],
    │   │   │       date(2025-07-01): [BarData(...)]
    │   │   │     }
    │   │   │
    │   │   └─ historical_indicators: Dict[str, Any]
    │   │       ├─ "avg_volume_2d": 24525389.0
    │   │       └─ "max_price_5d": 150.25
    │   │
    │   ├─ OTHER DATA TYPES
    │   │   ├─ quotes: List[QuoteData]
    │   │   │   ├─ QuoteData(timestamp=..., bid=150.0, ask=150.1, ...)
    │   │   │   └─ ...
    │   │   │
    │   │   └─ ticks: List[TickData]
    │   │       ├─ TickData(timestamp=..., price=150.0, ...)
    │   │       └─ ...
    │   │
    │   └─ INTERNAL (Delta Export Tracking)
    │       └─ _last_export_indices: Dict[str, Any]
    │           ├─ "ticks": 0
    │           ├─ "quotes": 0
    │           ├─ "bars_base": 0
    │           ├─ "bars_derived": {"5m": 0, "15m": 0}
    │           └─ "last_export_time": datetime(...)
    │
    ├─ "RIVN": SymbolSessionData
    │   ├─ symbol: "RIVN"
    │   ├─ base_interval: "1m"
    │   ├─ derived_intervals: ["5m", "15m"]
    │   ├─ is_loaded: True
    │   ├─ bars_base: Deque[...]
    │   ├─ bars_derived: {"5m": [...], "15m": [...]}
    │   ├─ bar_quality: {"1m": 100.0, "5m": 100.0}
    │   ├─ bar_gaps: {"1m": [], "5m": []}
    │   ├─ session_volume: 5432
    │   └─ ...
    │
    └─ "TSLA": SymbolSessionData
        └─ ... (same structure as above)


REMOVED (No longer needed):
══════════════════════════
❌ _active_symbols: Set[str]           → Infer from _symbols.keys()
❌ SessionCoordinator._loaded_symbols   → Use SymbolSessionData.is_loaded
❌ SessionCoordinator._streamed_data    → Use SymbolSessionData.base_interval
❌ SessionCoordinator._generated_data   → Use SymbolSessionData.derived_intervals
❌ DataProcessor._derived_intervals     → Query SessionData.get_symbols_with_derived()
```

---

## Access Patterns

### Getting Active Symbols
```
SessionData.get_active_symbols()
└─> return set(_symbols.keys())
    └─> {"AAPL", "RIVN", "TSLA"}
```

### Getting Loaded Symbols
```
SessionData.get_loaded_symbols()
└─> return {sym for sym, data in _symbols.items() if data.is_loaded}
    └─> {"AAPL", "RIVN"}  (TSLA still loading)
```

### Getting Derived Intervals for All Symbols
```
SessionData.get_symbols_with_derived()
└─> return {sym: data.derived_intervals for sym, data in _symbols.items()}
    └─> {
        "AAPL": ["5m", "15m"],
        "RIVN": ["5m", "15m"],
        "TSLA": ["5m"]
    }
```

### Getting Gap Details
```
SessionData.get_symbol_data("AAPL")
└─> _symbols["AAPL"]
    └─> bar_gaps["1m"]
        └─> [GapInfo(...), GapInfo(...)]
```

---

## Thread Access Pattern (All Threads Use Same Pattern)

```
┌─────────────────────────────────────────────┐
│ DataProcessor / QualityManager / etc.       │
│                                             │
│ Main Loop:                                  │
│   for symbol in session_data.get_active_symbols():
│     ↓                                       │
│     symbol_data = session_data.get_symbol_data(symbol)
│     ↓                                       │
│     if not symbol_data:                     │
│       continue  # Removed, skip gracefully  │
│     ↓                                       │
│     # All data available in symbol_data:   │
│     - symbol_data.base_interval            │
│     - symbol_data.derived_intervals        │
│     - symbol_data.is_loaded                │
│     - symbol_data.bars_base                │
│     - symbol_data.bars_derived             │
│     - symbol_data.bar_quality              │
│     - symbol_data.bar_gaps                 │
│     - symbol_data.bars_updated (flag)      │
│     ↓                                       │
│     Process based on available data        │
└─────────────────────────────────────────────┘

No separate tracking needed!
Everything discoverable from SessionData.
```

---

## Comparison: Data Locations

### Active Symbols
```
BEFORE:
SessionData
├─ _symbols: {"AAPL": ..., "RIVN": ...}     ← Actual data
└─ _active_symbols: {"AAPL", "RIVN"}        ← ❌ DUPLICATE

AFTER:
SessionData
└─ _symbols: {"AAPL": ..., "RIVN": ...}     ← ✅ SINGLE SOURCE
   (infer active from keys)
```

### Loaded Status
```
BEFORE:
SessionData._symbols["AAPL"]                 ← Actual data
SessionCoordinator._loaded_symbols           ← ❌ DUPLICATE set

AFTER:
SessionData._symbols["AAPL"]
└─ is_loaded: True                           ← ✅ STORED IN DATA
```

### Derived Intervals
```
BEFORE:
SessionCoordinator._generated_data           ← ❌ DUPLICATE
DataProcessor._derived_intervals             ← ❌ DUPLICATE

AFTER:
SessionData._symbols["AAPL"]
└─ derived_intervals: ["5m", "15m"]          ← ✅ SINGLE LOCATION
```

### Gap Information
```
BEFORE:
DataQualityManager._calculate_quality()
└─ gaps = detect_gaps(...)
   └─ Used for logging, then DISCARDED       ← ❌ LOST

AFTER:
SessionData._symbols["AAPL"]
└─ bar_gaps: {                               ← ✅ STORED
     "1m": [GapInfo(...), GapInfo(...)],
     "5m": [GapInfo(...)]
   }
```

---

## JSON Export Structure (Mirrors Object Hierarchy)

```
{
  "symbols": {
    "AAPL": {                                  ← From _symbols["AAPL"]
      "session": {
        "volume": 19106,                       ← session_volume
        "high": 13.54,                         ← session_high
        "low": 13.47,                          ← session_low
        "data": {
          "1m": {                              ← From bars_base (if base_interval="1m")
            "count": 112,
            "quality": 98.5,                   ← From bar_quality["1m"]
            "gaps": {                          ← ✨ From bar_gaps["1m"]
              "gap_count": 2,
              "missing_bars": 6,
              "ranges": [...]
            },
            "data": [...]
          },
          "5m": {                              ← From bars_derived["5m"]
            "count": 23,
            "generated": true,                 ← Inferred from derived_intervals
            "quality": 98.5,                   ← From bar_quality["5m"]
            "gaps": {...},                     ← From bar_gaps["5m"]
            "data": [...]
          }
        }
      },
      "historical": {
        "loaded": true,                        ← Inferred from historical_bars
        "data": {
          "1m": {                              ← From historical_bars["1m"]
            "count": 1656,
            "quality": 93.4,                   ← From bar_quality["1m"] (historical)
            "gaps": {...},                     ← From bar_gaps["1m"] (historical)
            "data": [...]
          }
        },
        "avg_volume_2d": 24525389.0            ← From historical_indicators
      }
    }
  }
}

JSON export directly mirrors the object hierarchy!
```

---

## Key Insights from Tree Structure

### 1. Everything Under One Root
```
SessionData._symbols
└─ Everything flows from here
   └─ No parallel tracking structures
   └─ No duplicate information
   └─ Single source of truth
```

### 2. Self-Describing Data
```
Each SymbolSessionData knows:
├─ What interval it streams (base_interval)
├─ What intervals it derives (derived_intervals)
├─ Whether it's loaded (is_loaded)
├─ Its quality per interval (bar_quality)
└─ Its gaps per interval (bar_gaps)

No need to ask anyone else!
```

### 3. Hierarchical Cleanup
```
Remove "AAPL" from SessionData._symbols
└─> All AAPL data gone:
    ├─ All bars (base + derived)
    ├─ All quality metrics
    ├─ All gaps
    ├─ All historical data
    └─ All indicators

One operation, complete cleanup!
```

### 4. Automatic Discovery
```
Thread wants to know about symbols?
└─> Iterate SessionData._symbols
    └─> Find everything needed in each SymbolSessionData
        └─> No registration required
        └─> No notification needed
        └─> No synchronization bugs possible
```

### 5. Gap Visibility
```
BEFORE: gaps computed → logged → discarded
        └─> No audit trail
        └─> No export
        └─> Quality % alone doesn't tell story

AFTER: gaps computed → stored → exported
       └─> Full audit trail
       └─> Visible in JSON/CSV
       └─> Complete data quality picture
```

---

## Summary: Tree Principles

1. **Single Root:** All data under `SessionData._symbols`
2. **Self-Contained:** Each `SymbolSessionData` has all its metadata
3. **No Duplication:** Information stored once, inferred where needed
4. **Hierarchical:** Natural parent-child relationships
5. **Discoverable:** Iterate root, find everything
6. **Complete:** Gap details stored, not just summary metrics

**Result:** Clean, maintainable, impossible to desynchronize!
