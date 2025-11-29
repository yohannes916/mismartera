# DataManager Documentation

## Overview

The **DataManager** is the central hub for all market data operations in the Mismartera trading system. It serves as the **single source of truth** for market data, time management, and trading calendar information across all modules and components.

### Role in the System

The DataManager acts as a unified interface that:

- **Abstracts data providers** - Supports multiple data sources (Alpaca, Schwab, etc.) through a consistent API
- **Integrates with SystemManager** - Receives SystemManager reference for operation mode and state coordination
- **Ensures time consistency** - Provides authoritative time across the system (real-time in live mode, simulated time in backtest mode)
- **Centralizes market intelligence** - Delivers trading hours, holidays, and market status information
- **Orchestrates data streams** - Coordinates chronological merging of multiple real-time or historical data streams
- **Enforces trading hours** - Filters imported data to regular trading hours (9:30 AM - 4:00 PM ET)

By centralizing these functions, the DataManager **prevents data inconsistencies** and ensures that all modules (Analysis Engine, Execution Manager, Strategy Engine, CLI) work with synchronized, reliable information.

### SystemManager Integration

**New Architecture**: DataManager is now created and managed by **SystemManager**, which provides:

- **Operation Mode Control** - SystemManager owns the mode state (live/backtest), DataManager reads from it
- **System State Coordination** - Stream processing respects system state (running/paused/stopped)
- **Inter-Manager Communication** - DataManager can access other managers via SystemManager reference

```python
# DataManager is created by SystemManager
from app.managers import get_system_manager

system_mgr = get_system_manager()
data_mgr = system_mgr.get_data_manager()  # Has reference to SystemManager

# Operation mode is managed by SystemManager
mode = system_mgr.mode.value  # "live" or "backtest"
system_mgr.set_mode("backtest")  # Can only change when stopped

# DataManager delegates mode queries to SystemManager
mode = data_mgr.system_manager.mode.value  # SystemManager.mode
```

---

## Services & Data Provided

The DataManager provides the following capabilities to all system components:

### 📊 Market Data Streams

- **Real-time Streaming** - Live bars, ticks (trades), and quotes via WebSocket connections
- **Historical Streaming** - Chronologically ordered backtest data from database
- **Multi-symbol Support** - Concurrent streams across multiple symbols with automatic chronological merging
- **Multiple Intervals** - 1-minute bars as base, with support for custom intervals (2m, 3m, 5m, etc.)
- **Data Types**
  - **Bars (OHLCV)** - Open, High, Low, Close, Volume candlestick data
  - **Ticks (Trades)** - Individual trade executions with price and size
  - **Quotes** - Bid/ask spreads with exchange information

### 📈 Volume Analytics

- **Average Volume** - Calculated over specified number of full trading days (with caching)
- **Current Session Volume** - Real-time cumulative volume for active trading session
  - **Live Mode**: Fetches from Alpaca daily bar API or stream tracker
  - **Backtest Mode**: Calculated from database up to current simulated time
- **Time-specific Average Volume** - Historical average volume up to specific time of day (with caching)
- **Performance Optimized** - Uses intelligent caching (5-minute TTL) and session tracking for frequently accessed metrics

### 💹 Price Analytics

- **Historical High/Low** - Highest and lowest prices over specified lookback period (with caching)
  - **Note**: For 52-week highs/lows, uses database history or requires provider like Polygon
  - **Alpaca**: Provides bar data but not specific 52-week high/low metrics
- **Current Session High/Low** - Intraday extremes updated in real-time during active session
  - **Live Mode**: Fetches from Alpaca daily bar API or stream tracker
  - **Backtest Mode**: Calculated from database up to current simulated time
- **Session Tracking** - Continuous monitoring of price movements within current trading day
- **Performance Optimized** - Uses caching and session tracker for real-time updates during streaming

**Data Source Priority** (Live Mode):
1. **Session Tracker** (if stream active) - Instant response ⚡
2. **Alpaca Daily Bar API** - Current session aggregated data
3. **Database** - Fallback for historical queries

### 🕐 Time Management

