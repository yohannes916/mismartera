# Data Session Display Redesign Plan

## Overview
Redesign the `data session` command to display comprehensive system information based on `system_manager.system_info()` API output.

**Goal**: Show all relevant information EXCEPT raw data arrays (bar data, tick data, etc.)

---

## Command Variations

```bash
data session           # Compact view, auto-refresh 1s
data session 5         # Compact view, auto-refresh 5s
data session 0         # Compact view, display once
data session --full    # Detailed view, auto-refresh 1s
data session 5 --full  # Detailed view, auto-refresh 5s
```

---

## Data Source Structure (from system_info())

```json
{
  "system_manager": {
    "_state": "running",
    "_mode": "backtest",
    "timezone": "America/New_York",
    "exchange_group": "US_EQUITY",
    "asset_class": "EQUITY",
    "backtest_window": {"start_date": "...", "end_date": "..."}
  },
  "performance_metrics": {
    "total_time": null,
    "trading_days": 0,
    "bars_processed": 0,
    "iterations": 0,
    ...
  },
  "time_manager": {
    "current_session": {
      "date": "2025-07-02",
      "time": "09:47:00",
      "regular_open": "09:30:00",
      "regular_close": "16:00:00",
      "is_trading_day": true,
      "is_holiday": false,
      "is_early_close": false
    }
  },
  "threads": {
    "data_processor": {"thread_info": {...}, "_running": true},
    "data_quality_manager": {...},
    "analysis_engine": {...}
  },
  "session_data": {
    "_session_active": true,
    "_active_symbols": ["RIVN"],
    "symbols": {
      "RIVN": {
        "bars": {
          "1m": {
            "derived": false,
            "quality": 50.0,
            "count": 3,
            "gaps": {...}
          }
        },
        "metrics": {"volume": 1280.0, "high": 13.49, "low": 13.47},
        "historical": {
          "loaded": true,
          "bars": {
            "1m": {
              "count": 1656,
              "quality": 0.0,
              "date_range": {"start_date": "...", "end_date": "...", "days": 3}
            }
          }
        }
      }
    }
  },
  "session_config": {
    "session_name": "Example Trading Session",
    "exchange_group": "US_EQUITY",
    "mode": "backtest",
    "session_data_config": {
      "symbols": ["RIVN"],
      "streams": ["1m", "5m"],
      "historical": {
        "data": [{...}]
      }
    }
  }
}
```

---

## COMPACT VIEW Design

### Layout: Horizontal 2-column with grouped sections

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ SESSION DATA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                                                                                             ┃
┃ ┌─ SYSTEM ───────────────────────────────────────────────────────────────────────────────┐ ┃
┃ │ State: RUNNING | Mode: BACKTEST | Exchange: US_EQUITY/EQUITY | TZ: America/New_York   │ ┃
┃ └────────────────────────────────────────────────────────────────────────────────────────┘ ┃
┃                                                                                             ┃
┃ ┌─ SESSION ──────────────────────────────────────────────────────────────────────────────┐ ┃
┃ │ Date: 2025-07-02 | Time: 09:47:00 | Active: ✓ | Trading Day: ✓ | Holiday: ✗           │ ┃
┃ │ Hours: 09:30 - 16:00 | Early Close: ✗ | Symbols: 1                                    │ ┃
┃ └────────────────────────────────────────────────────────────────────────────────────────┘ ┃
┃                                                                                             ┃
┃ ┌─ BACKTEST ─────────────────────────────────────────────────────────────────────────────┐ ┃
┃ │ Window: 2025-07-02 → 2025-07-03 (2 days) | Speed: 60x | Progress: Day 1/2             │ ┃
┃ └────────────────────────────────────────────────────────────────────────────────────────┘ ┃
┃                                                                                             ┃
┃ ┌─ PERFORMANCE ──────────────────────────────────────────────────────────────────────────┐ ┃
┃ │ Bars: 0 | Iterations: 0 | Trading Days: 0 | Backpressure: Coord→Proc: 0 | Proc→Anal: 0│ ┃
┃ └────────────────────────────────────────────────────────────────────────────────────────┘ ┃
┃                                                                                             ┃
┃ ┌─ THREADS ──────────────────────────────────────────────────────────────────────────────┐ ┃
┃ │ DataProcessor: ✓ RUNNING | DataQualityMgr: ✓ RUNNING | AnalysisEngine: ✓ RUNNING      │ ┃
┃ └────────────────────────────────────────────────────────────────────────────────────────┘ ┃
┃                                                                                             ┃
┃ ━━━ SYMBOLS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ┃
┃                                                                                             ┃
┃ ┌─ RIVN ─────────────────────────────────────────────────────────────────────────────────┐ ┃
┃ │ Session  │ Vol: 1,280 | High: $13.49 | Low: $13.47 | Last: 09:36:00                   │ ┃
┃ │ Bars     │ 1m: 3 bars (Q: 50.0%, 1 gap, 4 missing) | 5m: 0 bars                        │ ┃
┃ │ Historical│ Loaded: ✓ | 1m: 1,656 bars (3 days: Jun 27-Jul 01) | 1d: N/A               │ ┃
┃ └────────────────────────────────────────────────────────────────────────────────────────┘ ┃
┃                                                                                             ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

