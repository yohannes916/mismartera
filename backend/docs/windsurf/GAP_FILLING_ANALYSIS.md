# Gap Filling Logic - Comprehensive Analysis

**Date:** December 1, 2025  
**Purpose:** Explain gap filling across Historical/Stream × Backtest/Live dimensions

---

## 📊 **Gap Filling Matrix: 4 Scenarios**

Gap filling behavior varies across **two dimensions**:
1. **Data Phase:** Historical (before session) vs Stream (during session)
2. **Mode:** Backtest vs Live

This creates **4 distinct scenarios:**

```
              HISTORICAL                     STREAM (CURRENT DAY)
              (Before Session)               (During Session)
          ┌──────────────────────┐      ┌──────────────────────┐
BACKTEST  │   ✅ Gap Filling     │      │   ❌ NO Gap Filling  │
          │   (Generation)       │      │   (Stream Only)      │
          └──────────────────────┘      └──────────────────────┘
          ┌──────────────────────┐      ┌──────────────────────┐
LIVE      │   ✅ Gap Filling     │      │   ✅ Gap Filling     │
          │   (Generation)       │      │   (API Retry)        │
          └──────────────────────┘      └──────────────────────┘
```

---

## 🔍 **Scenario 1: Historical + Backtest**

### **When:** Loading historical data before backtest session starts

### **Gap Filling:** ✅ **YES** (via generation)

**How It Works:**
1. SessionCoordinator loads historical data (e.g., last 5 days)
2. Checks DB for each requested interval
3. If interval not in DB but lower interval exists:
   - **Generate** missing bars from lower interval
   - Requires **100% completeness** of source bars
   - Uses `gap_filler.py` aggregation functions

**Example:**
```python
Requested: 5m bars for 5 days of history
DB Has: Only 1m bars

Action:
1. Load 1m bars from DB
2. Check completeness: 390 bars per day? ✅
3. Aggregate to 5m (5 bars → 1 bar)
4. Generate 78 5m bars per day (390/5)
5. Store in session_data as historical
```

**Functions Used:**
- `determine_historical_loading()` - Decides what to load/generate
- `check_interval_completeness()` - Verifies 100% source data
- `aggregate_bars_to_interval()` - OHLCV aggregation
- `fill_1m_from_1s()`, `fill_1d_from_1m()` - Specialized functions

**Quality Requirement:** 100% source completeness
- If 1m has 389/390 bars → **Skip 5m generation** (incomplete)
- If 1m has 390/390 bars → **Generate 5m** (complete)

---

## 🔍 **Scenario 2: Historical + Live**

### **When:** Loading historical data before live session starts

### **Gap Filling:** ✅ **YES** (via generation)

**How It Works:**
Identical to Historical + Backtest! Same code path:
1. Load available data from DB
2. Generate missing intervals from lower intervals
3. Require 100% completeness
4. Aggregate via gap_filler functions

**Why Same as Backtest:**
- Historical loading logic is **mode-independent**
- Both modes use `determine_historical_loading()`
- Generation rules don't change based on mode
- Source: Database in both cases

**Example:**
```python
Requested: 15m bars for last 3 days
DB Has: 1m bars with 2 small gaps

Action:
1. Load 1m bars from DB (378/390, 390/390, 388/390)
2. Check completeness per day:
   - Day 1: 96.9% → ❌ Skip 15m generation
   - Day 2: 100% → ✅ Generate 26 15m bars
   - Day 3: 99.5% → ❌ Skip 15m generation
3. Store only Day 2's 15m bars in historical
```

---

## 🔍 **Scenario 3: Stream + Backtest**

### **When:** Streaming data during backtest session

### **Gap Filling:** ❌ **NO** (stream base interval only)

**How It Works:**
1. Stream coordinator loads ONLY **smallest available** base interval (1s > 1m > 1d)
2. Streams this base interval chronologically
3. DataUpkeepThread generates ALL derived intervals on-the-fly
4. **NO gap filling** - if base has gaps, derived will too

