# SessionData Structure Analysis: Python Objects vs JSON Export

**Date:** December 4, 2025  
**Analysis:** Object structure mapping and gap analysis information

---

## 1. Python Object Structure (SymbolSessionData)

### Core Data Structure
```python
@dataclass
class SymbolSessionData:
    # === IDENTITY ===
    symbol: str
    base_interval: str = "1m"  # "1s" or "1m"
    
    # === SESSION BARS (Current Trading Day) ===
    bars_base: Deque[BarData]              # Base interval bars (1s or 1m)
    bars_derived: Dict[str, List[BarData]] # {"5m": [...], "15m": [...]}
    _latest_bar: Optional[BarData]         # Cached latest bar
    
    # === QUALITY METRICS ===
    bar_quality: Dict[str, float]          # {"1m": 98.5, "5m": 98.5, "1d": 100.0}
    
    # === OTHER DATA TYPES ===
    quotes: List[QuoteData]
    ticks: List[TickData]
    
    # === SESSION METRICS ===
    session_volume: int
    session_high: Optional[float]
    session_low: Optional[float]
    last_update: Optional[datetime]
    
    # === UPDATE FLAGS ===
    bars_updated: bool
    quotes_updated: bool
    ticks_updated: bool
    
    # === HISTORICAL DATA (Trailing Days) ===
    historical_bars: Dict[str, Dict[date, List[BarData]]]
    # Structure: {interval: {date: [bars]}}
    # Example: {"1m": {date("2025-07-01"): [bar1, bar2...], 
    #                   date("2025-07-02"): [bar1, bar2...]}}
    
    historical_indicators: Dict[str, Any]  # {"avg_volume_2d": 12345678.9}
    
    # === DELTA EXPORT TRACKING ===
    _last_export_indices: Dict[str, Any]   # Internal tracking
```

---

## 2. JSON Export Structure

### Complete Export Hierarchy
```json
{
  "symbols": {
    "AAPL": {
      "session": {
        "volume": 19106,
        "high": 13.54,
        "low": 13.47,
        "data": {
          "1m": {
            "count": 112,
            "total_count": 112,
            "generated": false,
            "quality": 98.5,              // ← NOW HERE!
            "columns": [...],
            "data": [[...], [...]]
          },
          "5m": {
            "count": 23,
            "total_count": 23,
            "generated": true,
            "quality": 98.5,              // ← NOW HERE!
            "columns": [...],
            "data": [[...], [...]]
          }
        }
      },
      "historical": {
        "loaded": true,
        "data": {
          "1m": {
            "count": 1656,
            "date_range": {...},
            "dates": [...],
            "quality": 93.4,              // ← NOW HERE!
            "columns": [...],
            "data": [[...], [...]]
          },
          "1d": {
            "count": 2,
            "date_range": {...},
            "dates": [...],
            "quality": 100.0,             // ← NOW HERE!
            "columns": [...],
            "data": [[...], [...]]
          }
        },
        "avg_volume_2d": 24525389.0       // ← Historical indicators at this level
      }
    }
  }
}
```

---

## 3. Detailed Mapping: Python → JSON

### 3.1 Session Metrics (Top-Level)
| Python Object | JSON Path | Notes |
|---------------|-----------|-------|
| `session_volume` | `session.volume` | Direct mapping |
| `session_high` | `session.high` | Direct mapping |
| `session_low` | `session.low` | Direct mapping |
| `last_update` | Not exported | Internal state only |
| `bars_updated` | Not exported (visible in CSV) | Flag for internal use |

### 3.2 Base Bars (Current Session)
| Python Object | JSON Path | Notes |
|---------------|-----------|-------|
| `bars_base` (Deque) | `session.data[base_interval]` | Dynamic key: "1m" or "1s" |
| - | `session.data["1m"].count` | Length of new bars |
| - | `session.data["1m"].total_count` | Total bars in session |
| - | `session.data["1m"].generated` | Always `false` (streamed) |
| - | `session.data["1m"].quality` | **NEW**: From `bar_quality["1m"]` |
| - | `session.data["1m"].data` | Array of bar arrays |

### 3.3 Derived Bars (Current Session)
| Python Object | JSON Path | Notes |
|---------------|-----------|-------|
| `bars_derived["5m"]` | `session.data["5m"]` | One key per derived interval |
| - | `session.data["5m"].count` | Length of new bars |
| - | `session.data["5m"].total_count` | Total bars in session |
| - | `session.data["5m"].generated` | Always `true` (computed) |
| - | `session.data["5m"].quality` | **NEW**: From `bar_quality["5m"]` |
| - | `session.data["5m"].data` | Array of bar arrays |