### Compact View Sections

#### 1. **SYSTEM** (1 line)
- State: RUNNING/PAUSED/STOPPED (color coded)
- Mode: BACKTEST/LIVE
- Exchange: US_EQUITY/EQUITY
- Timezone: America/New_York

#### 2. **SESSION** (2 lines)
- **Line 1**: Date | Time | Active status | Trading day | Holiday status
- **Line 2**: Market hours | Early close | Symbol count

#### 3. **BACKTEST** (1 line, only if mode=backtest)
- Window dates
- Total days
- Speed multiplier
- Progress (current day / total days)

#### 4. **PERFORMANCE** (1 line)
- Bars processed
- Iterations
- Trading days
- Backpressure metrics (compact: just counts)

#### 5. **THREADS** (1 line)
- Each thread: Name + Status (✓ RUNNING / ✗ STOPPED)

#### 6. **SYMBOLS** (expandable section)
For each symbol:
- **Metrics** (1 line): Volume, high, low, last update time
- **Session** (header + N lines): Each data type (bars/ticks/quotes) on separate line
  - Each line shows: count, quality, time window (start-end), gaps
  - Example: `1m │ 45 bars | Q: 100% | 09:30-10:15`
  - Example: `5m │ 9 bars | Q: 97.8% | 09:30-10:15 | 1 gap (1 missing)`
  - Example: `Quotes│ 150 items | 09:30-10:15`
- **Historical** (header + N lines): Each interval on separate line
  - Each line shows: count, date range, trading days
  - Example: `1m │ 1,170 bars | Jun 29-Jul 01 (3 days)`
  - Example: `1d │ 252 bars | Jul 02, 2024 - Jul 01, 2025 (1 year)`

---

## DETAILED VIEW Design

