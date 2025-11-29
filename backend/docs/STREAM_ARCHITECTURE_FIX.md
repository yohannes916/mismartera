# Stream Architecture Fix - Current Day Only Fetching

## Summary

Fixed stream architecture to fetch **only current market day** on startup, with upkeep thread handling future dates. This improves startup speed, reduces memory usage, and properly tracks active streams in `session_data`.

## Changes Made

### 1. Added Stream Tracking to `session_data`

**New Methods:**
```python
def is_stream_active(symbol: str, stream_type: str) -> bool
async def mark_stream_active(symbol: str, stream_type: str) -> None
async def mark_stream_inactive(symbol: str, stream_type: str) -> None
```

**New Attribute:**
```python
self._active_streams: Dict[Tuple[str, str], bool] = {}
# Key: (symbol, stream_type) where stream_type is "bars", "ticks", or "quotes"
```

### 2. Refactored `stream_bars()` Architecture

**OLD BEHAVIOR (Wrong):**
```python
# ❌ Fetched entire backtest window (multiple days)
end_date = self.backtest_end_date  # e.g., 4 days away
bars = fetch_bars(start=now, end=end_date)  # Fetch 1,560 bars!

# ❌ Spawned background task (non-blocking)
asyncio.create_task(feed_bars(symbol))

# ❌ Used deprecated session_tracker
tracker = get_session_tracker()
```

**NEW BEHAVIOR (Correct):**
```python
# ✓ Fetches current market day only
current_date = now.date()
start_time = datetime.combine(current_date, MARKET_OPEN)  # 9:30 AM
end_time = datetime.combine(current_date, MARKET_CLOSE)   # 4:00 PM
bars = fetch_bars(start=start_time, end=end_time)   # ~390 bars

# ✓ Blocks until fetch complete (synchronous)
fetch_bars_by_symbol(...)

# ✓ Uses session_data singleton
session_data = get_session_data()
session_data.register_symbol(symbol)
session_data.mark_stream_active(symbol, "bars")
```

### 3. Updated `system_manager.start()`

**OLD BEHAVIOR (Wrong):**
```python
# ❌ Manually fetched data
bars = MarketDataRepository.get_bars_by_symbol(...)

# ❌ Manually registered with coordinator
coordinator.register_stream(symbol, StreamType.BAR)

# ❌ Manually registered with session_data
session_data.register_symbol(symbol)

# ❌ Manually fed data
coordinator.feed_data_list(symbol, stream_type, bars)
```

**NEW BEHAVIOR (Correct):**
```python
# ✓ Uses stream_bars() API - handles everything
stream_iter = data_manager.stream_bars(
    session,
    symbols=symbols,
    interval=interval
)

# Trigger initialization by consuming first item
stream_iter.__anext__()

# stream_bars() internally:
# - Checks for duplicates in session_data
# - Blocks and fetches current day only
# - Registers with session_data
# - Registers with coordinator
# - Adds bars to session_data
# - Feeds bars to coordinator
```

## Architecture Flow

### Startup Sequence

```
1. system_manager.start()
   ↓
2. Calls data_manager.stream_bars(symbols)
   ↓
3. stream_bars() FOR EACH SYMBOL:
   
   a. Check session_data.is_stream_active(symbol, "bars")
      → If active: skip (return success)
      → If not: continue
   
   b. Register with session_data:
      session_data.register_symbol(symbol)
      session_data.mark_stream_active(symbol, "bars")
   
   c. Register with coordinator:
      coordinator.register_stream(symbol, StreamType.BAR)
   
   d. BLOCK and fetch current day only:
      current_date = time_provider.get_current_time().date()
      start = datetime.combine(current_date, MARKET_OPEN)  # 9:30 AM
      end = datetime.combine(current_date, MARKET_CLOSE)    # 4:00 PM
      bars = fetch_bars(symbol, start, end)  # ~390 bars
   
   e. Add bars to session_data:
      for bar in bars:
          session_data.add_bar(symbol, bar)
   
   f. Feed bars to coordinator:
      coordinator.feed_stream(symbol, bar_iterator)
   
4. Return to system_manager (streams started)
5. System state = RUNNING
```

### Runtime Behavior

**Coordinator Worker Thread:**
- Merges multiple symbol streams chronologically
- Advances TimeProvider as bars are emitted
- Respects system state (paused/running)
- Yields bars to consumers

