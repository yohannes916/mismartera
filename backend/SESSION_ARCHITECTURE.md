# Session Handling Architecture - Simplified Design

## Overview

This document describes the session handling architecture. The architecture is built around a thread pool model with clear separation of concerns and configuration-driven behavior.

---

## Architecture Principles

### 1. Configuration Philosophy
- **No Settings Defaults**: Session configuration fields MUST NOT have corresponding defaults in `settings.py`
- **Source Code Defaults**: All defaults are defined in source code at the point of use
- **Safe Defaults**: Defaults should be either:
  - Invalid/None values that force explicit configuration
  - Safe fallback values that prevent destructive operations
- **Explicit Over Implicit**: Critical configurations require explicit values

### 1a. Historical Data & Indicators Definition
- **Historical Data**: Any data that depends ONLY on data prior to the current session
- **Historical Indicators**: Any indicators calculated from historical data only
- **Session Coordinator Responsibility**: Updates historical data and indicators BEFORE EVERY SESSION
- **Data Management**: 
  - Ensures only requested trailing data is available (drops old data outside window, adds new data)
  - Alternative simpler approach: Clear all historical data and reload + recalculate for each session
- **Frequency**: Updated daily (or per session) to maintain accurate trailing windows

### 2. Thread Pool Model
The session operates with a dedicated thread pool containing at least 4 specialized threads:

1. **Session Coordinator** (`session_coordinator`): Manages data stream lifecycle, marks streamed vs generated data, updates historical data and calculates historical indicators before EVERY session start, and orchestrates session flow
2. **Data Processor** (`data_processor`): Generates derivative data (intervals) and calculates real-time indicators; event-driven with subscriber notifications
3. **Data Quality Manager** (`data_quality_manager`): Measures data quality, publishes quality metrics; fills gaps in LIVE MODE ONLY; non-blocking background operation
4. **Analysis Engine** (`analysis_engine`): Consumes processed data and generates trading signals

### 3. Session Data: Unified Data Store for Current Session

**⚠️ CRITICAL: session_data is NOT just "today's data" - it's ALL data needed for analysis/decisions in the current session**

