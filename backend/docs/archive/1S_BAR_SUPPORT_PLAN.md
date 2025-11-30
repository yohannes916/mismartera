# Plan: Add 1-Second Bar Support to Stream Coordinator

## Analysis: Stream Coordinator Thread Responsibilities

### BacktestStreamCoordinator (`_merge_worker` thread)
**Primary responsibility: Chronological multi-stream merging**

- **Stream registration & lifecycle**
  - Register/deregister streams per (symbol, stream_type) key
  - Prevent duplicate streams for same symbol+type
  - Thread-safe queue management per stream

- **Chronological merging**
  - Pull data from multiple symbol streams (AAPL, RIVN, etc.)
  - Maintain pending_items staging area (one item per stream)
  - Find oldest timestamp across all pending items
  - Yield data in strict chronological order (oldest-first)

- **Backtest time advancement** (ONLY LOCATION)
  - Advance backtest time as data flows through
  - For BAR: timestamp + 1 minute (bar completion time)
  - For TICK/QUOTE: exact timestamp
  - Apply speed multiplier with sleep() for pacing

- **State-aware processing**
  - Check SystemManager.is_running() before advancing time
  - Pause when system is paused/stopped
  - Respect backtest mode vs live mode

- **Stale data filtering**
  - Skip data older than current backtest time
  - Handles mid-backtest stream registration

- **Session data integration**
  - Write BARs to session_data.add_bar() in thread
  - Provides data to AnalysisEngine and other consumers

### DataUpkeepThread (background maintenance)
**Primary responsibility: Data quality and derived computations**

- **Gap detection & filling**
  - Detect missing 1m bars in session_data
  - Fetch missing bars from database/parquet
  - Insert gaps maintaining chronological order
  - Retry failed gaps with backoff

- **Bar quality metrics**
  - Calculate quality percentage (actual vs expected bars)
  - Account for market hours, holidays, early closes
  - Update session_data.bar_quality per symbol

- **Derived bar computation**
  - Compute 5m, 15m, 30m bars from 1m bars
  - Progressive computation (5m before 15m)
  - Triggered by session_data.bars_updated flag
  - Only runs when enough 1m bars available

- **Configuration-driven**
  - Check interval: 60 seconds (configurable)
  - Derived intervals: [5, 15] (configurable)
  - Max retries for gap filling: 5

- **State-aware operation**
  - Only runs when system is running (backtest mode)
  - Always runs in live mode
  - Independent thread with asyncio event loop

---

## Current Architecture Constraints

### 1. Stream Coordinator Only Accepts 1m Bars
**Validation enforced in two places:**

```python
# system_manager.py lines 364-369
if stream_config.interval != "1m":
    raise ValueError(
        "Stream coordinator only supports 1m bars. "
        "Derived intervals (5m, 15m, etc.) are automatically computed by the data upkeep thread."
    )

# api.py lines 407-411
if interval != "1m":
    raise ValueError(
        "Stream coordinator only supports 1m bars (requested: {interval}). "
        "Derived intervals are automatically computed by the data upkeep thread."
    )
```

**Rationale:**
- Performance: No sorting overhead (DB data pre-sorted)
- Separation of concerns: Raw streaming vs derived computation
- Scalability: Add more derived intervals without affecting coordinator

### 2. Data Model Structure
**BarData (app/models/trading.py):**
```python
class BarData(BaseModel):
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
```
- No `interval` field in BarData model
- Interval implicit based on context (1m bars in session_data.bars_1m)

**Database Schema (MarketData):**
```python
interval = Column(String(10), default='1m', nullable=False)  # 1m, 5m, 15m, 1h, 1d
```
- Database has explicit interval column
- Supports storing multiple intervals

### 3. Session Configuration
**DataStreamConfig:**
```python
@dataclass
class DataStreamConfig:
    type: str  # "bars", "ticks", "quotes"
    symbol: str
    interval: Optional[str] = None  # Only for bars (e.g., "1m", "5m")
```
- Config supports interval specification
- But currently validated to reject non-1m

### 4. Session Data Storage
**Symbol data structure:**
```python
class SymbolData:
    bars_1m: deque[BarData]           # 1-minute bars
    bars_derived: Dict[int, List[BarData]]  # {5: [...], 15: [...]}
    bars_updated: bool                 # Triggers derived computation
```
- Fixed structure for 1m bars
- Derived intervals stored separately
- No support for 1s bars

