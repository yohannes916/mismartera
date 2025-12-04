# SessionData Structure: Refined Design (Based on User Feedback)

**Date:** December 4, 2025  
**Status:** Proposed Refinement - Analysis & Critique

---

## User's Proposed Improvements

### ✅ 1. Self-Describing Bar Intervals
**Suggestion:** Move `derived` flag and `base` reference under each bar interval structure

**Analysis:** ✅ **EXCELLENT** - Makes each interval completely self-contained

**Example:**
```python
bars: {
    "1m": {
        "derived": False,        # Streamed, not computed
        "base": None,           # Not derived from anything
        "data": [...],
        "quality": 98.5,
        "gaps": [...]
    },
    "5m": {
        "derived": True,         # Computed from base
        "base": "1m",           # Derived from 1m bars
        "data": [...],
        "quality": 98.5,
        "gaps": [...]
    }
}
```

### ✅ 2. Remove IDENTITY Section
**Suggestion:** Don't need separate `base_interval`, `derived_intervals` list when structure is self-describing

**Analysis:** ⚠️ **PARTIALLY AGREE** - Structure is self-describing, but consider:

**PROS:**
- No duplication
- Each interval self-contained
- Natural discovery

**CONS:**
- Performance: Must iterate all intervals to find base (minor)
- Explicit vs Implicit: `base_interval` makes coordinator code clearer
- Loading state: Need to know which interval to load queues for

**RECOMMENDATION:** Hybrid approach
```python
# Keep minimal identity for performance
symbol: str                    # Keep (obviously needed)
base_interval: str = "1m"      # Keep (performance + clarity)
# Remove: derived_intervals    # ✅ Remove (infer from bars structure)
# Remove: is_loaded            # ✅ Remove (see critique below)
```

### ✅ 3. Remove `is_loaded` Flag
**Suggestion:** If bars exist, it's loaded

**Analysis:** ✅ **AGREE WITH CAVEAT**

**Original intent:** Know when historical data + queues loaded (coordinator needs this)

**Better approach:** Infer from data presence
```python
def is_loaded(self) -> bool:
    """Symbol is loaded if it has bars or historical data."""
    return len(self.bars) > 0 or len(self.historical) > 0
```

**CAVEAT:** What about a symbol that:
- Is in config
- Historical load failed (0 bars)
- Stream not started yet

How do we distinguish "not yet loaded" vs "loaded but has no data"?

**SOLUTION:** Use presence of bars structure, not data
```python
# If bars structure exists (even if empty), it's initialized
self.bars: Dict[str, BarIntervalData] = {}

# Empty dict = not loaded
# Dict with keys (even empty data) = loaded
```

### ✅ 4. Naming Improvements
**Suggestions:**
- `historical_indicators` → `indicators` (already under historical)
- `SESSION METRICS` → Better name for session-level indicators

**Analysis:** ✅ **EXCELLENT**

**Proposed naming:**
```
session_metrics: SessionMetrics     # OHLCV summary (volume, high, low)
session_indicators: Dict[str, Any]  # Computed indicators (RSI, VWAP, etc.)
```

**Distinction:**
- **Metrics:** Basic aggregations (volume, high, low) - always present
- **Indicators:** Computed analytics (RSI, VWAP, etc.) - optional

### ✅ 5. Top-Level Structure per Symbol
**Suggestion:** `bars`, `quotes`, `ticks`, `indicators`, `historical` at same level

**Analysis:** ✅ **EXCELLENT** - Clean grouping by data type

---

## Refined Structure (Incorporating Feedback)

