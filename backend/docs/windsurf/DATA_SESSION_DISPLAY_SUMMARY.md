# Data Session Display Redesign - Executive Summary

## Problem
Current `data session` command is broken and doesn't show comprehensive system information.

## Solution
Redesign display to show ALL information from `system_manager.system_info()` API **except raw data arrays**.

---

## Quick Comparison

### What to INCLUDE ✓
- System state, mode, exchange, timezone
- Time manager session info (date, time, market hours)
- Backtest window and progress
- Performance metrics (counts, timing stats)
- Thread status
- Session metadata
- Symbol metrics (volume, high, low, last update)
- **Bar/tick/quote COUNTS and STATISTICS**
- **Historical data COUNTS and DATE RANGES**
- Gap information (count, missing bars, ranges)
- Configuration settings

### What to EXCLUDE ✗
- Bar data arrays (OHLCV values)
- Tick data arrays
- Quote data arrays
- Indicator value arrays

---

## Two Display Modes

### Compact Mode (Default)
**Goal**: Fit everything on one screen, horizontal layout

**Features**:
- 1-2 lines per major section
- Horizontal information flow
- Symbols: ✓ ✗ for booleans
- Short abbreviations (Vol, Q:, etc.)
- Only essential information

**Example**: `AAPL | Vol: 150K | $175.50-$178.25 | 1m: 45 bars (Q: 100%)`

### Detailed Mode (--full flag)
**Goal**: Show ALL available information in hierarchical tree

**Features**:
- Full property names
- Tree structure with indentation
- Complete values (no abbreviations)
- All timing statistics
- Full gap ranges
- Complete historical breakdown

**Example**:
```
┌─ AAPL
│ ┌─ Session Metrics
│ │ Volume             : 150,000
│ │ High               : $175.50
│ │ Low                : $178.25
│ └─────────────────────
│ ┌─ Session Bars
│ │ 1m (Base)
│ │   Count            : 45 bars
│ │   Quality          : 100.0%
```

---

## Information Architecture

### Top Level Sections (Always Shown)
1. **SYSTEM**: State, mode, exchange, timezone
2. **SESSION**: Date, time, market hours, symbol count
3. **BACKTEST**: Window, speed, progress (only in backtest mode)
4. **PERFORMANCE**: Bars processed, iterations, backpressure
5. **THREADS**: Status of each thread

### Symbol Level Sections (Per Symbol)
1. **Metrics** (1 line): Volume, high, low, last update time
2. **Session** (header + N lines): Each data type (bars/ticks/quotes) on separate line
   - Each line shows: count, quality, time window (start-end), gaps
3. **Historical** (header + N lines): Each interval on separate line
   - Each line shows: count, date range, trading days
4. **Configuration**: Streams, historical configs (detailed mode only)

---

## Key Display Features

### Color Coding
- **Green**: Running, active, high quality (≥95%)
- **Yellow**: Paused, warning, medium quality (80-95%)
- **Red**: Stopped, error, low quality (<80%)
- **Cyan**: Labels and headers
- **Dim**: Inactive or N/A

### Quality Display
- **Compact**: `Q: 50.0%` (color coded)
- **Detailed**: `Quality: 50.0%` (color coded)
- **Threshold**: Green ≥95%, Yellow 80-95%, Red <80%

### Session Bars/Ticks/Quotes Display
- **Compact**: Each data type on separate line with time window
  - Format: `{interval} │ {count} {type} | Q: {quality}% | {start_time}-{end_time} | {gaps}`
  - Example: `1m │ 45 bars | Q: 100% | 09:30-10:15`
  - Example: `5m │ 9 bars | Q: 97.8% | 09:30-10:15 | 1 gap (1 missing)`
  - Example: `Quotes│ 150 items | 09:30-10:15`
- **Detailed**: Full breakdown per interval with all statistics

### Gap Display
- **Compact**: `1 gap, 4 missing bars`
- **Detailed**: Each gap with time range and bar count
  ```
  Gaps: 1 gap (4 missing bars)
  Gap Range: 09:30:00 - 09:34:00 (4 bars)
  ```

### Historical Data
- **Compact**: Each interval on separate line with date range
  - Format: `{interval} │ {count} bars | {date_range} ({days} days)`
  - Example: `1m │ 1,656 bars | Jun 27-Jul 01 (3 days)`
  - Example: `1d │ 252 bars | Jul 02, 2024 - Jul 01, 2025 (1 year)`
- **Detailed**: Full breakdown with date range, quality, trading dates list
  ```
  1m Bars
    Count: 1,656 bars
    Quality: 0.0%
    Date Range: 2025-06-27 → 2025-07-01 (3 trading days)
    Trading Dates: Jun 27, Jun 30, Jul 01
  ```