---

## Target Architecture: ((1s or 1m) and/or quote) per ticker

### Requirements
1. Each ticker can have:
   - **Either** 1s bars **OR** 1m bars (not both)
   - **Optionally** quotes in addition to bars
   - Example valid configs:
     - AAPL: 1s bars + quotes
     - RIVN: 1m bars + quotes
     - TSLA: 1s bars only
     - MSFT: quotes only

2. Stream coordinator must:
   - Handle mixed 1s/1m bar streams across symbols
   - Maintain chronological ordering across all data types
   - Advance backtest time correctly for 1s bars

3. Derived bars:
   - 1m, 5m, 15m can be derived from 1s bars
   - 5m, 15m can be derived from 1m bars
   - Upkeep thread must handle both base intervals

---

## Implementation Plan

### Phase 1: Data Model & Storage Updates

#### 1.1 Update BarData Model
**File:** `app/models/trading.py`

```python
class BarData(BaseModel):
    """OHLCV bar with flexible interval support"""
    timestamp: datetime
    symbol: str
    interval: str = "1m"  # NEW: 1s, 1m, 5m, 15m, etc.
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
```

**Rationale:** Explicit interval makes bar type unambiguous

#### 1.2 Update SessionData Structure
**File:** `app/managers/data_manager/session_data.py`

```python
@dataclass
class SymbolData:
    # Raw bar storage (base interval per symbol)
    base_interval: str  # "1s" or "1m"
    bars_base: deque[BarData]  # Renamed from bars_1m
    
    # Derived bars
    bars_derived: Dict[str, List[BarData]]  # {"1m": [...], "5m": [...], "15m": [...]}
    
    # Existing fields
    bars_updated: bool
    bar_quality: float
    # ... quotes, ticks, etc.
```

**Migration strategy:**
- Keep `bars_1m` as alias to `bars_base` for backward compatibility
- Deprecate `bars_1m` over time

#### 1.3 Update Session Configuration
**File:** `app/models/session_config.py`

```python
@dataclass
class DataStreamConfig:
    type: str  # "bars", "ticks", "quotes"
    symbol: str
    interval: Optional[str] = None  # "1s", "1m" for bars
    
    def validate(self) -> None:
        # Bars require interval
        if self.type == "bars" and not self.interval:
            raise ValueError("Bar streams require an interval")
        
        # Only 1s or 1m allowed as base intervals
        if self.type == "bars" and self.interval not in ["1s", "1m"]:
            raise ValueError(
                f"Invalid bar interval: {self.interval}. "
                "Only '1s' or '1m' are supported as base intervals. "
                "Derived intervals (5m, 15m, etc.) are computed automatically."
            )
```

**Validation changes:**
- Allow "1s" in addition to "1m"
- Still reject 5m, 15m as base intervals
- Per-symbol validation: ensure no duplicates

---

### Phase 2: Stream Coordinator Updates

#### 2.1 Update BacktestStreamCoordinator
**File:** `app/managers/data_manager/backtest_stream_coordinator.py`

**Changes to `_merge_worker` method (lines 536-546):**

```python
# Determine the timestamp to set based on data type and interval
stream_type = oldest_key[1]
if stream_type == StreamType.BAR:
    # Extract interval from bar data
    bar_interval = oldest_item.data.interval
    
    if bar_interval == "1s":
        # 1s bar: add 1 second to get end of bar interval
        time_to_set = oldest_item.timestamp + timedelta(seconds=1)
    elif bar_interval == "1m":
        # 1m bar: add 1 minute to get end of bar interval
        time_to_set = oldest_item.timestamp + timedelta(minutes=1)
    else:
        # Derived bars shouldn't flow through coordinator
        logger.warning(f"Unexpected bar interval: {bar_interval}")
        time_to_set = oldest_item.timestamp
else:
    # Quote/tick: use exact timestamp
    time_to_set = oldest_item.timestamp
```

**Queue stats update (lines 293-353):**
- Track interval per stream: `(symbol, stream_type, interval)`
- Display queue stats with interval breakdown
- Example: "AAPL | 1s: 390 items | quotes: 15000 items"

#### 2.2 Remove 1m Validation
**Files to update:**
- `app/managers/system_manager.py` (lines 364-369) - **REMOVE** 1m-only check
- `app/managers/data_manager/api.py` (lines 407-411) - **REMOVE** 1m-only check