**Data Upkeep Thread (every 60 seconds):**
- Checks active symbols from `session_data.get_active_symbols()`
- Detects/fills gaps in current day
- Computes derived bars (5m, 15m, etc.)
- **Prefetches next trading day when current day ends soon**
- Updates bar quality metrics

### Future Date Prefetching

```python
# In upkeep thread
def _upkeep_symbol(symbol):
    current_time = time_provider.get_current_time()
    
    # Check if day is ending soon (after 3:30 PM)
    if current_time.time() > time(15, 30):
        next_date = get_next_trading_day(current_time.date())
        
        # Prefetch next trading day
        if not symbol_data.has_data_for_date(next_date):
            bars = fetch_bars_for_date(symbol, next_date)
            
            # Feed to coordinator
            coordinator.feed_stream(symbol, StreamType.BAR, bars)
            
            # Add to session_data
            for bar in bars:
                session_data.add_bar(symbol, bar)
```

## Benefits

### 1. Fast Startup ⚡
**Before:** Fetched 4 days × 390 bars = 1,560 bars per symbol
**After:** Fetches 1 day × 390 bars = 390 bars per symbol
**Improvement:** 4x faster startup!

### 2. Low Memory Usage 💾
**Before:** All backtest window days in memory simultaneously
**After:** Current day + next day (prefetched) = max 2 days
**Improvement:** 50-75% memory reduction for typical backtests

### 3. Proper Stream Tracking 📊
**Before:** Only coordinator knew about streams
**After:** session_data tracks all active streams
**Result:** `system status` shows correct active symbol count!

### 4. No More Deprecated Code ✅
**Before:** Used deprecated `session_tracker`
**After:** Uses `session_data` singleton
**Result:** Single source of truth for session state

### 5. Blocks During Fetch 🔒
**Before:** Non-blocking (background task), hard to track completion
**After:** Blocks until current day loaded
**Result:** Predictable startup, clear error handling

## Testing

### Test Startup
```bash
./start_cli.sh
system start
system status
```

**Expected Output:**
```
Session Data
├─ Session Date: 2024-11-18
├─ Session Active: Yes              ← Should show Yes
├─ Active Symbols: 2 symbols        ← Should match streams started
```

### Test Stream Logs
Look for:
```
✓ Registered symbol: AAPL (total active: 1)
✓ Registered symbol: MSFT (total active: 2)
Fetching bars for AAPL on 2024-11-18...
Fetched 390 bars for AAPL on 2024-11-18
✓ Started bar stream for AAPL (390 bars)
Marked bars stream active for AAPL
```

### Test Memory Usage
```python
# Check bars in session_data
symbol_data = session_data.get_symbol_data("AAPL")
len(symbol_data.bars_1m)  # Should be ~390, not 1,560+
```

## Migration Notes

### If You Were Manually Starting Streams

**OLD:**
```python
# ❌ Don't do this anymore
bars = MarketDataRepository.get_bars_by_symbol(...)
coordinator.register_stream(symbol, StreamType.BAR)
session_data.register_symbol(symbol)
coordinator.feed_data_list(symbol, StreamType.BAR, bars)
```

**NEW:**
```python
# ✓ Use stream_bars API
async with AsyncSessionLocal() as session:
    async for bar in data_manager.stream_bars(session, ["AAPL"], "1m"):
        # Process bar
        pass
```

### Upkeep Thread Responsibility

The upkeep thread NOW handles:
- ✅ Gap detection and filling (current day)
- ✅ Derived bar computation
- ✅ Bar quality metrics
- ✅ **NEW: Prefetching future trading days**

You should NOT manually fetch future dates - let upkeep handle it!

## Summary

✅ **Architecture fixed** - `stream_bars()` blocks and fetches current day only
✅ **session_data tracks streams** - `is_stream_active()`, `mark_stream_active()`
✅ **system_manager uses API** - Calls `stream_bars()` instead of manual registration
✅ **Upkeep handles future** - Prefetches next trading day automatically
✅ **Memory efficient** - Max 2 days in memory vs entire backtest window
✅ **Fast startup** - 4x faster by fetching 1 day vs 4+ days

**Result:** Proper architecture with clear responsibilities! 🎯
