# System Start Behavior

## Overview

`system start <config_file>` now automatically stops all existing streams and starts the streams defined in the configuration file.

## What Happens When You Run `system start`

### 1. Load Configuration ✅
- Reads and validates JSON configuration file
- Parses session settings, trading parameters, and stream definitions

### 2. Apply Configuration ✅
- Sets operation mode (live/backtest)
- Configures backtest window and speed (if backtest mode)
- Applies API configuration

### 3. Stop Existing Streams ✅
**NEW BEHAVIOR:**
- Calls `data_manager.stop_all_streams()`
- Stops all bar, tick, and quote streams
- Stops coordinator worker thread
- Cleans up all active stream resources

### 4. Start Configured Streams ✅
**NEW BEHAVIOR:**
- Initializes backtest mode if needed
- Starts coordinator worker thread
- For each stream in `data_streams[]`:
  - Fetches historical data from database
  - Registers stream with coordinator
  - Feeds data into coordinator queue
  - Activates stream

### 5. Transition to RUNNING ✅
- System state changes from STOPPED → RUNNING
- Session becomes active
- Streams begin processing

## Configuration File Format

```json
{
  "session_name": "My Trading Session",
  "mode": "backtest",
  "data_streams": [
    {
      "type": "bars",
      "symbol": "AAPL",
      "interval": "1m"
    },
    {
      "type": "bars",
      "symbol": "MSFT",
      "interval": "5m"
    },
    {
      "type": "ticks",
      "symbol": "TSLA"
    }
  ],
  "trading_config": {
    "max_buying_power": 100000.0,
    "max_per_trade": 10000.0,
    "max_per_symbol": 20000.0,
    "max_open_positions": 10,
    "paper_trading": true
  },
  "api_config": {
    "data_api": "alpaca",
    "trade_api": "alpaca"
  },
  "backtest_config": {
    "start_date": "2024-11-18",
    "end_date": "2024-11-21",
    "speed_multiplier": 60.0
  }
}
```

## Stream Types

### Bars
```json
{
  "type": "bars",
  "symbol": "AAPL",
  "interval": "1m"  // Required: 1m, 5m, 15m, etc.
}
```

### Ticks
```json
{
  "type": "ticks",
  "symbol": "AAPL"
  // No interval needed
}
```

### Quotes
```json
{
  "type": "quotes",
  "symbol": "AAPL"
  // No interval needed
}
```

## Examples

### Start System with Config
```bash
system@mismartera: system start ./configs/my_session.json
```

**Output:**
```
Starting system with configuration: ./configs/my_session.json
Loading configuration from: /home/user/configs/my_session.json
Configuration loaded: My Trading Session
Setting operation mode to: backtest
Configuring backtest window: 2024-11-18 to 2024-11-21
Backtest speed multiplier: 60.0

Stopping all existing streams...
✓ All existing streams stopped

Starting 2 configured stream(s)...
[1/2] Starting bars stream for AAPL
  Fetched 390 bars from database
  ✓ Bars stream started for AAPL (1m)
[2/2] Starting bars stream for MSFT
  Fetched 390 bars from database
  ✓ Bars stream started for MSFT (5m)

✓ All 2 streams started

System started successfully!
  Session: My Trading Session
  Mode: BACKTEST
  Backtest Window: 2024-11-18 to 2024-11-21
  Speed: 60.0x (0=max)
  Active Streams: 2
  Max Buying Power: $100,000.00
  Max Per Trade: $10,000.00
  Paper Trading: True

Streams are now active. Data is being streamed from the coordinator.
```

### Check Status After Start
```bash
system@mismartera: system status
```

**Shows:**
- State: RUNNING ✓
- Session Active: Yes ✓
- Active Symbols: 2 (AAPL, MSFT) ✓
- Worker Thread: Running ✓

## Differences from Previous Behavior

### Before (Old Behavior)
```bash
# Start system (no streams started)
system start ./config.json

# Session remains inactive
system status  # Shows: Session Active: No

# Manually start each stream
data stream-bars 1 AAPL
data stream-bars 5 MSFT
```

### After (New Behavior)
```bash
# Start system (automatically starts all configured streams)
system start ./config.json

# Session immediately active with streams running
system status  # Shows: Session Active: Yes, Active Symbols: 2
```

## Stream Management

### Stop All Streams
```bash
data stop-all-streams
```

### Stop Individual Stream
```bash
data stop-stream-bars <stream_id>
data stop-stream-ticks <stream_id>
data stop-stream-quotes <stream_id>
```

### Stop System (stops all streams automatically)
```bash
system stop
```

## Error Handling

### Invalid Stream Configuration
```
Error: Bar stream for AAPL requires an interval
```

**Solution:** Add `"interval": "1m"` to bars stream config

### Symbol Data Not Found
```
Error: Fetched 0 bars from database
```

**Solution:** Import data first
```bash
data import bars AAPL 2024-11-01 2024-11-21
```

### Stream Already Active
```
Warning: Stream already active for AAPL, skipping
```

**Solution:** Normal - stream was already running, continuing with others

## Best Practices

### 1. Define All Streams in Config
```json
{
  "data_streams": [
    {"type": "bars", "symbol": "AAPL", "interval": "1m"},
    {"type": "bars", "symbol": "MSFT", "interval": "1m"},
    {"type": "ticks", "symbol": "TSLA"}
  ]
}
```

### 2. Import Data Before Starting
```bash
# Import all symbols first
data import bars AAPL 2024-11-01 2024-11-21
data import bars MSFT 2024-11-01 2024-11-21
data import ticks TSLA 2024-11-01 2024-11-21

# Then start system
system start ./config.json
```

### 3. Use Appropriate Speed Multiplier
```json
{
  "speed_multiplier": 0.0   // Max speed (no delay)
  "speed_multiplier": 1.0   // Real-time speed
  "speed_multiplier": 60.0  // 60x speed
}
```

### 4. Stop System Cleanly
```bash
# Always use system stop (not Ctrl+C)
system stop
```

## Troubleshooting

### Session Not Active After Start
**Check:**
1. Were streams configured in JSON?
2. Was data imported for symbols?
3. Are there errors in logs?

**Debug:**
```bash
system status  # Check for errors
data stop-all-streams  # Clean up
system start ./config.json  # Try again
```

### Streams Not Producing Data
**Check:**
1. Worker thread status: `system status`
2. Data exists: `data query bars AAPL 2024-11-18 2024-11-19`
3. Backtest window correct

### System Stuck in RUNNING
**Solution:**
```bash
system stop  # Force stop
system status  # Verify STOPPED
```

## Summary

✅ **Automatic Stream Management:** `system start` now handles all stream lifecycle
✅ **Clean Shutdown:** Always stops existing streams first
✅ **Session Activation:** Session becomes active immediately with streams
✅ **Configuration-Driven:** All streams defined in JSON, no manual commands
✅ **Error Handling:** Clear error messages for configuration issues

**Result:** Cleaner, more predictable system startup with automatic stream orchestration!