### 3.4 Quality Metrics
| Python Object | JSON Path | Structure Change |
|---------------|-----------|------------------|
| `bar_quality` (Dict) | Multiple locations | **RESTRUCTURED** |
| `bar_quality["1m"]` | `session.data["1m"].quality` | ✅ Nested under each interval |
| `bar_quality["5m"]` | `session.data["5m"].quality` | ✅ Nested under each interval |
| `bar_quality["1d"]` | `historical.data["1d"].quality` | ✅ Nested under each interval |

**OLD Structure (REMOVED):**
```json
{
  "session": {
    "quality": {           // ❌ OLD: Top-level dict
      "1m": 98.5,
      "5m": 98.5
    }
  }
}
```

**NEW Structure (CURRENT):**
```json
{
  "session": {
    "data": {
      "1m": {
        "quality": 98.5    // ✅ NEW: Nested in each interval
      }
    }
  }
}
```

### 3.5 Historical Data (Trailing Days)
| Python Object | JSON Path | Notes |
|---------------|-----------|-------|
| `historical_bars["1m"]` | `historical.data["1m"]` | Multi-day aggregation |
| `historical_bars["1m"][date1]` | Aggregated into `historical.data["1m"].data` | Dates merged |
| - | `historical.data["1m"].count` | Total bars across all dates |
| - | `historical.data["1m"].date_range` | Start/end dates |
| - | `historical.data["1m"].dates` | List of all dates |
| - | `historical.data["1m"].quality` | **NEW**: From `bar_quality["1m"]` |
| `historical_indicators` | `historical.*` (top-level keys) | Flattened at historical level |

### 3.6 Other Data Types
| Python Object | JSON Path | Notes |
|---------------|-----------|-------|
| `ticks` (List) | `session.data.ticks` | Only if ticks exist |
| `quotes` (List) | `session.data.quotes` | Only if quotes exist |

---

## 4. Gap Analysis Information

### 4.1 What Data Quality Manager Computes

The `DataQualityManager` thread detects gaps using the `detect_gaps()` function:

```python
@dataclass
class GapInfo:
    """Information about a gap in bar data."""
    symbol: str
    start_time: datetime      # First missing timestamp
    end_time: datetime        # Last missing timestamp
    bar_count: int            # Number of missing bars
    retry_count: int = 0      # Fill attempts (live mode)
    last_retry: datetime      # Last retry timestamp
```

**Gap Detection Process:**
1. Generate expected timestamps (session_start to current_time)
2. Get actual bar timestamps from SessionData
3. Find missing timestamps (expected - actual)
4. Group consecutive missing timestamps into gap ranges
5. Calculate quality = (actual_bars / expected_bars) × 100

### 4.2 Current Gap Information Storage

**❌ PROBLEM: Gap details are NOT stored anywhere!**

| Gap Information | Where Computed | Where Stored | Exported to JSON? |
|-----------------|----------------|--------------|-------------------|
| Gap ranges | `detect_gaps()` | Nowhere | ❌ No |
| Gap bar count | `GapInfo.bar_count` | Nowhere | ❌ No |
| Gap timestamps | `GapInfo.start_time/end_time` | Nowhere | ❌ No |
| Gap retry count | `GapInfo.retry_count` | In memory (`_failed_gaps`) | ❌ No |
| **Quality percentage** | `calculate_quality()` | **✅ `bar_quality` dict** | **✅ Yes** |

**Current Flow:**
```
detect_gaps() → GapInfo objects created
                ↓
        Used for logging only
                ↓
        Discarded (not stored)
                ↓
Only quality percentage saved: bar_quality["1m"] = 98.5
```

### 4.3 Gap Information Per Interval

Gap analysis is **interval-specific**:

```python
# data_quality_manager.py line 386
gaps = detect_gaps(
    symbol=symbol,
    session_start=session_start_time,
    current_time=effective_end,
    bars=bars,                    # Bars for this specific interval
    interval_minutes=interval_minutes
)
```

**Each interval gets separate gap analysis:**
- `1m` bars → gaps detected → quality calculated
- `5m` bars → gaps detected → quality calculated
- `1d` bars → gaps detected → quality calculated

But only quality percentage is saved, not gap details!

---

## 5. Proposed Enhancement: Store Gap Details

### 5.1 Add Gap Storage to SymbolSessionData

```python
@dataclass
class SymbolSessionData:
    # ... existing fields ...
    
    # NEW: Gap information per interval
    bar_gaps: Dict[str, List[GapInfo]] = field(default_factory=dict)
    # Structure: {interval: [gap1, gap2, ...]}
    # Example: {"1m": [GapInfo(...), GapInfo(...)], "5m": [...]}
```

### 5.2 Update JSON Export Structure

**Proposed structure:**
```json
{
  "session": {
    "data": {
      "1m": {
        "count": 112,
        "quality": 98.5,
        "gaps": {                          // ← NEW SECTION
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
        "data": [[...], [...]]
      }
    }
  }
}
```

