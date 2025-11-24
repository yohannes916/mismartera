# Stream Types Support Status

## Currently Supported Stream Types

### ✅ Bars (Fully Supported)

**Status:** Implemented and tested

**Configuration:**
```json
{
  "type": "bars",
  "symbol": "AAPL",
  "interval": "1m"  // Required: 1m, 5m, 15m, etc.
}
```

**Features:**
- Database storage via `MarketDataRepository.get_bars_by_symbol()`
- Backtest streaming via `BacktestStreamCoordinator`
- Historical data support
- Derived intervals (5m, 15m, etc.)

**Usage:**
```bash
# Import data
data import bars AAPL 2024-11-01 2024-11-21

# Configure in session JSON
{
  "data_streams": [
    {"type": "bars", "symbol": "AAPL", "interval": "1m"}
  ]
}

# Start system (automatically starts bars stream)
system start ./config.json
```

## Currently Unsupported Stream Types

### ⚠️ Ticks (Not Yet Implemented)

**Status:** Planned, not implemented

**What happens:**
```bash
# If configured in session JSON:
{
  "data_streams": [
    {"type": "ticks", "symbol": "MSFT"}
  ]
}

# System start will:
# ⚠ Ticks streams not yet implemented, skipping MSFT
# (continues with other streams)
```

**Future Implementation:**
- Repository method: `MarketDataRepository.get_ticks_by_symbol()`
- Database model: `Tick` table
- Import command: `data import ticks SYMBOL`

### ⚠️ Quotes (Not Yet Implemented)

**Status:** Planned, not implemented

**What happens:**
```bash
# If configured in session JSON:
{
  "data_streams": [
    {"type": "quotes", "symbol": "TSLA"}
  ]
}

# System start will:
# ⚠ Quotes streams not yet implemented, skipping TSLA
# (continues with other streams)
```

**Future Implementation:**
- Repository method: `MarketDataRepository.get_quotes_by_symbol()`
- Database model: `Quote` table
- Import command: `data import quotes SYMBOL`

## Error Handling Behavior

### Graceful Degradation

`system start` now handles unsupported/missing streams gracefully:

**Scenario 1: Mixed supported/unsupported**
```json
{
  "data_streams": [
    {"type": "bars", "symbol": "AAPL", "interval": "1m"},   // ✓ Supported
    {"type": "ticks", "symbol": "MSFT"},                    // ⚠ Skipped
    {"type": "bars", "symbol": "TSLA", "interval": "1m"}    // ✓ Supported
  ]
}
```

**Output:**
```
Starting 3 configured stream(s)...
[1/3] Starting bars stream for AAPL
  Fetched 390 bars from database
  ✓ Bars stream started for AAPL (1m)
[2/3] Starting ticks stream for MSFT
  ⚠ Ticks streams not yet implemented, skipping MSFT
[3/3] Starting bars stream for TSLA
  Fetched 390 bars from database
  ✓ Bars stream started for TSLA (1m)

✓ Started 2 stream(s)
⚠ Skipped 1 stream(s) (unsupported or no data)

System started successfully!
  Configured Streams: 3
  Active Streams: 2
  Skipped Streams: 1
```

**Scenario 2: No data in database**
```json
{
  "data_streams": [
    {"type": "bars", "symbol": "AAPL", "interval": "1m"}
  ]
}
```

**If AAPL data not imported:**
```
Starting 1 configured stream(s)...
[1/1] Starting bars stream for AAPL
  ⚠ No bars data found for AAPL in database. 
     Import data first with: data import bars AAPL

⚠ Skipped 1 stream(s) (unsupported or no data)

System started successfully!
  Configured Streams: 1
  Active Streams: 0
  Skipped Streams: 1
  ⚠ No streams active. Import data and configure bar streams in your session config.
```

**Scenario 3: All streams unsupported**
```json
{
  "data_streams": [
    {"type": "ticks", "symbol": "AAPL"},
    {"type": "quotes", "symbol": "MSFT"}
  ]
}
```

