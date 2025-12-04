# Visual Comparison: Current vs Proposed Architecture

## Current Architecture: Fragmented Tracking

```
┌─────────────────────────────────────────────────────────────────────────┐
│ SessionData                                                             │
├─────────────────────────────────────────────────────────────────────────┤
│ _symbols: Dict[str, SymbolSessionData]    ← ACTUAL DATA                │
│   "AAPL": SymbolSessionData(...)                                        │
│   "RIVN": SymbolSessionData(...)                                        │
│                                                                         │
│ _active_symbols: Set[str]                 ← DUPLICATE! Same info       │
│   {"AAPL", "RIVN"}                          (can infer from _symbols)  │
│                                                                         │
│ _active_streams: Dict[Tuple, bool]        ← OK (stream lifecycle)     │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↑
                                    │ Must synchronize manually
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ SessionCoordinator                                                      │
├─────────────────────────────────────────────────────────────────────────┤
│ _loaded_symbols: Set[str]                 ← DUPLICATE! Can be flag in  │
│   {"AAPL", "RIVN"}                          SymbolSessionData          │
│                                                                         │
│ _pending_symbols: Set[str]                ← OK (temporary operation)   │
│   {"TSLA"}                                                              │
│                                                                         │
│ _streamed_data: Dict[str, List[str]]      ← DUPLICATE! Can be in       │
│   {"AAPL": ["1m"], "RIVN": ["1m"]}         SymbolSessionData          │
│                                                                         │
│ _generated_data: Dict[str, List[str]]     ← DUPLICATE! Can be in       │
│   {"AAPL": ["5m","15m"], "RIVN": [...]}     SymbolSessionData          │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↑
                                    │ Must notify explicitly
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ DataProcessor                                                           │
├─────────────────────────────────────────────────────────────────────────┤
│ _derived_intervals: Dict[str, List[str]]  ← DUPLICATE! Same as         │
│   {"AAPL": ["5m","15m"], "RIVN": [...]}     coordinator._generated     │
│                                                                         │
│ set_generated_data(...)                   ← Must be told explicitly    │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↑
                                    │ Discovers via polling
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ DataQualityManager                                                      │
├─────────────────────────────────────────────────────────────────────────┤
│ _failed_gaps: Dict[str, List[GapInfo]]   ← OK (retry state, live mode)│
│                                                                         │
│ _last_quality_calc: Dict[str, datetime]  ← OK (throttling state)      │
│                                                                         │
│ Gap details computed but DISCARDED       ← PROBLEM! Not stored        │
└─────────────────────────────────────────────────────────────────────────┘

PROBLEMS:
════════
❌ Symbol tracking in 4 places (SessionData, Coordinator, implicit in Processor)
❌ Derived intervals in 3 places (Coordinator streamed/generated, Processor)
❌ Loaded status in 2 places (Coordinator._loaded_symbols + implicit)
❌ Gap details computed but not stored
❌ Manual synchronization required (add symbol → tell everyone)
❌ Cleanup fragmented (remove symbol → clean up 3-4 places)
```

---

## Proposed Architecture: Single Source of Truth

