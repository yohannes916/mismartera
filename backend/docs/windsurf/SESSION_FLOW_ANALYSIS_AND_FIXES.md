# Session Flow: Current vs Desired - Analysis & Fixes

## Your Desired Flow ✅ (Architecturally Sound)

```
LOOP (while not last_day):
  PRE-SESSION (Preparation for new day)
  ================================
  1. Clear SessionData completely (remove ALL SymbolSessionData)
  2. Advance clock to new date @ market open (from TimeManager)
  3. Initialize scanner
  4. Run pre-session scans (if configured)
  5. Process session_config: 
     - Register symbols
     - Load bars
     - Register indicators
  6. Activate session
  
  DURING-SESSION (Active trading simulation)
  =====================================
  7. Advance clock and stream data (clock-driven or data-driven)
  8. Pause for mid-session scans (coordinated pause)
  9. Pause for mid-session insertions (coordinated pause)
  
  POST-SESSION (Cleanup but KEEP data)
  ====================================
  10. When clock reaches market close:
      - Deactivate session
      - Leave data INTACT (for analysis)
  11. Check if last backtesting day:
      - If YES: Stop system, keep last day's data
      - If NO: Loop back to step 1
```

## Current Flow ❌ (Has Deviations)

```
LOOP (while not last_day):
  PHASE 1: _initialize_session()
  ===============================
  ❌ Does NOT clear SessionData
  ❌ Does NOT advance clock
  - Only validates streams (first time)
  - Resets some flags

  PHASE 2: _manage_historical_data()
  ===================================
  ❌ Clock still at PREVIOUS day's market close
  - Pre-registers symbols (creates empty SymbolSessionData)
  ❌ Clears bars but NOT symbols (partial clear)
  - Loads historical data
  - Calculates historical indicators (NOT session indicators!)
  
  PHASE 2.5: Scanner Setup
  ========================
  - Scanner setup happens here (should be after clock advance)
  
  PHASE 3-4: Load queues & Activate
  ==================================
  - Loads backtest queues
  - Activates session
  
  PHASE 5: Streaming
  ==================
  - Advances clock during streaming
  - Processes bars
  
  PHASE 6: _end_session()
  =======================
  - Deactivates session
  ❌ Clears session bars (should NOT clear at end!)
  ✅ Advances clock to next day's market open
  - Loop continues
```

## Detailed Deviations

### DEVIATION 1: SessionData Symbols Never Fully Cleared ❌

**Current** (`_manage_historical_data` lines 1086-1088):
```python
self.session_data.clear_session_bars()      # Clears bars only
self.session_data.clear_historical_bars()   # Clears historical only
# Symbols remain! (_symbols dict not cleared)
```

**Problem**: 
- First day: Registers AAPL, RIVN → `_symbols = {AAPL, RIVN}`
- Day 2: Symbols still exist, bars cleared
- Indicators were registered on Day 1 but then cleared → Empty forever

**Your Desired**:
```python
# At START of new session (Phase 1)
self.session_data.clear()  # Remove ALL symbols, reset to initial state
```

### DEVIATION 2: Clock Advanced POST-Session Instead of PRE-Session ❌

**Current** (`_end_session` lines 2429-2431):
```python
# PHASE 6 (END of session)
if self.mode == "backtest":
    self._advance_to_next_trading_day(current_date)  # Advance AFTER session
# Loop continues with clock already at Day 2 market open
```

**Problem**:
- Day 1 ends → Clock advances to Day 2 open
- Day 2 Phase 2 starts → Clock still at Day 2 open (CORRECT by accident)
- But conceptually wrong: advance should be BEFORE new session prep

**Your Desired**:
```python
# PHASE 1 (START of new session)
# Clear data first
self.session_data.clear()
# THEN advance clock
self._advance_to_next_trading_day()  # Move to new day @ market open
```

### DEVIATION 3: Scanner Setup at Wrong Time ❌

**Current** (Phase 2.5, lines 908-915):
```python
# After historical data loaded, before queues loaded
success = self._scanner_manager.setup_pre_session_scanners()
```

