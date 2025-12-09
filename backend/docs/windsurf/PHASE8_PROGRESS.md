# Phase 8 Progress: CLI Display Updates

**Date:** December 4, 2025  
**Status:** IN PROGRESS - System JSON integration started, needs complete symbol display revamp

---

## Goal

Completely revamp the `data session` command to:
1. Call `system_manager.to_json()` for system status (single source of truth)
2. Display based on the JSON structure (new bar structure with metadata)
3. Support compact and full display modes
4. Show quality, gaps, and derived intervals with metadata

---

## Progress So Far

### ✅ Completed

1. **Updated imports** - Removed unused imports, streamlined
2. **Added system JSON call** - Now calls `system_manager.to_json(complete=True)`
3. **Extracted JSON data** - Parses system_info, session_data, time_manager from JSON
4. **Updated time handling** - Gets current time from JSON instead of direct query

### 🔄 In Progress

1. **Symbol display section** - Needs complete rewrite to show new structure
2. **Interval display** - Should show each interval with its metadata (derived, base, quality, gaps)
3. **Compact vs Full modes** - Need to implement properly for new structure

### ⏳ TODO

1. **Symbol Section Rewrite**
   - Iterate through `symbols_data` from JSON
   - For each symbol, show `bars` dictionary with all intervals
   - Display interval metadata: `derived`, `base`, `quality`, `gaps`, `updated`
   - Show bar counts per interval
   - Calculate and display quality per interval

2. **Compact Mode Design**
   ```
   SYSTEM    | State: RUNNING | Mode: BACKTEST
   SESSION   | 2024-01-15 | 09:45:23 | ✓ Active | Symbols: 2
   
   ━━ SYMBOLS ━━
   AAPL      | Vol: 1.2M | High: $185.50 | Low: $182.30
             | 1m: 150 bars (09:30-09:45) | Quality: 98.5% | ✓ Base
             | 5m: 30 bars | Quality: 98.5% | Derived from 1m
   
   RIVN      | Vol: 850K | High: $22.15 | Low: $21.80
             | 1m: 150 bars (09:30-09:45) | Quality: 100% | ✓ Base
             | 5m: 30 bars | Quality: 100% | Derived from 1m
   ```

3. **Full Mode Design**
   ```
   ┌─ SYMBOLS
   │
   │  ┌─ AAPL
   │  │
   │  │  Metrics
   │  │  ├─ Volume: 1,200,000
   │  │  ├─ High: $185.50
   │  │  └─ Low: $182.30
   │  │
   │  │  Bars
   │  │  ├─ 1m (Base)
   │  │  │  ├─ Count: 150 bars
   │  │  │  ├─ Quality: 98.5%
   │  │  │  ├─ Time Range: 09:30:00 - 09:45:00
   │  │  │  ├─ Gaps: None
   │  │  │  └─ Updated: Yes
   │  │  │
   │  │  └─ 5m (Derived from 1m)
   │  │     ├─ Count: 30 bars
   │  │     ├─ Quality: 98.5% (from base)
   │  │     ├─ Time Range: 09:30:00 - 09:45:00
   │  │     └─ Updated: Yes
   │  │
   │  └─
   ```

4. **Gap Display**
   - When gaps exist, show them with details
   - Format: "3 gaps (12 missing bars)"
   - Optionally show gap ranges in full mode

5. **Updated Flag**
   - Show checkmark/indicator when `updated = True`
   - Helps identify which intervals have new data

---

## Current Implementation Status

### Modified Files

- `/app/cli/session_data_display.py` (partially updated)
  - Lines 1-79: Header and initialization updated
  - Lines 80+: Old symbol display code still present (needs replacement)

### Key Changes Made

**Before:**
```python
from app.managers.data_manager.session_data import get_session_data
session_data = get_session_data()
symbol_data = session_data.get_symbol_data(symbol)
bars = symbol_data.bars_1m
quality = symbol_data.bar_quality.get(interval)
```

**After (Target):**
```python
status = system_mgr.to_json(complete=True)
symbols_data = status["session_data"]["symbols"]
symbol_info = symbols_data[symbol]
bars_info = symbol_info["bars"]  # Dict of intervals
for interval_key, interval_data in bars_info.items():
    count = interval_data["bar_count"]
    quality = interval_data["quality"]
    is_derived = interval_data["derived"]
    base = interval_data["base"]
    gaps = interval_data.get("gaps", {})
```