```
┌─────────────────────────────────────────────────────────────────────────┐
│ SessionData                                                             │
├─────────────────────────────────────────────────────────────────────────┤
│ _symbols: Dict[str, SymbolSessionData]    ← SINGLE SOURCE OF TRUTH     │
│   "AAPL": SymbolSessionData(                                            │
│     symbol="AAPL",                                                      │
│     base_interval="1m",                                                 │
│     derived_intervals=["5m", "15m"],     ← Self-describing!            │
│     is_loaded=True,                      ← Self-describing!            │
│     bar_quality={"1m": 98.5, "5m": 98.5},                              │
│     bar_gaps={"1m": [gap1, gap2]},       ← Stored!                     │
│     bars_base=[...],                                                    │
│     bars_derived={"5m": [...], "15m": [...]},                          │
│     ...                                                                 │
│   ),                                                                    │
│   "RIVN": SymbolSessionData(...)                                        │
│                                                                         │
│ _active_streams: Dict[Tuple, bool]        ← OK (stream lifecycle)     │
│                                                                         │
│ REMOVED: _active_symbols                  ← Use _symbols.keys()       │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↑
                                    │ All threads query here
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ SessionCoordinator                                                      │
├─────────────────────────────────────────────────────────────────────────┤
│ _pending_symbols: Set[str]                ← OK (temporary operation)   │
│   {"TSLA"}                                                              │
│                                                                         │
│ REMOVED: _loaded_symbols                  ← Query SessionData         │
│ REMOVED: _streamed_data                   ← In SymbolSessionData      │
│ REMOVED: _generated_data                  ← In SymbolSessionData      │
│                                                                         │
│ get_loaded_symbols() →                    ← Delegates to SessionData  │
│   session_data.get_loaded_symbols()                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↑
                                    │ Queries SessionData
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ DataProcessor                                                           │
├─────────────────────────────────────────────────────────────────────────┤
│ REMOVED: _derived_intervals               ← Query SessionData         │
│                                                                         │
│ Main loop:                                                              │
│   for symbol in session_data.get_active_symbols():                     │
│     symbol_data = session_data.get_symbol_data(symbol)                 │
│     if not symbol_data:                                                 │
│       continue  # Removed mid-iteration, skip gracefully               │
│                                                                         │
│     for interval in symbol_data.derived_intervals:  ← Self-describing! │
│       generate_derived_bars(symbol, interval)                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↑
                                    │ Queries SessionData
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ DataQualityManager                                                      │
├─────────────────────────────────────────────────────────────────────────┤
│ _failed_gaps: Dict[str, List[GapInfo]]   ← OK (retry state, live mode)│
│ _last_quality_calc: Dict[str, datetime]  ← OK (throttling state)      │
│                                                                         │
│ _calculate_quality(...):                                                │
│   gaps = detect_gaps(...)                                              │
│   quality = calculate_quality(...)                                     │
│   session_data.set_gaps(symbol, interval, gaps)  ← STORED!            │
│                                                                         │
│ Main loop:                                                              │
│   for symbol in session_data.get_active_symbols():                     │
│     symbol_data = session_data.get_symbol_data(symbol)                 │
│     if not symbol_data:                                                 │
│       continue  # Removed mid-iteration, skip gracefully               │
│                                                                         │
│     check_quality(symbol, symbol_data.base_interval)                   │
│     for interval in symbol_data.derived_intervals:  ← Self-describing! │
│       check_quality(symbol, interval)                                  │
└─────────────────────────────────────────────────────────────────────────┘

BENEFITS:
════════
✅ Symbol tracking in 1 place (SessionData._symbols)
✅ Derived intervals in 1 place (SymbolSessionData.derived_intervals)
✅ Loaded status in 1 place (SymbolSessionData.is_loaded)
✅ Gap details stored (SymbolSessionData.bar_gaps)
✅ Automatic synchronization (threads iterate SessionData)
✅ Single cleanup operation (remove from SessionData → done)
✅ Self-describing data (each SymbolSessionData knows its state)
```

---

## Add Symbol Flow Comparison

### BEFORE: Fragmented (5 Steps, 3-4 Components)

```
┌──────────────┐
│ User Request │ "Add TSLA"
└──────┬───────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 1: SessionData.register_symbol("TSLA")                 │
│   → _symbols["TSLA"] = SymbolSessionData(symbol="TSLA")     │
│   → _active_symbols.add("TSLA")          ← Manual update    │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 2: SessionCoordinator.add_symbol("TSLA")               │
│   → _pending_symbols.add("TSLA")         ← Manual update    │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 3: Load historical + queues                            │
│   → _loaded_symbols.add("TSLA")          ← Manual update    │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 4: DataProcessor.set_generated_data(...)               │
│   → _derived_intervals["TSLA"] = ["5m"]  ← Manual notify    │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 5: DataQualityManager discovers via polling            │
│   (May take 1-2 iterations to discover)                     │
└─────────────────────────────────────────────────────────────┘

PROBLEMS:
• 5 manual updates across 3 components
• Must remember all places
• Race conditions possible
• Error-prone
```