**Problem**:
- Scanner setup happens in middle of prep
- Clock might not be at correct time yet
- Pre-session scans should run AFTER clock advance, BEFORE queue loading

**Your Desired**:
```python
# PHASE 1 (after clock advance)
1. Clear SessionData
2. Advance clock to new date @ market open
3. Initialize scanner
4. Run pre-session scans (if configured)
5. THEN load symbols/bars/indicators
```

### DEVIATION 4: Indicators Never Registered ❌

**Current** (`_manage_historical_data` lines 1071-1076):
```python
for symbol in symbols_to_process:
    if symbol not in self.session_data._symbols:
        self.session_data.register_symbol(symbol)  # ← Creates empty SymbolSessionData
        # NO call to _register_symbol_indicators!
```

**Problem**:
- Creates `SymbolSessionData` with `indicators = {}`
- Never populates indicators
- `_register_symbol_indicators()` exists but is NEVER called
- Historical indicators calculated separately, not session indicators

**Your Desired**:
```python
# After symbol registration
for symbol in symbols_to_process:
    # Register symbol with full setup
    await self.register_symbol(
        symbol=symbol,
        load_historical=True,
        calculate_indicators=True  # ← Calls _register_symbol_indicators
    )
```

### DEVIATION 5: Data Cleared POST-Session Instead of PRE-Session ❌

**Current** (`_end_session` line 2420):
```python
# PHASE 6 (end of session)
self.session_data.clear_session_bars()  # ← Clears bars after session
```

**Problem**:
- Data cleared at END of day
- Last day's data gets cleared too
- Can't analyze final session

**Your Desired**:
```python
# PHASE 1 (start of NEW session)
self.session_data.clear()  # ← Clear BEFORE new session starts
# PHASE 6 (end of session)
# Do NOT clear anything - leave data intact
```

### DEVIATION 6: Clock Never Exceeds Market Close? (Verify) ⚠️

**Current** (`_streaming_phase` lines 2266-2271):
```python
if current_time >= market_close:
    logger.info("Market close reached, ending session")
    break

if current_time > market_close:  # Should never hit this
    logger.error("CRITICAL ERROR: Time exceeded market close!")
    raise RuntimeError(...)
```

**Status**: ✅ **CORRECT** - Clock stops exactly at market close

**Verification Needed**:
- Data-driven: Last bar timestamp = close time
- Clock-driven: Advances by 1m, checks before setting

### DEVIATION 7: Pause Coordination? (Scanner vs Mid-Session) ⚠️

**Current**: Need to verify if two pause mechanisms conflict

**Scanner pause**: `_scanner_manager.pause_system()`
**Mid-session insertion pause**: `self.pause_backtest()`

Both use `self._stream_paused` Event?

**Need to check**: Do they coordinate or conflict?

## Summary of Required Fixes

### Fix 1: Clear SessionData at START of New Session

**Location**: `_coordinator_loop()` or new Phase 0

```python
def _coordinator_loop(self):
    while not self._stop_event.is_set():
        try:
            # NEW PHASE 0: Pre-Session Cleanup
            logger.info("Phase 0: Pre-Session Cleanup")
            self._clear_session_data()  # NEW
            
            # Phase 1: Initialization
            self._initialize_session()
            # ...
```

### Fix 2: Advance Clock in Phase 0 (PRE-session)

```python
def _clear_session_data(self):
    """Clear all session data and advance clock to new day."""
    # 1. Clear SessionData completely
    self.session_data.clear()
    logger.info("SessionData cleared (all symbols removed)")
    
    # 2. Advance clock to new trading day @ market open
    current_time = self._time_manager.get_current_time()
    current_date = current_time.date()
    
    # Get next trading day
    with SessionLocal() as session:
        next_date = self._time_manager.get_next_trading_date(
            session, current_date, exchange=self.session_config.exchange_group
        )
    
    # Advance to market open
    with SessionLocal() as session:
        next_session = self._time_manager.get_trading_session(
            session, next_date, exchange=self.session_config.exchange_group
        )
    
    next_open = datetime.combine(next_date, next_session.regular_open)
    self._time_manager.set_backtest_time(next_open)
    
    logger.info(f"Clock advanced to {next_date} @ {next_open.time()}")
```

