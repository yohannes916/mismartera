# Dynamic Symbol Addition - Flow Verification

## Complete Backtest Mode Flow

When `data add-symbol AAPL` is executed during an active backtest session:

### 1. **Pause Streaming**
```python
self._stream_paused.clear()  # Signal pause
time.sleep(0.1)              # Give streaming loop time to detect
```
- Streaming loop checks `_stream_paused` event
- When cleared, streaming pauses (stops advancing time)
- Clock is frozen at current backtest time

### 2. **Deactivate Session & Pause Notifications**
```python
self.session_data.deactivate_session()
self.data_processor.pause_notifications()
```
- `session_data._session_active = False`
- Read operations on session_data return None
- DataProcessor stops sending notifications to AnalysisEngine
- AnalysisEngine sees NO intermediate data during catchup

### 3. **Register Symbol**
```python
self._load_symbol_historical(symbol, streams)
```
- Registers symbol in session_data
- Symbol structure is created but empty

### 4. **Populate Queues (Full Day)**
```python
self._populate_symbol_queues(symbol, streams)
```
- Calls `_load_historical_bars()` for current session date
- Loads ALL bars from 00:00 to 23:59 for the date
- Puts bars in `_bar_queues[(symbol, "1m")]`
- Bars are chronologically sorted

**Example:** Session date is 2025-07-02, current time is 12:06
- Loads bars from 2025-07-02 00:00 to 2025-07-02 23:59
- Queue now contains ~390 bars (full trading day + pre/post market)

### 5. **Catchup to Current Time**
```python
self._catchup_symbol_to_current_time(symbol)
```

**Step-by-step:**

a. **Get Current Backtest Time**
```python
current_time = self._time_manager.get_current_time()  # e.g., 12:06:00
```

b. **Get Trading Session from TimeManager**
```python
trading_session = time_mgr.get_trading_session(db_session, current_date)
market_open = datetime.combine(date, trading_session.regular_open)   # 09:30:00
market_close = datetime.combine(date, trading_session.regular_close) # 16:00:00
```

c. **Process Queues**
```python
while bar_queue:
    bar = bar_queue[0]  # Peek
    
    # Stop if we've reached current time
    if bar.timestamp >= current_time:  # >= 12:06:00
        break
    
    bar = bar_queue.popleft()  # Pop
    
    # Drop if outside trading hours
    if bar.timestamp < market_open or bar.timestamp >= market_close:
        bars_dropped += 1
        continue
    
    # Write to session_data
    self.session_data.append_bar(symbol, "1m", bar)
    bars_processed += 1
```

**Example Flow:**
- Bar 09:00 → timestamp < 09:30 → **DROPPED** (pre-market)
- Bar 09:30 → within hours, < 12:06 → **WRITTEN** to session_data
- Bar 09:31 → within hours, < 12:06 → **WRITTEN** to session_data
- ...
- Bar 12:05 → within hours, < 12:06 → **WRITTEN** to session_data
- Bar 12:06 → timestamp >= 12:06 → **STOP** (reached current time)
- Remaining bars stay in queue for normal streaming

**Result:** 
- All bars from 09:30 to 12:05 are written to session_data
- Bars from 12:06 onwards remain in queue
- Pre-market bars (before 09:30) are dropped
- Post-market bars (after 16:00) are dropped

### 6. **Mark as Dynamic**
```python
self._dynamic_symbols.add(symbol)
```
- Symbol is now tracked as dynamically added
- Shows up in `data list-dynamic`

### 7. **Reactivate Session & Resume Notifications**
```python
self.session_data.activate_session()
self.data_processor.resume_notifications()
```
- `session_data._session_active = True`
- Reads now work normally
- DataProcessor resumes sending notifications
- AnalysisEngine can now see the full history (09:30 to 12:06)

### 8. **Resume Streaming**
```python
self._stream_paused.set()  # Signal resume
```
- Streaming loop detects event is set
- Clock resumes advancing
- Next bar (12:06) is processed normally from queue