**Example:**
```python
DB Has: 1m bars with gaps (382/390 bars)

Current Day Streaming:
1. Determine stream interval: "1m" (smallest available)
2. Load 382 1m bars into queue
3. Stream them chronologically
4. DataUpkeepThread generates 5m, 15m as bars arrive
5. Quality: 97.9% (reflects the gaps)
6. NO attempt to fill gaps during streaming
```

**Why No Gap Filling:**
- **Performance:** Gap filling is expensive, would slow streaming
- **Design:** Stream what exists, generate derivatives
- **Quality Transparency:** Gaps are reflected in quality %
- **Separation:** Gap filling is historical-only concern

**Functions Used:**
- `determine_stream_interval()` - Decides "1m" to stream
- SessionCoordinator loads 1m bars into queue
- Streams bars chronologically
- No gap_filler functions called

---

## 🔍 **Scenario 4: Stream + Live**

### **When:** Streaming live API data during live session

### **Gap Filling:** ✅ **YES** (via API retry)

**How It Works:**
1. Stream smallest base interval from API (1s > 1m > 1d)
2. **DataQualityManager** monitors for gaps in real-time
3. When gap detected:
   - Retry fetching missing bar from API
   - Up to `max_retries` attempts (default: 5)
   - Wait `retry_interval_seconds` between retries (default: 60s)
4. Background operation - doesn't block streaming

**Example:**
```python
Streaming: 1m bars from API in live mode
Gap Detected: Missing 10:15 bar

DataQualityManager Action:
1. Detect gap: Expected 10:15, got 10:16
2. Log gap: "Missing 1m bar at 10:15"
3. Background retry:
   - Attempt 1 (10:16): Request 10:15 from API → Fail
   - Wait 60s
   - Attempt 2 (10:17): Request 10:15 from API → Success!
4. Insert 10:15 bar into session_data
5. Update quality: 99.7% → 100%
6. DataUpkeepThread regenerates affected 5m bar
```

**Why Gap Filling Here:**
- **Live Data:** API may have delayed bars available later
- **Improvable Quality:** Retry can actually get missing data
- **Background:** Non-blocking, best-effort improvement
- **Real Value:** Can achieve 100% quality over time

**Configuration:**
```python
gap_filler:
  max_retries: 5              # Try up to 5 times
  retry_interval_seconds: 60  # Wait 1 minute between retries
  enable_session_quality: true # Required for gap detection
```

**Important Notes:**
- ⚠️ **Requires** `enable_session_quality: true`
- ⚠️ **LIVE MODE ONLY** - disabled in backtest
- ⚠️ **API-based** - not generation-based
- ⚠️ **Background** - doesn't block streaming

---

## 🎯 **Summary Table**

| Scenario | Gap Filling? | Method | Source | Completeness | Blocking? |
|----------|--------------|--------|--------|--------------|-----------|
| **Historical + Backtest** | ✅ YES | Generation | Parquet lower interval | 100% required | Yes (init) |
| **Historical + Live** | ✅ YES | Generation | Parquet lower interval | 100% required | Yes (init) |
| **Stream + Backtest** | ❌ NO | N/A | Stream base only | Accept gaps | No |
| **Stream + Live** | ✅ YES | API retry | Live API | Best effort | No (background) |

---

## 🔧 **API Capability Detection**

### **How Code Determines Gap Filling Capability**

The code uses **multiple checks** to determine if gap filling can occur:

#### 1. **Mode Check** (Live vs Backtest)
```python
# In DataQualityManager
if self.mode == "backtest":
    # Gap detection: YES
    # Gap filling: NO
    logger.info("Backtest mode: gap filling disabled")
else:  # live mode
    # Gap detection: YES
    # Gap filling: YES (if configured)
    logger.info("Live mode: gap filling enabled")
```

**Location:** `app/threads/data_quality_manager.py`  
**Decision:** Live mode enables gap filling, backtest disables it