### Layout: Tree structure with full details

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ SESSION DATA (DETAILED) ━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                                                                                             ┃
┃ ┌─ SYSTEM ───────────────────────────────────────────────────────────────────────────────┐ ┃
┃ │ State                  : RUNNING                                                        │ ┃
┃ │ Mode                   : BACKTEST                                                       │ ┃
┃ │ Exchange               : US_EQUITY / EQUITY                                             │ ┃
┃ │ Timezone               : America/New_York                                               │ ┃
┃ └────────────────────────────────────────────────────────────────────────────────────────┘ ┃
┃                                                                                             ┃
┃ ┌─ TIME MANAGER ─────────────────────────────────────────────────────────────────────────┐ ┃
┃ │ Current Session                                                                         │ ┃
┃ │   Date               : 2025-07-02                                                       │ ┃
┃ │   Time               : 09:47:00                                                         │ ┃
┃ │   Regular Open       : 09:30:00                                                         │ ┃
┃ │   Regular Close      : 16:00:00                                                         │ ┃
┃ │   Pre-Market         : 04:00:00 - 09:30:00                                              │ ┃
┃ │   Post-Market        : 16:00:00 - 20:00:00                                              │ ┃
┃ │   Is Trading Day     : ✓ Yes                                                            │ ┃
┃ │   Is Holiday         : ✗ No                                                             │ ┃
┃ │   Is Early Close     : ✗ No                                                             │ ┃
┃ │   Holiday Name       : None                                                             │ ┃
┃ └────────────────────────────────────────────────────────────────────────────────────────┘ ┃
┃                                                                                             ┃
┃ ┌─ BACKTEST WINDOW ──────────────────────────────────────────────────────────────────────┐ ┃
┃ │ Start Date           : 2025-07-02                                                       │ ┃
┃ │ End Date             : 2025-07-03                                                       │ ┃
┃ │ Total Days           : 2 days                                                           │ ┃
┃ │ Speed Multiplier     : 60x                                                              │ ┃
┃ │ Progress             : Day 1 of 2 (50%)                                                 │ ┃
┃ └────────────────────────────────────────────────────────────────────────────────────────┘ ┃
┃                                                                                             ┃
┃ ┌─ PERFORMANCE METRICS ──────────────────────────────────────────────────────────────────┐ ┃
┃ │ Total Time           : null                                                             │ ┃
┃ │ Trading Days         : 0                                                                │ ┃
┃ │ Bars Processed       : 0                                                                │ ┃
┃ │ Iterations           : 0                                                                │ ┃
┃ │ Backpressure                                                                            │ ┃
┃ │   Coordinator→Processor : 0                                                             │ ┃
┃ │   Processor→Analysis    : 0                                                             │ ┃
┃ │ Processing Times                                                                        │ ┃
┃ │   Data Processor     : min: 0.71ms | max: 2.51ms | avg: 1.88ms | count: 3              │ ┃
┃ │   Analysis Engine    : min: 0.00ms | max: 0.00ms | avg: 0.00ms | count: 0              │ ┃
┃ └────────────────────────────────────────────────────────────────────────────────────────┘ ┃
┃                                                                                             ┃
┃ ┌─ THREADS ──────────────────────────────────────────────────────────────────────────────┐ ┃
┃ │ DataProcessor                                                                           │ ┃
┃ │   Name               : DataProcessor                                                    │ ┃
┃ │   Alive              : ✓ Yes                                                            │ ┃
┃ │   Daemon             : ✓ Yes                                                            │ ┃
┃ │   Running            : ✓ Yes                                                            │ ┃
┃ │                                                                                         │ ┃
┃ │ DataQualityManager                                                                      │ ┃
┃ │   Name               : DataQualityManager                                               │ ┃
┃ │   Alive              : ✓ Yes                                                            │ ┃
┃ │   Daemon             : ✓ Yes                                                            │ ┃
┃ │   Running            : ✓ Yes                                                            │ ┃
┃ │                                                                                         │ ┃
┃ │ AnalysisEngine                                                                          │ ┃
┃ │   Name               : AnalysisEngine                                                   │ ┃
┃ │   Alive              : ✓ Yes                                                            │ ┃
┃ │   Daemon             : ✓ Yes                                                            │ ┃
┃ │   Running            : ✓ Yes                                                            │ ┃
┃ └────────────────────────────────────────────────────────────────────────────────────────┘ ┃
┃                                                                                             ┃
┃ ┌─ SESSION DATA ─────────────────────────────────────────────────────────────────────────┐ ┃
┃ │ Session Active       : ✓ Yes                                                            │ ┃
┃ │ Active Symbols       : RIVN (1 symbol)                                                  │ ┃
┃ └────────────────────────────────────────────────────────────────────────────────────────┘ ┃
┃                                                                                             ┃
┃ ━━━ SYMBOLS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ┃
┃                                                                                             ┃
┃ ┌─ RIVN ─────────────────────────────────────────────────────────────────────────────────┐ ┃
┃ │ ┌─ Session Metrics ──────────────────────────────────────────────────────────────────┐ │ ┃
┃ │ │ Volume             : 1,280                                                          │ │ ┃
┃ │ │ High               : $13.49                                                         │ │ ┃
┃ │ │ Low                : $13.47                                                         │ │ ┃
┃ │ │ Last Update        : 2025-07-02T09:36:00-04:00                                      │ │ ┃
┃ │ └────────────────────────────────────────────────────────────────────────────────────┘ │ ┃
┃ │                                                                                         │ ┃
┃ │ ┌─ Session Bars ─────────────────────────────────────────────────────────────────────┐ │ ┃
┃ │ │ 1m (Base)                                                                           │ │ ┃
┃ │ │   Count            : 3 bars                                                         │ │ ┃
┃ │ │   Quality          : 50.0%                                                          │ │ ┃
┃ │ │   Gaps             : 1 gap (4 missing bars)                                         │ │ ┃
┃ │ │   Gap Range        : 09:30:00 - 09:34:00 (4 bars)                                   │ │ ┃
┃ │ │                                                                                     │ │ ┃
┃ │ │ 5m (Derived from 1m)                                                                │ │ ┃
┃ │ │   Count            : 0 bars                                                         │ │ ┃
┃ │ │   Quality          : N/A                                                            │ │ ┃
┃ │ └────────────────────────────────────────────────────────────────────────────────────┘ │ ┃
┃ │                                                                                         │ ┃
┃ │ ┌─ Historical Data ──────────────────────────────────────────────────────────────────┐ │ ┃
┃ │ │ Loaded             : ✓ Yes                                                          │ │ ┃
┃ │ │                                                                                     │ │ ┃
┃ │ │ 1m Bars                                                                             │ │ ┃
┃ │ │   Count            : 1,656 bars                                                     │ │ ┃
┃ │ │   Quality          : 0.0%                                                           │ │ ┃
┃ │ │   Date Range       : 2025-06-27 → 2025-07-01 (3 trading days)                      │ │ ┃
┃ │ │   Trading Dates    : Jun 27, Jun 30, Jul 01                                        │ │ ┃
┃ │ │                                                                                     │ │ ┃
┃ │ │ 1d Bars                                                                             │ │ ┃
┃ │ │   Count            : N/A                                                            │ │ ┃
┃ │ └────────────────────────────────────────────────────────────────────────────────────┘ │ ┃
┃ │                                                                                         │ ┃
┃ │ ┌─ Configuration ────────────────────────────────────────────────────────────────────┐ │ ┃
┃ │ │ Base Interval      : 1m                                                             │ │ ┃
┃ │ │ Streams            : 1m, 5m, quotes                                                 │ │ ┃
┃ │ │ Historical Configs :                                                                │ │ ┃
┃ │ │   Config 1         : 3 trailing days × [1m]                                        │ │ ┃
┃ │ │   Config 2         : 2 trailing days × [1d]                                        │ │ ┃
┃ │ └────────────────────────────────────────────────────────────────────────────────────┘ │ ┃
┃ └─────────────────────────────────────────────────────────────────────────────────────────┘ ┃
┃                                                                                             ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