### Fix 3: Move Scanner Setup to Phase 1 (After Clock Advance)

```python
def _initialize_session(self):
    """Initialize session (called at start of each session)."""
    # Existing stream validation...
    
    # NEW: Initialize and run pre-session scanners
    logger.info("Phase 1.3: Scanner Setup")
    success = self._scanner_manager.setup_pre_session_scanners()
    if not success:
        raise RuntimeError("Pre-session scanner setup failed")
    logger.info("Pre-session scanners complete")
```

### Fix 4: Register Indicators During Symbol Setup

**Option A**: Call unified `register_symbol()` method

```python
def _manage_historical_data(self, symbols: Optional[List[str]] = None):
    # Instead of session_data.register_symbol(), call:
    for symbol in symbols_to_process:
        await self.register_symbol(
            symbol=symbol,
            load_historical=True,
            calculate_indicators=True  # ← Enables indicator registration
        )
```

**Option B**: Explicit call after registration

```python
# After pre-registering symbols
for symbol in symbols_to_process:
    self.session_data.register_symbol(symbol)

# Then register indicators
for symbol in symbols_to_process:
    historical_bars = self._get_historical_bars_for_symbol(symbol)
    self._register_symbol_indicators(
        symbol=symbol,
        historical_bars=historical_bars
    )
```

### Fix 5: Remove Bar Clearing from _end_session()

```python
def _end_session(self):
    """End current session and prepare for next."""
    # 1. Deactivate session
    self._session_active = False
    self.session_data.set_session_active(False)
    
    # 2. Notify scanner manager
    self._scanner_manager.on_session_end()
    
    # 3. Record metrics
    if self._session_start_time is not None:
        self.metrics.record_session_duration(self._session_start_time)
    
    # 4. Increment trading days counter
    self.metrics.increment_trading_days()
    
    # REMOVED: Do NOT clear session bars!
    # self.session_data.clear_session_bars()  # ← DELETE THIS
    
    # 5. Leave data INTACT for analysis
    logger.info("Session ended - data preserved for analysis")
    
    # 6. Do NOT advance clock here (moved to Phase 0)
    # Clock advance happens at START of next session
```

### Fix 6: Update Indicator Persistence Logic

Since we're clearing SessionData completely at the start of each session, indicators will be re-registered each day. This is actually CORRECT because:

1. Clear → Register → Use → Keep → Clear (next day)
2. Last day: Clear → Register → Use → **Keep** (no next day)

Update `reset_session_metrics()` to handle this:

```python
def reset_session_metrics(self) -> None:
    """Reset session metrics for a new session.
    
    NOTE: Only called within a session (NOT between sessions).
    Between sessions, entire SymbolSessionData is deleted and recreated.
    """
    self.metrics = SessionMetrics()
    
    # Reset indicator VALUES (if indicators exist)
    for ind_data in self.indicators.values():
        ind_data.current_value = None
        ind_data.last_updated = None
        ind_data.valid = False
    
    self.quotes_updated = False
    self.ticks_updated = False
    self._latest_bar = None
```

## Revised Session Flow (After Fixes)