---

#### 2. **Configuration Check** (enable_session_quality)
```python
# From session config
session_data_config:
  gap_filler:
    enable_session_quality: true  # Required for gap detection

# In code
if not self.config.enable_session_quality:
    # NO gap detection → NO gap filling
    # All bars assigned 100% quality
    return
```

**Decision:** If session quality disabled, no gap detection occurs, so no gap filling

---

#### 3. **Data Phase Check** (Historical vs Stream)

**Historical Phase:**
```python
# In determine_historical_loading()
decision = HistoricalDecision(
    load_from_db="1m",        # Load source from DB
    generate_from="1m",       # Generate target from it
    needs_gap_fill=True       # May need gap filling (generation)
)
```

**Stream Phase:**
```python
# In determine_stream_interval()
decision = StreamDecision(
    stream_interval="1m",     # Stream base interval
    generate_intervals=["5m"] # Generate others (no gap fill check)
)
```

**Decision:** Historical phase can gap-fill (generation), stream phase depends on mode

---

#### 4. **Source Quality Check** (100% completeness)

**Historical Generation:**
```python
# In can_fill_gap()
if source_quality < 100.0:
    return False, "Source quality {source_quality:.1f}% < 100% required"

# In check_interval_completeness()
is_complete = (actual_count == expected_count)
quality = (actual_count / expected_count) * 100.0

if not is_complete:
    logger.warning(f"Skipping generation: only {quality:.1f}% complete")
    return None  # Cannot gap fill
```

**Decision:** Historical gap filling requires **100% source completeness**

---

#### 5. **Derivation Validity Check**

```python
# In can_fill_gap()
priority = get_generation_source_priority(target_interval)

if source_interval not in priority:
    return False, "Target {target} cannot be derived from {source}"

# Priority examples:
# 5s → ["1s"]                    # ONLY from 1s
# 5m → ["1m", "1s"]              # Prefer 1m, fallback 1s
# 5d → ["1d", "1m", "1s"]        # Prefer 1d, fallback chain
```

**Decision:** Target must be derivable from source per priority rules

---

#### 6. **Source Availability Check**

```python
# In check_db_availability()
from app.models.schemas import BarData_1s, BarData_1m, BarData_1d

availability = AvailabilityInfo(
    symbol=symbol,
    has_1s=query_db_for_1s(session, symbol, date_range),  # Real DB query
    has_1m=query_db_for_1m(session, symbol, date_range),  # Real DB query
    has_1d=query_db_for_1d(session, symbol, date_range),  # Real DB query
    has_quotes=query_db_for_quotes(session, symbol, date_range)
)

# In determine_historical_loading()
if requested_interval == "5m":
    if availability.has_1m:
        source = "1m"  # ✅ Can gap fill (generate) from 1m
    elif availability.has_1s:
        source = "1s"  # ✅ Can gap fill (generate) from 1s
    else:
        error = "No source available"  # ❌ Cannot gap fill
```

**Decision:** Source interval must exist in DB for historical gap filling

---

#### 7. **Size Comparison Check**

```python
# In can_fill_gap()
source_info = parse_interval(source_interval)
target_info = parse_interval(target_interval)

if source_info.seconds >= target_info.seconds:
    return False, "Source not smaller than target"
```