---

## JSON Structure from `system_manager.to_json()`

```json
{
  "system_info": {
    "state": "running",
    "mode": "backtest",
    ...
  },
  "session_data": {
    "current_session_date": "2024-01-15",
    "session_active": true,
    "symbols": {
      "AAPL": {
        "symbol": "AAPL",
        "base_interval": "1m",
        "bars": {
          "1m": {
            "derived": false,
            "base": null,
            "bar_count": 150,
            "quality": 98.5,
            "gaps": {
              "gap_count": 0,
              "missing_bars": 0,
              "ranges": []
            },
            "updated": true,
            "first_bar_time": "09:30:00",
            "last_bar_time": "09:45:00"
          },
          "5m": {
            "derived": true,
            "base": "1m",
            "bar_count": 30,
            "quality": 98.5,
            "gaps": {...},
            "updated": true,
            "first_bar_time": "09:30:00",
            "last_bar_time": "09:45:00"
          }
        },
        "metrics": {
          "volume": 1200000,
          "high": 185.50,
          "low": 182.30,
          "last_update": "2024-01-15T09:45:00"
        },
        ...
      }
    }
  },
  "time_manager": {
    "current_time": "2024-01-15T09:45:23",
    "mode": "backtest",
    ...
  }
}
```

---

## Implementation Plan

### Step 1: Symbol Display Loop (Compact)
```python
symbols_data = session_data_info.get("symbols", {})

if compact:
    main_table.add_row("", "")
    main_table.add_row("[bold green]━━ SYMBOLS ━━[/bold green]", "")
    
    for symbol, symbol_info in symbols_data.items():
        # Symbol header with metrics
        metrics = symbol_info.get("metrics", {})
        volume = metrics.get("volume", 0)
        high = metrics.get("high")
        low = metrics.get("low")
        
        metrics_str = f"Vol: {volume:,.0f}"
        if high and low:
            metrics_str += f" | High: ${high:.2f} | Low: ${low:.2f}"
        
        main_table.add_row(f"[bold cyan]{symbol}[/bold cyan]", metrics_str)
        
        # Bar intervals
        bars_info = symbol_info.get("bars", {})
        base_interval = symbol_info.get("base_interval", "1m")
        
        for interval_key in sorted(bars_info.keys(), 
                                    key=lambda x: int(x[:-1]) if x.endswith('m') else 999):
            interval_data = bars_info[interval_key]
            
            # Build interval line
            count = interval_data.get("bar_count", 0)
            quality = interval_data.get("quality", 0.0)
            is_derived = interval_data.get("derived", False)
            base = interval_data.get("base")
            
            # Quality color
            quality_color = "green" if quality >= 95 else "yellow" if quality >= 80 else "red"
            
            # Build display string
            parts = [
                f"{count} bars",
                f"Quality: [{quality_color}]{quality:.1f}%[/{quality_color}]"
            ]
            
            if is_derived:
                parts.append(f"Derived from {base}")
            else:
                parts.append("✓ Base")
            
            interval_str = " | ".join(parts)
            main_table.add_row(f"  {interval_key}", interval_str)
        
        main_table.add_row("", "")  # Spacing
```