### Performance Metrics
- **Compact**: `Bars: 0 | Iterations: 0 | Backpressure: 0/0`
- **Detailed**:
  ```
  Processing Times
    Data Processor: min: 0.71ms | max: 2.51ms | avg: 1.88ms | count: 3
    Analysis Engine: min: 0.00ms | max: 0.00ms | avg: 0.00ms | count: 0
  ```

---

## Command Usage

```bash
# Compact view (default), auto-refresh 1s
data session

# Compact view, auto-refresh 5s
data session 5

# Compact view, display once (no refresh)
data session 0

# Detailed view, auto-refresh 1s
data session --full

# Detailed view, auto-refresh 5s
data session 5 --full

# Detailed view, display once
data session 0 --full
```

---

## Implementation Strategy

### 1. Data Source
```python
system_mgr = get_system_manager()
status = system_mgr.system_info(complete=True)
```

### 2. Display Generation
```python
def generate_session_display(compact: bool = True) -> Table:
    # Get system info
    status = system_manager.system_info(complete=True)
    
    # Build display based on mode
    if compact:
        return build_compact_view(status)
    else:
        return build_detailed_view(status)
```

### 3. Refresh Logic
- Use Rich `Live` for smooth in-place updates
- Call `system_info()` on each refresh
- Handle `KeyboardInterrupt` gracefully
- Auto-stop when system stops running

---

## Visual Examples

### Compact View - Running Session
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ SESSION DATA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ SYSTEM    │ State: RUNNING | Mode: BACKTEST | Exchange: US_EQUITY/EQUITY     ┃
┃ SESSION   │ 2025-07-02 | 09:47:00 | ✓ Active | ✓ Trading | Symbols: 1        ┃
┃ BACKTEST  │ 2025-07-02 → 2025-07-03 (2 days) | Speed: 60x | Day 1/2          ┃
┃ THREADS   │ DataProc: ✓ | QualityMgr: ✓ | AnalysisEng: ✓                     ┃
┃ ━━━ SYMBOLS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ┃
┃ RIVN                                                                         ┃
┃   Metrics │ Vol: 1,280 | High: $13.49 | Low: $13.47 | Last: 09:36:00       ┃
┃   Session │                                                                  ┃
┃     1m    │ 3 bars | Q: 50% | 09:34-09:36 | 1 gap (4 missing)               ┃
┃     5m    │ 0 bars                                                           ┃
┃     Quotes│ 0 items                                                          ┃
┃ Historical│                                                                  ┃
┃     1m    │ 1,656 bars | Jun 27-Jul 01 (3 days)                             ┃
┃     1d    │ 0 bars                                                           ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

### Compact View - Stopped System
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━ SESSION DATA ━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ SYSTEM   │ State: STOPPED | Mode: BACKTEST                        ┃
┃ SESSION  │ N/A | ⚠ Inactive | No Symbols                          ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

---

## Benefits

### 1. **Comprehensive**
- Shows ALL available system information (except raw data)
- No need to call multiple commands to see full state

### 2. **Flexible**
- Compact mode for monitoring
- Detailed mode for debugging
- Configurable refresh rate

### 3. **Accurate**
- Single source of truth: `system_manager.system_info()`
- No duplicate data structures
- Always shows current state

### 4. **User Friendly**
- Color coded for quick scanning
- Hierarchical organization
- Consistent formatting
- Clear status indicators

### 5. **Performant**
- Only fetches what's needed
- Efficient Rich display updates
- No data arrays (just metadata)

---

## Open Questions for Review

1. **Section ordering**: Is the proposed order logical?
   - Current: SYSTEM → SESSION → BACKTEST → PERFORMANCE → THREADS → SYMBOLS
   
2. **Compact layout width**: Should we optimize for 80, 100, or 120 character width?

3. **Symbol ordering**: Alphabetical or by some other criteria?

4. **Gap display threshold**: Show all gaps or only first N in compact mode?

5. **Performance metrics**: Which ones are most important for compact view?

6. **Thread display**: Show all threads or only running ones in compact mode?

---

## Next Steps

1. ✅ **Review this plan** - Confirm design approach
2. **Implement compact view** - Start with basic structure
3. **Implement detailed view** - Add full hierarchy
4. **Add color coding** - Apply visual styling
5. **Test scenarios** - Multiple symbols, stopped system, gaps, etc.
6. **Update command** - Add --full flag support
7. **Documentation** - Update CLI help and README

---

## Estimated Effort

- **Compact view**: ~2-3 hours
- **Detailed view**: ~3-4 hours
- **Color coding & polish**: ~1-2 hours
- **Testing**: ~1-2 hours
- **Total**: ~7-11 hours

---

## Risk Mitigation

### Missing Data Handling
- Always check for null/None values
- Provide sensible defaults ("N/A", "Unknown")
- Don't crash on missing sections

### Performance
- Limit data array processing (metadata only)
- Efficient JSON parsing
- Rich display caching

### Compatibility
- Works with empty sessions
- Works with stopped system
- Works with both backtest and live modes
- Handles multiple symbols gracefully
