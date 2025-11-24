# Backtest Auto-Initialization

## Overview

As of this update, backtest mode **automatically initializes** on first access. You no longer need to manually run `data init` before using backtest features.

## How It Works

### Configuration-Based Initialization

The backtest window is automatically calculated using settings from `app/config/settings.py`:

```python
# DataManager defaults
DATA_MANAGER_DATA_API: str = "alpaca"          # Data provider
DATA_MANAGER_BACKTEST_DAYS: int = 60           # Trading days for backtest window
DATA_MANAGER_BACKTEST_SPEED: float = 60.0      # Speed multiplier
```

### Auto-Initialization Triggers

Backtest initialization happens automatically when:

1. **First call to `get_current_time()`** in backtest mode (from sync context)
2. **`system status` command** (from async context)
3. **Any command requiring time** (market status, data streams, etc.)

### What Gets Initialized

When auto-initialization runs:

1. **Backtest Window**: Calculates last N trading days (excluding weekends/holidays)
   - Uses `DATA_MANAGER_BACKTEST_DAYS` from settings
   - Queries database for holidays
   - Sets `backtest_start_date` and `backtest_end_date`

2. **Backtest Time**: Sets initial time to market open on start date
   - Opens at 09:30:00 ET (canonical trading timezone)
   - Stored in TimeProvider singleton

3. **Streams**: Stops any active streams (for consistency)

### Example Flow

```python
# Before (manual initialization required)
data init                # ❌ Manual step required
system status            # ✓ Works

# After (automatic)
system status            # ✓ Auto-initializes and works immediately
```

## Implementation Details

### TimeProvider Auto-Init (Sync Contexts)

```python
# In TimeProvider.get_current_time()
if mode == "backtest":
    if self._backtest_time is None:
        logger.info("Backtest time not set - auto-initializing from settings")
        self._auto_initialize_backtest()  # ← Calls DataManager.init_backtest()
    return self._backtest_time
```

### Command-Level Auto-Init (Async Contexts)

```python
# In system_status_impl.py
if data_mgr and system_mgr.mode.value == "backtest" and data_mgr.backtest_start_date is None:
    async with AsyncSessionLocal() as session:
        await data_mgr.init_backtest(session)  # ← Auto-initialize
```

## Context Handling

### Sync Context (No Event Loop)
- TimeProvider creates event loop and runs initialization
- Works from CLI commands, scripts, tests

### Async Context (Event Loop Running)
- Command-level auto-init handles it (like `system status`)
- TimeProvider raises helpful error if called directly from async

## Manual Initialization (Still Supported)

You can still manually initialize if needed:

```bash
# CLI command
data init

# Or with custom window
data init --days 30
```

```python
# Python code
async with AsyncSessionLocal() as session:
    await data_mgr.init_backtest(session)
```

## Settings Reference

Relevant backtest settings in `app/config/settings.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `DATA_MANAGER_BACKTEST_DAYS` | 60 | Trading days in backtest window |
| `DATA_MANAGER_BACKTEST_SPEED` | 60.0 | Speed multiplier (0=max, 1=realtime) |
| `SYSTEM_OPERATING_MODE` | "backtest" | Operating mode (live/backtest) |
| `TRADING_TIMEZONE` | "America/New_York" | Canonical trading timezone (ET) |

## Benefits

✅ **Zero Configuration** - Works out of the box  
✅ **Settings-Driven** - Controlled by configuration file  
✅ **Lazy Loading** - Only initializes when needed  
✅ **Consistent** - Uses same logic as manual init  
✅ **Transparent** - Logs when auto-init happens  

## Migration Guide

### Before This Change

```bash
# Required sequence
data init           # Must run first
system status       # Then can check status
data stream bars AAPL  # Then can stream
```

### After This Change

```bash
# Just works - auto-initializes as needed
system status       # ✓ Auto-inits on first access
data stream bars AAPL  # ✓ Already initialized
```

### Scripts

Old startup scripts can be simplified:

```bash
# Before
clear
data init              # ← Can remove this line
system status
market status

# After  
clear
system status          # ← Auto-initializes
market status
```

## Error Handling

If auto-initialization fails, you'll see a clear error:

```
Backtest time not set and auto-initialization failed: <reason>
Call DataManager.init_backtest() manually or use 'data init' command.
```

Common failure reasons:
- Database not accessible
- No trading days found in date range
- SystemManager not initialized

## Logging

Watch for these log messages:

```
INFO: Backtest time not set - auto-initializing from settings
INFO: Auto-initialized backtest: 2024-09-01 to 2024-11-22 (60 trading days)
```

## See Also

- `settings.py` - Configuration values
- `time_provider.py` - Auto-init implementation
- `api.py` - `init_backtest()` and `init_backtest_window()`
- `SCRIPT_COMMAND_README.md` - Script automation