### Step 2: Symbol Display Loop (Full)
```python
else:  # Full mode
    main_table.add_row("", "")
    main_table.add_row("[bold green]┌─ SYMBOLS[/bold green]", "")
    main_table.add_row("│", "")
    
    for symbol, symbol_info in symbols_data.items():
        main_table.add_row(f"│  [bold]┌─ {symbol}[/bold]", "")
        
        # Metrics
        metrics = symbol_info.get("metrics", {})
        main_table.add_row(f"│  │  Metrics", "")
        main_table.add_row(f"│  │  ├─ Volume", f"{metrics.get('volume', 0):,.0f}")
        if metrics.get("high"):
            main_table.add_row(f"│  │  ├─ High", f"${metrics['high']:.2f}")
        if metrics.get("low"):
            main_table.add_row(f"│  │  └─ Low", f"${metrics['low']:.2f}")
        
        # Bars
        main_table.add_row(f"│  │", "")
        main_table.add_row(f"│  │  Bars", "")
        
        bars_info = symbol_info.get("bars", {})
        intervals = sorted(bars_info.keys(), 
                          key=lambda x: int(x[:-1]) if x.endswith('m') else 999)
        
        for idx, interval_key in enumerate(intervals):
            interval_data = bars_info[interval_key]
            is_last = (idx == len(intervals) - 1)
            prefix = "└─" if is_last else "├─"
            
            # Interval header
            is_derived = interval_data.get("derived", False)
            base = interval_data.get("base")
            
            if is_derived:
                header = f"{interval_key} (Derived from {base})"
            else:
                header = f"{interval_key} (Base)"
            
            main_table.add_row(f"│  │  {prefix} {header}", "")
            
            # Interval details
            sub_prefix = "  │" if not is_last else "   "
            count = interval_data.get("bar_count", 0)
            quality = interval_data.get("quality", 0.0)
            
            quality_color = "green" if quality >= 95 else "yellow" if quality >= 80 else "red"
            
            main_table.add_row(f"│  │  {sub_prefix}  ├─ Count", f"{count} bars")
            main_table.add_row(f"│  │  {sub_prefix}  ├─ Quality", 
                              f"[{quality_color}]{quality:.1f}%[/{quality_color}]")
            
            # Time range
            first_time = interval_data.get("first_bar_time")
            last_time = interval_data.get("last_bar_time")
            if first_time and last_time:
                main_table.add_row(f"│  │  {sub_prefix}  ├─ Time Range", 
                                  f"{first_time} - {last_time}")
            
            # Gaps
            gaps_info = interval_data.get("gaps", {})
            gap_count = gaps_info.get("gap_count", 0)
            if gap_count > 0:
                missing = gaps_info.get("missing_bars", 0)
                main_table.add_row(f"│  │  {sub_prefix}  ├─ Gaps", 
                                  f"[yellow]{gap_count} gaps ({missing} missing bars)[/yellow]")
            else:
                main_table.add_row(f"│  │  {sub_prefix}  ├─ Gaps", "[green]None[/green]")
            
            # Updated flag
            updated = interval_data.get("updated", False)
            status = "[green]✓ Yes[/green]" if updated else "[dim]No[/dim]"
            main_table.add_row(f"│  │  {sub_prefix}  └─ Updated", status)
        
        main_table.add_row(f"│  │", "")
        main_table.add_row(f"│  └─", "")
```

---

## Benefits of New Approach

### Single Source of Truth ✅
- All data comes from `system_manager.to_json()`
- No direct queries to session_data or other components
- Consistent snapshot of system state

### Shows New Structure ✅
- Displays `bars` dictionary with all intervals
- Shows metadata: `derived`, `base`, `quality`, `gaps`, `updated`
- Hierarchical display matches data structure

### Self-Documenting ✅
- Display shows which intervals are derived
- Shows source interval for derived bars
- Quality and gaps visible per interval

### Flexible ✅
- Works with any base interval (1s, 1m, etc.)
- Works with any derived intervals (5m, 15m, 30m, etc.)
- Adapts to symbol configuration

---

## Next Steps

1. **Complete symbol display implementation**
   - Replace old bar access code (lines 80-700)
   - Implement compact and full mode symbol display
   - Add gap display logic

2. **Test with real data**
   - Run backtest with 2 symbols
   - Verify all intervals display correctly
   - Check quality and gap display

3. **Polish**
   - Adjust formatting and colors
   - Optimize for readability
   - Add helpful indicators

4. **Update CSV export**
   - Ensure CSV export also uses new structure
   - Export quality and gaps per interval

---

## Estimated Completion

**Time Remaining:** 1-2 hours
- 30 min: Symbol display implementation
- 30 min: Testing and refinement
- 30 min: Documentation

**Status:** 50% complete (foundation laid, needs symbol display)

---

## Files Modified

- `/app/cli/session_data_display.py` (partial, needs completion)
  - Function: `generate_session_display()`
  - Lines updated: 1-79 (imports, initialization, JSON extraction)
  - Lines remaining: 80-700 (symbol display, needs rewrite)

---

**Next Session:** Complete symbol display implementation with new structure