**Decision:** Source must be smaller than target (can't fill 1m from 5m)

---

## 🎯 **Gap Filling Decision Flow**

### **Historical Phase (Both Modes):**

```
Requested Interval (e.g., 5m)
    ↓
Is it in DB? (Check BarData_5m table)
    ↓ No
Get source priority: ["1m", "1s"]
    ↓
Is 1m available? (Check BarData_1m table)
    ↓ Yes
Load 1m bars from DB
    ↓
Check completeness: 100%?
    ↓ Yes
Generate 5m bars (gap filling via aggregation)
    ✅ SUCCESS
```

### **Stream Phase - Backtest:**

```
Requested Intervals: ["1m", "5m", "15m"]
    ↓
Determine base interval: 1m (smallest in DB)
    ↓
Stream 1m bars chronologically
    ↓
DataUpkeepThread generates 5m, 15m on-the-fly
    ↓
Gaps in 1m → reflected in quality %
    ❌ NO gap filling
```

### **Stream Phase - Live:**

```
API streams 1m bars
    ↓
DataQualityManager monitors
    ↓
Gap detected at 10:15?
    ↓ Yes
enable_session_quality: true?
    ↓ Yes
Background retry (max 5 times, 60s intervals)
    ↓
Request 10:15 from API
    ↓
Got bar? → Insert and update quality
    ✅ Gap filled (API retry)
```

---

## 📋 **Key Differences Summary**

### **Historical Gap Filling (Generation)**
- **Method:** Aggregate lower interval bars
- **Requirement:** 100% source completeness
- **Blocking:** Yes (during initialization)
- **Scope:** All missing derived intervals
- **Mode:** Both backtest and live
- **Success Rate:** Deterministic (depends on DB)

### **Stream Gap Filling (API Retry)**
- **Method:** Re-request from API
- **Requirement:** Best effort (may fail)
- **Blocking:** No (background)
- **Scope:** Only live API gaps
- **Mode:** Live only
- **Success Rate:** Probabilistic (depends on API)

---

## ⚠️ **Important Clarifications**

### **"Gap Filling" has TWO meanings:**

1. **Historical Gap Filling = Generation**
   - Generate missing intervals from lower intervals
   - E.g., Generate 5m from 1m
   - Happens in both backtest and live modes
   - Code: `gap_filler.py` aggregation functions

2. **Stream Gap Filling = API Retry**
   - Re-request missing bars from live API
   - E.g., Retry fetching missing 10:15 bar
   - Happens ONLY in live mode
   - Code: `DataQualityManager` retry logic

### **Why the Confusion:**

The `gap_filler` config mentions "LIVE MODE ONLY" because it refers to **Stream Gap Filling (API retry)**, not **Historical Gap Filling (generation)**.

**Historical generation** works in both modes and is controlled by:
- `determine_historical_loading()`
- `check_interval_completeness()`
- `aggregate_bars_to_interval()`

**Stream API retry** works only in live mode and is controlled by:
- `gap_filler.enable_session_quality`
- `gap_filler.max_retries`
- `gap_filler.retry_interval_seconds`

---

## 🎯 **API Capability Summary**

### **Current Data APIs Support Gap Filling:**

| API | Historical Generation | Stream Retry | Notes |
|-----|----------------------|--------------|-------|
| **Parquet Storage** | ✅ YES | N/A | Provides source intervals for aggregation |
| **Live API** | ✅ YES (via Parquet) | ✅ YES | Can retry missing bars in real-time |
| **Backtest** | ✅ YES (via Parquet) | ❌ NO | No API to retry from |

### **How Code Determines This:**

1. **Parquet Availability:** `check_db_availability()` checks Parquet files for intervals
2. **Live API:** Mode check + config (`enable_session_quality`)
3. **Completeness:** `check_interval_completeness()` verifies 100%
4. **Derivation:** `get_generation_source_priority()` defines valid paths
5. **Quality:** `can_fill_gap()` enforces all rules

**Result:** Code has **full capability detection** and only attempts gap filling when:
- ✅ Source data exists (Parquet availability check)
- ✅ Source is complete (100% quality check)
- ✅ Target is derivable (priority check)
- ✅ Mode allows it (backtest vs live)
- ✅ Config enables it (session quality enabled)

---

**Last Updated:** December 1, 2025  
**Code Locations:**
- `app/threads/quality/gap_filler.py` - Historical generation
- `app/threads/quality/stream_determination.py` - Decision logic
- `app/threads/data_quality_manager.py` - Stream retry (live only)
- `app/threads/session_coordinator.py` - Integration