```
LOOP (while not last_day):
  PHASE 0: _clear_session_data() [NEW]
  ====================================
  ✅ Clear SessionData completely (remove ALL symbols)
  ✅ Advance clock to new date @ market open
  
  PHASE 1: _initialize_session()
  ===============================
  ✅ Validate streams (first time only)
  ✅ Initialize scanner
  ✅ Run pre-session scans (if configured)
  
  PHASE 2: _manage_historical_data()
  ===================================
  ✅ Register symbols (fresh SymbolSessionData objects)
  ✅ Load historical bars
  ✅ Register indicators (NEW - call _register_symbol_indicators)
  ✅ Calculate historical indicators
  ✅ Calculate quality
  
  PHASE 3: _load_queues()
  =======================
  - Load backtest queues with today's data
  
  PHASE 4: _activate_session()
  =============================
  - Mark session as active
  
  PHASE 5: _streaming_phase()
  ============================
  - Advance clock (data-driven or clock-driven)
  - Process bars
  - Update indicators
  - Pause for scans (coordinated)
  - Pause for mid-session insertions (coordinated)
  - Stop at market close (exactly)
  
  PHASE 6: _end_session()
  =======================
  ✅ Deactivate session
  ✅ Record metrics
  ✅ Leave data INTACT (no clearing!)
  ✅ Check if last day → break loop
  
  (Loop continues → Phase 0 clears for next day)
```

## Implementation Plan

### Step 1: Create Phase 0
- Add `_clear_session_data()` method
- Call at top of `_coordinator_loop()` 
- Move clock advance from `_end_session()` to `_clear_session_data()`

### Step 2: Update _end_session()
- Remove `clear_session_bars()` call
- Remove `_advance_to_next_trading_day()` call
- Keep deactivation and metrics recording

### Step 3: Move Scanner Setup
- Remove from Phase 2.5
- Add to Phase 1 (after stream validation)

### Step 4: Register Indicators
- Add call to `_register_symbol_indicators()` in `_manage_historical_data()`
- Or use unified `register_symbol(calculate_indicators=True)`

### Step 5: Test Multi-Day Backtest
- Verify data cleared at START of Day 2
- Verify data kept at END of last day
- Verify indicators registered and populated each day

### Step 6: Verify Pause Coordination
- Check scanner pause implementation
- Check mid-session insertion pause
- Ensure they don't conflict

## Questions to Verify

1. ✅ **Clock stops exactly at market close?** 
   - YES - Code has checks in `_streaming_phase()`

2. ⚠️ **Scanner pause vs mid-session insertion pause - do they conflict?**
   - Need to check `_scanner_manager` pause implementation
   - Both use `self._stream_paused`?

3. ✅ **First session - special handling?**
   - YES - Stream validation only on first session
   - After fix: Also skip Phase 0 on first session (no previous data to clear)

4. ⚠️ **Mid-session insertion - how does it coordinate with pauses?**
   - Need to trace `add_symbol()` implementation
   - Does it properly pause streaming?

## Expected Behavior After Fixes

### First Day (Day 1)
```
Phase 0: SKIP (no previous data)
Phase 1: Initialize, validate streams, scanner setup
Phase 2: Register AAPL, RIVN with indicators
Phase 3-5: Load queues, activate, stream
Phase 6: Deactivate, keep data
```

### Second Day (Day 2)
```
Phase 0: Clear SessionData (AAPL, RIVN removed), advance clock to Day 2 open
Phase 1: Initialize (skip stream validation), scanner setup
Phase 2: Register AAPL, RIVN again with indicators (fresh objects)
Phase 3-5: Load queues, activate, stream
Phase 6: Deactivate, keep data
```

### Last Day
```
Phase 0: Clear previous day's data, advance clock
Phase 1-5: Normal flow
Phase 6: Deactivate, check is_last_day → TRUE
Loop breaks → Last day's data remains in SessionData ✅
```

## Files to Modify

1. `/app/threads/session_coordinator.py`
   - Add `_clear_session_data()` method
   - Update `_coordinator_loop()` to call Phase 0
   - Update `_end_session()` to remove clearing
   - Move scanner setup to Phase 1
   - Add indicator registration to Phase 2

2. `/app/managers/data_manager/session_data.py`
   - Verify `clear()` method removes all symbols
   - Update `reset_session_metrics()` docstring

3. `/app/indicators/manager.py`
   - No changes needed (already has registration method)

4. Test files
   - Verify multi-day backtest preserves last day
   - Verify indicators registered each day
   - Verify data cleared between days