- **Current DateTime** - Authoritative time source for entire system
  - **Live Mode**: System time in trading timezone (US/Eastern)
  - **Backtest Mode**: Simulated time that advances with data stream
- **Time Provider Integration** - Centralized clock managed by `TimeProvider` class
- **Automatic Time Advancement** - BacktestStreamCoordinator advances time as data flows

### 📅 Trading Calendar

- **Market Status** - Boolean flag indicating market open/closed state
- **Holiday Information** - Detection and identification of market holidays
- **Session Times** - Precise market open/close times for current day
  - Standard hours (9:30 AM - 4:00 PM ET)
  - Early close days (half-days)
  - Market closure days
- **Trading Day Validation** - Weekend and holiday filtering

### 🔄 Data Import & Export

- **CSV Import** - Batch import of historical market data
  - **Trading Hours Filter** - Automatically filters to regular trading hours (9:30 AM - 4:00 PM ET)
  - **Pre-market/After-hours excluded** - Only regular session data is imported
- **API Import** - Fetch and import from external providers
  - **Trading Hours Filter** - Filters bars to regular trading hours before DB insertion
  - **Quality Assurance** - Ensures clean, consistent data for backtesting
- **Database Persistence** - Storage and retrieval of bars, ticks, quotes
- **Provider Integration** - Fetch and cache data from external APIs

### 🎯 Provider Management

- **Multi-provider Support** - Alpaca, Schwab, and extensible to others
- **Connection Validation** - Health checks and API authentication
- **Automatic Failover** - Graceful handling of provider outages
- **Configuration Management** - API keys, base URLs, paper trading flags

**Provider Capabilities & Limitations**:

| Feature | Alpaca | Polygon | Database |
|---------|--------|---------|----------|
| Session High/Low/Volume | ✅ Daily bar API | ✅ | ✅ |
| 52-Week High/Low | ❌ Not directly | ✅ | ✅ Calculated |
| Real-time Snapshot | ✅ | ✅ | N/A |
| Historical Bars | ✅ | ✅ | ✅ |
| WebSocket Streaming | ✅ | ✅ | N/A |

**Note**: For metrics not provided directly by Alpaca (like 52-week high/low), the system:
1. Calculates from historical database records
2. Can integrate with additional providers (e.g., Polygon) for richer data sets
3. Caches calculated results for performance

---

## Table of Contents

