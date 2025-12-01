# Dynamic Symbol Management - Implementation Plan

**Date:** 2025-12-01  
**Feature:** Add/Remove trading symbols during active session  
**Owner:** SessionCoordinator

---

## Overview

Enable dynamic addition and removal of trading symbols during an active session, with different strategies for backtest vs live modes.

**Core Principle:** Maintain data integrity and temporal consistency while minimizing disruption to ongoing operations.

---

## Architecture Overview

```
User Request (CLI/API)
    ↓
SessionCoordinator.add_symbol(symbol)
    ↓
├─ Common Checks (duplicate prevention)
    ↓
├─ Backtest Mode: PAUSE → LOAD → CATCHUP → RESUME
│   ↓
│   ├─ Pause streaming/time advance
│   ├─ Load full-day historical data
│   ├─ Populate queue with data
│   ├─ Advance to current simulated time
│   ├─ Resume streaming/time advance
│   └─ DataProcessor/QualityManager auto-detect
    ↓
└─ Live Mode: IMMEDIATE → LOAD (blocking) → CONTINUE
    ↓
    ├─ Start stream immediately (non-blocking)
    ├─ Load historical data (caller blocks)
    ├─ SessionCoordinator continues
    └─ Gap filling + derivatives (retry-based)
```

---

## Phase 1: Common Infrastructure

### 1.1 Symbol State Tracking

**Location:** `session_coordinator.py`

**Add tracking attributes:**
```python
class SessionCoordinator:
    def __init__(self, ...):
        # Existing
        self._streamed_data = defaultdict(list)
        self._generated_data = defaultdict(list)
        
        # NEW: Dynamic symbol tracking
        self._active_symbols = set()              # Currently streaming
        self._pending_additions = dict()          # symbol -> add_request
        self._pending_removals = set()            # symbols to remove
        self._symbol_add_lock = threading.Lock()  # Thread-safe operations
```

### 1.2 Add Symbol API

**New method signature:**
```python
def add_symbol(
    self,
    symbol: str,
    streams: Optional[List[str]] = None,  # Default: config base streams
    blocking: bool = True                  # Wait for completion
) -> bool:
    """Add a symbol to active session.
    
    Args:
        symbol: Stock symbol to add
        streams: Stream types to enable (default: ["1m"])
        blocking: Whether to wait for symbol to be fully integrated
    
    Returns:
        True if successful, False if failed or already exists
        
    Raises:
        RuntimeError: If session not running
        ValueError: If invalid symbol or stream types
    """
```

### 1.3 Remove Symbol API

**New method signature:**
```python
def remove_symbol(
    self,
    symbol: str,
    immediate: bool = False  # Force immediate removal
) -> bool:
    """Remove a symbol from active session.
    
    Args:
        symbol: Stock symbol to remove
        immediate: If True, remove immediately; if False, graceful shutdown
    
    Returns:
        True if successful, False if not found
        
    Note:
        Graceful removal waits for queues to drain.
        Immediate removal stops streams and clears queues.
    """
```

---

## Phase 2: Backtest Mode Implementation

### 2.1 Pause Mechanism

**Challenge:** Pause both time advancement and data streaming

**Implementation:**
```python
# Add pause control
self._stream_paused = threading.Event()
self._stream_paused.set()  # Initially not paused

# In _streaming_phase():
def _streaming_phase(self):
    while not self._stop_event.is_set():
        # Wait if paused
        self._stream_paused.wait()
        
        # Continue normal streaming
        ...
```

### 2.2 Historical Data Load

**Steps:**
1. Query TimeManager for current session date
2. Fetch full-day data for new symbol (1m bars)
3. Filter to regular trading hours
4. Load into BacktestStreamCoordinator queue

**Implementation:**
```python
def _load_symbol_historical_backtest(
    self,
    symbol: str,
    up_to_time: datetime
) -> bool:
    """Load historical data for symbol up to current backtest time.
    
    Args:
        symbol: Symbol to load
        up_to_time: Current simulated time (don't load data after this)
    
    Returns:
        True if data loaded successfully
    """
    # Get current session date
    current_date = self._time_manager.get_current_time().date()
    
    # Get trading session for date
    trading_session = await self._time_manager.get_trading_session(
        session=db_session,
        date=current_date
    )
    
    if not trading_session or trading_session.is_holiday:
        logger.warning(f"No trading session for {current_date}")
        return False
    
    # Fetch data via DataManager
    data_manager = self._system_manager.get_data_manager()
    
    start_dt = datetime.combine(current_date, trading_session.regular_open)
    end_dt = up_to_time  # Only up to current time
    
    bars = data_manager.get_bars(
        session=None,
        symbol=symbol,
        start=start_dt,
        end=end_dt,
        interval="1m",
        regular_hours_only=True  # Only regular hours
    )
    
    if not bars:
        logger.error(f"No historical data found for {symbol}")
        return False
    
    # Add to stream coordinator queue
    self._stream_coordinator.add_symbol_data(symbol, bars)
    
    logger.info(f"Loaded {len(bars)} bars for {symbol} up to {up_to_time}")
    return True
```

