# Quick Start: Backtest Mode

## Current Status
✅ System is running
✅ DataManager is active
❌ No active session (need to start streaming)

## Step-by-Step: Start Your First Backtest Session

### 1. Check System Status
```bash
system status
```

Should show:
- State: RUNNING
- Mode: BACKTEST
- Session Active: No ← We'll fix this

### 2. Start Streaming Data
```bash
# Stream 1-minute bars for AAPL
data stream-bars 1 AAPL
```

**What happens:**
- Creates backtest session starting at 2024-11-18 09:30:00
- Loads historical data from database
- Starts coordinator worker thread
- Begins streaming bars at 60x speed

### 3. Verify Session is Active
```bash
system status
```

Should now show:
- Session Active: Yes ✓
- Active Symbols: 1 symbol (AAPL)
- Worker Thread: Running

### 4. Watch Data Stream
The bars will stream to console. You'll see:
```
[09:30:00] AAPL | Open: 150.00 | High: 150.50 | Low: 149.80 | Close: 150.30 | Vol: 50000
[09:31:00] AAPL | Open: 150.30 | High: 150.80 | Low: 150.20 | Close: 150.60 | Vol: 45000
...
```

### 5. Stop Streaming
```bash
# Stop all streams
data stop-all-streams
```

## Common Commands

### Start Multiple Symbols
```bash
data stream-bars 1 AAPL
data stream-bars 1 MSFT
data stream-bars 1 TSLA
```

### Stream to CSV File
```bash
# Save to file instead of console
data stream-bars 1 AAPL aapl_backtest.csv
```

### Check Active Streams
```bash
system status
```
Look for "Active Streams" section.

### Pause/Resume
```bash
system pause   # Pause streaming
system resume  # Resume streaming
```

### Change Speed
```bash
# Speed up to 120x
data speed 120

# Max speed (no delay)
data speed 0

# Real-time speed
data speed 1.0
```

## Troubleshooting

### "No data available for symbol"
**Problem:** Symbol data not in database

**Solution:**
```bash
# Import data first
data import bars AAPL 2024-11-01 2024-11-21
```

### Session ends immediately
**Problem:** Reached end of backtest period (2024-11-21)

**Solution:**
```bash
# Check backtest dates
system status

# Backtest only has 3 days: 2024-11-18 to 2024-11-21
# If you want more days, import more historical data
```

### Worker thread stopped
**Problem:** Stream finished or error occurred

**Solution:**
```bash
# Check for errors in logs
# Restart stream
data stream-bars 1 AAPL
```

## Full Example Session

```bash
# 1. Start CLI
system@mismartera: system status
# Verify: State=RUNNING, Session Active=No

# 2. Start streaming AAPL
system@mismartera: data stream-bars 1 AAPL
Starting 1-minute bar stream for AAPL...
Session created: 2024-11-18
Loading historical data...
Stream started!

# 3. Watch data stream (shows bars)
[09:30:00] AAPL | Open: 150.00 | ...
[09:31:00] AAPL | Open: 150.30 | ...

# 4. Check status (should show active session)
system@mismartera: system status
Session Active: Yes ✓
Active Symbols: 1 symbol (AAPL)

# 5. Add another symbol
system@mismartera: data stream-bars 1 MSFT

# 6. Stop when done
system@mismartera: data stop-all-streams
Stopping all streams...
Done!
```

## Next Steps

### After Session is Active:

1. **Add Trading Logic:**
   - ExecutionManager will activate
   - Place orders
   - Track positions

2. **Use Analysis Engine:**
   - Ask Claude for analysis
   - Get AI-powered insights

3. **Monitor Performance:**
   - Track P&L
   - Review trades
   - Analyze strategy

## Key Points

- ✅ `system start` starts the system, not a session
- ✅ `data stream-bars` starts a session
- ✅ Session = active data streaming
- ✅ No streams = no session
- ✅ Backtest runs at simulated time (2024-11-18)
- ✅ Speed is configurable (default 60x)