---

## Key Invariants

### ✅ Clock Never Advances During Catchup
- Current time stays at 12:06 throughout entire process
- `time_manager.get_current_time()` returns same value
- No `time_manager.set_backtest_time()` calls

### ✅ AnalysisEngine Sees No Intermediate Data
- Session is deactivated before catchup starts
- Notifications are paused
- When reactivated, AnalysisEngine sees complete history
- As if symbol was there from the start

### ✅ Only Regular Trading Hours
- Pre-market bars (before 09:30) are dropped
- Post-market bars (after 16:00) are dropped
- Only regular session bars are written
- Uses TimeManager for correct trading hours

### ✅ Chronological Order Maintained
- Bars from DataManager are pre-sorted
- Queue preserves order (deque)
- Bars written to session_data in order
- No sorting overhead

### ✅ Thread Safety
- `_symbol_operation_lock` protects `_dynamic_symbols`
- `_pending_symbol_additions` is a thread-safe queue
- session_data has internal locking
- Coordinator thread is the only writer during catchup

---

## Verification Checklist

When testing `data add-symbol AAPL`:

1. **Before Addition:**
   - Session running at time T (e.g., 12:06)
   - AAPL not in session_data
   - Only RIVN has bars

2. **During Addition (should see logs):**
   ```
   [DYNAMIC] Pausing streaming
   [DYNAMIC] Deactivating session for catchup
   [DYNAMIC] Processing addition: AAPL
   [DYNAMIC] Populating queues for AAPL
   [DYNAMIC] Loaded N bars for AAPL 1m
   [DYNAMIC] Populated queue for AAPL 1m with N bars
   [DYNAMIC] Catching up AAPL to current time
   [DYNAMIC] Current backtest time: 12:06:00
   [DYNAMIC] Trading hours: 09:30:00 - 16:00:00
   [DYNAMIC] Catchup complete: X bars processed, Y bars dropped
   [DYNAMIC] Reactivating session after catchup
   [DYNAMIC] Resuming streaming
   ```

3. **After Addition:**
   - Session still at time T (clock didn't advance)
   - AAPL now has bars from 09:30 to T
   - AAPL shows in `data list-dynamic`
   - `data session` shows AAPL with full history

4. **Expected Output:**
   ```
   AAPL
     1m Bars: ~156 bars
     Start: 09:30
     Last: 12:06
     Span: 156min
   ```

---

## Common Issues (Fixed)

### ❌ Issue 1: Wrong Attribute Name
**Symptom:** "No active session. Session coordinator not initialized"
**Cause:** CLI looking for `_session_coordinator` instead of `_coordinator`
**Fix:** Use `system_mgr._coordinator` (commit 2e26395)

### ❌ Issue 2: Wrong DataManager API
**Symptom:** "get_bars() got unexpected keyword argument 'start_date'"
**Cause:** Calling with `start_date`/`end_date` instead of `start`/`end` datetimes
**Fix:** Use correct API signature (commit 19e48d9)

### ❌ Issue 3: Wrong session_data API
**Symptom:** "'SymbolSessionData' object has no attribute 'append_bar'"
**Cause:** Directly accessing `symbol_data.append_bar()`
**Fix:** Use `session_data.append_bar(symbol, interval, bar)` (commit e3e44ac)

### ❌ Issue 4: Stale Trading Hours
**Symptom:** Bars from 11:16 instead of 09:30
**Cause:** Using `getattr(self, '_market_open', None)` from stale attributes
**Fix:** Query TimeManager for correct trading session (commit fcf46cd)

### ❌ Issue 5: Timezone Comparison Error
**Symptom:** "can't compare offset-naive and offset-aware datetimes"
**Cause:** Comparing timezone-aware bar.timestamp with naive current_time/market_open
**Fix:** Strip timezone info from all datetimes before comparison (commit 1f26cc4)

---

**Status:** ✅ All flow steps verified and implemented correctly
**Last Updated:** 2025-12-01 17:40 PST