### AFTER: Centralized (1 Step, Automatic Discovery)

```
┌──────────────┐
│ User Request │ "Add TSLA"
└──────┬───────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│ SessionData.register_symbol_data(...)                       │
│   _symbols["TSLA"] = SymbolSessionData(                     │
│     symbol="TSLA",                                          │
│     base_interval="1m",                                     │
│     derived_intervals=["5m", "15m"],                        │
│     is_loaded=False  # Will be set to True after loading   │
│   )                                                         │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
          ┌────────────────┴────────────────┐
          ↓                ↓                ↓
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│DataProcessor  │ │QualityManager │ │Coordinator    │
│discovers TSLA │ │discovers TSLA │ │marks loaded   │
│on next        │ │on next        │ │when ready     │
│iteration      │ │iteration      │ │               │
└───────────────┘ └───────────────┘ └───────────────┘

BENEFITS:
• 1 operation in SessionData
• All threads discover automatically
• No race conditions
• No manual synchronization
• Can't forget to notify
```

---

## Remove Symbol Flow Comparison

### BEFORE: Fragmented (4-5 Cleanup Steps)

```
┌──────────────┐
│ User Request │ "Remove TSLA"
└──────┬───────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 1: SessionData.remove_symbol("TSLA")                   │
│   → del _symbols["TSLA"]                                    │
│   → _active_symbols.discard("TSLA")      ← Manual cleanup   │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 2: SessionCoordinator cleanup                          │
│   → _loaded_symbols.discard("TSLA")      ← Manual cleanup   │
│   → _pending_symbols.discard("TSLA")     ← Manual cleanup   │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 3: DataProcessor cleanup                               │
│   → del _derived_intervals["TSLA"]       ← Manual cleanup   │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 4: DataQualityManager cleanup                          │
│   → May process TSLA one more time (race condition)         │
│   → Eventually discovers it's gone                          │
└─────────────────────────────────────────────────────────────┘

PROBLEMS:
• 4-5 cleanup steps
• Easy to forget one
• Race conditions (quality manager might process after removal)
• Fragmented, error-prone
```

### AFTER: Centralized (1 Step, Graceful Handling)

```
┌──────────────┐
│ User Request │ "Remove TSLA"
└──────┬───────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│ SessionData.remove_symbol("TSLA")                           │
│   → del _symbols["TSLA"]                                    │
│   → That's it! All data gone.                               │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
          ┌────────────────┴────────────────┐
          ↓                ↓                ↓
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│DataProcessor  │ │QualityManager │ │Coordinator    │
│               │ │               │ │               │
│if not data:   │ │if not data:   │ │if not data:   │
│  continue     │ │  continue     │ │  continue     │
│               │ │               │ │               │
│Graceful skip! │ │Graceful skip! │ │Graceful skip! │
└───────────────┘ └───────────────┘ └───────────────┘

BENEFITS:
• 1 operation in SessionData
• All threads handle removal gracefully
• No race conditions (None check)
• No manual cleanup needed
• Can't forget anything
```

---

## Data Flow: Processing Bars

### BEFORE: Must Query Multiple Places

```
DataProcessor receives bar for "AAPL" interval "1m"
  ↓
┌─────────────────────────────────────────────┐
│ Get symbol data from SessionData            │
│   symbol_data = session_data.get("AAPL")    │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│ Check if should generate derived            │
│   if interval == "1m":                      │
│     derived = self._derived_intervals["AAPL"]  ← Internal tracking
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│ Generate derived bars                       │
│   for interval in derived:                  │
│     generate_bars(interval)                 │
└─────────────────────────────────────────────┘

PROBLEM: Must maintain separate _derived_intervals dict
```