### 5.3 Implementation Requirements

**1. Modify DataQualityManager:**
```python
def _calculate_quality(self, symbol: str, interval: str):
    # ... existing gap detection ...
    gaps = detect_gaps(...)
    
    # NEW: Store gaps in SessionData
    self.session_data.set_gaps(symbol, interval, gaps)
    
    # Existing: Store quality
    self.session_data.set_quality(symbol, interval, quality)
```

**2. Add methods to SessionData:**
```python
def set_gaps(self, symbol: str, interval: str, gaps: List[GapInfo]):
    """Store gap information for a symbol's interval."""
    symbol_data = self.get_symbol_data(symbol)
    if symbol_data:
        symbol_data.bar_gaps[interval] = gaps

def get_gaps(self, symbol: str, interval: str) -> List[GapInfo]:
    """Get gap information for a symbol's interval."""
    symbol_data = self.get_symbol_data(symbol)
    if symbol_data and interval in symbol_data.bar_gaps:
        return symbol_data.bar_gaps[interval]
    return []
```

**3. Update JSON export in session_data.py:**
```python
# In to_json() method
if interval in self.bar_gaps and self.bar_gaps[interval]:
    gaps = self.bar_gaps[interval]
    base_data["gaps"] = {
        "gap_count": len(gaps),
        "missing_bars": sum(g.bar_count for g in gaps),
        "ranges": [
            {
                "start_time": g.start_time.time().isoformat(),
                "end_time": g.end_time.time().isoformat(),
                "bar_count": g.bar_count
            }
            for g in gaps
        ]
    }
```

---

## 6. Benefits of Storing Gap Details

### 6.1 Debugging & Diagnostics
- See exactly when gaps occurred during the session
- Identify patterns (e.g., gaps at market open, lunch hour)
- Correlate gaps with system events

### 6.2 Gap Analysis Per Interval
- Different intervals may have different gap patterns
- 1m bars: 6 gaps (98.5% quality)
- 5m bars: 1 gap (99.8% quality)
- 1d bars: 0 gaps (100% quality)

### 6.3 Quality Audit Trail
- Quality percentage alone doesn't tell full story
- `98.5%` could be:
  - One 6-bar gap, OR
  - Six 1-bar gaps (different implications)

### 6.4 Live Mode Gap Filling
- Track retry attempts per gap
- Monitor which gaps were successfully filled
- Historical record of data quality issues

---

## 7. Key Architectural Insights

### 7.1 Nesting Structure Comparison

| Concept | Python | JSON | Nesting Difference |
|---------|--------|------|-------------------|
| Symbol data | `_symbols[symbol]` | `symbols.AAPL` | Same level |
| Session metrics | Flat attributes | `session.*` | JSON groups under "session" |
| Base bars | `bars_base` deque | `session.data["1m"]` | JSON nests under "data" |
| Derived bars | `bars_derived` dict | `session.data["5m"]` | Same: flat dict of intervals |
| Quality | `bar_quality` dict | **Multiple locations** | **JSON nests per interval** |
| Historical | `historical_bars` nested dict | `historical.data` | JSON flattens date dimension |
| Indicators | `historical_indicators` dict | `historical.*` | JSON flattens to top level |

### 7.2 Data Transformation During Export

**Python (In-Memory):**
- Optimized for performance (deque, caching)
- Per-date storage: `historical_bars["1m"][date1]`, `[date2]`
- Quality as flat dict: `bar_quality["1m"]`

**JSON (Export):**
- Optimized for human readability
- Multi-date aggregation: All dates merged into single array
- Quality nested: Each interval has its own quality field

### 7.3 What's NOT Exported

| Python Field | Reason Not Exported |
|--------------|-------------------|
| `_latest_bar` | Cache only (performance) |
| `bars_updated` / `quotes_updated` | Internal flags (but in CSV for validation) |
| `_last_export_indices` | Delta tracking (internal) |
| `last_update` | Redundant (can derive from latest bar) |
| **Gap details** | **Currently not stored at all!** |

---

## 8. Summary

### Current State
✅ **Quality percentage** is computed per interval and stored  
✅ **Quality percentage** is now nested under each interval in JSON (recent change)  
❌ **Gap details** are computed but immediately discarded  
❌ **Gap ranges/timestamps** are not available in JSON export  

### Recommendation
**Add gap detail storage** to provide complete data quality diagnostics:
1. Store `List[GapInfo]` per interval in `SymbolSessionData.bar_gaps`
2. Export gap details nested under each interval in JSON
3. Include gap ranges, timestamps, and bar counts
4. Enables full audit trail of data quality issues

This would make gap analysis information available at the same level as quality percentage: **nested under each bar interval** where it logically belongs.