**Replace with:**
```python
# Validate base interval
if stream_config.interval not in ["1s", "1m"]:
    raise ValueError(
        f"Stream coordinator only supports 1s or 1m bars (requested: {stream_config.interval}). "
        f"Derived intervals (5m, 15m, etc.) are automatically computed by the data upkeep thread."
    )
```

---

### Phase 3: DataUpkeepThread Updates

#### 3.1 Multi-Interval Gap Detection
**File:** `app/managers/data_manager/data_upkeep_thread.py`

**Update `_check_and_fill_gaps` (lines 269-347):**

```python
async def _check_and_fill_gaps(self, symbol: str) -> None:
    """Detect gaps and attempt to fill them."""
    symbol_data = self._session_data.get_symbol_data(symbol)
    if symbol_data is None:
        return
    
    # Get base interval for this symbol
    base_interval = symbol_data.base_interval
    
    # Get expected bar frequency
    if base_interval == "1s":
        expected_bars_per_minute = 60
    elif base_interval == "1m":
        expected_bars_per_minute = 1
    else:
        logger.error(f"Unknown base interval: {base_interval}")
        return
    
    # Detect gaps using appropriate frequency
    bars_base = list(symbol_data.bars_base)
    gaps = detect_gaps(
        symbol=symbol,
        interval=base_interval,
        session_start=session_start_time,
        current_time=current_time,
        existing_bars=bars_base,
        expected_bars_per_minute=expected_bars_per_minute
    )
    
    # Fill gaps...
```

#### 3.2 Multi-Source Derived Bars
**Update `_update_derived_bars` (lines 441-489):**

```python
async def _update_derived_bars(self, symbol: str) -> None:
    """Recompute derived bars when base bars are updated."""
    symbol_data = self._session_data.get_symbol_data(symbol)
    if symbol_data is None or not symbol_data.bars_updated:
        return
    
    # Get base bars and interval
    base_bars = list(symbol_data.bars_base)
    base_interval = symbol_data.base_interval
    total_bars = len(base_bars)
    
    if total_bars == 0:
        return
    
    # Determine which derived intervals to compute
    if base_interval == "1s":
        # From 1s bars, can derive: 1m, 5m, 15m, 30m
        # Need 60 bars for 1m, 300 for 5m, 900 for 15m
        derived_intervals = ["1m", "5m", "15m"]
        min_bars_needed = {"1m": 60, "5m": 300, "15m": 900}
    elif base_interval == "1m":
        # From 1m bars, can derive: 5m, 15m, 30m
        # Need 5 bars for 5m, 15 for 15m
        derived_intervals = ["5m", "15m"]
        min_bars_needed = {"5m": 5, "15m": 15}
    else:
        return
    
    # Compute each interval independently
    computed_intervals = {}
    for interval in derived_intervals:
        if total_bars >= min_bars_needed.get(interval, 0):
            bars = compute_derived_interval(
                base_bars, 
                base_interval=base_interval,
                target_interval=interval
            )
            if bars:
                computed_intervals[interval] = bars
    
    # Update session_data
    async with self._session_data._lock:
        for interval, bars in computed_intervals.items():
            symbol_data.bars_derived[interval] = bars
        symbol_data.bars_updated = False
```

#### 3.3 Add Derived Bar Computation Function
**File:** `app/managers/data_manager/derived_bars.py`

```python
def compute_derived_interval(
    base_bars: List[BarData],
    base_interval: str,
    target_interval: str
) -> List[BarData]:
    """Compute derived bars from base bars.
    
    Args:
        base_bars: List of base interval bars (1s or 1m)
        base_interval: Base interval ("1s" or "1m")
        target_interval: Target interval ("1m", "5m", "15m", etc.)
    
    Returns:
        List of derived bars
    
    Examples:
        1s -> 1m: Aggregate 60 bars
        1s -> 5m: Aggregate 300 bars
        1m -> 5m: Aggregate 5 bars
    """
    # Parse intervals to seconds
    base_seconds = parse_interval_to_seconds(base_interval)
    target_seconds = parse_interval_to_seconds(target_interval)
    
    # Calculate aggregation factor
    factor = target_seconds // base_seconds
    
    # Aggregate bars
    derived = []
    for i in range(0, len(base_bars), factor):
        chunk = base_bars[i:i+factor]
        if len(chunk) < factor:
            break  # Incomplete bar
        
        # Aggregate OHLCV
        derived_bar = BarData(
            timestamp=chunk[0].timestamp,
            symbol=chunk[0].symbol,
            interval=target_interval,
            open=chunk[0].open,
            high=max(b.high for b in chunk),
            low=min(b.low for b in chunk),
            close=chunk[-1].close,
            volume=sum(b.volume for b in chunk)
        )
        derived.append(derived_bar)
    
    return derived
```