---

## Key Design Principles

### 1. **Data Inclusion**
- **Include**: All metadata, counts, statistics, configuration
- **Exclude**: Raw data arrays (bar data, tick data, quote data)

### 2. **Color Coding**
- **Green**: Good status (running, active, high quality)
- **Yellow**: Warning (paused, low quality, gaps)
- **Red**: Error/stopped
- **Cyan**: Labels and headers
- **Dim**: Inactive or unavailable data

### 3. **Compact View Strategy**
- Maximum 1-2 lines per major section
- Horizontal layout for space efficiency
- Only show essential information
- Use symbols: ✓ ✗ for boolean values

### 4. **Detailed View Strategy**
- Tree structure for hierarchy
- Full property names and values
- All available information displayed
- Proper indentation and grouping

### 5. **Session Bars/Ticks/Quotes Display**
- **Compact**: Each data type on separate line with time window
  - Format: `{interval} │ {count} {type} | Q: {quality}% | {start_time}-{end_time} | {gaps}`
  - Example: `1m │ 45 bars | Q: 100% | 09:30-10:15`
  - Example: `Quotes│ 150 items | 09:30-10:15`
- **Detailed**: Full breakdown per interval with all statistics

### 6. **Historical Data Display**
- **Compact**: Each interval on separate line with date range
  - Format: `{interval} │ {count} bars | {date_range} ({days} days)`
  - Example: `1m │ 1,656 bars | Jun 27-Jul 01 (3 days)`
- **Detailed**: Full breakdown with date range, quality, trading dates list

### 7. **Gap Information**
- **Compact**: `1 gap, 4 missing bars`
- **Detailed**: Each gap range with start/end times and bar count

### 8. **Performance Metrics**
- **Compact**: Key counts only (bars, iterations, backpressure)
- **Detailed**: Full timing statistics (min/max/avg for each component)

---

## Information Not Shown

Based on user requirement to exclude data but show most other information:

### ✗ Excluded (raw data arrays)
- Bar data arrays (OHLCV values)
- Tick data arrays
- Quote data arrays
- Indicator computed values (arrays)

### ✓ Included (everything else)
- System state and configuration
- Time manager current session info
- Performance metrics and timing
- Thread status
- Session metadata
- Symbol metrics (volume, high, low)
- Bar counts, quality, gap statistics
- Historical data counts and date ranges
- Configuration settings
- Backtest window information

---

## Implementation Notes

### Data Retrieval
```python
system_mgr = get_system_manager()
status = system_mgr.system_info(complete=True)  # Get full status
```

### Refresh Logic
- Use Rich `Live` for in-place updates
- Call `system_info()` on each refresh
- Handle KeyboardInterrupt gracefully
- Auto-stop when system stops

### Display Generation
1. Parse JSON structure
2. Format each section based on view mode (compact/detailed)
3. Build Rich Table with appropriate styling
4. Color code based on values (state, quality, etc.)
5. Handle missing/null values gracefully