```python
@dataclass
class BarIntervalData:
    """Self-describing bar interval with all metadata."""
    
    # Metadata (self-describing!)
    derived: bool               # Is this interval computed?
    base: Optional[str]         # What interval is it derived from? (None if not derived)
    
    # Data
    data: List[BarData]         # Actual bars (or Deque for base interval)
    
    # Quality
    quality: float              # Quality percentage (0-100)
    gaps: List[GapInfo]         # Gap details
    
    # Flags
    updated: bool = False       # New data since last check


@dataclass
class SessionMetrics:
    """Basic session metrics (OHLCV aggregations)."""
    volume: int = 0
    high: Optional[float] = None
    low: Optional[float] = None
    last_update: Optional[datetime] = None


@dataclass
class SymbolSessionData:
    """Per-symbol data for current trading session.
    
    Organized by data type: bars, quotes, ticks, indicators, historical.
    Each section is self-contained with all relevant metadata.
    """
    
    # === IDENTITY (Minimal) ===
    symbol: str
    base_interval: str = "1m"   # Keep for performance/clarity
    
    # === BARS (Self-Describing Structure) ===
    bars: Dict[str, BarIntervalData] = field(default_factory=dict)
    # Example:
    # {
    #   "1m": BarIntervalData(derived=False, base=None, data=[...], quality=98.5, gaps=[...]),
    #   "5m": BarIntervalData(derived=True, base="1m", data=[...], quality=98.5, gaps=[...]),
    #   "15m": BarIntervalData(derived=True, base="1m", data=[...], quality=99.2, gaps=[])
    # }
    
    # === QUOTES ===
    quotes: List[QuoteData] = field(default_factory=list)
    quotes_updated: bool = False
    
    # === TICKS ===
    ticks: List[TickData] = field(default_factory=list)
    ticks_updated: bool = False
    
    # === SESSION METRICS ===
    metrics: SessionMetrics = field(default_factory=SessionMetrics)
    
    # === SESSION INDICATORS (Optional computed metrics) ===
    indicators: Dict[str, Any] = field(default_factory=dict)
    # Example: {"rsi_14": 65.5, "vwap": 150.25, "session_momentum": 0.85}
    
    # === HISTORICAL DATA ===
    historical: HistoricalData = field(default_factory=lambda: HistoricalData())
    
    # === INTERNAL ===
    _latest_bar: Optional[BarData] = None  # Cache for O(1) access
    _last_export_indices: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HistoricalData:
    """Historical data for trailing days."""
    
    # Bars (structured like session bars)
    bars: Dict[str, HistoricalBarIntervalData] = field(default_factory=dict)
    # Example:
    # {
    #   "1m": HistoricalBarIntervalData(
    #       data_by_date={date1: [...], date2: [...]},
    #       quality=93.4,
    #       gaps=[...]
    #   ),
    #   "1d": HistoricalBarIntervalData(...)
    # }
    
    # Indicators (historical aggregations)
    indicators: Dict[str, Any] = field(default_factory=dict)
    # Example: {"avg_volume_2d": 24525389.0, "max_price_5d": 150.25}


@dataclass
class HistoricalBarIntervalData:
    """Historical bars for one interval across multiple dates."""
    
    # Data organized by date
    data_by_date: Dict[date, List[BarData]] = field(default_factory=dict)
    
    # Quality (historical)
    quality: float = 0.0
    gaps: List[GapInfo] = field(default_factory=list)
    
    # Metadata
    date_range: Optional[DateRange] = None
```

---

## Complete Tree Structure (Refined)

```
SymbolSessionData ("AAPL")
│
├─ symbol: "AAPL"
├─ base_interval: "1m"                        ← Keep for performance
│
├─ bars: Dict[str, BarIntervalData]           ← Self-describing!
│   │
│   ├─ "1m": BarIntervalData
│   │   ├─ derived: False                     ← Streamed
│   │   ├─ base: None                         ← Not derived
│   │   ├─ data: Deque[BarData]              ← Actual bars
│   │   ├─ quality: 98.5                      ← Quality %
│   │   ├─ gaps: [GapInfo(...), GapInfo(...)] ← Gap details
│   │   └─ updated: True                      ← Flag for processing
│   │
│   ├─ "5m": BarIntervalData
│   │   ├─ derived: True                      ← Computed
│   │   ├─ base: "1m"                         ← Derived from 1m
│   │   ├─ data: List[BarData]
│   │   ├─ quality: 98.5
│   │   ├─ gaps: [GapInfo(...)]
│   │   └─ updated: False
│   │
│   └─ "15m": BarIntervalData
│       ├─ derived: True
│       ├─ base: "1m"
│       ├─ data: List[BarData]
│       ├─ quality: 99.2
│       ├─ gaps: []
│       └─ updated: False
│
├─ quotes: List[QuoteData]
│   ├─ QuoteData(timestamp=..., bid=150.0, ask=150.1)
│   └─ ...
│
├─ quotes_updated: bool
│
├─ ticks: List[TickData]
│   ├─ TickData(timestamp=..., price=150.0)
│   └─ ...
│
├─ ticks_updated: bool
│
├─ metrics: SessionMetrics                    ← Basic OHLCV aggregations
│   ├─ volume: 19106
│   ├─ high: 13.54
│   ├─ low: 13.47
│   └─ last_update: datetime(...)
│
├─ indicators: Dict[str, Any]                 ← Computed session indicators
│   ├─ "rsi_14": 65.5
│   ├─ "vwap": 150.25
│   └─ "session_momentum": 0.85
│
├─ historical: HistoricalData
│   │
│   ├─ bars: Dict[str, HistoricalBarIntervalData]
│   │   │
│   │   ├─ "1m": HistoricalBarIntervalData
│   │   │   ├─ data_by_date: {
│   │   │   │   date(2025-06-30): [BarData(...)],
│   │   │   │   date(2025-07-01): [BarData(...)]
│   │   │   │ }
│   │   │   ├─ quality: 93.4
│   │   │   ├─ gaps: [GapInfo(...)]
│   │   │   └─ date_range: DateRange(...)
│   │   │
│   │   └─ "1d": HistoricalBarIntervalData
│   │       └─ ...
│   │
│   └─ indicators: Dict[str, Any]            ← Historical aggregations
│       ├─ "avg_volume_2d": 24525389.0
│       └─ "max_price_5d": 150.25
│
├─ _latest_bar: Optional[BarData]            ← Internal cache
└─ _last_export_indices: Dict[str, Any]      ← Internal tracking
```