**Definition**:
- `session_data` is the **single unified data store** containing ALL data available for the current session
- Holds BOTH **historical data** (trailing days/periods) AND **current session data** (today's bars, indicators)
- From a strategy perspective: ALL data required to make analysis/decisions for the current session
- Contains all data available **up to current time** (NO future data)

**Data Flow**:
```
Coordinator Input Queues → session_data → Analysis Engine
```

**What session_data Contains**:
1. **Historical Bars**: Trailing days of bars loaded before session start (e.g., last 10 days of 1m bars)
2. **Historical Indicators**: Pre-calculated indicators from historical data (e.g., 10-day moving average)
3. **Current Session Bars**: Bars arriving during today's session (streamed or generated)
4. **Real-Time Indicators**: Indicators calculated during the session as new bars arrive
5. **Derived Data**: Generated intervals (5m from 1m, etc.)
6. **Quality Metrics**: Quality percentage per symbol per data type (from data_quality_manager)
   - Example: `AAPL 1m bars: 98.5%`, `RIVN 1m bars: 100%`
   - ALL bar data sets have quality scores (historical + current, base + derived)
   - Derived bars get quality copied from base bars (updated when base changes)
   - Historical bars get quality assigned by coordinator thread before session start

**Population by Different Threads**:
- **Session Coordinator**: Loads historical bars, calculates historical indicators, assigns historical bar quality, streams current session data
- **Data Processor**: Generates derivative intervals, calculates real-time indicators
- **Data Quality Manager**: Measures quality for streamed bars, and detailed gap analysis, copies quality to derived bars, updates quality when base changes, attempts gap fill

**Access Pattern**:
- ⚠️ **CRITICAL**: Analysis Engine accesses data **ONLY from session_data** (never from queues or other sources)
- All threads write to session_data by **appending references** (object data not copied)
- Analysis Engine reads from session_data by **accessing references** (object data not copied)
- **session_data is the single interface** between data pipeline and analysis
- **Zero-Copy Principle**: Bar/tick/quote objects exist once in memory; only references are passed between containers

**Performance**:
- Uses fast containers (`collections.deque` for O(1) append)
- Zero-copy principle: Bar objects stored once; only references passed between containers
- Coordinator: `bar = queue.get()` → `session_data.append(bar)` (same object reference)
- Analysis Engine: Accesses bars by reference, no copying
- Indexed access for historical indicators (O(1) lookup)

**Lifetime**:
- Created at session start
- Cleared at session end (via `session_coordinator.stop()`)
- Reloaded before each session with fresh historical data

### 4. Single Source of Truth
- **Time Operations**: ALL time/calendar operations via `TimeManager`
- **Trading Hours**: Query from `TimeManager.get_trading_session()`, never hardcode
- **Timezone**: Automatically derived from `exchange_group` + `asset_class` and stored in `system_manager.timezone`
  - Updated automatically when `exchange_group` or `asset_class` changes via API
  - NEVER update `timezone` directly
  - NEVER explicitly configured in session config
- **Holidays**: Managed by `TimeManager`, never manual checks

---

## Session Configuration Structure

### Complete Example

**Notes:**
- Valid `mode` values: `"backtest"` or `"live"` only
- For single-day backtest: Set `start_date` = `end_date` (e.g., both `"2025-07-02"`)
- Dates don't need to be trading days; TimeManager finds the next valid trading day

```json
{
  "session_name": "Example Trading Session",
  "exchange_group": "US_EQUITY",
  "asset_class": "EQUITY",
  "mode": "backtest",
  "backtest_config": {
    "start_date": "2025-07-02",
    "end_date": "2025-07-07",
    "speed_multiplier": 360.0,
    "prefetch_days": 3
  },
  "session_data_config": {
    "symbols": ["RIVN", "AAPL"],
    "streams": ["1s", "1m", "5m", "10m", "quotes"],
    "_note": "Coordinator marks which are streamed vs generated based on mode and availability",
    "historical": {
      "enable_quality": true,
      "data": [
        {
          "trailing_days": 3,
          "intervals": ["1m"],
          "apply_to": "all"
        },
        {
          "trailing_days": 10,
          "intervals": ["1d"],
          "apply_to": "all"
        }
      ],
      "indicators": {
        "avg_volume": {
          "type": "trailing_average",
          "period": "10d",
          "granularity": "daily"
        },
        "avg_volume_intraday": {
          "type": "trailing_average",
          "period": "10d",
          "granularity": "minute"
        },
        "high_52w": {
          "type": "trailing_max",
          "period": "52w",
          "field": "high"
        },
        "low_52w": {
          "type": "trailing_min",
          "period": "52w",
          "field": "low"
        }
      }
    },
    "gap_filler": {
      "max_retries": 5,
      "retry_interval_seconds": 60,
      "enable_session_quality": true
    }
  },
  "trading_config": {
    "max_buying_power": 100000.0,
    "max_per_trade": 10000.0,
    "max_per_symbol": 20000.0,
    "max_open_positions": 5
  },
  "api_config": {
    "data_api": "alpaca",
    "trade_api": "alpaca"
  },
  "metadata": {
    "created_by": "user",
    "description": "Example session configuration for testing",
    "strategy": "momentum_scalping",
    "version": "1.0"
  }
}
```

---

## Streaming Architecture & Mode-Based Behavior

### Stream vs Generate Decision (Coordinator Responsibility)

The **Coordinator Thread** determines which data is **streamed** vs **generated** based on:
1. **Mode** (backtest vs live)
2. **Data availability** from API/database
3. **Configuration** (`session_data_config.streams`)

#### Backtest Mode Rules
- **Base Data**: Stream ONLY the smallest available interval per symbol
  - Priority: `1s` > `1m` > `1d` (stream only one)
  - Example: If `["1s", "1m", "10m"]` requested → stream `1s` only, generate `1m` and `10m`
- **Quotes**: Stream if available in database (optional, ignored if not available)
- **Ticks**: NEVER streamed in backtest (ignored)
- **Derivatives**: ALL generated by data_processor (5m, 10m, 15m, etc.)

#### Live Mode Rules
- **Any Data**: Stream if data API has it available as a stream
- **Quotes**: Stream if API provides
- **Ticks**: Stream if API provides
- **Derivatives**: Generate what's not available from API

#### Session Coordinator Marking
- Session Coordinator **marks** each requested stream as:
  - `STREAMED`: Data will come from session_coordinator
  - `GENERATED`: Data will be computed by data_processor
  - `IGNORED`: Not available, not generated (e.g., ticks in backtest)
- Data Processor knows what to generate
- Data Quality Manager knows what to validate/fill

### Data Scope (Applied to All Symbols)

Both `session_data_config.streams` and `session_data_config.historical` apply to **ALL symbols** in `session_data_config.symbols`:

- **streams**: Requested for every symbol
- **historical.data**: Loaded for every symbol (or targeted subset via `apply_to`)
- **historical.indicators**: Computed for every symbol

### No Async Prefetch

- Prefetch is **synchronous** in session_coordinator loop
- In backtest: Session Coordinator loads stream queues with up to `prefetch_days` of data (min 1 day)
- In live: Streams start immediately without prefetch

---

## Configuration Field Reference

### Top-Level Fields

#### `session_name` (string, required)
- **Description**: Human-readable name for the session
- **Code Default**: `None` (must be provided)
- **Example**: `"Example Trading Session"`

#### `exchange_group` (string, required)
- **Description**: Exchange group determining timezone and trading hours
- **Code Default**: `"US_EQUITY"`
- **Valid Values**: `"US_EQUITY"`, `"CRYPTO"`, `"FOREX"`, `"COMMODITIES"`
- **Side Effects**: 
  - Combined with `asset_class` to automatically derive timezone
  - Updates `system_manager.timezone` when changed via API
- **Update Rule**: ONLY update through SystemManager API, not directly

#### `asset_class` (string, required)
- **Description**: Asset class for trading rules and data handling
- **Code Default**: `"EQUITY"`
- **Valid Values**: `"EQUITY"`, `"CRYPTO"`, `"OPTIONS"`, `"FUTURES"`
- **Side Effects**: 
  - Combined with `exchange_group` to automatically derive timezone
  - Updates `system_manager.timezone` when changed via API
- **Update Rule**: ONLY update through SystemManager API, not directly

#### `mode` (string, required)
- **Description**: Execution mode for the session
- **Code Default**: `"backtest"`
- **Valid Values**: `"backtest"`, `"live"`
- **Side Effects**: 
  - `backtest`: Uses simulated time via `TimeManager`
  - `live`: Uses real-time clock

---

### `backtest_config` (object, required if mode="backtest")

#### `start_date` (ISO date string, required)
- **Description**: Reference date for backtest start; TimeManager will find the first valid trading day from this date
- **Code Default**: `None` (must be provided in backtest mode)
- **Format**: `"YYYY-MM-DD"`
- **Validation**: Must be a valid calendar date
- **Processing**: 
  - `TimeManager.get_first_trading_date(start_date)` finds first valid trading day
  - If `start_date` is already a trading day, uses it; otherwise finds next trading day
  - `TimeManager.get_trading_session(first_trading_day)` provides market open time
  - Backtest starts at: `datetime.combine(first_trading_day, market_open_time)`
- **Note**: Can be a weekend or holiday; TimeManager handles finding the actual trading day

#### `end_date` (ISO date string, required)
- **Description**: Reference date for backtest end; TimeManager will find the appropriate trading day
- **Code Default**: `None` (must be provided in backtest mode)
- **Format**: `"YYYY-MM-DD"`
- **Validation**: Must be a valid calendar date >= `start_date`
- **Processing**: 
  - If `end_date` is a trading day, use it; otherwise find next trading day
  - `TimeManager.get_trading_session(last_trading_day)` provides market close time
  - Backtest ends at: `datetime.combine(last_trading_day, market_close_time)`
- **Single-Day Backtest**: `start_date` and `end_date` can be identical (if it's a trading day)
- **Example**: `start_date="2025-07-05"`, `end_date="2025-07-05"` = single trading day

#### `speed_multiplier` (float, optional)
- **Description**: Time acceleration factor for backtest
- **Code Default**: `1.0` (real-time speed)
- **Valid Values**: 
  - `0.0`: Maximum possible speed (no delays)
  - `> 0.0`: Multiplier of real-time (e.g., 360.0 = 360x faster)
- **Example**: `360.0` runs 6 hours/minute
- **Clock-Driven Behavior**: When speed > 0, session_coordinator is clock-driven; data_processor can gate stream in backtest

#### `prefetch_days` (integer, optional)
- **Description**: Number of days of data to load into stream queues at start of each trading day in backtest
- **Code Default**: `1`
- **Valid Values**: `>= 1`
- **Behavior**: Session Coordinator loads up to this many days of data before activating session each day
- **Example**: `3` = load 3 days of historical data into queues before starting stream

---

### `session_data_config` (object, required)

#### `symbols` (array of strings, required)
- **Description**: List of symbols to trade/analyze
- **Code Default**: `[]` (empty list, must provide at least one)
- **Example**: `["RIVN", "AAPL", "TSLA"]`
- **Validation**: Each symbol must be valid for the configured `asset_class`

#### `streams` (array of strings, required)
- **Description**: Requested data streams for ALL symbols (session_coordinator determines streamed vs generated)
- **Code Default**: `[]` (must provide at least one)
- **Valid Values**: Bar intervals (`"1s"`, `"1m"`, `"5m"`, `"10m"`, `"15m"`, `"30m"`, `"1h"`, `"1d"`), market data (`"ticks"`, `"quotes"`)
- **Example**: `["1s", "1m", "5m", "quotes"]`
- **Applies To**: ALL symbols in `session_data_config.symbols`
- **Session Coordinator Decision**:
  - **Backtest**: Streams smallest base interval (1s > 1m > 1d), generates rest, optionally streams quotes
  - **Live**: Streams what API provides, generates rest
- **Note**: Session Coordinator marks each as `STREAMED`, `GENERATED`, or `IGNORED`

---

### `session_data_config.historical` (object, optional)

#### `historical.enable_quality` (boolean, optional)
- **Description**: Enable quality calculation for historical bars loaded before session start
- **Code Default**: `true`
- **Valid Values**: `true`, `false`
- **Applies To**: Both backtest and live modes
- **When Disabled**: All historical bars assigned 100% quality score
- **When Enabled**: Coordinator calculates actual quality before session start
- **Performance**: Disabling saves CPU cycles during session initialization

#### `historical.data` (array of objects, optional)
- **Description**: Historical bar data updated by session_coordinator BEFORE EVERY SESSION
- **Code Default**: `[]` (no historical data)
- **Update Frequency**: EVERY SESSION (daily in backtest, each trading session in live)
- **Management**: Drop old data outside trailing window + add new data OR clear + reload (simpler)
- **Purpose**: Maintain accurate trailing windows as they shift daily
- **Structure**:
  ```json
  {
    "trailing_days": 3,
    "intervals": ["1m"],
    "apply_to": "all"
  }
  ```

##### `trailing_days` (integer, required)
- **Description**: Number of trading days to maintain (rolling window)
- **Validation**: Must be > 0
- **Behavior**: Window shifts daily (e.g., "last 10 days" always means the most recent 10 trading days)
- **Calculation**: Uses `TimeManager.count_trading_days()` to exclude holidays/weekends

##### `intervals` (array of interval strings, required)
- **Description**: Bar intervals to load
- **Valid Values**: `["1s", "1m", "5m", "15m", "30m", "1h", "1d"]` (NO quotes or ticks)
- **Note**: Historical data supports any bar interval, each with its own trailing days range

##### `apply_to` (string or array, required)
- **Description**: Symbols to apply this historical config to
- **Valid Values**: 
  - `"all"`: Apply to all symbols in `session_data_config.symbols`
  - `["AAPL", "RIVN"]`: Apply to specific symbols only
- **Default Behavior**: Historical data configs apply to ALL symbols unless targeted

#### `historical.indicators` (object, optional)
- **Description**: Historical indicators (depend only on prior data, no future data) calculated by session_coordinator before EVERY session
- **Code Default**: `{}` (no indicators)
- **Structure**: Each key is indicator name, value is configuration object
- **Definition**: Historical = depends ONLY on data prior to current session
- **Calculation Frequency**: 
  - Computed BEFORE EVERY SESSION (daily or per session)
  - Ensures trailing windows are accurate (e.g., "last 10 days" shifts daily)
- **Data Management**: 
  - Session Coordinator drops old data outside requested window, adds new data
  - Or simpler: Clear and reload all historical data + recalculate indicators each session
- **Intelligent Augmentation**: Session Coordinator automatically adds required historical data to `session_config` if not present
  - Example: If `avg_volume_intraday` (minute granularity) is requested but `historical.data` lacks trailing 1m bars, coordinator adds them automatically
- **Access Pattern**: Indicators stored with fast indexed access (e.g., by time: 9:00 AM, 9:01 AM)
- **Analysis Engine Usage**: Can calculate index for desired time and access data directly via index

##### Indicator Types

**1. Trailing Average (Daily Granularity)**
```json
"avg_volume": {
  "type": "trailing_average",
  "period": "10d",
  "granularity": "daily",
  "field": "volume",
  "skip_early_close": true
}
```
- **period**: `"Nd"` = N trading days, `"Nw"` = N weeks
- **granularity**: `"daily"` = one value per day
- **skip_early_close**: If true, exclude early close days from average

**2. Trailing Average (Intraday Granularity)**
```json
"avg_volume_intraday": {
  "type": "trailing_average",
  "period": "10d",
  "granularity": "minute",
  "field": "volume"
}
```
- **granularity**: `"minute"` = average for every minute of the day
- **Result**: Array of 390 values (one per minute of trading day)
- **Use Case**: Compare current minute's volume to historical average for that minute

**3. Trailing Max/Min**
```json
"high_52w": {
  "type": "trailing_max",
  "period": "52w",
  "field": "high"
},
"low_52w": {
  "type": "trailing_min",
  "period": "52w",
  "field": "low"
}
```
- **period**: `"Nw"` = N weeks, `"Nm"` = N months, `"Ny"` = N years
- **field**: Which OHLCV field to track

---

### `session_data_config.gap_filler` (object, optional)

**⚠️ CRITICAL**: 
- Gap filling is **LIVE MODE ONLY**. In backtest mode, quality is calculated but gaps are NOT filled.
- Gap filling requires `enable_session_quality=true`. When session quality is disabled, no gap detection occurs.

#### `max_retries` (integer, optional)
- **Description**: Maximum attempts to fill a detected data gap
- **Code Default**: `5`
- **Valid Range**: `1-20`
- **Applies To**: LIVE MODE ONLY

#### `retry_interval_seconds` (integer, optional)
- **Description**: Interval between gap fill retry attempts in live mode
- **Code Default**: `60` (1 minute)
- **Valid Range**: `>= 1`
- **Applies To**: LIVE MODE ONLY
- **Note**: Gap filling attempts occur in background without blocking data pipeline

#### `enable_session_quality` (boolean, optional)
- **Description**: Enable quality calculation for current session bars (streamed/generated)
- **Code Default**: `true`
- **Valid Values**: `true`, `false`
- **Applies To**: Both backtest and live modes
- **When Disabled**: All session bars assigned 100% quality score (no gap detection)
- **When Enabled**: Data quality manager calculates quality in real-time (event-driven)
- **Note**: Gap filling requires this to be enabled (live mode only)
- **Behavior**: Always event-driven; non-blocking background operation

---

### `trading_config` (object, required)

#### `max_buying_power` (float, required)
- **Description**: Total capital available for trading
- **Code Default**: `None` (must be provided)
- **Unit**: USD (or account currency)
- **Validation**: Must be > 0

#### `max_per_trade` (float, required)
- **Description**: Maximum capital for a single trade
- **Code Default**: `None` (must be provided)
- **Validation**: Must be > 0 and <= `max_buying_power`

#### `max_per_symbol` (float, required)
- **Description**: Maximum capital exposure per symbol
- **Code Default**: `None` (must be provided)
- **Validation**: Must be > 0 and <= `max_buying_power`

#### `max_open_positions` (integer, required)
- **Description**: Maximum number of concurrent open positions
- **Code Default**: `None` (must be provided)
- **Validation**: Must be > 0

---

### `api_config` (object, required)

#### `data_api` (string, required)
- **Description**: Data provider for market data
- **Code Default**: `"alpaca"`
- **Valid Values**: `"alpaca"`, `"schwab"`, `"polygon"`, `"local"`

#### `trade_api` (string, required)
- **Description**: Broker API for order execution
- **Code Default**: `"alpaca"`
- **Valid Values**: `"alpaca"`, `"schwab"`, `"paper"` (paper trading)

---

### `metadata` (object, optional)

#### `created_by` (string, optional)
- **Description**: User or system that created this configuration
- **Code Default**: `"system"`

#### `description` (string, optional)
- **Description**: Human-readable description of session purpose
- **Code Default**: `""`

#### `strategy` (string, optional)
- **Description**: Trading strategy name/identifier
- **Code Default**: `""`

#### `version` (string, optional)
- **Description**: Configuration version for tracking changes
- **Code Default**: `"1.0"`

---

## Architecture Rules (CRITICAL)

### 1. Session Coordinator Marks Streamed vs Generated Data
- **Rule**: Session Coordinator determines what's streamed vs generated based on mode and availability
- **Backtest**: Stream smallest base interval (1s > 1m > 1d), optional quotes, NO ticks
- **Live**: Stream what API provides, generate rest
- **Marking**: Each stream marked as `STREAMED`, `GENERATED`, or `IGNORED`
- **Communication**: Data Processor knows what to generate, Data Quality Manager knows what to validate

### 2. Session Coordinator Updates Historical Data & Indicators Before EVERY Session
- **Definition**: Historical = depends ONLY on data prior to current session (no future data)
- **Timing**: BEFORE EVERY SESSION (daily or per session in backtest)
- **Purpose**: Maintain accurate trailing windows (e.g., "last 10 days" shifts daily)
- **Data Management**: 
  - Drop old data outside requested trailing window, add new data
  - Or simpler: Clear and reload all historical data + recalculate indicators
- **Intelligent Augmentation**: Automatically adds required historical data to session_config if missing
- **Example**: If `avg_volume_intraday` requested but 1m bars missing, coordinator adds them
- **Storage**: Fast indexed access (by time) for O(1) lookup by Analysis Engine
- **Scope**: ONLY historical indicators (prior data), NOT real-time indicators (during session)

### 3. Session Coordinator Loads Its Own Stream Queues
- **Rule**: Session Coordinator is responsible for loading its own input queues (NOT system_manager)
- **Timing**: BEFORE EVERY SESSION in initialization phase
- **Backtest Mode**: 
  - Coordinator loads queues with up to `prefetch_days` of data
  - Uses existing `start_bars()`, `start_ticks()`, `start_quotes()` APIs
  - Follows "use API as much as possible" principle
- **Live Mode**: 
  - Coordinator starts API streams using existing stream APIs
  - No queue preloading needed
- **System Manager**: Does NOT preload queues anymore (coordinator's responsibility)

### 4. Data Processor Computes Real-Time Derivatives & Indicators
- **Scope**: Generate derivative bars + calculate **real-time** indicators, NO quality management, NO historical indicators
- **Event-Driven**: Waits for data arrival, processes immediately
- **Subscriber Pattern**: One-shot subscriptions, must signal ready for next notification
- **Gating**: Can gate stream in backtest when speed > 0 (clock-driven)
- **Priority**: Processes intervals in ascending order (5m before 15m)

### 5. Data Quality Manager Manages Quality
- **Responsibility**: ALL data quality (measurement, gap detection, gap filling)
- **Quality Scope**: ONLY streamed bar data (1s, 1m, 1d), NOT generated, NOT ticks/quotes
- **Event-Driven**: Updates quality when data arrives
- **Output**: Quality percentage per symbol, available to all (especially Analysis Engine)
- **Configuration**: Via `session_data_config.gap_filler`

### 6. Time Operations via TimeManager Only
- **Current Time**: `time_manager.get_current_time()`, NEVER `datetime.now()`
- **Trading Hours**: `time_manager.get_trading_session()`, NEVER hardcode 9:30/16:00
- **Holidays**: `time_manager.is_holiday()`, NEVER manual checks
- **Timezone**: Automatically derived and stored in `system_manager.timezone`
  - Updated via API when `exchange_group` or `asset_class` changes
  - NEVER update `timezone` directly

### 7. Thread Synchronization: Event-Based One-Shot Subscriptions

**Data Flow**: `session_coordinator → data_processor → analysis_engine`

**Two Operation Modes**:
- **Data-Driven (speed=0)**: Subsequent threads BLOCK previous threads when not ready
- **Clock-Driven (speed>0 or live)**: No blocking, but detect and raise overrun errors

**Core Pattern: One-Shot Subscription**
```python
class StreamSubscription:
    """One-shot subscription for a specific stream"""
    def __init__(self, symbol, data_type, interval=None):
        self.symbol = symbol
        self.data_type = data_type  # 'bars', 'ticks', 'quotes', 'indicator'
        self.interval = interval  # For bars only
        self.ready_event = threading.Event()
        self.ready_event.set()  # Initially ready
        
    def signal_ready(self):
        """Consumer: Signal ready for next data"""
        self.ready_event.set()
        
    def wait_until_ready(self, mode, timeout=1.0):
        """Producer: Wait for consumer to be ready (one-shot)"""
        if mode == 'data_driven':
            # Blocking wait
            if not self.ready_event.wait(timeout):
                raise TimeoutError(f"Consumer timeout: {self.symbol} {self.data_type}")
            self.ready_event.clear()  # One-shot: clear after consumed
        else:  # clock_driven or live
            # Non-blocking check
            if not self.ready_event.is_set():
                raise OverrunError(f"Consumer overrun: {self.symbol} {self.data_type}")
            self.ready_event.clear()  # One-shot: clear after consumed
```

**Selective Synchronization** (Performance Critical):
- **NOT all streams are sync points** - only those needed for generation/processing
- **Coordinator → Data Processor**: Only base intervals used for derivative generation (e.g., 1m bars)
- **Data Processor → Analysis Engine**: Only streams analysis engine explicitly subscribes to
- Non-subscribed streams flow freely with no synchronization overhead

**Zero-Copy Data Flow** (Performance Critical):
```python
class SessionData:
    def __init__(self):
        # Fast containers: deque for O(1) append
        self.bars = defaultdict(lambda: defaultdict(deque))  # {symbol: {interval: deque}}
        
    def append_bar(self, symbol, interval, bar):
        """Append by reference (no copy)"""
        self.bars[symbol][interval].append(bar)
        
    def get_bars(self, symbol, interval):
        """Return reference to deque (no copy)"""
        return self.bars[symbol][interval]  # Reference only
```

**Usage Pattern - Coordinator → Data Processor**:
```python
class SessionCoordinator:
    def setup_data_processor_subscriptions(self):
        """Setup subscriptions for sync points only"""
        # Example: Only 1m bars used to generate 5m, 15m, etc.
        for symbol in self.symbols:
            if '1m' in self.base_intervals:
                key = (symbol, 'bars', '1m')
                self.dp_subscriptions[key] = StreamSubscription(symbol, 'bars', '1m')
                
    def stream_bar(self, symbol, interval, bar):
        """Stream bar to session_data"""
        key = (symbol, 'bars', interval)
        subscription = self.dp_subscriptions.get(key)
        
        if subscription:
            # Sync point: wait for data_processor to be ready
            subscription.wait_until_ready(mode=self.mode)
        
        # Write to session_data (by reference, no copy)
        self.session_data.append_bar(symbol, interval, bar)
        
        if subscription:
            # Notify data_processor (non-blocking)
            self.data_processor.notify_bar_available(symbol, interval)
```

**Usage Pattern - Data Processor**:
```python
class DataProcessor:
    def __init__(self):
        # Lightweight queue for notifications only (no data)
        self.notification_queue = queue.Queue()
        
    def notify_bar_available(self, symbol, interval):
        """Coordinator notifies data available (non-blocking)"""
        self.notification_queue.put(('bars', symbol, interval))
        
    def run(self):
        """Event-driven processing loop"""
        while self.active:
            # Wait for notification
            data_type, symbol, interval = self.notification_queue.get(timeout=0.1)
            
            # Read from session_data by reference (no copy)
            bars = self.session_data.get_bars(symbol, interval)
            
            # Generate derivatives
            self._generate_derivatives(symbol, interval, bars)
            
            # Signal ready for next (one-shot)
            key = (symbol, data_type, interval)
            if subscription := self.coordinator_subscriptions.get(key):
                subscription.signal_ready()
```

**Usage Pattern - Data Processor → Analysis Engine**:
```python
class AnalysisEngine:
    def setup_subscriptions(self):
        """Subscribe only to streams it needs"""
        # Example: Only 5m bars and volume indicator
        for symbol in self.symbols:
            if self.config.needs_5m_bars:
                key = (symbol, 'bars', '5m')
                self.subscriptions[key] = StreamSubscription(symbol, 'bars', '5m')
            if self.config.needs_volume_indicator:
                key = (symbol, 'indicator', 'volume')
                self.subscriptions[key] = StreamSubscription(symbol, 'indicator', 'volume')
```

**Key Benefits**:
- ✅ **Mode Flexibility**: Same code path handles both data-driven (blocking) and clock-driven (error detection)
- ✅ **Zero-Copy Performance**: Pass references, never copy data
- ✅ **Selective Sync**: Only synchronize on streams that matter (no overhead for others)
- ✅ **Explicit Flow Control**: Clear producer/consumer contract
- ✅ **Overrun Detection**: Clock-driven mode detects when consumer can't keep up
- ✅ **Minimal Overhead**: Event-based, no polling, notifications only (no data in queue)

#### Required TimeManager API for Backtest Initialization

The following TimeManager methods are required to support the backtest date handling logic:

**1. Get First Trading Date (NEW - Required)**
```python
def get_first_trading_date(
    self, 
    session, 
    from_date: date, 
    exchange: str = 'NYSE'
) -> date:
    """Returns the first valid trading day from the given date (inclusive).
    
    If from_date is already a trading day, returns it.
    Otherwise, returns the next trading day after it.
    """
```
- **Used to convert reference dates to actual trading days**
- If `from_date` is already a trading day, **returns it** (inclusive)
- If `from_date` is weekend/holiday, returns next trading day

**Note:** Existing `get_next_trading_date()` is **exclusive** (starts from `from_date + 1 day`), which is NOT what we need for backtest initialization.

**2. Get Session Start/End Times (NEW - if not exists)**
```python
def get_backtest_start_time(
    self, 
    session, 
    reference_date: date, 
    exchange: str = 'NYSE'
) -> datetime:
    """
    Returns the market open datetime for the first trading day 
    on or after the reference date.
    
    Logic:
    - Find next trading day from reference_date
    - Get trading session for that day
    - Combine date + regular_open time
    - Return timezone-aware datetime
    """
```

```python
def get_backtest_end_time(
    self, 
    session, 
    reference_date: date, 
    exchange: str = 'NYSE'
) -> datetime:
    """
    Returns the market close datetime for the trading day 
    on or after the reference date.
    
    Logic:
    - If reference_date is a trading day, use it; else find next
    - Get trading session for that day
    - Combine date + regular_close time
    - Return timezone-aware datetime
    """
```

**3. Alternative: Generic Session Boundary Method (RECOMMENDED)**
```python
def get_session_boundary_times(
    self,
    session,
    start_ref_date: date,
    end_ref_date: date,
    exchange: str = 'NYSE'
) -> tuple[datetime, datetime]:
    """
    Returns (start_datetime, end_datetime) for a backtest window.
    
    Args:
        start_ref_date: Reference date for backtest start
        end_ref_date: Reference date for backtest end
        
    Returns:
        Tuple of (market_open_datetime, market_close_datetime)
        
    Implementation:
        Uses get_first_trading_date() for both dates to ensure
        if the reference date is already a trading day, it's used.
        
    Example:
        start, end = time_mgr.get_session_boundary_times(
            session, 
            date(2025, 7, 5),  # Saturday
            date(2025, 7, 5)   # Saturday
        )
        # Returns: (2025-07-07 09:30:00 ET, 2025-07-07 16:00:00 ET)
        
        start, end = time_mgr.get_session_boundary_times(
            session,
            date(2025, 7, 2),  # Wednesday (trading day)
            date(2025, 7, 2)   # Wednesday (trading day)
        )
        # Returns: (2025-07-02 09:30:00 ET, 2025-07-02 16:00:00 ET)
    """
```

**Usage in Session Initialization**:
```python
# In system_manager.py or session initialization code
config = load_session_config()
time_mgr = self.get_time_manager()

# Get database session
db_session = SessionLocal()
try:
    # Get actual backtest window with market hours
    start_time, end_time = time_mgr.get_session_boundary_times(
        db_session,
        config['backtest_config']['start_date'],
        config['backtest_config']['end_date'],
        exchange=config.get('exchange_group', 'US_EQUITY')
    )
    
    # Set backtest clock to start
    time_mgr.set_backtest_time(start_time)
    
    # Store for session tracking
    self.backtest_start = start_time
    self.backtest_end = end_time
finally:
    db_session.close()
```

### 8. No Settings Defaults for Session Config
- **Rationale**: Session configs are explicit, self-contained documents
- **Pattern**: Defaults in source code at point of use, not in `settings.py`
- **Exception**: System-wide settings (DB connection, log level) stay in `settings.py`

---

## Implementation Principles (CRITICAL)

### 1. TimeManager for ALL Date/Time Operations
- **Rule**: Use TimeManager API for ALL date and time related operations
- **API Creation**: If needed API doesn't exist, create a generic one that may be helpful for others
- **No Timezone Conversion Outside TimeManager**: ALL timezone operations MUST be in TimeManager
- **No Hardcoded Dates/Times**: NEVER hardcode dates or times anywhere (including TimeManager itself)

**Caching Strategy (Instead of Asyncio):**
- **Performance**: TimeManager implements intelligent caching for fast responses
- **Cache Last Request**: Store most recent query results
- **Lookup Table**: Maintain cache of several recent queries (LRU or similar)
- **Cache Keys**: 
  - Trading sessions: `(date, exchange)` → TradingSession object
  - Trading dates: `(from_date, exchange)` → first/next trading date
  - Market hours: `(date, exchange)` → (open_time, close_time)
- **Cache Invalidation**: Clear on session start or when needed
- **Rationale**: Avoid repeated database queries for same data (e.g., same date queried 100+ times during session)

**Examples:**
```python
# ✅ CORRECT - with caching
time_mgr = system_manager.get_time_manager()
current_time = time_mgr.get_current_time()
trading_session = time_mgr.get_trading_session(session, date)  # First call: DB query
trading_session = time_mgr.get_trading_session(session, date)  # Subsequent: cached
first_trading_day = time_mgr.get_first_trading_date(session, ref_date)

# ❌ WRONG
now = datetime.now()  # FORBIDDEN
market_open = time(9, 30)  # FORBIDDEN
tz = pytz.timezone('US/Eastern')  # FORBIDDEN - use TimeManager
```

**Cache Implementation Guidelines:**
```python
# Example cache structure in TimeManager
class TimeManager:
    def __init__(self):
        # LRU cache for trading sessions (last N queries)
        self._trading_session_cache = {}  # {(date, exchange): TradingSession}
        self._cache_max_size = 100  # Keep last 100 queries
        
        # Last query result (most common case: same date repeatedly)
        self._last_session_query = None
        self._last_session_result = None
    
    def get_trading_session(self, session, date, exchange='NYSE'):
        # Check last query first (O(1), most common)
        if self._last_session_query == (date, exchange):
            return self._last_session_result
        
        # Check cache
        cache_key = (date, exchange)
        if cache_key in self._trading_session_cache:
            result = self._trading_session_cache[cache_key]
            self._last_session_query = cache_key
            self._last_session_result = result
            return result
        
        # Query database (cache miss)
        result = self._query_trading_session_from_db(session, date, exchange)
        
        # Update cache
        self._trading_session_cache[cache_key] = result
        self._last_session_query = cache_key
        self._last_session_result = result
        
        # Evict old entries if cache too large
        if len(self._trading_session_cache) > self._cache_max_size:
            self._evict_oldest_entry()
        
        return result
```

### 2. Database Storage & Timezone Handling
- **Storage Format**: ALL databases store dates/times in **UTC**
- **Timezone Storage**: Also store timezone for times (e.g., market open/close times)
- **Delivery Format**: Deliver all datetime objects in `system_manager.timezone`
- **Safe Comparisons**: Within the system, all time comparisons are safe (no timezone worry)
- **Rationale**: Single timezone (`system_manager.timezone`) for all in-memory operations

**Database Schema Pattern:**
```python
# Example: TradingSession model
class TradingSession:
    date = Column(Date)  # UTC
    regular_open = Column(Time)  # Store with timezone info
    regular_close = Column(Time)  # Store with timezone info
    timezone = Column(String)  # e.g., "America/New_York"
    
    # When queried, TimeManager converts to system_manager.timezone
```

**Query Pattern:**
```python
# TimeManager handles conversion when delivering data
trading_session = time_mgr.get_trading_session(session, date)
# Returns times already converted to system_manager.timezone
# Safe to compare: if current_time >= trading_session.regular_open
```

### 3. Module Access Patterns: API vs Direct Access

#### Default: Use APIs
- **Rule**: Access other modules/managers through their API
- **Rationale**: Encapsulation, maintainability, flexibility

```python
# ✅ CORRECT - API access
time_mgr = system_manager.get_time_manager()
current_time = time_mgr.get_current_time()
data_mgr = system_manager.get_data_manager()
bars = data_mgr.get_bars(symbol, interval)
```

#### Exception: Critical Path Performance
- **When**: Sub-second access frequency (e.g., hundreds/thousands of times per second)
- **Examples**: 
  - Advancing backtest time in tight loop
  - Accessing current date during streaming
  - Reading/writing to session_data during data pipeline
- **Justification Required**: Must demonstrate performance necessity

```python
# ✅ ACCEPTABLE for critical path (with justification)
# Example: Advancing backtest time in streaming loop
time_mgr._current_time = next_bar_timestamp  # Direct access for performance

# Example: Writing to session_data during pipeline
session_data._bars[symbol].append(bar)  # Direct access for performance

# ❌ NOT JUSTIFIED
config_value = system_manager._config['some_field']  # Use API instead
```

**Decision Criteria:**
1. **Frequency**: Is this accessed 100+ times per second?
2. **Critical Path**: Is this in the data pipeline (stream → session_data → analysis)?
3. **Profiling**: Have you measured and confirmed the performance bottleneck?
4. **Documentation**: Document WHY direct access is necessary

### 4. Session Data Access Pattern

**⚠️ CRITICAL Rule**: Analysis Engine accesses data ONLY from session_data

**What session_data Is**:
- **Unified data store** for ALL session analysis data
- Contains BOTH historical data (trailing periods) AND current session data
- NOT just "today's data" - it's ALL data needed for current session decisions
- Contains all data available up to current time (NO future data)

**Data Flow**:
```
Coordinator Input Queues → session_data → Analysis Engine
                ↓
         Data Processor writes derived data/indicators
                ↓
         Data Quality Manager writes quality metrics
```

**Access Rules**:
- ✅ **Analysis Engine**: Reads ONLY from session_data (never from queues or other threads)
- ✅ **All Threads**: Write to session_data (by reference, zero-copy)
- ✅ **session_data is the single interface** between data pipeline and analysis
- ❌ **Never**: Analysis engine reads directly from coordinator queues
- ❌ **Never**: Analysis engine reads directly from other threads

**What's in session_data**:
1. Historical bars (trailing days loaded before session)
2. Historical indicators (pre-calculated before session)
3. Current session bars (arriving during session)
4. Real-time indicators (calculated during session)
5. Derived intervals (5m from 1m, etc.)
6. Quality metrics

### 5. Performance: Data Pipeline is Paramount

**Critical Path**: `coordinator_queues → session_data → analysis_engine`

**Performance Requirements:**
- **Minimize Copying**: Use references, views, or in-place operations
- **Fast Containers**: 
  - Use `deque` for queues (O(1) append/pop)
  - Use `dict` for O(1) lookups
  - Use `list` for indexed access
  - Consider `numpy` arrays for numerical data
- **Event-Driven**: Avoid polling, use notifications/callbacks
- **Avoid Blocking**: Never block the critical path
- **Memory Efficiency**: Minimize allocations in hot loops

**Examples:**

```python
# ✅ CORRECT - Coordinator queue to session_data migration (zero-copy)
def stream_from_queue(self):
    # Get bar object reference from queue (bar data not copied)
    bar = self._input_queue.get()
    # Append same reference to session_data deque (bar data not copied)
    self._session_data.append_bar(symbol, interval, bar)
    # Result: One bar object in memory, referenced by session_data deque
    # Notify subscribers (event-driven)
    self._notify_subscribers(symbol, 'bar')

# ✅ CORRECT - Analysis Engine reading from session_data (zero-copy)
def analyze(self):
    # Get deque reference from session_data (no copy)
    bars = self._session_data.get_bars(symbol, interval)
    # Iterate over deque, accessing bar references (no copy)
    for bar in bars:
        price = bar.close  # Direct attribute access on same object

# ❌ WRONG - Copying data unnecessarily
def on_bar_received(self, bar):
    # Creates a NEW list and copies all references
    bars_copy = list(self._session_data.bars[symbol])
    bars_copy.append(bar)
    self._session_data.bars[symbol] = bars_copy
    # Polling-based notification (inefficient)
    while not self._check_if_ready():
        time.sleep(0.001)
```

**Zero-Copy Clarification:**
- **What Zero-Copy Means**: Bar/tick/quote object data (OHLCV, timestamp, etc.) is not duplicated in memory
- **What Actually Happens**: Object references (memory addresses) are passed between containers
- **Queue → Deque**: `queue.get()` returns reference; `deque.append()` stores same reference
- **Memory Benefit**: One 1m bar object (~50 bytes) vs. 10,000 copies = saves ~500KB per symbol
- **NOT Zero-Copy**: Creating new derived bars (5m from 1m) requires new objects, but source bars not copied

**Container Selection Guide:**
- **Queue operations**: `collections.deque`
- **Fast lookups**: `dict` or `set`
- **Indexed access**: `list`
- **Numerical operations**: `numpy.ndarray`
- **Time series**: Consider `pandas.DataFrame` for historical (NOT real-time)

**Benchmarking Requirement:**
- Profile hot paths with `cProfile` or `py-spy`
- Measure throughput (bars/second)
- Measure latency (time from bar arrival to analysis)
- Target: Handle 1000+ bars/second per symbol

### 6. Performance Monitoring Instrumentation

**Purpose**: Track critical path performance to identify bottlenecks and plan future optimizations

**Key Metrics to Track:**

#### 1. Analysis Engine Performance (Measured by data_processor)
- **What**: Time from notification sent to ready signal received
- **Granularity**: Per analysis cycle (min/max/avg)
- **Measurement Point**: `data_processor` thread
- **Implementation**: 
  ```python
  notify_time = time.perf_counter()
  # Send notification to analysis_engine
  subscription.wait_until_ready()  # Blocks until ready
  processing_time = time.perf_counter() - notify_time
  # Track: min, max, avg, count
  ```

#### 2. Data Processor Performance (Measured by coordinator)
- **What**: Time from data delivery to ready signal received
- **Granularity**: Per data item (min/max/avg)
- **Measurement Point**: `session_coordinator` thread
- **Implementation**:
  ```python
  delivery_time = time.perf_counter()
  # Deliver data to data_processor queue
  subscription.wait_until_ready()  # Blocks until ready
  processing_time = time.perf_counter() - delivery_time
  # Track: min, max, avg, count
  ```

#### 3. Data Loading Performance
- **Initial Data Load**: Time to load ALL historical data at backtest start
  - Measure: Start of first historical data load to completion (all symbols)
  - Track: Single time value for initial load
  - Includes: Historical bars + indicators + quality assignment + queue prefetch
- **Subsequent Data Load**: Time to load data between sessions
  - Measure: Start of historical data update to completion (all symbols)
  - Track: Min/max/avg across all sessions (after first session)
  - Includes: Historical bars update + indicators recalc + quality assignment + queue reload
  - Note: May be faster than initial load depending on algorithm (drop/add vs clear/reload)

#### 4. Session Lifecycle Timing
- **Session Gap**: Time from session inactive to active again
  - Measure: End of session deactivation to start of next session activation
  - Track: Per session gap (between trading days)
  - Components: Historical update + indicator calculation + quality assignment + queue load
- **Active Session Duration**: Time session is active (market open to close)
  - Measure: Session activation to deactivation
  - Track: Per session (min/max/avg across all sessions)
  - Expected: ~6.5 hours for regular sessions

#### 5. Backtest Summary Metrics
- **Total Backtest Time**: Wall clock time from backtest start to completion
  - Measure: First session start to last session end
  - Track: Single value per backtest run
- **Average Time Per Trading Day**: Total backtest time / number of trading days
  - Measure: Derived from total time and session count
  - Track: Single value per backtest run
  - Helps: Compare performance across different backtest configurations

**Reporting Format:**
```
Performance Metrics Summary:
==================================================
Analysis Engine:
  - Cycles: 15,234
  - Min: 0.12 ms | Max: 45.67 ms | Avg: 2.34 ms
  
Data Processor:
  - Items: 30,468
  - Min: 0.08 ms | Max: 23.45 ms | Avg: 1.12 ms
  
Data Loading (All Symbols):
  - Initial Load: 1.23 s
  - Subsequent Load: Avg: 0.87 s | Min: 0.65 s | Max: 1.05 s
  
Session Lifecycle:
  - Sessions: 5
  - Avg Gap: 1.23 s | Min: 0.98 s | Max: 1.67 s
  - Avg Duration: 6.45 hrs | Min: 6.40 hrs | Max: 6.50 hrs
  
Backtest Summary:
  - Total Time: 12.34 s
  - Trading Days: 5
  - Avg per Day: 2.47 s
==================================================
```

**Implementation Notes:**
- Use `time.perf_counter()` for high-resolution timing
- Track min/max/avg using running statistics (avoid storing all values)
- Log metrics at session end and backtest end
- Consider exposing metrics via API for real-time monitoring
- Store metrics in session_data for access by other threads
- Reset metrics at start of each session (except backtest summary)
- **Data Loading**: 
  - Initial load is first session only (one-time measurement)
  - Subsequent loads are all sessions after first (min/max/avg tracked)
  - Subsequent may be faster if using drop/add algorithm vs clear/reload

**Critical Path Focus:**
- **Highest Priority**: Analysis Engine and Data Processor timings (directly impact backtest speed)
- **Medium Priority**: Data loading times (impacts session startup)
- **Lower Priority**: Session gaps and totals (informational, not critical path)

---

## Thread Pool Details & Lifecycle

### Thread Launch Sequence

1. **SystemManager.start()**:
   - Parses `session_config` 
   - Updates internal session_config object
   - Starts **Analysis Engine** using thread pool

2. **Analysis Engine**:
   - Launches **session_coordinator.start()** using thread pool

3. **session_coordinator.start()**:
   - Calls `session_coordinator.stop()` first:
     - Stops any active streams
     - Resets backtest dates
     - Clears queues and `session_data`
   - Marks which data will be `STREAMED` vs `GENERATED` vs `IGNORED`
   - Starts **data_processor.start()** using worker thread
   - Starts **data_quality_manager.start()** using worker thread
   - Enters **SESSION_COORDINATOR_LOOP**

---

### 1. Session Coordinator Thread - SESSION_COORDINATOR_LOOP

**⚠️ CRITICAL: Initialization Phase Runs BEFORE EVERY SESSION (Each Trading Day)**

**Initialization Phase (Runs Daily/Per Session):**
1. **Intelligent Config Augmentation**: Analyzes `historical.indicators` requirements (first time only)
   - Automatically adds missing historical data types needed for indicator calculation
   - Example: If `avg_volume_intraday` (minute granularity) requested, adds trailing 1m bars if not present
   - Updates internal session_config with additional data requirements
2. **Update Historical Data** (Every Session):
   - **Option A**: Drop old data outside trailing window, add new data for current session
   - **Option B (Simpler)**: Clear all historical data, reload fresh based on trailing window config
   - Ensures only requested trailing data is available (e.g., "last 10 days" shifts daily)
   - Definition: Historical = depends ONLY on data prior to current session (no future data)
3. **Calculate Historical Indicators** (Every Session):
   - Computes ALL indicators in `historical.indicators` with updated historical data
   - Stores results with fast indexed access (e.g., by time: 9:00 AM, 9:01 AM, etc.)
   - Analysis Engine can access via index calculation (time → index → data)
4. **Assign Historical Bar Quality** (Every Session):
   - Assigns quality scores to ALL historical bars (base + derived)
   - Ensures all historical data has quality scores before session starts
   - Result: Historical bars ready with quality for analysis_engine
5. **Load Stream Queues** (Coordinator Responsibility):
   - **⚠️ IMPORTANT**: Session Coordinator loads its own queues (NOT system_manager)
   - **Backtest Mode**: 
     - Coordinator loads stream queues with up to `prefetch_days` of data
     - Uses existing `start_bar_streams()`, etc. APIs (follow "use API" principle)
     - Loads data for current session date (or up to prefetch_days ahead)
   - **Live Mode**: 
     - Coordinator starts API streams immediately using existing stream APIs (`start_bar_streams()`, etc.)
     - No queue preloading needed in live mode
   - **System Manager Does NOT Preload**: This is coordinator's responsibility now
6. Activates session (signals data_processor, data_quality_manager, analysis_engine)

**Streaming Phase:**
- Advances time and streams data
- **⚠️ CRITICAL**: Market time MUST stay within trading hours (market_open ≤ time ≤ market_close)
- Marks streamed data types per symbol based on:
  - **Backtest**: Smallest base interval (1s > 1m > 1d), quotes optional, NO ticks
  - **Live**: Whatever API provides

**Time Advancement Logic:**
- Advance time based on next data timestamp in queues
- If data exhausted OR next timestamp > market_close:
  - Automatically advance time to market_close
  - This is NOT end-of-session detection, just time management
- After each time advancement:
  - Check: `if current_time >= market_close` → End-of-Session detected
  - Check: `if current_time > market_close` → **CRITICAL ERROR** (should never happen in backtest)

**Operation Modes:**
- **Data-Driven** (speed = 0):
  - Time advances based on data timestamps
  - Threads can block previous threads (backpressure)
  - Data exhaustion triggers time advancement to market_close
- **Clock-Driven** (speed > 0):
  - Time advances at specified speed multiplier
  - If unable to deliver data, raises error but still delivers
  - Data Processor can gate stream in backtest
  - Overrun errors detected if threads can't keep up
- **Live Mode**:
  - Time advances in real-time
  - Cannot gate streamer
  - Streams as fast as API provides
  - Overrun errors detected if threads can't keep up

**End-of-Session Detection:**
- **ONLY** based on: `current_time >= market_close_time`
- Check after each time advancement: `if time_mgr.get_current_time() >= trading_session.regular_close`
- **⚠️ CRITICAL ERROR in Backtest**: If `current_time > market_close_time` (passing, not reaching):
  - Should NEVER occur in backtest mode
  - Indicates bug in time advancement logic
  - Trigger critical error and abort session

**End-of-Session Phase:**
- When end of session detected (`current_time >= market_close_time`):
  - Deactivates session
  - Advances to next trading day
  - **Returns to Initialization Phase** (updates historical data & indicators for new session)
  - **Loop continues**: Each trading day gets fresh historical data and recalculated indicators

**Termination Phase:**
- If end of backtest reached (no more trading days):
  - Triggers `data_processor.stop()`
  - Triggers `data_quality_manager.stop()`
  - Triggers `system_manager.stop()`
  - **Loop exits**: Only when backtest date range is complete

---

### 2. Data Processor Thread - Event-Driven with Subscriber Notifications

**Responsibilities:**
- Generate derivative data (5m from 1m, 10m from 1m, etc.)
- Calculate **real-time** indicators when base stream data arrives (NOT historical indicators)
- Notify subscribers when subscribed data is updated
- **Note**: Historical indicators are pre-calculated by session_coordinator before session starts

**Synchronization Pattern** (see Architecture Rules #7):
- **From Coordinator**: Receives notifications via lightweight queue (tuples only, no data)
- **From Coordinator**: Subscribes to coordinator streams (receives ready signals via `StreamSubscription`)
- **To Coordinator**: Signals ready via `subscription.signal_ready()` after processing (one-shot)
- **To Analysis Engine**: Notifies when data available (bars, indicators)
- **Mode-Aware**:
  - Data-driven (speed=0): Blocks coordinator when not ready
  - Clock-driven (speed>0 or live): Raises `OverrunError` if data arrives before processing complete
- **Zero-Copy**: Reads from session_data by reference, never copies

**Event-Driven Processing Loop:**
1. Wait on notification queue (blocking with timeout)
2. Read data from session_data (by reference, no copy)
3. Generate derivatives (5m from 1m, etc.)
4. Calculate real-time indicators
5. Signal ready to coordinator (one-shot)
6. Notify analysis engine of available data

**Scope:**
- Does NOT handle data quality (data_quality_manager responsibility)
- Focuses purely on computation and transformation

---

### 3. Data Quality Manager Thread - Quality & Gap Management

**Responsibilities:**
- Measure data quality for streamed bar data (1s, 1m, 1d)
- Generate two types of data:
  1. **Detailed gap analysis** (internal use for gap filling)
  2. **Quality percentage per symbol per data type** (for analysis_engine decisions)
- Fill detected gaps (**LIVE MODE ONLY**)
- **NO quality measurement for ticks or quotes**

**⚠️ Operating Mode:**
- **Backtest Mode**: Quality calculation ONLY (gap filling turned OFF)
- **Live Mode**: Quality calculation AND gap filling (attempts to improve quality scores)
- Thread is ACTIVE in both modes, but gap filling disabled in backtest

**⚠️ Quality Calculation Control:**
- **Historical Quality**: Controlled by `historical.enable_quality` config (in session_data_config)
  - If disabled: All historical bars assigned 100% quality score
  - If enabled: Coordinator calculates actual quality before session start
- **Session Quality**: Controlled by `gap_filler.enable_session_quality` config
  - If disabled: All session bars assigned 100% quality score (no gap detection)
  - If enabled: Data quality manager calculates quality in real-time
- **Default**: Both enabled (`true`)
- **Performance**: Disabling quality calculation saves CPU cycles if quality not needed

**Quality Measurement:**
- **Always Event-Driven**: Updates when data arrives (no periodic mode)
- **Scope**: Quality measurement done ONLY on **STREAMED** bar intervals (NOT derived bars, NOT ticks/quotes)
- **Output**: Percentage quality score **per symbol, per data type**
  - Example: `AAPL 1m bars: 98.5%`, `RIVN 1m bars: 100%`
  - **NOT** overall quality across all symbols (not useful for analysis)
- **Derived Bar Quality**: Copied from base bars and updated when base quality changes
  - When 1m bar quality changes, data_quality_manager copies score to all derived intervals (5m, 15m, etc.)
  - Example: If 1m bars = 98% quality, then 5m and 15m bars also get 98% quality score
  - From consumer perspective: Each bar data set has its own quality score (don't need to know if derived)
- **Historical Bar Quality**: Checked by session_coordinator before session start
  - Coordinator assigns quality scores to all historical bars before session begins
  - Ensures all historical data has quality scores ready for use
- **Data Type**: Only applies to bar data (NOT quotes or ticks)
- **Result**: ALL bar type data (historical + current session, base + derived) have associated quality scores
- **Usage**: Analysis Engine can factor quality into decision-making without caring about source

**Gap Analysis (Internal):**
- **Purpose**: Detailed gap detection and tracking for gap filling operations
- **Scope**: STREAMED bar data only
- **Output**: Internal data structure with gap locations, timestamps, retry counts
- **Not Published**: This detailed analysis is for data_quality_manager internal use only

**Gap Filling (LIVE MODE ONLY):**
- **Backtest Mode**: Gap filling DISABLED (quality calculation only)
- **Live Mode**: Attempts fill every `retry_interval_seconds` (default 60s) IF `enable_session_quality=true`
  - If session quality disabled: No gap detection, no gap filling
  - If session quality enabled: Gap detection active, gap filling attempts in background
- **Retry Logic**: Up to `max_retries` attempts (default 5)
- **Process**:
  1. Detect missing bars in streamed data (uses detailed gap analysis)
  2. Query API for missing data
  3. Store in database
  4. Notify session_coordinator to re-stream
  5. Update quality percentage after fill
- **Failure**: Log and mark gap as unfillable after max retries
- **Background Operation**: Gap filling runs in background, does not block data pipeline

**Non-Blocking Background Operation:**
- **Event-Driven**: Processes quality checks when data arrives
- **No Gating**: Does NOT block coordinator or data_processor (unlike data_processor which gates coordinator)
- **No Ready Signals**: Does NOT signal ready to any thread
- **Best Effort**: Updates quality scores in background as fast as possible
- **Live Mode**: Attempts gap filling in background to improve quality scores over time
- Quality updates appear in session_data as they are calculated

---

### 4. Analysis Engine Thread

**Responsibilities:**
- Consume processed data from session_data
- Generate trading signals
- Make trading decisions

**⚠️ CRITICAL: Analysis Engine accesses data ONLY from session_data**
- Never reads from coordinator input queues
- Never reads directly from data_processor or other threads
- **session_data is the single interface** for all analysis data

**Synchronization Pattern** (see Architecture Rules #7):
- **Selective Subscriptions**: Only subscribes to streams it needs (e.g., 5m bars, specific indicators)
- **From Data Processor**: Receives notifications via lightweight queue (tuples only, no data)
- **To Data Processor**: Signals ready via `subscription.signal_ready()` after processing (one-shot)
- **Mode-Aware**:
  - Data-driven (speed=0): Blocks data_processor when not ready
  - Clock-driven (speed>0 or live): Raises `OverrunError` if data arrives before processing complete
- **Zero-Copy**: Reads from session_data by reference, never copies

**Data Access (ALL from session_data)**:
- **Historical Bars**: Trailing days loaded before session (e.g., last 10 days of 1m bars)
- **Historical Indicators**: Pre-calculated indicators (e.g., 10-day moving average up to session start)
- **Current Session Bars**: Bars arriving during today's session (base + derived)
- **Real-Time Indicators**: Indicators calculated during session as new bars arrive
- **Quality Metrics**: Quality percentage per symbol per data type (e.g., AAPL 1m: 98.5%)
  - ALL bar data sets have associated quality scores (historical + current, base + derived)
  - Each bar data set comes with its own quality score (consumer doesn't need to know if derived)
  - Can factor quality into trading decisions for any bar type

**Historical Indicator Access:**
- Pre-calculated indicators stored with fast indexed access
- Analysis Engine calculates index for desired time (e.g., 9:00 AM → index N)
- Direct array/dict access via index for O(1) lookup performance
- Example: `historical_avg_volume[time_to_index("09:00")]`

**Event-Driven Processing Loop:**
1. Wait on notification queue (blocking with timeout)
2. Read data from session_data (by reference, no copy)
3. Access historical indicators via fast index
4. Generate trading signals
5. Signal ready to data_processor (one-shot)

**Configuration:**
- Initial state via `historical.indicators` (calculated by session_coordinator)
- Real-time updates as data arrives (calculated by data_processor)

---

## Configuration Migration from Old Format

### Removed Fields
- `data_streams`: Replaced by `symbols` + `streams` (flat array)
- `session_data_config.data_upkeep`: Replaced by `session_data_config.gap_filler`
- `session_data_config.data_upkeep.derived_intervals`: Coordinator now marks generated data
- `session_data_config.data_upkeep.auto_compute_derived`: Implicit
- `session_data_config.data_upkeep.gap_detection_threshold`: Moved to `gap_filler`
- `session_data_config.data_upkeep.quality_check_interval`: Replaced by event-driven quality
- `prefetch_manager` configs: No more async prefetch

### Renamed Fields
- `data_upkeep.max_gap_fill_retries` → `gap_filler.max_retries`

### New Fields
- `backtest_config.prefetch_days`: Synchronous prefetch in session_coordinator loop (min 1 day)
- `session_data_config.streams`: Flat array of all requested streams (bars + market data)
- `session_data_config.gap_filler`: Configuration for gap-filler thread
- `gap_filler.retry_interval_seconds`: Gap fill retry interval for live mode
- `gap_filler.quality_update_frequency`: Event-driven vs periodic quality updates

### Changed Behavior
- **session_coordinator marks data**: `STREAMED` vs `GENERATED` vs `IGNORED` based on mode
- **streams applies to ALL symbols**: No per-symbol stream configuration
- **historical applies to ALL symbols**: Unless targeted via `apply_to`
- **No async prefetch**: session_coordinator loads data synchronously at session start
- **Event-driven data_processor**: One-shot subscriptions, must signal ready
- **Quality in data_quality_manager**: data_processor no longer measures quality

---

## Configuration Validation

### Load-Time Validation
```python
# Example validation logic (to be implemented)
def validate_session_config(config: dict) -> tuple[bool, list[str]]:
    errors = []
    
    # Required fields
    if "session_name" not in config:
        errors.append("Missing required field: session_name")
    
    # Mode-specific validation
    if config.get("mode") == "backtest":
        if "backtest_config" not in config:
            errors.append("backtest mode requires backtest_config")
        else:
            if "start_date" not in config["backtest_config"]:
                errors.append("backtest_config missing start_date")
    
    # Architecture rules
    bars = config.get("session_data_config", {}).get("streams", {}).get("bars", [])
    if bars and bars != ["1m"]:
        errors.append(f"streams.bars must be ['1m'], got {bars}")
    
    # Trading config validation
    trading = config.get("trading_config", {})
    if trading.get("max_per_trade", 0) > trading.get("max_buying_power", 0):
        errors.append("max_per_trade cannot exceed max_buying_power")
    
    return len(errors) == 0, errors
```

---

## Default Values Summary

| Field | Code Default | Notes |
|-------|--------------|-------|
| `exchange_group` | `"US_EQUITY"` | Safe default, auto-updates timezone |
| `asset_class` | `"EQUITY"` | Safe default, auto-updates timezone |
| `mode` | `"backtest"` | Safe default (non-destructive) |
| `backtest_config.start_date` | `None` | Must provide in backtest mode |
| `backtest_config.end_date` | `None` | Must provide in backtest mode |
| `backtest_config.speed_multiplier` | `1.0` | Real-time speed |
| `backtest_config.prefetch_days` | `1` | Min 1 day prefetch |
| `session_name` | `None` | Must provide |
| `symbols` | `[]` | Must provide at least one |
| `streams` | `[]` | Must provide at least one, applies to ALL symbols |
| `historical.data` | `[]` | No historical by default |
| `historical.indicators` | `{}` | No indicators by default |
| `gap_filler.max_retries` | `5` | Both backtest and live |
| `gap_filler.retry_interval_seconds` | `60` | Live mode only |
| `gap_filler.quality_update_frequency` | `"event"` | Event-driven |
| `trading_config.*` | `None` | Must provide all |
| `api_config.data_api` | `"alpaca"` | Safe default |
| `api_config.trade_api` | `"alpaca"` | Safe default |
| `metadata.*` | Various | Optional |

---

## Implementation Checklist

### Phase 1: Configuration Loading & TimeManager
- [ ] Create `SessionConfig` class with validation
- [ ] Implement field validation logic
- [ ] session_coordinator marking logic: determine `STREAMED` vs `GENERATED` vs `IGNORED`
- [ ] Create config file loader with error handling
- [ ] Add default value application logic
- [ ] **Implement TimeManager Caching (instead of asyncio)**:
  - [ ] Implement last-query cache (most common case: same date repeatedly)
  - [ ] Implement LRU cache for trading sessions (cache key: `(date, exchange)`)
  - [ ] Implement cache for trading dates lookups
  - [ ] Implement cache for market hours
  - [ ] Cache size: ~100 entries per cache type
  - [ ] Cache invalidation on session start
- [ ] Implement `TimeManager.get_first_trading_date()` (inclusive date finding, with caching)
- [ ] Implement `TimeManager.get_session_boundary_times()` for backtest date resolution (with caching)

### Phase 1a: Session Data Implementation
- [ ] **Create session_data unified data store**:
  - [ ] Implement fast containers for bars (`defaultdict` of `deque`)
  - [ ] Implement storage for historical indicators (indexed for O(1) access)
  - [ ] Implement storage for real-time indicators
  - [ ] Implement storage for quality metrics (per symbol, per data type)
  - [ ] Support zero-copy access (return references, not copies)
- [ ] **Implement session_data API**:
  - [ ] `append_bar(symbol, interval, bar)` - append by reference
  - [ ] `get_bars(symbol, interval)` - return deque reference
  - [ ] `get_bar_at_index(symbol, interval, index)` - O(n) for deque but fast for recent
  - [ ] `set_historical_indicator(name, data)` - store with indexed access
  - [ ] `get_historical_indicator(name, time_index)` - O(1) lookup
  - [ ] `set_realtime_indicator(symbol, name, value)` - update real-time indicator
  - [ ] `set_quality_metric(symbol, data_type, percentage)` - set quality for symbol+data_type
  - [ ] `get_quality_metric(symbol, data_type)` - get quality percentage (e.g., AAPL, '1m')
- [ ] **Implement lifecycle management**:
  - [ ] Create at session start
  - [ ] Clear at session end (via `session_coordinator.stop()`)
  - [ ] Reload historical data before each session
- [ ] **Document critical rule**: Analysis Engine accesses ONLY from session_data (never from queues)

### Phase 2: Session Coordinator Refactor
- [ ] Rename `BacktestStreamCoordinator` → `session_coordinator`
- [ ] Implement thread launch sequence (SystemManager → analysis_engine → session_coordinator)
- [ ] Implement `session_coordinator.stop()` reset logic
- [ ] Implement stream/generate marking logic (mode-based)
- [ ] **Implement intelligent config augmentation**:
  - [ ] Analyze `historical.indicators` to determine required data
  - [ ] Automatically add missing historical data types to internal session_config
  - [ ] Example: Add trailing 1m bars if minute-granularity indicators requested
- [ ] **Implement historical data & indicator management**:
  - [ ] Update historical data BEFORE EVERY SESSION (drop old + add new OR clear + reload)
  - [ ] Calculate ALL indicators in `historical.indicators` before EVERY session
  - [ ] **Assign quality scores to ALL historical bars before EVERY session**:
    - [ ] Check `historical.enable_quality` config (default: true)
    - [ ] If disabled: Assign all historical bars 100% quality score
    - [ ] If enabled: Calculate actual quality from historical data
  - [ ] Implement fast indexed storage (by time) for O(1) access
  - [ ] Provide API for Analysis Engine to access via index
  - [ ] Ensure trailing windows shift properly (e.g., "last 10 days" shifts daily)
  - [ ] Ensure all historical bars have quality scores before session activation
- [ ] **Implement thread synchronization (coordinator → data_processor)**:
  - [ ] Create `StreamSubscription` class with threading.Event
  - [ ] Implement one-shot pattern (set/clear ready_event)
  - [ ] Implement mode-aware `wait_until_ready()` (blocking vs overrun detection)
  - [ ] Setup selective subscriptions (only base intervals for generation, e.g., 1m)
  - [ ] Implement `notify_bar_available()` for non-blocking notifications
  - [ ] Use notification queue (lightweight, no data - just tuples)
- [ ] Implement SESSION_COORDINATOR_LOOP with phases:
  - [ ] Intelligent config augmentation (analyze indicator requirements - first time only)
  - [ ] **Historical data update** (EVERY SESSION - drop/add or clear/reload)
  - [ ] **Historical indicator calculation** (EVERY SESSION with updated data)
  - [ ] **Historical bar quality assignment** (EVERY SESSION):
    - [ ] Check `historical.enable_quality` config
    - [ ] If disabled: Assign 100% quality; if enabled: Calculate actual quality
  - [ ] **Queue loading** (EVERY SESSION - coordinator's responsibility):
    - [ ] Backtest: Load queues with `prefetch_days` data using `start_bar_streams()` etc. APIs
    - [ ] Live: Start API streams using existing stream APIs
    - [ ] **System Manager does NOT preload** - coordinator handles this
  - [ ] Session activation signaling
  - [ ] **Streaming phase with time advancement logic**:
    - [ ] Advance time based on next data timestamp in queues
    - [ ] If data exhausted OR next timestamp > market_close: advance to market_close
    - [ ] **CRITICAL**: Ensure market time stays within trading hours (open ≤ time ≤ close)
    - [ ] After each advancement: check if `current_time >= market_close` (end-of-session)
    - [ ] **CRITICAL ERROR**: If `current_time > market_close` in backtest → abort session
    - [ ] Support data-driven (speed=0), clock-driven (speed>0), and live modes
  - [ ] **End-of-session phase** (ONLY when `current_time >= market_close`):
    - [ ] Deactivate session
    - [ ] Advance to next trading day
    - [ ] LOOP BACK to Initialization Phase (historical update)
  - [ ] Termination phase (exit loop when backtest complete)
- [ ] Remove system_manager queue preloading logic (coordinator handles now)

### Phase 3: Data Processor Refactor
- [ ] Rename `DataUpkeepThread` → `data_processor`
- [ ] **Implement thread synchronization (bidirectional)**:
  - [ ] **From coordinator**: Receive notifications via lightweight queue (no data, just tuples)
  - [ ] **From coordinator**: Implement subscriptions to coordinator (receive ready signals)
  - [ ] **To coordinator**: Signal ready via `subscription.signal_ready()` after processing
  - [ ] **To analysis engine**: Setup subscriptions for streams analysis engine needs
  - [ ] **To analysis engine**: Implement `notify_data_available()` (bars, indicators, etc.)
  - [ ] Zero-copy data access: Read from session_data by reference
- [ ] Implement event-driven processing loop:
  - [ ] Wait on notification queue (blocking with timeout)
  - [ ] Read data from session_data (by reference, no copy)
  - [ ] Generate derivatives (5m from 1m, etc.)
  - [ ] Calculate real-time indicators (NOT historical)
  - [ ] Signal ready to coordinator (one-shot)
  - [ ] Notify analysis engine of available data
- [ ] Remove all quality measurement logic
- [ ] **Important**: Historical indicators calculated by session_coordinator, NOT data_processor

### Phase 4: Data Quality Manager Implementation
- [ ] Create new `data_quality_manager` thread (was gap-filler)
- [ ] **Implement mode and configuration detection**:
  - [ ] Detect backtest vs live mode from system_manager
  - [ ] Enable gap filling ONLY in live mode
  - [ ] Check `enable_session_quality` config (default: true)
  - [ ] If session quality disabled: Assign all session bars 100% quality score
  - [ ] If session quality enabled: Calculate actual quality (event-driven)
- [ ] **Implement detailed gap analysis (internal use)**:
  - [ ] Detect gaps in STREAMED bar data
  - [ ] Track gap locations, timestamps, retry counts
  - [ ] Internal data structure (not published to session_data)
  - [ ] Use for gap filling operations (live mode only)
- [ ] **Implement quality percentage calculation**:
  - [ ] Calculate quality **per symbol, per data type** (e.g., AAPL 1m: 98.5%)
  - [ ] ONLY measure quality for STREAMED bars (NOT derived, NOT ticks/quotes)
  - [ ] Copy quality from base bars to all derived bars (e.g., copy 1m quality to 5m, 15m)
  - [ ] Update derived bar quality when base bar quality changes
  - [ ] Result: Each bar data set has its own quality score (consumer doesn't need to know if derived)
  - [ ] **NOT** overall quality across all symbols
  - [ ] Publish to session_data (accessible to analysis_engine)
- [ ] **Implement gap filling (LIVE MODE ONLY)**:
  - [ ] Gap filling DISABLED in backtest mode
  - [ ] In live mode: Periodic attempts every `retry_interval_seconds`
  - [ ] Background operation (does not block data pipeline)
  - [ ] Update quality percentage after successful gap fill
- [ ] **Implement non-blocking background operation**:
  - [ ] Event-driven quality updates (when data arrives)
  - [ ] NO gating behavior (unlike data_processor)
  - [ ] NO ready signals to any thread
  - [ ] Best effort: Update quality scores as fast as possible in background
  - [ ] Quality updates appear in session_data as they complete

### Phase 5: Analysis Engine Integration
- [ ] **Implement selective subscriptions**:
  - [ ] Define which streams analysis engine needs (e.g., 5m bars, specific indicators)
  - [ ] Setup `StreamSubscription` objects for each needed stream
  - [ ] Subscribe only to streams that matter (no overhead for others)
- [ ] **Implement synchronization from data_processor**:
  - [ ] Receive notifications from data_processor (non-blocking queue)
  - [ ] Signal ready to data_processor after processing (one-shot)
  - [ ] Mode-aware: blocking in data-driven, overrun detection in clock-driven
- [ ] **⚠️ CRITICAL: Implement session_data-only access pattern**:
  - [ ] Read ALL data from session_data (historical + current + indicators + quality)
  - [ ] NEVER read from coordinator input queues
  - [ ] NEVER read directly from data_processor or other threads
  - [ ] session_data is the SINGLE interface for all analysis data
- [ ] **Implement zero-copy data access from session_data**:
  - [ ] Read historical bars from session_data by reference (trailing days)
  - [ ] Read current session bars from session_data by reference
  - [ ] Access historical indicators via fast index (O(1) lookup)
  - [ ] Read real-time indicators from session_data by reference
  - [ ] Read quality metrics from session_data
- [ ] **Implement trading logic**:
  - [ ] Event-driven processing loop (wait for notifications)
  - [ ] Generate trading signals based on ALL data from session_data

### Phase 6: Performance Monitoring Instrumentation
- [ ] **Implement performance metrics tracking**:
  - [ ] Create metrics storage class (min/max/avg tracking with running statistics)
  - [ ] Store metrics in session_data for thread access
  - [ ] Use `time.perf_counter()` for high-resolution timing
- [ ] **Analysis Engine Performance (measured by data_processor)**:
  - [ ] Track time from notification sent to ready signal received
  - [ ] Record per analysis cycle: min, max, avg, count
  - [ ] Wrap `subscription.wait_until_ready()` with timing logic
- [ ] **Data Processor Performance (measured by coordinator)**:
  - [ ] Track time from data delivery to ready signal received
  - [ ] Record per data item: min, max, avg, count
  - [ ] Wrap `subscription.wait_until_ready()` with timing logic
- [ ] **Data Loading Performance (measured by coordinator)**:
  - [ ] Track initial data load time (first session - all symbols, all components)
  - [ ] Track subsequent data load times (between sessions - all symbols)
  - [ ] Initial load: Single time value (historical + indicators + quality + queue prefetch)
  - [ ] Subsequent loads: Min/max/avg across sessions (may be faster with drop/add algorithm)
  - [ ] Measure from start of historical data operation to completion
- [ ] **Session Lifecycle Timing (measured by coordinator)**:
  - [ ] Track session gap time (inactive to active)
  - [ ] Break down gap components: historical update + indicators + quality + queue load
  - [ ] Track active session duration (activation to deactivation)
  - [ ] Record per session: min, max, avg
- [ ] **Backtest Summary Metrics (measured by coordinator)**:
  - [ ] Track total backtest time (first session start to last session end)
  - [ ] Track number of trading days processed
  - [ ] Calculate average time per trading day
- [ ] **Implement metrics reporting**:
  - [ ] Log metrics at session end (per-session report)
  - [ ] Log metrics at backtest end (summary report)
  - [ ] Format report as shown in Architecture Rules #6
  - [ ] Consider exposing metrics via API for real-time monitoring
- [ ] **Implement metrics reset logic**:
  - [ ] Reset per-session metrics at session start
  - [ ] Keep backtest summary metrics across sessions
  - [ ] Clear all metrics at backtest start

### Phase 7: Migration & Testing
- [ ] Convert existing session configs to new format
- [ ] Remove `data_upkeep` configs, add `gap_filler`
- [ ] Update CLI commands to use new structure
- [ ] Update validation framework for new config
- [ ] Test session_coordinator marking logic (backtest vs live)
- [ ] Test event-driven data_processor/data_quality_manager
- [ ] Test quality measurement and publication

---

## Design Decisions (Resolved)

1. **Data Quality Manager Thread Isolation** ✅
   - **Decision**: Separate thread (confirmed in this design)
   - **Rationale**: data_processor focuses on computation, data_quality_manager on quality/integrity

2. **Historical Data & Indicator Management** ✅
   - **Definition**: Historical = depends ONLY on data prior to current session (no future data)
   - **Update Frequency**: BEFORE EVERY SESSION (daily/per session in backtest)
   - **Historical Data**: Drop old + add new OR clear + reload all (simpler approach)
   - **Historical Indicators**: session_coordinator calculates ALL `historical.indicators` before EVERY session
   - **Real-Time Indicators**: data_processor calculates indicators as new bars arrive during session
   - **Intelligent Augmentation**: session_coordinator auto-adds missing historical data required for indicators
   - **Access Pattern**: Historical indicators stored with fast indexed access (O(1) lookup by time)
   - **Purpose**: Maintain accurate trailing windows (e.g., "last 10 days" shifts daily)

3. **Config Hot-Reload** ✅
   - **Decision**: No hot-reload, require session restart
   - **Rationale**: Simpler, safer, session_coordinator.stop() provides clean reset

4. **Async Prefetch** ✅
   - **Decision**: Removed, replaced with synchronous prefetch in session_coordinator loop
   - **Rationale**: Simpler model, session_coordinator controls data loading

5. **Event-Driven vs Polling** ✅
   - **Decision**: Event-driven for data_processor and data_quality_manager (wait on data arrival)
   - **Rationale**: More efficient, responsive, natural fit for data processing

6. **Caching vs Asyncio for TimeManager** ✅
   - **Decision**: Use intelligent caching instead of asyncio
   - **Implementation**:
     - Last-query cache for most common case (same date repeatedly)
     - LRU cache (~100 entries) for trading sessions, dates, market hours
     - Cache keys: `(date, exchange)` for trading sessions
     - Cache invalidation on session start
   - **Rationale**: 
     - Avoids asyncio complexity
     - Same performance benefit (avoid repeated DB queries)
     - Simpler, synchronous API
     - Same date often queried 100+ times during session (perfect for caching)

7. **Thread Synchronization Pattern** ✅
   - **Decision**: Event-Based One-Shot Subscriptions with Selective Synchronization
   - **Core Mechanism**:
     - `threading.Event` for ready/available signaling
     - One-shot pattern: clear event after each use
     - Separate `StreamSubscription` object per sync point
   - **Mode Handling**:
     - Data-driven (speed=0): `event.wait()` blocks producer until consumer ready
     - Clock-driven (speed>0 or live): `event.is_set()` checks, raises `OverrunError` if not ready
   - **Selective Synchronization**:
     - Only create subscriptions for streams that need synchronization
     - Coordinator → Data Processor: Only base intervals used for generation (e.g., 1m)
     - Data Processor → Analysis Engine: Only streams analysis engine subscribes to
     - Non-subscribed streams flow freely (no overhead)
   - **Performance**:
     - Zero-copy: Pass references via session_data, never copy
     - Notification queue contains only tuples (no data)
     - Fast containers: `collections.deque` for O(1) append/access
   - **Rationale**:
     - Explicit flow control (clear producer/consumer contract)
     - Works in both data-driven and clock-driven modes
     - Minimal overhead (event-based, no polling)
     - Selective sync avoids unnecessary blocking
     - Overrun detection in clock-driven mode

8. **Data Quality Manager Output** ✅
   - **Decision**: Generate two types of data
   - **Type 1 - Detailed Gap Analysis (Internal)**:
     - Gap locations, timestamps, retry counts
     - Internal data structure (not published to session_data)
     - Used for gap filling operations only
   - **Type 2 - Quality Percentage (Published)**:
     - Per symbol, per data type (e.g., AAPL 1m: 98.5%)
     - Quality measurement done ONLY on STREAMED bars (not derived, not ticks/quotes)
     - Quality score COPIED from base bars to derived bars (updated when base changes)
     - Historical bar quality assigned by session_coordinator before session start
     - Result: ALL bar data sets have quality scores (consumer doesn't care about source)
     - Published to session_data via API
     - NOT overall quality across all symbols (not useful for analysis)
   - **Rationale**:
     - Separation of internal operations vs. published metrics
     - Per-symbol granularity allows analysis engine to make symbol-specific decisions
     - Active copying ensures derived bars have their own quality scores
     - Coordinator assigns historical quality ensures completeness before session
     - Consumer transparency: All bars have quality, source doesn't matter
     - Quality only meaningful for bar data (not ticks/quotes)

9. **Data Quality Manager Behavior** ✅
   - **Decision**: Non-blocking background operation with mode-specific gap filling and configurable quality calculation
   - **Gap Filling**:
     - LIVE MODE ONLY: Gap filling enabled with periodic retry attempts
     - BACKTEST MODE: Gap filling DISABLED (quality calculation only)
     - Rationale: Backtest data is static; gaps can't be filled from database (same source as initial data)
   - **Quality Calculation**:
     - Active in BOTH backtest and live modes (if enabled)
     - Configurable separately for historical vs session data:
       - `historical.enable_quality` (default: true): Controls coordinator's historical quality calculation
       - `gap_filler.enable_session_quality` (default: true): Controls data_quality_manager's session quality calculation
     - When disabled: All bars assigned 100% quality score
     - When enabled: Always event-driven (updates when data arrives)
     - Non-blocking: Does NOT gate data pipeline
     - No ready signals: Does NOT communicate readiness to any thread
   - **Background Operation**:
     - Best effort: Updates quality scores as fast as possible
     - Quality updates appear in session_data as they complete
     - Does not block coordinator, data_processor, or analysis_engine
   - **Rationale**:
     - Quality monitoring is informational, not critical path
     - Separate controls allow disabling quality calculation for performance
     - When disabled, 100% score provides safe default (no analysis disruption)
     - Analysis engine can proceed with current quality scores
     - Gap filling in live mode improves quality over time
     - No performance impact on critical data pipeline
     - Backtest doesn't need gap filling (all data pre-loaded)
     - Always event-driven (no periodic mode) for simplicity and performance

## Open Questions

1. **Multi-Exchange Support**: Phase 2 feature
   - Single exchange per session for now
   - Future: Multiple exchange groups with different timezones

---

## Related Documentation

- `/backend/REMOVED_DATA_MANAGER_APIS.md` - Time operations migration
- `/backend/MIGRATION_FINAL_STATUS.md` - Component migration status
- `/app/managers/time_manager/README.md` - TimeManager API reference
- `/validation/session_validation_requirements.md` - Session validation rules

---

**Version**: 1.0  
**Last Updated**: 2025-11-28  
**Status**: DRAFT - Architecture Design Phase