1. [API Reference](#api-reference)
2. [Configuration & Settings](#configuration--settings)
3. [CLI Commands](#cli-commands)
4. [Streaming Architecture](#streaming-architecture)
5. [Backtest Mode](#backtest-mode)
6. [Data Providers](#data-providers)
7. [Examples & Usage Patterns](#examples--usage-patterns)

---

## API Reference

All public methods available in the `DataManager` class, organized by category.

### Configuration & Providers

- `__init__(mode, config, system_manager)` - Initialize DataManager instance (typically called by SystemManager)
- `select_data_api(api)` - Select and connect to a data provider (e.g., "alpaca")
- `get_execution_manager()` - Access ExecutionManager via SystemManager reference
- `get_analysis_engine()` - Access AnalysisEngine via SystemManager reference

### Time & Clock Management

- `get_current_time()` - Get current datetime (live or simulated backtest time)
- `init_backtest_window(session)` - Compute backtest window based on backtest_days (stops all streams)
- `init_backtest(session)` - Initialize backtest window and reset clock (stops all streams)
- `reset_backtest_clock()` - Reset simulated time to start of backtest window (stops all streams)
- `set_backtest_window(session, start_date, end_date)` - Override backtest date range (stops all streams)
- `set_backtest_speed(speed)` - Set backtest execution speed multiplier (0=max, 1.0=realtime, 2.0=2x, 0.5=half)
- `stop_all_streams()` - Stop all active data streams and coordinator worker

### Market Status & Trading Calendar

- `is_market_open(session, timestamp)` - Check if market is currently open
- `get_trading_hours(session, day)` - Get open/close times for a specific day
- `is_holiday(session, day)` - Check if a date is a market holiday
- `is_early_day(session, day)` - Check if a date has early market close
- `get_holidays(session, start_date, end_date)` - Get all holidays in date range
- `get_current_day_market_info(session)` - Get comprehensive market info for current day
- `import_holidays_from_file(session, file_path)` - Import holidays from JSON file
- `delete_holidays_for_year(session, year)` - Delete all holidays for a specific year

### Bar Data (OHLCV)

- `get_bars(session, symbol, start, end, interval)` - Retrieve historical bar data
- `get_latest_bar(session, symbol, interval)` - Get most recent bar for a symbol
- `stream_bars(session, symbols, interval, stream_id)` - Stream bars in real-time or backtest
- `stop_bars_stream(stream_id)` - Cancel active bar stream(s)

### Tick Data (Trades)

- `get_ticks(session, symbol, start, end)` - Retrieve historical tick/trade data
- `get_latest_tick(session, symbol)` - Get most recent tick for a symbol
- `stream_ticks(session, symbols, stream_id)` - Stream ticks in real-time or backtest
- `stop_ticks_stream(stream_id)` - Cancel active tick stream(s)

### Quote Data (Bid/Ask)

- `get_quotes(session, symbol, start, end)` - Retrieve historical quote data
- `get_latest_quote(session, symbol)` - Get most recent quote for a symbol
- `stream_quotes(session, symbols, stream_id)` - Stream quotes in real-time or backtest
- `stop_quotes_stream(stream_id)` - Cancel active quote stream(s)

### Data Import

- `import_csv(session, file_path, symbol, **options)` - Import market data from CSV file
- `import_from_api(session, data_type, symbol, start_date, end_date, **options)` - Import data from external API (Alpaca)

### Data Quality & Metadata

- `check_data_quality(session, symbol, interval)` - Analyze data completeness and quality
- `get_symbols(session, interval)` - Get list of all available symbols in database
- `get_bar_count(session, symbol, interval)` - Count total bars for symbol/interval
- `get_date_range(session, symbol, interval)` - Get earliest and latest dates for symbol

### Snapshot & Live Data

- `get_snapshot(symbol)` - Get latest snapshot from provider (live mode only) - includes latest trade, quote, and bars

### Volume Analytics

- `get_average_volume(session, symbol, days, interval)` - Average daily volume over specified trading days (cached)
- `get_time_specific_average_volume(session, symbol, target_time, days, interval)` - Average volume up to specific time of day (cached)
- `get_current_session_volume(session, symbol, interval)` - Cumulative volume for current trading session (real-time)

### Price Analytics

- `get_historical_high_low(session, symbol, days, interval)` - Highest and lowest prices over period (cached)
- `get_current_session_high_low(session, symbol, interval)` - Session high/low prices for current session (real-time)

### Data Deletion

- `delete_symbol_data(session, symbol, interval)` - Delete all data for a specific symbol
- `delete_all_data(session)` - Delete ALL market data from database (use with caution)

---

### Method Details

#### `get_current_time() -> datetime`

**Purpose**: Returns the authoritative current time for the entire system, serving as the single source of truth for all time-dependent operations.

**Signature**:
```python
def get_current_time(self) -> datetime
```

**Parameters**: None

**Returns**: `datetime` - Naive datetime object (no timezone info attached) that represents:
- **Live Mode**: Current system time in US Eastern Time (America/New_York)
- **Backtest Mode**: Simulated time maintained by TimeProvider and advanced by BacktestStreamCoordinator

**Raises**:
- `ValueError` - In backtest mode when `_backtest_time` has not been initialized
- `ValueError` - When `SYSTEM_OPERATING_MODE` contains an invalid value

---

**Behavior by Mode**

##### Live Mode (`SYSTEM_OPERATING_MODE = "live"`)

**Behavior**:
1. Reads current system time using `datetime.now()`
2. Applies timezone conversion to `TRADING_TIMEZONE` (default: "America/New_York")
3. Strips timezone information (converts to naive datetime)
4. Returns naive datetime interpreted as Eastern Time

**Example**:
```python
# System time: 2024-01-15 14:30:00 UTC
# TRADING_TIMEZONE = "America/New_York" (UTC-5 during winter)
dm = DataManager()
current = dm.get_current_time()
# Returns: datetime(2024, 1, 15, 9, 30, 0)  # 9:30 AM ET (naive)
```

**Important Notes**:
- Always returns time in Eastern Time regardless of system timezone
- Timezone info is stripped to maintain consistency across the codebase
- Time reflects actual wall clock, including seconds and microseconds
- Each call queries system clock (not cached)

##### Backtest Mode (`SYSTEM_OPERATING_MODE = "backtest"`)

**Behavior**:
1. Checks if `_backtest_time` has been set via `set_backtest_time()`
2. If set: Returns the stored `_backtest_time` value
3. If not set: Raises `ValueError` with initialization instructions

**Initialization Requirements**:
Before calling `get_current_time()` in backtest mode, you **must** initialize the clock:
```python
dm.init_backtest(session)  # Sets clock to DataManager.backtest_start_date at market open
# OR
dm.reset_backtest_clock()  # Resets to start of backtest window (DataManager.backtest_start_date at market open)
```

**IMPORTANT**: Both `init_backtest()` and `reset_backtest_clock()` are now **async** methods that automatically stop all active streams before modifying backtest time. This prevents inconsistencies when time is reset while streams are actively running.

**Time Advancement**:
- Time does NOT advance automatically
- `BacktestStreamCoordinator` advances time as it yields data chronologically
- Each data point's timestamp becomes the new "current time"

**Example**:
```python
# Backtest initialized to 2024-01-10 09:30:00 ET
current = dm.get_current_time()
# Returns: datetime(2024, 1, 10, 9, 30, 0)

# After stream yields bar at 2024-01-10 09:31:00
current = dm.get_current_time()  
# Returns: datetime(2024, 1, 10, 9, 31, 0)
```

**Error Case** (Uninitialized):
```python
# SYSTEM_OPERATING_MODE = "backtest"
# _backtest_time not set
dm = DataManager()
current = dm.get_current_time()
# Raises: ValueError("Backtest time not set. Call DataManager.init_backtest() or "
#                    "DataManager.reset_backtest_clock() before requesting time...")
```

---

**Edge Cases & Corner Cases**

##### Case-Insensitive Mode Checking
The mode string is converted to lowercase before comparison:
```python
SYSTEM_OPERATING_MODE = "Live"    # Works (converted to "live")
SYSTEM_OPERATING_MODE = "BACKTEST"  # Works (converted to "backtest")
SYSTEM_OPERATING_MODE = "LiVe"     # Works (converted to "live")
```

##### Invalid Operating Mode
Any value other than "live" or "backtest" raises `ValueError`:
```python
SYSTEM_OPERATING_MODE = "paper"
dm.get_current_time()
# Raises: ValueError("Invalid SYSTEM_OPERATING_MODE: paper")

SYSTEM_OPERATING_MODE = ""
dm.get_current_time()
# Raises: ValueError("Invalid SYSTEM_OPERATING_MODE: ")

SYSTEM_OPERATING_MODE = None  # Invalid in pydantic settings, would fail at startup
```

##### Runtime Mode Switching
The mode is read from `settings.SYSTEM_OPERATING_MODE` **on every call**, not cached:
```python
settings.SYSTEM_OPERATING_MODE = "live"
time1 = dm.get_current_time()  # Returns system time

settings.SYSTEM_OPERATING_MODE = "backtest"
dm.reset_backtest_clock()
time2 = dm.get_current_time()  # Returns backtest time

# Mode can change dynamically (though not recommended in production)
```

##### Timezone Edge Cases

**Non-existent Timezone**:
```python
TRADING_TIMEZONE = "Invalid/Timezone"
dm.get_current_time()
# Raises: ZoneInfoNotFoundError (from zoneinfo module)
```

**Daylight Saving Time Transitions**:
```python
# Spring forward (2024-03-10 02:00:00 ET doesn't exist)
# datetime.now(ZoneInfo("America/New_York")) handles this automatically
# Returns 03:00:00 ET after the transition

# Fall back (2024-11-03 01:00:00 ET occurs twice)
# Uses the second occurrence (after DST ends)
```

##### Backtest Time Persistence
The `_backtest_time` persists across multiple calls until explicitly changed:
```python
dm.reset_backtest_clock()  # Sets to 2024-01-10 09:30:00
t1 = dm.get_current_time()  # 2024-01-10 09:30:00
time.sleep(5)
t2 = dm.get_current_time()  # Still 2024-01-10 09:30:00 (unchanged)
```

##### Naive Datetime Interpretation
All returned datetimes are **naive** (no tzinfo):
```python
result = dm.get_current_time()
assert result.tzinfo is None  # Always True
# Datetime should be interpreted as Eastern Time by convention
```

---

**Implementation Details**

**Delegation Pattern**:
`DataManager.get_current_time()` is a simple proxy to `TimeProvider.get_current_time()`:
```python
# DataManager.get_current_time()
def get_current_time(self) -> datetime:
    return self.time_provider.get_current_time()
```

**TimeProvider Internal State**:
- `_backtest_time: Optional[datetime]` - Stores simulated time (None when uninitialized)
- No mode state stored locally - always reads from global settings
- Initialized to `None` on construction

**Settings Dependencies**:
- `SYSTEM_OPERATING_MODE` - Must be "live" or "backtest"
- `TRADING_TIMEZONE` - Used in live mode (default: "America/New_York")

**Stream Safety Mechanism**:
As of the latest implementation, any function that resets or modifies backtest time automatically stops all active streams first. This prevents data inconsistencies when time changes during active streaming.

Functions that stop streams before backtest modification:
- `init_backtest_window()` - Stops all streams, then computes backtest window
- `reset_backtest_clock()` - Stops all streams, then resets time to start
- `init_backtest()` - Calls both methods above, each stops streams before making changes
- `set_backtest_window()` - Calls `reset_backtest_clock()` which stops streams

The `stop_all_streams()` public method:
1. Stops all bar streams via `stop_bars_stream()`
2. Stops all tick streams via `stop_ticks_stream()`
3. Stops all quote streams via `stop_quotes_stream()`
4. Stops the BacktestStreamCoordinator worker

This method can be called directly when you need to manually stop all streams,
or it's automatically called by time modification functions.

**Example of Safe Time Reset**:
```python
# Streams are actively running
async for bar in dm.stream_bars(session, ["AAPL", "TSLA"]):
    process(bar)
    
    # User decides to restart backtest
    if restart_needed:
        dm.reset_backtest_clock()  # Automatically stops all streams
        # Previous stream loop will exit, safe to start new streams
        break

# Start fresh streams after reset
async for bar in dm.stream_bars(session, ["AAPL", "TSLA"]):
    process(bar)
```

---

**Common Usage Patterns**

**Pattern 1: Query Current Market Time**
```python
now = dm.get_current_time()
if now.time() >= time(9, 30) and now.time() <= time(16, 0):
    print("Market is open")
```

**Pattern 2: Timestamp Data Operations**
```python
# Get bars up to current time
bars = dm.get_bars(session, "AAPL", start, dm.get_current_time())
```

**Pattern 3: Check Backtest Progress**
```python
current = dm.get_current_time()
print(f"Backtest at: {current.date()} {current.time()}")
```

**Pattern 4: Compare with Data Timestamps**
```python
async for bar in dm.stream_bars(session, ["AAPL"]):
    now = dm.get_current_time()
    assert bar.timestamp <= now  # Data is never from the future
```

**Pattern 5: Manual Stream Cleanup**
```python
# Start multiple streams
async for bar in dm.stream_bars(session, ["AAPL", "TSLA", "MSFT"]):
    process(bar)
    
    # Emergency stop condition
    if should_stop():
        dm.stop_all_streams()  # Clean shutdown of all streams
        break

# Or from CLI
# $ data stop-all-streams
```

---

**Testing Considerations**

When writing tests for `get_current_time()`, verify:

1. **Mode Switching**: Live → Backtest → Live transitions work correctly
2. **Initialization**: Backtest mode raises ValueError when uninitialized
3. **Time Advancement**: Backtest time advances with stream coordinator
4. **Timezone Handling**: Live mode correctly converts to Eastern Time
5. **Case Insensitivity**: Mode values are case-insensitive
6. **Invalid Modes**: Proper ValueError raised for invalid modes
7. **Naive Datetime**: Returned datetime has no timezone info
8. **Persistence**: Backtest time persists until explicitly changed
9. **DST Handling**: Daylight saving transitions handled correctly
10. **Concurrent Access**: Thread-safe when multiple components query time
11. **Stream Stopping**: `reset_backtest_clock()` and `init_backtest()` stop all active streams before resetting time
12. **Async Behavior**: Clock reset methods are async and must be awaited

**Mock Scenarios for Tests**:
- Mock `settings.SYSTEM_OPERATING_MODE` to control mode
- Mock `datetime.now()` for deterministic live mode testing
- Mock `settings.TRADING_TIMEZONE` to test timezone edge cases
- Test uninitialized backtest state
- Test time advancement during streaming

---

## Configuration & Settings

> **Section Status**: 🚧 To be documented

This section will document all configuration settings used by DataManager:

- System Operating Mode (`SYSTEM_OPERATING_MODE`)
- Trading Timezone (`TRADING_TIMEZONE`)
- Data Provider Settings
  - Alpaca Configuration
  - Schwab Configuration
- Backtest Configuration
- Database Settings

---

## CLI Commands

> **Section Status**: 🚧 To be documented

This section will document all CLI commands that interact with DataManager:

### Stream Management Commands

- `data stream-bars <interval> <symbol> [file]` - Start streaming bars (live or backtest)
- `data stream-ticks <symbol> [file]` - Start streaming ticks
- `data stream-quotes <symbol> [file]` - Start streaming quotes
- `data stop-stream-bars [id]` - Stop active bar stream(s)
- `data stop-stream-ticks [id]` - Stop active tick stream(s)
- `data stop-stream-quotes [id]` - Stop active quote stream(s)
- `data stop-all-streams` - **Stop ALL active streams and coordinator worker**

### Snapshot & Analytics Commands

- `data snapshot <symbol>` - Get latest snapshot (live mode only) - trade, quote, bars
- `data session-volume <symbol>` - Get cumulative volume for current trading session
- `data session-high-low <symbol>` - Get session high and low prices
- `data avg-volume <symbol> <days>` - Get average daily volume over specified trading days
- `data high-low <symbol> <days>` - Get historical high/low prices over period

### Market Status Commands

- Market status commands (to be documented)

### Data Import Commands

- Data import commands (to be documented)

### Backtest Window Management

- Backtest window management commands (to be documented)

### Provider Management Commands

- Provider management commands (to be documented)

---

## Streaming Architecture

### BacktestStreamCoordinator

The **BacktestStreamCoordinator** is a singleton that manages chronological merging of multiple backtest data streams:

#### Key Features

- **Threading Model** - Runs in dedicated worker thread, independent of CLI event loop
- **Chronological Merging** - Merges multiple streams (bars/ticks/quotes) across symbols in timestamp order
- **Time Advancement** - **Only component** that advances backtest time forward
- **System State Awareness** - **NEW**: Respects SystemManager state before advancing time
- **Precise Pacing** - Uses configurable speed multiplier for backtest acceleration

#### State-Aware Streaming

**NEW**: The coordinator now checks SystemManager state before advancing time:

```python
# In backtest mode, before advancing time:
if system_manager.is_running():
    # Advance time and yield data
    time_provider.set_backtest_time(next_timestamp)
else:
    # System paused or stopped - wait
    while not system_manager.is_running():
        time.sleep(0.1)  # Poll until resumed
```

**Behavior by System State**:

- **RUNNING** - Time advances normally, data streams continuously
- **PAUSED** - Time advancement halts, coordinator waits for resume
- **STOPPED** - Coordinator exits cleanly

**Usage Example**:

```bash
# Start backtest stream
system start
data stream-bars 1m AAPL
# Time advances: 09:30 → 09:31 → 09:32...

# Pause to investigate
system pause
# Time freezes, stream waits

# Resume
system resume
# Time continues: 09:32 → 09:33...

# Stop
system stop
```

#### Stream Lifecycle

1. **Registration** - Streams register with coordinator via `register_stream()`
2. **Worker Start** - Worker thread starts via `start_worker()`
3. **Data Feeding** - Data is fed via `feed_data_list()` or `feed_stream()`
4. **Chronological Merge** - Worker merges streams and advances time
5. **Output** - Merged data yielded via `get_merged_stream()`
6. **Cleanup** - Worker stops via `stop_worker()`

#### Live Mode Streaming

- **WebSocket Connections** - Real-time data from providers (Alpaca, etc.)
- **No Time Advancement** - Uses actual wall clock time
- **Immediate Delivery** - Data yielded as received from provider

---

## Backtest Mode

> **Section Status**: 🚧 To be documented

This section will detail backtest functionality:

- Backtest window configuration
- Time simulation
- Clock management
- Date range restrictions
- Performance considerations

---

## Data Providers

> **Section Status**: 🚧 To be documented

This section will document provider integrations:

- Alpaca Integration
- Schwab Integration (planned)
- Adding custom providers
- Provider interface requirements

---

## Examples & Usage Patterns

> **Section Status**: 🚧 To be documented

This section will provide practical examples:

- Basic data retrieval
- Streaming with multiple symbols
- Backtest setup and execution
- Integration with Analysis Engine
- Integration with Execution Manager

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                      SystemManager                                │
│    (Singleton - Coordinates all managers)                         │
│    - Owns operation mode (live/backtest)                          │
│    - Controls system state (running/paused/stopped)               │
└─────────────┬────────────────────────────────────────────────────┘
              │
    ┏━━━━━━━━━┻━━━━━━━━━┓
    ▼                    ▼
┌─────────────────┐  ┌──────────────┐  ┌─────────────────┐
│  DataManager    │  │ ExecutionMgr │  │ AnalysisEngine  │
│  system_manager ├──┤ system_mgr   │  │ system_manager  │
└────────┬────────┘  └──────────────┘  └─────────────────┘
         │
         │ <- SystemManager.mode
         │
    ┌────┴─────┐
    │          │
    ▼          ▼
┌─────────┐  ┌──────────────────────┐
│  Live   │  │  Backtest            │
│  Mode   │  │  Mode                │
└────┬────┘  └──────┬───────────────┘
     │              │
     ▼              ▼
┌──────────┐  ┌──────────────────────┐
│ Alpaca   │  │ BacktestStream       │
│ WebSocket│  │ Coordinator          │
│          │  │ - system_manager ref │
└──────────┘  │ - Checks state       │
              │ - Pauses when needed │
              └─────────┬────────────┘
                        │
                        ▼
                 ┌─────────────┐
                 │  Database   │
                 │  (Historical)│
                 └─────────────┘
```

---

## Key Design Principles

1. **Single Source of Truth** - All modules query DataManager, never directly access data providers
2. **SystemManager Coordination** - DataManager integrates with SystemManager for mode and state
3. **Mode Transparency** - Same API works in both live and backtest modes
4. **Chronological Consistency** - Multi-stream data always merged in timestamp order
5. **Time Authority** - Only BacktestStreamCoordinator advances time in backtest
6. **State-Aware Streaming** - Streaming respects system state (running/paused/stopped)
7. **Provider Agnostic** - Business logic independent of underlying data provider
8. **Trading Hours Enforcement** - Imported data filtered to regular trading hours
9. **Fail-Safe Defaults** - Graceful degradation when data unavailable

---

## Contributing

When extending DataManager functionality:

1. Maintain mode transparency (live/backtest)
2. Use TimeProvider for all time operations
3. Add appropriate error handling and logging
4. Document new APIs in this README
5. Add CLI commands for new features
6. Write integration tests

---

## Related Documentation

- [TimeProvider Documentation](./time_provider.py)
- [BacktestStreamCoordinator Documentation](./backtest_stream_coordinator.py)
- [Data Repositories](./repositories/)
- [Provider Integrations](./integrations/)
- [Migration Guide](../../MIGRATION_GUIDE.md)