---

### Phase 4: Database & Storage Updates

#### 4.1 Query Updates
**File:** `app/managers/data_manager/repositories/market_data_repo.py`

**Update `get_bars_by_symbol` to support interval parameter:**

```python
@staticmethod
async def get_bars_by_symbol(
    session: AsyncSession,
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    interval: str = "1m",  # UPDATED: default 1m for backward compatibility
) -> List[MarketData]:
    """Fetch bars with specific interval."""
    query = (
        select(MarketData)
        .where(
            MarketData.symbol == symbol.upper(),
            MarketData.timestamp >= start_date,
            MarketData.timestamp < end_date,
            MarketData.interval == interval  # NEW: filter by interval
        )
        .order_by(MarketData.timestamp)
    )
    result = session.execute(query)
    return result.scalars().all()
```

#### 4.2 Parquet Storage Updates
**File:** `app/managers/data_manager/parquet_storage.py`

**Update read_bars to support interval:**

```python
def read_bars(
    self,
    interval: str,  # "1s" or "1m"
    symbol: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> pd.DataFrame:
    """Read bars from parquet storage."""
    # Construct path with interval
    interval_dir = self.base_path / "bars" / interval
    if not interval_dir.exists():
        return pd.DataFrame()
    
    # Read files...
```

**Directory structure:**
```
data/parquet/
├── bars/
│   ├── 1s/
│   │   ├── AAPL_1s_2024-01-01.parquet
│   │   └── RIVN_1s_2024-01-01.parquet
│   └── 1m/
│       ├── AAPL_1m_2024-01-01.parquet
│       └── TSLA_1m_2024-01-01.parquet
└── quotes/
    └── ...
```

---

### Phase 5: CLI & Display Updates

#### 5.1 Session Data Display
**File:** `app/cli/session_data_display.py`

**Update to show base interval per symbol:**

```python
# STREAM section (lines 200-300)
stream_lines = []
for symbol, data in sorted(symbol_data.items()):
    # Show base interval
    base_interval = data.base_interval
    bar_count = len(data.bars_base)
    
    line = f"{symbol:6} | {base_interval:3} | {bar_count:4} bars | ..."
    stream_lines.append(line)
```

**Example output:**
```
STREAM DATA
┏━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Symbol┃ Interval┃ Bars    ┃ Quality    ┃
┡━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━┩
│ AAPL  │ 1s     │ 23400   │ 100.0%     │
│ RIVN  │ 1m     │ 390     │ 100.0%     │
└───────┴────────┴─────────┴────────────┘
```

#### 5.2 Queue Statistics
**Update `get_queue_stats` to show interval:**

```python
# STREAM COORDINATOR QUEUES
AAPL | 1s: 390 items (09:30:00 - 09:36:30) | quotes: 1200 items (09:30:00 - 09:31:00)
RIVN | 1m: 6 items (09:30:00 - 09:35:00)
```

---

### Phase 6: Validation & Testing

#### 6.1 Configuration Validation
**Add per-symbol interval validation:**

```python
def validate_session_config(config: SessionConfig) -> None:
    """Validate session configuration."""
    
    # Check for duplicate symbol+type combinations
    seen = {}
    for stream in config.data_streams:
        key = (stream.symbol, stream.type)
        
        if key in seen:
            prev_interval = seen[key]
            if stream.type == "bars":
                raise ValueError(
                    f"Duplicate bar stream for {stream.symbol}. "
                    f"Found both {prev_interval} and {stream.interval}. "
                    f"Only one bar interval allowed per symbol."
                )
        
        if stream.type == "bars":
            seen[key] = stream.interval
        else:
            seen[key] = None
```

#### 6.2 Stream Coordinator Tests
**Test scenarios:**

1. **Mixed intervals across symbols**
   - AAPL: 1s bars
   - RIVN: 1m bars
   - Verify chronological ordering maintained

2. **1s bar time advancement**
   - Feed 60 1s bars (09:30:00 - 09:30:59)
   - Verify time advances: 09:30:01, 09:30:02, ..., 09:31:00