### 2.3 Catch-Up Processing

**Challenge:** Process new symbol's data up to current time before resuming

**Strategy:**
- Data already filtered to `up_to_time` during load
- Stream coordinator queue now has bars ≤ current_time
- When time resumes, normal processing continues
- DataProcessor will detect new symbol and generate derivatives

**No special catch-up needed** - data is already at correct position.

### 2.4 Resume Flow

**Implementation:**
```python
def add_symbol(self, symbol: str, ...) -> bool:
    # 1. Common checks
    if symbol in self._active_symbols:
        logger.warning(f"Symbol {symbol} already active")
        return False
    
    if self.mode == "backtest":
        logger.info(f"[DYNAMIC] Adding {symbol} (BACKTEST MODE)")
        
        # 2. PAUSE
        logger.info("[DYNAMIC] Pausing streaming/time advance")
        self._stream_paused.clear()  # Pause streaming
        time.sleep(0.1)  # Let current iteration complete
        
        # 3. LOAD
        logger.info(f"[DYNAMIC] Loading historical data for {symbol}")
        current_time = self._time_manager.get_current_time()
        success = self._load_symbol_historical_backtest(symbol, current_time)
        
        if not success:
            logger.error(f"[DYNAMIC] Failed to load data for {symbol}")
            self._stream_paused.set()  # Resume
            return False
        
        # 4. MARK STREAMS
        self._streamed_data[symbol] = ["1m"]  # Base interval
        self._generated_data[symbol] = [5, 15]  # Derived (from config)
        self._active_symbols.add(symbol)
        
        # 5. RESUME
        logger.info("[DYNAMIC] Resuming streaming/time advance")
        self._stream_paused.set()
        
        # 6. AUTO-PROCESSING
        # DataProcessor will detect new symbol automatically in next iteration
        # QualityManager will detect new symbol automatically
        
        logger.info(f"[DYNAMIC] ✓ Symbol {symbol} added successfully")
        return True
```

---

## Phase 3: Live Mode Implementation

### 3.1 Non-Blocking Stream Start

**Challenge:** Can't pause real-time market data

**Strategy:**
- Start stream immediately (via data_manager)
- Load historical data in caller thread (blocking)
- Session coordinator continues processing existing symbols

**Implementation:**
```python
def add_symbol(self, symbol: str, ...) -> bool:
    if self.mode == "live":
        logger.info(f"[DYNAMIC] Adding {symbol} (LIVE MODE)")
        
        # 1. START STREAM (non-blocking)
        logger.info(f"[DYNAMIC] Starting stream for {symbol}")
        data_manager = self._system_manager.get_data_manager()
        
        # Start stream (returns immediately)
        data_manager.start_stream(
            symbol=symbol,
            interval="1m",
            callback=self._on_live_data  # Existing callback
        )
        
        # 2. MARK AS ACTIVE (stream is live now)
        self._streamed_data[symbol] = ["1m"]
        self._generated_data[symbol] = [5, 15]
        self._active_symbols.add(symbol)
        
        # 3. LOAD HISTORICAL (BLOCKING - caller waits)
        logger.info(f"[DYNAMIC] Loading historical data for {symbol} (caller blocks)")
        success = self._load_symbol_historical_live(symbol)
        
        if not success:
            logger.warning(f"[DYNAMIC] Historical load failed for {symbol}")
            # Stream continues, gaps will be handled by retry logic
        
        # 4. CONTINUE
        # SessionCoordinator was never paused
        # DataProcessor handles gap filling (if historical load failed)
        # QualityManager generates quality scores
        
        logger.info(f"[DYNAMIC] ✓ Symbol {symbol} added (stream active)")
        return True
```

### 3.2 Historical Data Load (Live)