### AFTER: All Info in One Place

```
DataProcessor receives bar for "AAPL" interval "1m"
  ↓
┌─────────────────────────────────────────────┐
│ Get symbol data from SessionData            │
│   symbol_data = session_data.get("AAPL")    │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│ Check if should generate derived            │
│   if interval == symbol_data.base_interval: │
│     derived = symbol_data.derived_intervals │  ← Self-describing!
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│ Generate derived bars                       │
│   for interval in derived:                  │
│     generate_bars(interval)                 │
└─────────────────────────────────────────────┘

BENEFIT: All data in SymbolSessionData, no separate tracking
```

---

## Gap Information: Before vs After

### BEFORE: Computed But Discarded

```
DataQualityManager._calculate_quality("AAPL", "1m")
  ↓
┌─────────────────────────────────────────────┐
│ Detect gaps                                 │
│   gaps = detect_gaps(...)                   │
│   # gaps = [                                │
│   #   GapInfo(start=09:45, end=09:47, count=3),
│   #   GapInfo(start=10:15, end=10:17, count=3)
│   # ]                                       │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│ Calculate quality                           │
│   quality = (actual / expected) * 100       │
│   # quality = 98.5                          │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│ Store quality percentage                    │
│   session_data.set_quality("AAPL", "1m", 98.5)
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│ Log gaps (for debugging)                    │
│   logger.info(f"Found {len(gaps)} gaps")    │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│ DISCARD gaps                                │
│   gaps goes out of scope                    │
│   Details LOST ❌                           │
└─────────────────────────────────────────────┘

JSON Export:
{
  "1m": {
    "quality": 98.5,  ← Only percentage exported
    "gaps": ???       ← NOT AVAILABLE
  }
}
```

### AFTER: Gaps Stored and Exported

```
DataQualityManager._calculate_quality("AAPL", "1m")
  ↓
┌─────────────────────────────────────────────┐
│ Detect gaps                                 │
│   gaps = detect_gaps(...)                   │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│ Calculate quality                           │
│   quality = (actual / expected) * 100       │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│ Store quality AND gaps                      │
│   session_data.set_quality("AAPL", "1m", 98.5)
│   session_data.set_gaps("AAPL", "1m", gaps) ← NEW!
└─────────────────────────────────────────────┘

JSON Export:
{
  "1m": {
    "quality": 98.5,
    "gaps": {              ← NOW AVAILABLE! ✅
      "gap_count": 2,
      "missing_bars": 6,
      "ranges": [
        {
          "start_time": "09:45:00",
          "end_time": "09:47:00",
          "bar_count": 3
        },
        {
          "start_time": "10:15:00",
          "end_time": "10:17:00",
          "bar_count": 3
        }
      ]
    },
    "data": [...]
  }
}
```

---

## Summary: Architectural Transformation

| Aspect | Before | After |
|--------|--------|-------|
| **Symbol tracking** | 4 places | 1 place (SessionData) |
| **Derived intervals** | 3 places | 1 place (SymbolSessionData) |
| **Loaded status** | 2 places | 1 place (SymbolSessionData.is_loaded) |
| **Gap details** | Computed, discarded | Stored, exported |
| **Add symbol** | 5 manual steps | 1 operation |
| **Remove symbol** | 4-5 cleanup steps | 1 operation |
| **Synchronization** | Manual notifications | Automatic (iteration) |
| **Data location** | Scattered | Hierarchical (single tree) |
| **Thread discovery** | Explicit notify | Automatic iteration |
| **Cleanup safety** | Error-prone | Automatic cascade |

### Key Insight

**Before:** Data scattered → Manual synchronization → Error-prone  
**After:** Data centralized → Automatic discovery → Bulletproof

All threads iterate `SessionData`, find what they need, skip gracefully if removed.  
**One truth, many readers** → No synchronization bugs possible.
