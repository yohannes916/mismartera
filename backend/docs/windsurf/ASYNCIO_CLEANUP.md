# Asyncio Cleanup Summary

## Overview
Removed all asyncio usage from the DataManager and CLI commands. The codebase now uses synchronous operations and threading instead of async/await.

## Timezone Standardization (Dec 8, 2024)

All Parquet data storage now uses **exchange timezone** (e.g., America/New_York for US_EQUITY) instead of UTC:

### Fixed:
- **Bars** - Already using exchange timezone
- **Quotes** - Updated to use exchange timezone (was UTC)
- **Ticks** - Not currently saved separately

### Breaking Change:
- **All existing UTC-based quote data was deleted** for a clean break
- No backward compatibility with UTC-based data
- All new data imported will be in exchange timezone
- Displayed times will show correct local exchange time (e.g., EDT/EST)

### Implementation:
- `parquet_storage.py::write_quotes()` - Now converts timestamps to exchange timezone before saving
- Uses `self._get_system_timezone()` which reads from `SystemManager.timezone`
- Matches bars implementation exactly (lines 273-284)

## Files Modified

### Core Managers
- **`app/managers/data_manager/api.py`**
  - Converted 22 async methods to synchronous
  - Replaced `asyncio.Event` with `threading.Event` for cancel tokens
  - Removed `asyncio` import
  - Removed nested async helper functions in `stream_quotes()` and `stream_ticks()`

### CLI Commands
- **`app/cli/data_commands.py`**
  - Converted all async command functions to synchronous
  - Removed all `asyncio.run()` wrapper calls
  - Replaced `asyncio.Task` with `threading.Thread` for background file writing
  - Removed `asyncio` import

- **`app/cli/interactive.py`**
  - Replaced `asyncio.sleep()` with `time.sleep()`
  - Removed `asyncio.run()` calls for `add_symbol_command` and `remove_symbol_command`
  - Removed `asyncio` import

## Changes Made

### 1. DataManager API Methods (Synchronous)
All these methods are now synchronous (no `async def`):
- `select_data_api()`
- `import_from_api()`
- `import_csv()`
- `get_session_metrics()`
- `get_latest_bar()`
- `stream_bars()`
- `stop_bars_stream()`
- `get_ticks()`
- `get_latest_tick()`
- `get_quotes()`
- `get_latest_quote()`
- `stream_quotes()`
- `stop_quotes_stream()`
- `stream_ticks()`
- `stop_ticks_stream()`
- `get_snapshot()`
- `get_average_volume()`
- `get_time_specific_average_volume()`
- `get_current_session_volume()`
- `get_historical_high_low()`
- `get_current_session_high_low()`
- `delete_symbol_data()`
- `delete_all_data()`
- `load_historical_bars()`

### 2. Cancel Tokens
**Before:**
```python
self._bar_stream_cancel_tokens: Dict[str, asyncio.Event] = {}
cancel_event = asyncio.Event()
```

**After:**
```python
self._bar_stream_cancel_tokens: Dict[str, threading.Event] = {}
cancel_event = threading.Event()
```

### 3. Background Tasks
**Before:**
```python
async def feed_quotes(sym: str):
    # ...
asyncio.create_task(feed_quotes(symbol))
```

**After:**
```python
def feed_quotes(sym: str):
    # ...
feed_quotes(symbol)  # Direct synchronous call
```

### 4. File Writing Threads
**Before:**
```python
task = asyncio.create_task(consume_and_close())
register_background_task(task)
asyncio.sleep(0)
```

**After:**
```python
thread = threading.Thread(target=consume_and_close, daemon=True)
register_background_task(thread)
thread.start()
```

### 5. CLI Command Wrappers
**Before:**
```python
@app.command("import-api")
def import_api(...):
    asyncio.run(import_from_api_command(data_type, symbol, start_date, end_date))
```

**After:**
```python
@app.command("import-api")
def import_api(...):
    import_from_api_command(data_type, symbol, start_date, end_date)
```

## Additional Cleanup (Dec 8, 2025)

### Data Integration Functions
- **`app/managers/data_manager/integrations/alpaca_data.py`**
  - Converted all fetch functions to synchronous (fetch_1m_bars, fetch_1d_bars, fetch_ticks, fetch_quotes, fetch_snapshot, fetch_session_data)
  - Replaced `httpx.AsyncClient` with `httpx.Client`
  - Removed all `async def` and `await` keywords

- **`app/managers/data_manager/integrations/schwab_data.py`**
  - Converted all fetch functions to synchronous (fetch_1m_bars, fetch_1d_bars, fetch_ticks, fetch_quotes, get_latest_quote)
  - Replaced `httpx.AsyncClient` with `httpx.Client`
  - Removed all `async def` and `await` keywords

- **`app/integrations/schwab_client.py`**
  - Converted `get_valid_access_token()` to synchronous
  - Converted `refresh_access_token()` to synchronous
  - Replaced `httpx.AsyncClient` with `httpx.Client`

### SystemManager Timezone Initialization
- **`app/managers/system_manager/api.py`**
  - Added `_update_timezone()` call in `__init__()` to ensure timezone is always initialized
  - Prevents `None` timezone errors when running CLI commands without `system start`

### Timezone Safety
Added fallback handling for `None` timezone in:
- `app/managers/data_manager/parquet_storage.py`
- `app/managers/data_manager/integrations/alpaca_data.py`
- `app/managers/data_manager/integrations/schwab_data.py`
- `app/managers/data_manager/api.py` (3 locations)

## Remaining asyncio Usage
The following files still have asyncio imports (need review):
- `app/cli/execution_commands.py`
- `app/cli/main.py` - Used for database initialization
- `app/cli/session_data_display_old.py` - Old file, likely can be deleted
- `app/cli/system_commands.py`
- `app/cli/time_commands.py`
- `app/managers/data_manager/integrations/alpaca_streams.py` - Websocket streams (inherently async)

These may need to be cleaned up if they don't actually use async operations.

## Testing Recommendations
1. Test `data import-api` command
2. Test `data api` command  
3. Test all streaming commands (`data stream-bars`, `data stream-ticks`, `data stream-quotes`)
4. Test background file writing for streams
5. Test cancel tokens work correctly with `threading.Event`

## Benefits
1. **Simpler code**: No async/await complexity
2. **Better compatibility**: Works with synchronous database sessions
3. **Clearer execution flow**: No event loop management
4. **Thread-based concurrency**: More explicit and easier to debug

## Date
December 8, 2025