---

## Comparison: Current Plan vs Refined

| Aspect | Current Plan | Refined (User's Suggestion) | Winner |
|--------|--------------|----------------------------|---------|
| **Bar metadata location** | Separate `derived_intervals` list | In each `BarIntervalData` | ✅ Refined |
| **Derived flag** | Infer from list | Explicit per interval | ✅ Refined |
| **Base source** | Implicit (always base_interval) | Explicit `base` field | ✅ Refined |
| **is_loaded flag** | Separate field | Infer from data presence | ✅ Refined |
| **Top-level grouping** | Mixed | By data type | ✅ Refined |
| **Naming** | `historical_indicators` | `indicators` (under historical) | ✅ Refined |
| **Session metrics** | Flat fields | Grouped in `SessionMetrics` | ✅ Refined |
| **Indicators** | Not distinguished | Separate from metrics | ✅ Refined |
| **base_interval field** | Kept | Suggested removal | ⚠️ Keep (performance) |

---

## Critique & Improvements

### ✅ What's Better in Refined Design

1. **Self-Describing Intervals**
   ```python
   # OLD: Must check separate list
   if interval in symbol_data.derived_intervals:
       base = symbol_data.base_interval
   
   # NEW: Everything in one place
   interval_data = symbol_data.bars["5m"]
   if interval_data.derived:
       base = interval_data.base
   ```

2. **Natural Grouping**
   ```
   OLD: bars_base, bars_derived, quotes, ticks, session_volume, ...
   NEW: bars, quotes, ticks, metrics, indicators, historical
   ```

3. **Cleaner Historical Structure**
   ```python
   # OLD
   historical_bars: Dict[str, Dict[date, List[BarData]]]
   historical_indicators: Dict[str, Any]
   
   # NEW
   historical: HistoricalData
   ├─ bars: {...}
   └─ indicators: {...}
   ```

4. **Metrics vs Indicators Distinction**
   - **Metrics:** Always present (volume, high, low)
   - **Indicators:** Optional computed values (RSI, VWAP)

### ⚠️ Keep `base_interval` Field

**Reason:** Performance & clarity

**Without it:**
```python
# Must iterate all intervals to find base
base = None
for interval, data in symbol_data.bars.items():
    if not data.derived:
        base = interval
        break
```

**With it:**
```python
# Direct access
base = symbol_data.base_interval
```

**Use cases:**
- Coordinator loading queues (needs to know which interval to load)
- Processor determining when to compute derived (check if bar is base)
- Display code showing primary interval

**Cost:** One string field (4-8 bytes)  
**Benefit:** O(1) access vs O(n) iteration

**VERDICT:** Keep it (micro-optimization, but free)

### ⚠️ Handle Empty Data vs Not Loaded

**Problem:** How to distinguish:
1. Symbol added but not loaded yet
2. Symbol loaded but has no data (rare)

**Solution 1:** Presence of keys
```python
# Not loaded
symbol_data.bars = {}

# Loaded (even if no data)
symbol_data.bars = {"1m": BarIntervalData(derived=False, data=[])}
```

**Solution 2:** Explicit initialization
```python
def is_initialized(self) -> bool:
    """Check if symbol has been initialized."""
    return len(self.bars) > 0

def is_loaded(self) -> bool:
    """Check if symbol has data."""
    return any(len(interval.data) > 0 for interval in self.bars.values())
```

**VERDICT:** Solution 1 is cleaner (structure presence = loaded)

---

## JSON Export Structure (Refined)

```json
{
  "symbols": {
    "AAPL": {
      "bars": {                              ← Bars section
        "1m": {
          "derived": false,                  ← Self-describing!
          "base": null,
          "count": 112,
          "quality": 98.5,
          "gaps": {
            "gap_count": 2,
            "missing_bars": 6,
            "ranges": [...]
          },
          "data": [[...], [...]]
        },
        "5m": {
          "derived": true,                   ← Self-describing!
          "base": "1m",
          "count": 23,
          "quality": 98.5,
          "gaps": {...},
          "data": [[...], [...]]
        }
      },
      
      "quotes": {                            ← Quotes section
        "count": 450,
        "data": [[...], [...]]
      },
      
      "ticks": {                             ← Ticks section
        "count": 1200,
        "data": [[...], [...]]
      },
      
      "metrics": {                           ← Session metrics
        "volume": 19106,
        "high": 13.54,
        "low": 13.47,
        "last_update": "11:52:00"
      },
      
      "indicators": {                        ← Session indicators
        "rsi_14": 65.5,
        "vwap": 150.25,
        "session_momentum": 0.85
      },
      
      "historical": {                        ← Historical section
        "bars": {
          "1m": {
            "count": 1656,
            "quality": 93.4,
            "gaps": {...},
            "date_range": {...},
            "dates": [...],
            "data": [[...], [...]]
          }
        },
        "indicators": {                      ← Historical indicators
          "avg_volume_2d": 24525389.0,
          "max_price_5d": 150.25
        }
      }
    }
  }
}
```

**Benefits:**
- ✅ Clean grouping by data type
- ✅ Each bar interval self-describes if derived
- ✅ Clear distinction between metrics and indicators
- ✅ Historical structure mirrors session structure

---

## Migration Impact

### What Changes

**SymbolSessionData:**
```python
# REMOVE
derived_intervals: List[str]              # ❌ Remove (in BarIntervalData now)
is_loaded: bool                           # ❌ Remove (infer from structure)
bars_base: Deque[BarData]                 # ❌ Remove (in bars dict)
bars_derived: Dict[str, List[BarData]]    # ❌ Remove (in bars dict)
bar_quality: Dict[str, float]             # ❌ Remove (in BarIntervalData)
bar_gaps: Dict[str, List[GapInfo]]        # ❌ Remove (in BarIntervalData)
session_volume: int                       # ❌ Remove (in metrics)
session_high: float                       # ❌ Remove (in metrics)
session_low: float                        # ❌ Remove (in metrics)
bars_updated: bool                        # ❌ Remove (in BarIntervalData)
historical_bars: Dict[...]                # ❌ Remove (in historical)
historical_indicators: Dict[...]          # ❌ Remove (in historical)

# ADD
bars: Dict[str, BarIntervalData]          # ✅ Add
metrics: SessionMetrics                   # ✅ Add
indicators: Dict[str, Any]                # ✅ Add
historical: HistoricalData                # ✅ Add

# KEEP
symbol: str                               # ✅ Keep
base_interval: str                        # ✅ Keep (performance)
quotes: List[QuoteData]                   # ✅ Keep (but regroup)
ticks: List[TickData]                     # ✅ Keep (but regroup)
_latest_bar: Optional[BarData]            # ✅ Keep (cache)
```

### Access Pattern Changes

**OLD:**
```python
# Check if derived
if interval in symbol_data.derived_intervals:
    ...

# Get quality
quality = symbol_data.bar_quality.get(interval)

# Get gaps
gaps = symbol_data.bar_gaps.get(interval, [])

# Get bars
if interval == symbol_data.base_interval:
    bars = symbol_data.bars_base
else:
    bars = symbol_data.bars_derived.get(interval, [])
```

**NEW:**
```python
# Everything in one place
interval_data = symbol_data.bars.get(interval)
if not interval_data:
    return

# Check if derived
if interval_data.derived:
    base = interval_data.base

# Get quality
quality = interval_data.quality

# Get gaps
gaps = interval_data.gaps

# Get bars
bars = interval_data.data
```

**Benefit:** Single dict lookup instead of multiple checks!

---

## Final Verdict

### User's Suggestions: 95% Excellent! 🎉

| Suggestion | Verdict | Reason |
|------------|---------|--------|
| Self-describing intervals | ✅ Adopt | Cleaner, more maintainable |
| Remove `derived_intervals` list | ✅ Adopt | Redundant with structure |
| Remove `is_loaded` flag | ✅ Adopt | Infer from structure presence |
| Keep `base_interval` | ⚠️ Keep | Performance/clarity (minor field) |
| Rename `historical_indicators` | ✅ Adopt | Natural nesting |
| Split metrics/indicators | ✅ Adopt | Clear distinction |
| Top-level grouping | ✅ Adopt | Clean organization |

### Recommended Structure

```python
SymbolSessionData:
    symbol: str                           # Identity
    base_interval: str                    # Performance helper
    
    bars: Dict[str, BarIntervalData]      # Self-describing!
    quotes: List[QuoteData]
    ticks: List[TickData]
    
    metrics: SessionMetrics               # OHLCV aggregations
    indicators: Dict[str, Any]            # Computed analytics
    
    historical: HistoricalData
        bars: Dict[str, HistoricalBarIntervalData]
        indicators: Dict[str, Any]
```

**This is cleaner, more maintainable, and more self-describing than the original plan!**

Should we proceed with this refined structure?