---

## Command Implementation

```python
def data_session_command(
    refresh_seconds: Optional[int] = None,
    full: bool = False  # New parameter
):
    """Display session data.
    
    Args:
        refresh_seconds: Refresh interval (None/1 = 1s, 0 = once)
        full: If True, show detailed view. If False, show compact view.
    """
    if refresh_seconds is None:
        refresh_seconds = 1
    
    try:
        if refresh_seconds == 0:
            # Display once
            table = generate_session_display(compact=not full)
            console.print(table)
        else:
            # Live refresh
            with Live(generate_session_display(compact=not full), 
                     console=console, refresh_per_second=1) as live:
                while True:
                    time.sleep(refresh_seconds)
                    live.update(generate_session_display(compact=not full))
    except KeyboardInterrupt:
        console.print("\n[yellow]Display stopped by user[/yellow]")
```

---

## Testing Checklist

- [ ] Compact view shows all sections correctly
- [ ] Detailed view shows full hierarchy
- [ ] Color coding works (green/yellow/red/cyan/dim)
- [ ] Auto-refresh updates in place
- [ ] KeyboardInterrupt exits gracefully
- [ ] Handles missing data (nulls, empty arrays)
- [ ] Backtest-specific sections only show in backtest mode
- [ ] Historical data formatted correctly
- [ ] Gap information displays properly
- [ ] Performance metrics formatted with proper units
- [ ] Thread status updates correctly
- [ ] Works with multiple symbols
- [ ] Works with no symbols (empty session)
- [ ] Symbol metrics handle missing values
- [ ] Date/time formatting consistent

---

## Example Outputs

### Minimal Session (Compact)
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━ SESSION DATA ━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ SYSTEM   │ State: STOPPED | Mode: BACKTEST | Exchange: US_EQUITY  ┃
┃ SESSION  │ N/A | Inactive | No Symbols                            ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

### Multi-Symbol Session (Compact)
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━ SESSION DATA ━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ SYSTEM   │ State: RUNNING | Mode: BACKTEST | Exchange: US_EQUITY  ┃
┃ SESSION  │ 2025-07-02 | 10:15:30 | Active | 3 Symbols            ┃
┃ BACKTEST │ 2025-07-02 → 2025-07-05 (3 days) | Speed: 60x | Day 1/3┃
┃ ━━━ SYMBOLS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ┃
┃ AAPL                                                               ┃
┃   Metrics │ Vol: 150K | High: $178.25 | Low: $175.50 | Last: 10:15┃
┃   Session │                                                        ┃
┃     1m    │ 45 bars | Q: 100% | 09:30-10:15                       ┃
┃     5m    │ 9 bars | Q: 100% | 09:30-10:15                        ┃
┃ Historical│                                                        ┃
┃     1m    │ 1,170 bars | Jun 29-Jul 01 (3 days)                   ┃
┃     1d    │ 252 bars | Jul 02, 2024 - Jul 01, 2025 (1 year)       ┃
┃                                                                    ┃
┃ TSLA                                                               ┃
┃   Metrics │ Vol: 95K | High: $248.75 | Low: $245.10 | Last: 10:15 ┃
┃   Session │                                                        ┃
┃     1m    │ 45 bars | Q: 97.8% | 09:30-10:15 | 1 gap (1 missing)  ┃
┃     5m    │ 9 bars | Q: 100% | 09:30-10:15                        ┃
┃ Historical│                                                        ┃
┃     1m    │ 1,170 bars | Jun 29-Jul 01 (3 days)                   ┃
┃     1d    │ 252 bars | Jul 02, 2024 - Jul 01, 2025 (1 year)       ┃
┃                                                                    ┃
┃ RIVN                                                               ┃
┃   Metrics │ Vol: 12K | High: $13.52 | Low: $13.47 | Last: 10:14   ┃
┃   Session │                                                        ┃
┃     1m    │ 40 bars | Q: 88.9% | 09:30-10:14 | 2 gaps (5 missing) ┃
┃     5m    │ 8 bars | Q: 88.9% | 09:30-10:10                       ┃
┃ Historical│                                                        ┃
┃     1m    │ 1,170 bars | Jun 29-Jul 01 (3 days)                   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

---

## Next Steps

1. Review and approve this design
2. Implement compact view generation
3. Implement detailed view generation
4. Add color coding logic
5. Test with various scenarios
6. Update command registration
7. Update documentation