**Output:**
```
Starting 2 configured stream(s)...
[1/2] Starting ticks stream for AAPL
  ⚠ Ticks streams not yet implemented, skipping AAPL
[2/2] Starting quotes stream for MSFT
  ⚠ Quotes streams not yet implemented, skipping MSFT

⚠ Skipped 2 stream(s) (unsupported or no data)
No streams were started. System is running but inactive.

System started successfully!
  Configured Streams: 2
  Active Streams: 0
  Skipped Streams: 2
  ⚠ No streams active. Import data and configure bar streams in your session config.
```

## Best Practices

### 1. Use Only Bars for Now

Until ticks/quotes are implemented:

```json
{
  "data_streams": [
    {"type": "bars", "symbol": "AAPL", "interval": "1m"},
    {"type": "bars", "symbol": "MSFT", "interval": "1m"},
    {"type": "bars", "symbol": "TSLA", "interval": "5m"}
  ]
}
```

### 2. Import Data Before Starting

```bash
# Import all symbols first
data import bars AAPL 2024-11-01 2024-11-21
data import bars MSFT 2024-11-01 2024-11-21
data import bars TSLA 2024-11-01 2024-11-21

# Then start
system start ./config.json
```

### 3. Check System Status

```bash
system status
```

Look for:
- **Active Streams:** Should match your configured bars streams
- **Session Active:** Should be "Yes" if streams started

### 4. Remove Unsupported Streams from Config

To avoid warning messages:

```json
// ❌ Bad (causes warnings)
{
  "data_streams": [
    {"type": "bars", "symbol": "AAPL", "interval": "1m"},
    {"type": "ticks", "symbol": "AAPL"}
  ]
}

// ✓ Good (clean startup)
{
  "data_streams": [
    {"type": "bars", "symbol": "AAPL", "interval": "1m"}
  ]
}
```

## Implementation Status

| Feature | Status | Notes |
|---------|--------|-------|
| **Bars** | ✅ Complete | Full support in backtest and live |
| **Derived Bars** | ✅ Complete | 5m, 15m, etc. auto-computed |
| **Historical Bars** | ✅ Complete | Trailing days support |
| **Ticks** | ❌ Not Started | Planned for Phase 2 |
| **Quotes** | ❌ Not Started | Planned for Phase 2 |
| **Live Streaming** | 🚧 Partial | Bars only via Alpaca |

## Roadmap

### Phase 1 (Current)
- ✅ Bars support
- ✅ Graceful degradation
- ✅ Error handling

### Phase 2 (Planned)
- [ ] Ticks repository methods
- [ ] Ticks import command
- [ ] Ticks streaming
- [ ] Quotes repository methods
- [ ] Quotes import command
- [ ] Quotes streaming

### Phase 3 (Future)
- [ ] Live ticks via Alpaca WebSocket
- [ ] Live quotes via Alpaca WebSocket
- [ ] Combined bar/tick/quote streams

## Troubleshooting

### "Ticks streams not yet implemented"

**Cause:** Configured a ticks stream in JSON

**Solution:** Remove ticks from config or wait for implementation
```json
// Remove this:
{"type": "ticks", "symbol": "AAPL"}
```

### "No bars data found"

**Cause:** Symbol data not imported

**Solution:** Import data
```bash
data import bars AAPL 2024-11-01 2024-11-21
```

### "System is running but inactive"

**Cause:** All streams were skipped (no data or unsupported)

**Solution:** 
1. Check configured streams are type "bars"
2. Ensure data is imported for all symbols
3. Verify intervals are valid (1m, 5m, 15m, etc.)

## Summary

✅ **Bars streams:** Fully supported, use these!
⚠️ **Ticks/Quotes:** Not yet implemented, will be skipped
✅ **Graceful handling:** System continues with supported streams
📊 **Accurate reporting:** Shows started vs skipped counts
🔧 **Clear messages:** Helpful warnings guide you to solutions

**Recommendation:** Configure only bars streams until ticks/quotes are implemented!