**Implementation:**
```python
def _load_symbol_historical_live(self, symbol: str) -> bool:
    """Load historical data for live symbol (caller blocks).
    
    Args:
        symbol: Symbol to load
    
    Returns:
        True if loaded successfully
        
    Note:
        This runs in CALLER THREAD (blocking).
        SessionCoordinator continues processing other symbols.
    """
    # Get trailing days from config
    trailing_days = self.session_config.session_data_config.historical.trailing_days
    
    # Calculate date range
    time_mgr = self._time_manager
    current_date = time_mgr.get_current_time().date()
    
    # Go back trailing_days trading days
    start_date = current_date - timedelta(days=trailing_days * 1.5)  # Buffer
    
    # Fetch via DataManager
    data_manager = self._system_manager.get_data_manager()
    bars = data_manager.get_bars(
        session=None,
        symbol=symbol,
        start=datetime.combine(start_date, time.min),
        end=time_mgr.get_current_time(),
        interval="1m",
        regular_hours_only=True
    )
    
    if not bars:
        logger.error(f"No historical data for {symbol}")
        return False
    
    # Add to session_data (bypassing queue - direct insertion)
    for bar in bars:
        self.session_data.add_bar(symbol, bar)
    
    logger.info(f"Loaded {len(bars)} historical bars for {symbol}")
    return True
```

### 3.3 Gap Filling & Retry

**Existing Infrastructure:**
- DataProcessor already has retry logic for gaps
- QualityManager tracks data quality scores
- No changes needed - auto-detection works

**Note:** If historical load fails, gaps will trigger retry up to max attempts.

---

## Phase 4: Symbol Removal

### 4.1 Graceful Removal

**Strategy:**
- Mark symbol for removal
- Stop accepting new data
- Drain existing queues
- Clean up state

**Implementation:**
```python
def remove_symbol(self, symbol: str, immediate: bool = False) -> bool:
    """Remove symbol from session."""
    if symbol not in self._active_symbols:
        logger.warning(f"Symbol {symbol} not active")
        return False
    
    logger.info(f"[DYNAMIC] Removing {symbol} (immediate={immediate})")
    
    if immediate:
        # IMMEDIATE: Stop and clear
        self._immediate_remove_symbol(symbol)
    else:
        # GRACEFUL: Mark and drain
        self._pending_removals.add(symbol)
        # Will be removed when queues drain
    
    return True

def _immediate_remove_symbol(self, symbol: str):
    """Immediately remove symbol (stop streams, clear queues)."""
    # 1. Stop stream
    data_manager = self._system_manager.get_data_manager()
    data_manager.stop_stream(symbol)
    
    # 2. Clear queues
    self._stream_coordinator.clear_symbol_queue(symbol)
    
    # 3. Remove from state
    self._active_symbols.remove(symbol)
    del self._streamed_data[symbol]
    del self._generated_data[symbol]
    
    # 4. Clean up session_data (optional - may want to keep for analysis)
    # self.session_data.clear_symbol(symbol)
    
    logger.info(f"[DYNAMIC] ✓ Symbol {symbol} removed immediately")

def _check_graceful_removals(self):
    """Check if pending removals can be completed (queues empty).
    
    Call this periodically in _streaming_phase().
    """
    for symbol in list(self._pending_removals):
        if self._stream_coordinator.is_queue_empty(symbol):
            logger.info(f"[DYNAMIC] Queue drained for {symbol}, removing")
            self._immediate_remove_symbol(symbol)
            self._pending_removals.remove(symbol)
```

---

## Phase 5: DataProcessor & QualityManager Integration

### 5.1 Auto-Detection (Existing)

**Good News:** Both components already auto-detect new data!

**DataProcessor:**
- Iterates over `session_data.get_all_symbols()`
- Automatically processes new symbols
- No code changes needed

**DataQualityManager:**
- Monitors all symbols in session_data
- Generates quality scores for new symbols
- No code changes needed

### 5.2 Verification

**Add logging to confirm auto-detection:**
```python
# In DataProcessor
def _process_derived_intervals(self):
    current_symbols = self.session_data.get_all_symbols()
    
    # Log new symbols
    new_symbols = current_symbols - self._previously_seen_symbols
    if new_symbols:
        logger.info(f"[PROCESSOR] New symbols detected: {new_symbols}")
    
    self._previously_seen_symbols = current_symbols
    
    # Continue normal processing
    ...
```

---

## Phase 6: CLI Integration

### 6.1 CLI Commands

