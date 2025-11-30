# Phase 5: Data Quality Manager - Design Document

**Status**: 🚧 In Planning  
**Start Date**: November 28, 2025  
**Estimated Duration**: 1-2 days  

---

## 🎯 Objective

Extract quality measurement and gap management from `DataUpkeepThread` into a focused `DataQualityManager` that:
1. **Measures data quality** for streamed bars (gap detection, quality scoring)
2. **Fills gaps** in LIVE mode only (backtest = quality calculation only)
3. **Copies quality** from base bars to derived bars
4. **Non-blocking** background operation (doesn't gate other threads)
5. **Event-driven** (processes quality when data arrives)
6. **Mode-aware** (backtest vs live)

---

## 📋 Architecture Reference

**SESSION_ARCHITECTURE.md**: Lines 1362-1432 (Data Quality Manager Thread)

### Key Architectural Rules

1. **Non-Blocking**: Does NOT gate coordinator or processor (best effort)
2. **No Ready Signals**: Does NOT signal ready to any thread
3. **Event-Driven**: Processes quality when data arrives (not periodic)
4. **Mode-Aware**: 
   - Backtest: Quality calculation ONLY
   - Live: Quality calculation + gap filling
5. **Configuration-Controlled**:
   - `historical.enable_quality` - Historical quality (coordinator handles)
   - `gap_filler.enable_session_quality` - Session quality (this thread handles)
6. **Scope**: ONLY streamed bar intervals (NOT derived bars, NOT ticks/quotes)

---

## 🏗️ Current State Analysis

### What DataUpkeepThread Currently Does (Relevant to Quality)

**Quality Management** (Lines 799-869):
- `_update_bar_quality()` - Calculate quality percentage
- Uses `detect_gaps()` from `gap_detection.py`
- Updates `symbol_data.bar_quality`
- Logs quality metrics

**Gap Detection** (Lines 871-987):
- `_check_and_fill_gaps()` - Detect and fill gaps
- Uses `detect_gaps()` from `gap_detection.py`
- `_fill_gap()` - Fetch missing bars from Parquet
- Retry logic with max retries
- Track failed gaps for retry

**Gap Detection Module** (`gap_detection.py` - 318 lines):
- `GapInfo` dataclass - Gap information
- `detect_gaps()` - Main gap detection logic
- `generate_expected_timestamps()` - Expected bar timestamps
- `group_consecutive_timestamps()` - Group missing bars into gaps
- `merge_overlapping_gaps()` - Merge overlapping gaps

**Quality Checker Module** (`quality_checker.py`):
- `calculate_session_quality()` - Quality calculation helper
- (Need to check this module)

---

## 🎨 New DataQualityManager Architecture

### Responsibilities

**Primary**:
1. **Quality Measurement** - Calculate quality scores for streamed bars
2. **Gap Detection** - Detect missing bars in streamed data
3. **Gap Filling** - Fill gaps in LIVE mode only
4. **Quality Propagation** - Copy quality from base bars to derived bars

**Secondary**:
- Thread lifecycle (start, stop, cleanup)
- Configuration awareness
- Mode detection (backtest vs live)
- Retry logic for failed gap fills

### Thread Synchronization Design

```python
┌─────────────────────────┐
│  Session Coordinator    │
│  (streams bars)         │
└───────────┬─────────────┘
            │
            │ Bars flow to SessionData
            ▼
    ┌──────────────────┐
    │   SessionData    │
    │   (bars storage) │
    └────────┬─────────┘
             │
             │ Quality Manager reads (non-blocking)
             ▼
┌─────────────────────────────────────────┐
│     Data Quality Manager                │
│  1. Detect gaps in streamed bars        │
│  2. Calculate quality percentage        │
│  3. Fill gaps (LIVE mode only)          │
│  4. Copy quality to derived bars        │
│  5. Update SessionData quality          │
└─────────────────────────────────────────┘
              │
              │ No notifications, no blocking
              ▼
         (Background updates)
```

### Non-Blocking Design

**Key Difference from DataProcessor**:
- **DataProcessor**: BLOCKS coordinator until processing done
- **DataQualityManager**: NEVER blocks, best-effort background updates

**No Subscriptions**:
- Does NOT use StreamSubscription
- Does NOT signal ready
- Does NOT wait for coordinator

**Event-Driven**:
- Notification queue receives updates
- Processes when data arrives
- No periodic polling

---

## 📝 Implementation Tasks

### Task 5.1: Project Setup ✅
- [ ] Copy relevant modules to backup
- [ ] Create new `data_quality_manager.py` skeleton
- [ ] Set up imports (Phase 1, 2, 3 dependencies)
- [ ] Create initial class structure

### Task 5.2: Gap Detection Integration ✅
- [ ] Copy `gap_detection.py` to `app/threads/quality/`
- [ ] Copy `GapInfo` dataclass
- [ ] Import and integrate `detect_gaps()`
- [ ] Update imports in quality manager

### Task 5.3: Quality Measurement ✅
- [ ] Implement quality calculation logic
- [ ] Expected bars vs actual bars
- [ ] Quality percentage (0-100%)
- [ ] Update SessionData quality metrics

### Task 5.4: Gap Filling (Live Mode) ✅
- [ ] Mode detection (backtest vs live)
- [ ] Gap filling logic (from Parquet)
- [ ] Retry mechanism
- [ ] Failed gap tracking
- [ ] Only active in live mode

### Task 5.5: Quality Propagation ✅
- [ ] Copy quality from base bars to derived bars
- [ ] When 1m quality changes, update 5m, 15m, etc.
- [ ] Automatic propagation

### Task 5.6: Event-Driven Loop ✅
- [ ] Notification queue setup
- [ ] Main processing loop
- [ ] Timeout handling
- [ ] Graceful shutdown

### Task 5.7: Configuration Support ✅
- [ ] `enable_session_quality` flag
- [ ] `max_retries` configuration
- [ ] `retry_interval_seconds` configuration
- [ ] Mode detection from SessionConfig

### Task 5.8: Testing & Cleanup ✅
- [ ] Verify non-blocking behavior
- [ ] Test backtest mode (quality only)
- [ ] Test live mode (quality + gap filling)
- [ ] Update PROGRESS.md

---

## 🗑️ Code to Extract from DataUpkeepThread

### Quality Management (Keep & Refactor)
- `_update_bar_quality()` → Integrate into quality manager
- Gap detection logic → Use existing `gap_detection.py`
- Quality calculation → Adapt for event-driven

### Gap Filling (Keep & Refactor)
- `_check_and_fill_gaps()` → Mode-aware gap filling
- `_fill_gap()` → Parquet fetch logic
- Failed gap tracking → Retry mechanism

### Modules to Reuse
- `gap_detection.py` → Copy to `app/threads/quality/`
- `quality_checker.py` → Review and integrate
- `GapInfo` dataclass → Keep as-is

---

## 🎯 Quality Calculation Design

### Formula
```python
Quality = (actual_bars / expected_bars) * 100

Where:
- expected_bars = minutes from session_start to current_time
- actual_bars = expected_bars - missing_bars
- missing_bars = sum of all gaps detected
```

### Gap Detection Process
1. Generate expected timestamps (session_start → current_time)
2. Get actual bar timestamps from SessionData
3. Find missing timestamps (expected - actual)
4. Group consecutive missing timestamps into gaps
5. Create `GapInfo` objects for each gap

### Quality Score Examples
- **100%**: No gaps, perfect data
- **98.5%**: 5 missing bars out of 390 (6.5 hours)
- **0%**: All data missing

---

## 🔄 Gap Filling Process (Live Mode Only)

### Detection
```python
gaps = detect_gaps(
    symbol=symbol,
    session_start=session_start_time,
    current_time=current_time,
    existing_bars=bars_1m
)
```

### Filling
```python
for gap in gaps:
    if gap.retry_count < max_retries:
        # Fetch from Parquet storage
        missing_bars = fetch_bars_from_parquet(
            symbol, gap.start_time, gap.end_time
        )
        
        # Add to SessionData
        for bar in missing_bars:
            session_data.add_bar(symbol, "1m", bar)
        
        # Update quality
        quality = recalculate_quality(symbol)
```

### Retry Logic
- Track failed gaps with retry count
- Retry up to `max_retries` times
- Wait `retry_interval_seconds` between retries
- Log and abandon after max retries

---

## 🎨 Quality Propagation Design

### Base to Derived
```python
# When 1m bar quality changes
quality_1m = 98.5

# Copy to all derived intervals
for interval in [5, 15, 30, 60]:
    session_data.set_quality(symbol, f"{interval}m", quality_1m)
```

### Automatic Update
- Quality manager detects quality change in base interval
- Automatically propagates to all derived intervals
- Analysis engine sees consistent quality across all intervals

---

## 📊 Expected Outcome

### New DataQualityManager
- **~400-500 lines** (focused on quality/gaps)
- **Non-blocking** (background operation)
- **Event-driven** (notification queue)
- **Mode-aware** (backtest vs live)
- **Configuration-controlled**

### Extracted Modules
- `app/threads/quality/gap_detection.py` (reused)
- `app/threads/quality/__init__.py`
- Support for `GapInfo` dataclass

### Integration Points
- ✅ SessionData for bar storage and quality metrics
- ✅ Notification queue for event-driven updates
- ✅ TimeManager for current time and trading sessions
- ✅ DataManager for Parquet fetching (gap filling)

---

## 🚀 Success Criteria

1. ✅ Quality measurement for streamed bars
2. ✅ Gap detection with detailed analysis
3. ✅ Gap filling in live mode only (disabled in backtest)
4. ✅ Quality propagation to derived bars
5. ✅ Non-blocking background operation
6. ✅ Event-driven architecture
7. ✅ Mode-aware behavior
8. ✅ Configuration-controlled
9. ✅ Retry logic for failed gap fills
10. ✅ Clean, maintainable code

---

## 🎯 Key Design Decisions

### 1. Non-Blocking
**Decision**: Quality manager does NOT block coordinator or processor  
**Reason**: Quality is informational, not critical path  
**Impact**: Best-effort updates, may lag slightly

### 2. Event-Driven
**Decision**: Process quality when data arrives (not periodic)  
**Reason**: Aligns with overall architecture, more efficient  
**Impact**: Quality updates immediately when new bars arrive

### 3. Mode-Aware Gap Filling
**Decision**: Gap filling ONLY in live mode  
**Reason**: Backtest data is static, no point filling gaps  
**Impact**: Simpler backtest mode, gap filling only when useful

### 4. Quality Propagation
**Decision**: Automatically copy base quality to derived  
**Reason**: Simplifies analysis engine (all intervals have quality)  
**Impact**: Derived intervals inherit base quality

### 5. Configuration-Controlled
**Decision**: `enable_session_quality` flag controls entire feature  
**Reason**: Performance - skip quality calculation if not needed  
**Impact**: Can disable for performance-critical backtests

---

## 📚 Reference

- **SESSION_ARCHITECTURE.md**: Lines 1362-1432
- **DataUpkeepThread**: Lines 799-987 (quality/gap code)
- **gap_detection.py**: 318 lines (gap detection logic)
- **Phase 4 Complete**: DataProcessor (derived bars)
- **Phase 1**: SessionData (quality metrics storage)

---

**Next**: Begin implementation with Task 5.1!