3. **Mixed data types per symbol**
   - AAPL: 1s bars + quotes
   - Verify interleaving: bar at 09:30:00, quote at 09:30:00.5, bar at 09:30:01

4. **Derived bar computation from 1s**
   - Feed 300 1s bars
   - Verify upkeep computes: 5x 1m bars, 1x 5m bar

#### 6.3 CSV Validation Updates
**File:** `validation/validate_session_dump.py`

**Update to handle variable intervals:**

```python
# Check expected base intervals from config
for stream in config.data_streams:
    if stream.type == "bars":
        symbol = stream.symbol
        expected_interval = stream.interval
        
        # Verify CSV has correct interval data
        interval_col = f"{symbol}_base_interval"
        if interval_col in csv_data.columns:
            actual_interval = csv_data[interval_col].iloc[-1]
            if actual_interval != expected_interval:
                errors.append(
                    f"Interval mismatch for {symbol}: "
                    f"config={expected_interval}, actual={actual_interval}"
                )
```

---

## Migration Strategy

### Backward Compatibility
1. **Phase 1-2 deployment:**
   - Default to "1m" if no interval specified in BarData
   - Keep `bars_1m` as alias in SessionData
   - Update all existing configs to explicitly specify "1m"

2. **Phase 3-4 deployment:**
   - Enable 1s bar support in new configs
   - Gradually migrate existing backtests to explicit intervals

3. **Phase 5-6 deployment:**
   - Update CLI displays
   - Deprecate `bars_1m` references
   - Update documentation

### Testing Plan
1. **Unit tests** - Each component in isolation
2. **Integration tests** - Full backtest with 1s+1m mixed
3. **Performance tests** - 1s bar throughput vs 1m
4. **Validation tests** - CSV export/validate with 1s data

### Performance Considerations
1. **Memory**: 1s bars = 60x more data than 1m
   - Monitor session_data queue sizes
   - Implement queue size limits per stream

2. **CPU**: More frequent time updates
   - Profile coordinator merge worker
   - Optimize pending_items lookup

3. **Storage**: Larger parquet files
   - Consider compression settings
   - Partition by date and interval

---

## Configuration Examples

### Example 1: Mixed Intervals + Quotes
```json
{
  "session_name": "1s_mixed_test",
  "mode": "backtest",
  "data_streams": [
    {"type": "bars", "symbol": "AAPL", "interval": "1s"},
    {"type": "quotes", "symbol": "AAPL"},
    {"type": "bars", "symbol": "RIVN", "interval": "1m"},
    {"type": "bars", "symbol": "TSLA", "interval": "1s"}
  ],
  "session_data_config": {
    "data_upkeep": {
      "enabled": true,
      "derived_intervals": ["1m", "5m", "15m"]
    }
  }
}
```

### Example 2: Pure 1s Bars (High Frequency)
```json
{
  "session_name": "hft_1s_backtest",
  "mode": "backtest",
  "data_streams": [
    {"type": "bars", "symbol": "SPY", "interval": "1s"},
    {"type": "bars", "symbol": "QQQ", "interval": "1s"}
  ],
  "session_data_config": {
    "data_upkeep": {
      "enabled": true,
      "derived_intervals": ["5s", "15s", "1m", "5m"]
    }
  }
}
```

---

## Summary

### Key Changes
1. **BarData model** - Add `interval` field
2. **SessionData** - Change `bars_1m` to `bars_base` with dynamic interval
3. **Stream coordinator** - Support 1s bar time advancement
4. **Upkeep thread** - Multi-interval gap detection and derived computation
5. **Configuration** - Allow "1s" or "1m" as base intervals
6. **Validation** - Enforce one bar interval per symbol

### Benefits
- ✅ High-frequency backtesting with 1s bars
- ✅ Flexible per-symbol interval configuration
- ✅ Automatic derived bar computation from any base
- ✅ Maintains chronological ordering across all data
- ✅ Backward compatible with existing 1m infrastructure

### Risks
- ⚠️ 60x more data volume for 1s bars
- ⚠️ More frequent time updates may impact performance
- ⚠️ Requires careful testing of derived bar computation

### Next Steps
1. Review plan with team
2. Implement Phase 1 (data models)
3. Update unit tests
4. Implement Phase 2 (coordinator)
5. Integration testing with sample 1s data