**Add commands to `data_commands.py`:**
```python
@data_command("symbol-add", "Add symbol to active session")
async def cmd_symbol_add(self, symbol: str, blocking: bool = True):
    """Add a symbol to the active session.
    
    Usage:
        data symbol-add AAPL
        data symbol-add TSLA --blocking=false
    """
    if not self.system_manager.session_coordinator:
        print("Error: No active session")
        return
    
    success = self.system_manager.session_coordinator.add_symbol(
        symbol=symbol.upper(),
        blocking=blocking
    )
    
    if success:
        print(f"✓ Symbol {symbol} added to session")
    else:
        print(f"✗ Failed to add symbol {symbol}")

@data_command("symbol-remove", "Remove symbol from active session")
async def cmd_symbol_remove(self, symbol: str, immediate: bool = False):
    """Remove a symbol from the active session.
    
    Usage:
        data symbol-remove AAPL
        data symbol-remove TSLA --immediate
    """
    if not self.system_manager.session_coordinator:
        print("Error: No active session")
        return
    
    success = self.system_manager.session_coordinator.remove_symbol(
        symbol=symbol.upper(),
        immediate=immediate
    )
    
    if success:
        mode = "immediately" if immediate else "gracefully"
        print(f"✓ Symbol {symbol} removed {mode}")
    else:
        print(f"✗ Failed to remove symbol {symbol}")

@data_command("symbol-list", "List active symbols")
async def cmd_symbol_list(self):
    """List all active symbols in session."""
    if not self.system_manager.session_coordinator:
        print("Error: No active session")
        return
    
    coord = self.system_manager.session_coordinator
    symbols = sorted(coord._active_symbols)
    
    if not symbols:
        print("No active symbols")
        return
    
    print(f"Active symbols ({len(symbols)}):")
    for symbol in symbols:
        streams = coord._streamed_data.get(symbol, [])
        generated = coord._generated_data.get(symbol, [])
        print(f"  {symbol:6} | Stream: {streams} | Generate: {generated}")
```

---

## Phase 7: Testing Strategy

### 7.1 Unit Tests

**File:** `tests/unit/test_dynamic_symbol_management.py`

**Test cases:**
```python
def test_add_symbol_duplicate_check():
    """Test that adding duplicate symbol is rejected."""
    
def test_add_symbol_backtest_pause():
    """Test that streaming pauses during symbol addition (backtest)."""
    
def test_add_symbol_live_non_blocking():
    """Test that live mode doesn't pause for symbol addition."""
    
def test_remove_symbol_immediate():
    """Test immediate symbol removal."""
    
def test_remove_symbol_graceful():
    """Test graceful removal waits for queue drain."""
```

### 7.2 Integration Tests

**File:** `tests/integration/test_dynamic_symbols_integration.py`

**Test cases:**
```python
def test_add_symbol_dataprocessor_detection():
    """Test that DataProcessor auto-detects new symbol."""
    
def test_add_symbol_quality_manager_detection():
    """Test that QualityManager auto-detects new symbol."""
    
def test_backtest_time_consistency():
    """Test that time remains consistent after symbol addition."""
```

### 7.3 E2E Tests

**File:** `tests/e2e/test_dynamic_symbols_e2e.py`

**Test cases:**
```python
def test_add_symbol_full_flow_backtest():
    """Test complete add flow in backtest mode."""
    
def test_add_symbol_full_flow_live():
    """Test complete add flow in live mode (mock streams)."""
    
def test_remove_symbol_full_flow():
    """Test complete removal flow."""
```

---

## Phase 8: Error Handling & Edge Cases

### 8.1 Error Scenarios

| Scenario | Handling |
|----------|----------|
| Symbol already active | Log warning, return False |
| Invalid symbol | Validate, return ValueError |
| Historical data unavailable | Continue with stream only (live mode) or fail (backtest) |
| Stream start fails | Rollback state, return False |
| Queue full | Wait or reject (configurable) |

### 8.2 Thread Safety

**Critical sections:**
```python
# Protect state modifications
with self._symbol_add_lock:
    self._active_symbols.add(symbol)
    self._streamed_data[symbol] = streams
    self._generated_data[symbol] = derived
```

### 8.3 Pause Safety (Backtest)

**Ensure clean pause:**
```python
def _pause_streaming(self):
    """Pause streaming with grace period."""
    logger.debug("[DYNAMIC] Requesting pause")
    self._stream_paused.clear()
    
    # Wait for current iteration to complete
    time.sleep(0.1)
    
    # Verify pause took effect
    if self._current_streaming:
        logger.warning("[DYNAMIC] Streaming still active, waiting...")
        time.sleep(0.2)
    
    logger.debug("[DYNAMIC] Pause confirmed")
```

---

## Implementation Phases Summary

### Phase 1: Foundation (Week 1)
- [ ] Add symbol tracking attributes
- [ ] Implement `add_symbol()` method (stub)
- [ ] Implement `remove_symbol()` method (stub)
- [ ] Add thread-safety locks
- [ ] Write unit tests for state management

### Phase 2: Backtest Mode (Week 2)
- [ ] Implement pause mechanism
- [ ] Implement `_load_symbol_historical_backtest()`
- [ ] Integrate with stream coordinator queue
- [ ] Handle resume logic
- [ ] Test pause/resume cycle

### Phase 3: Live Mode (Week 3)
- [ ] Implement non-blocking stream start
- [ ] Implement `_load_symbol_historical_live()`
- [ ] Handle concurrent operations
- [ ] Test with mock streams
- [ ] Verify gap filling works

### Phase 4: Symbol Removal (Week 4)
- [ ] Implement immediate removal
- [ ] Implement graceful removal
- [ ] Add queue drain detection
- [ ] Test removal scenarios
- [ ] Verify cleanup

### Phase 5: Integration (Week 5)
- [ ] Verify DataProcessor auto-detection
- [ ] Verify QualityManager auto-detection
- [ ] Add logging for new symbol detection
- [ ] Test derivative generation
- [ ] Test quality scoring

### Phase 6: CLI & UX (Week 6)
- [ ] Add CLI commands
- [ ] Add command help text
- [ ] Test CLI integration
- [ ] Document user workflows
- [ ] Add examples

### Phase 7: Testing & Polish (Week 7)
- [ ] Write all unit tests
- [ ] Write integration tests
- [ ] Write E2E tests
- [ ] Performance testing
- [ ] Documentation

### Phase 8: Production Ready (Week 8)
- [ ] Error handling review
- [ ] Thread safety audit
- [ ] Logging audit
- [ ] Documentation complete
- [ ] Release notes

---

## Success Criteria

### Functional
- ✅ Can add symbol during active backtest session
- ✅ Can add symbol during live session
- ✅ New symbol data processed up to current time
- ✅ DataProcessor auto-generates derivatives
- ✅ QualityManager auto-scores quality
- ✅ Can remove symbol gracefully
- ✅ Can remove symbol immediately

### Performance
- ✅ Backtest pause < 1 second for typical symbol
- ✅ Live mode doesn't block session coordinator
- ✅ Historical load completes within retry window

### Reliability
- ✅ No data loss during addition
- ✅ No time inconsistency in backtest
- ✅ Thread-safe operations
- ✅ Graceful failure handling

---

## Documentation Deliverables

1. **User Guide:** How to add/remove symbols via CLI
2. **API Reference:** `add_symbol()` and `remove_symbol()` documentation
3. **Architecture Doc:** Flow diagrams for both modes
4. **Testing Guide:** How to test dynamic symbol management
5. **Troubleshooting:** Common issues and solutions

---

## Dependencies

### Required Components
- ✅ SessionCoordinator (exists)
- ✅ BacktestStreamCoordinator (exists)
- ✅ DataManager.get_bars() (exists)
- ✅ TimeManager.get_current_time() (exists)
- ✅ DataProcessor auto-detection (exists)
- ✅ QualityManager auto-detection (exists)

### New Components
- ⚠️ Pause mechanism (Phase 2)
- ⚠️ Queue drain detection (Phase 4)
- ⚠️ CLI commands (Phase 6)

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Pause disrupts time consistency | HIGH | Verify time unchanged after resume |
| Live historical load blocks too long | MEDIUM | Set timeout, continue with gaps |
| Race condition on state | HIGH | Use locks, audit thread safety |
| Queue overflow on add | LOW | Check capacity before load |
| DataProcessor misses new symbol | MEDIUM | Add explicit notification |

---

## Open Questions

1. **Queue size limits:** Should we check capacity before adding symbol?
2. **Historical data range:** Should live mode load same trailing_days as initial symbols?
3. **Removal timing:** Should graceful removal have a timeout?
4. **State persistence:** Should dynamic additions persist across session restarts?
5. **Notification:** Should we emit events for symbol add/remove?

---

## Next Steps

1. **Review this plan** with team/stakeholders
2. **Clarify open questions** 
3. **Prioritize phases** (all phases or MVP?)
4. **Assign resources** (who implements what)
5. **Start Phase 1** (foundation)

---

**Status:** 📋 **PLAN READY FOR REVIEW**  
**Estimated Effort:** 8 weeks (1 developer)  
**Priority:** TBD  
**Blocking Issues:** None
