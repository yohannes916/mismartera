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
├─ BACKTEST MODE: PAUSE → NOTIFY → PROCESS → DEACTIVATE → CATCHUP → REACTIVATE → RESUME
│   ↓
│   Caller Thread:
│   ├─ 1.1 Pause streaming/time advance (both clock/data-driven)
│   ├─ 1.2 Notify session_coordinator thread (via queue)
│   └─ 1.3 Return (or block waiting for completion)
│   ↓
│   SessionCoordinator Thread:
│   ├─ 2. Update config (determine streams/generated/skipped)
│   ├─ 3. Load full-day historical data (reuse normal process)
│   ├─ 4. Populate stream input queue (reuse normal process)
│   ├─ 5. DEACTIVATE SESSION (block access, pause notifications)
│   │   ├─ 5.1 Clear _session_active flag
│   │   └─ 5.2 DataProcessor.pause_notifications()
│   ├─ 6. CATCHUP: Advance to current time (NEW - while deactivated)
│   │   ├─ 6.1 Drop data outside regular hours (use TimeManager)
│   │   ├─ 6.2 Forward regular-hours data before current time to session_data
│   │   └─ 6.3 AnalysisEngine sees empty (session_data returns [] when deactivated)
│   ├─ 7. REACTIVATE SESSION (resume access, resume notifications)
│   │   ├─ 7.1 Set _session_active flag
│   │   └─ 7.2 DataProcessor.resume_notifications()
│   ├─ 8. Resume streaming/time advance
│   └─ 9. DataProcessor/QualityManager see data and process normally
    ↓
└─ LIVE MODE: CONFIG → LOAD → STREAM → AUTO-DETECT
    ↓
    Caller Thread (blocks):
    ├─ 1. Update config (determine streams/generated/skipped)
    ├─ 2. Load historical data (CALLER BLOCKS)
    ├─ 3. Start stream from data API
    └─ 4. Return
    ↓
    SessionCoordinator Thread (continues normally):
    ├─ 5. Detects new queue automatically
    ├─ 6. Forwards data to session_data (normal process)
    └─ 7. DataProcessor/QualityManager handle gaps + derivatives
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
        
        # NEW: Session activation state (for dynamic symbol catchup)
        self._session_active = threading.Event()  # Session active/deactivated
        self._session_active.set()                # Initially active
```

### 1.2 Session Activation Control

**Purpose:** Prevent AnalysisEngine from seeing intermediate state during catchup.

**Mechanism:**
- Deactivate session during catchup (paused + processing historical data)
- Block session_data access when deactivated
- Drop DataProcessor → AnalysisEngine notifications when deactivated
- Reactivate after catchup completes

**Why this matters:**
During catchup, we're "fast-forwarding" historical data to reach current backtest time. This isn't real-time simulation - it's initialization. AnalysisEngine should only see data after catchup completes to properly simulate real-world behavior.

**Implementation:**
```python
class SessionCoordinator:
    def deactivate_session(self):
        """Deactivate session (block access, drop notifications).
        
        Used during dynamic symbol catchup to prevent AnalysisEngine
        from seeing intermediate state.
        """
        logger.info("[SESSION] Deactivating session (catchup mode)")
        self._session_active.clear()
        
        # Notify DataProcessor to drop AnalysisEngine notifications
        if self.data_processor:
            self.data_processor.pause_notifications()
    
    def activate_session(self):
        """Reactivate session (resume access, resume notifications).
        
        Called after catchup completes to resume normal operations.
        """
        logger.info("[SESSION] Reactivating session (normal mode)")
        self._session_active.set()
        
        # Notify DataProcessor to resume AnalysisEngine notifications
        if self.data_processor:
            self.data_processor.resume_notifications()
    
    def is_session_active(self) -> bool:
        """Check if session is active (not in catchup mode)."""
        return self._session_active.is_set()
```

### 1.3 SessionData Access Control

**Location:** `session_data.py`

**Add access checks to prevent reading during catchup:**

```python
class SessionData:
    def __init__(self, session_coordinator=None):
        self._session_coordinator = session_coordinator  # Reference for active check
        # ... existing attributes
    
    def _check_session_active(self) -> bool:
        """Check if session is active before allowing access.
        
        Returns:
            True if active, False if deactivated (catchup mode)
        """
        if self._session_coordinator is None:
            return True  # No coordinator reference, allow access
        
        return self._session_coordinator.is_session_active()
    
    # Update all access methods to check session state
    def get_bars(self, symbol: str, interval: str = "1m") -> List[BarData]:
        """Get bars for symbol (if session active)."""
        if not self._check_session_active():
            logger.debug(f"[SESSION_DATA] Access blocked (session deactivated): get_bars({symbol}, {interval})")
            return []  # Return empty during catchup
        
        # Normal access
        return self._bars.get((symbol, interval), [])
    
    def get_all_symbols(self) -> Set[str]:
        """Get all symbols (if session active)."""
        if not self._check_session_active():
            logger.debug("[SESSION_DATA] Access blocked (session deactivated): get_all_symbols()")
            return set()  # Return empty during catchup
        
        # Normal access
        return set(self._symbols)
    
    # Similar checks for:
    # - get_latest_bar()
    # - get_bars_since()
    # - get_historical_bars()
    # - etc.
```

**Key Points:**
- All read operations check `is_session_active()` first
- During catchup (deactivated), return empty/None instead of real data
- Write operations (add_bar) continue to work (building state for later)
- AnalysisEngine sees empty results during catchup

### 1.4 DataProcessor Notification Control

**Location:** `data_processor.py`

**Add notification pausing mechanism:**

```python
class DataProcessor:
    def __init__(self, ...):
        # ... existing attributes
        
        # NEW: Notification control
        self._notifications_paused = threading.Event()
        self._notifications_paused.set()  # Initially active (not paused)
    
    def pause_notifications(self):
        """Pause AnalysisEngine notifications (during catchup)."""
        logger.info("[PROCESSOR] Pausing AnalysisEngine notifications")
        self._notifications_paused.clear()
    
    def resume_notifications(self):
        """Resume AnalysisEngine notifications (after catchup)."""
        logger.info("[PROCESSOR] Resuming AnalysisEngine notifications")
        self._notifications_paused.set()
    
    def _notify_analysis_engine(self, event_type: str, data: dict):
        """Notify AnalysisEngine (if not paused).
        
        Args:
            event_type: Type of event (bar_update, derived_computed, etc.)
            data: Event data
        """
        # Check if notifications are paused
        if not self._notifications_paused.is_set():
            logger.debug(f"[PROCESSOR] Dropping notification (paused): {event_type}")
            return  # Drop notification during catchup
        
        # Normal notification
        if self.analysis_engine:
            self.analysis_engine.on_data_update(event_type, data)
    
    # Update all notification call sites:
    def _process_derived_intervals(self):
        # ... compute derived bars ...
        
        # Notify (will be dropped if paused)
        self._notify_analysis_engine("derived_computed", {
            "symbol": symbol,
            "interval": interval,
            "bar": derived_bar
        })
```

**Key Points:**
- Notifications paused via threading.Event (thread-safe)
- All notifications go through `_notify_analysis_engine()` (single point of control)
- Dropped notifications during catchup (no queue buildup)
- Resume after catchup completes

### 1.5 Add Symbol API

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

### 2.1 Thread Coordination

**Flow:**
1. **Caller thread:** Calls `session_coordinator.add_symbol(symbol)`
2. **Caller thread:** Pauses streaming/time advance (both clock-driven and data-driven)
3. **Caller thread:** Notifies session_coordinator thread via flag/queue
4. **Caller thread:** Returns immediately
5. **Session coordinator thread:** Detects notification, processes symbol addition
6. **Session coordinator thread:** Resumes streaming/time advance when complete

**Implementation:**
```python
# Add notification mechanism
self._pending_symbol_additions = queue.Queue()  # Thread-safe queue
self._stream_paused = threading.Event()
self._stream_paused.set()  # Initially not paused

# Caller thread API
def add_symbol(self, symbol: str, blocking: bool = True) -> bool:
    """Add symbol to backtest (caller thread).
    
    Args:
        symbol: Symbol to add
        blocking: If True, wait for completion; if False, return immediately
    
    Returns:
        True if queued successfully (non-blocking) or completed (blocking)
    """
    if self.mode == "backtest":
        logger.info(f"[DYNAMIC] Queueing {symbol} for addition (BACKTEST)")
        
        # 1. PAUSE streaming/time advance
        logger.debug("[DYNAMIC] Pausing streaming/time advance")
        self._stream_paused.clear()
        
        # 2. NOTIFY session coordinator thread
        self._pending_symbol_additions.put(symbol)
        logger.debug(f"[DYNAMIC] Queued {symbol} for processing")
        
        # 3. RETURN (or wait if blocking)
        if blocking:
            # Wait for symbol to appear in active set
            timeout = 10  # seconds
            start = time.time()
            while symbol not in self._active_symbols:
                if time.time() - start > timeout:
                    logger.error(f"[DYNAMIC] Timeout waiting for {symbol}")
                    return False
                time.sleep(0.1)
            logger.info(f"[DYNAMIC] ✓ {symbol} added successfully")
        
        return True

# Session coordinator thread processing
def _streaming_phase(self):
    while not self._stop_event.is_set():
        # Check for pending symbol additions
        if not self._pending_symbol_additions.empty():
            self._process_pending_symbol_additions()
        
        # Wait if paused
        self._stream_paused.wait()
        
        # Continue normal streaming
        ...
```

### 2.2 Config Update & Stream Determination

**Reuse existing logic from session initialization:**

**Implementation:**
```python
def _process_pending_symbol_additions(self):
    """Process pending symbol additions (session coordinator thread)."""
    while not self._pending_symbol_additions.empty():
        symbol = self._pending_symbol_additions.get()
        
        logger.info(f"[DYNAMIC] Processing addition: {symbol}")
        
        try:
            # 1. UPDATE CONFIG (determine streams/generated/skipped)
            self._update_symbol_config(symbol)
            
            # 2. LOAD HISTORICAL DATA (reuse normal process)
            success = self._load_symbol_historical(symbol)
            
            if not success:
                logger.error(f"[DYNAMIC] Failed to load {symbol}")
                self._stream_paused.set()  # Resume anyway
                continue
            
            # 3. POPULATE STREAM INPUT QUEUE (reuse normal process)
            self._populate_symbol_queue(symbol)
            
            # 4. DEACTIVATE SESSION (prevent AnalysisEngine access)
            self.deactivate_session()
            logger.info("[DYNAMIC] Session deactivated (catchup mode)")
            
            # 5. CATCH UP TO CURRENT TIME (unique handling - while deactivated)
            self._catchup_symbol_to_current_time(symbol)
            
            # 6. REACTIVATE SESSION (resume AnalysisEngine access)
            self.activate_session()
            logger.info("[DYNAMIC] Session reactivated (normal mode)")
            
            # 7. SUCCESS - mark active
            self._active_symbols.add(symbol)
            logger.info(f"[DYNAMIC] ✓ {symbol} ready for streaming")
            
        except Exception as e:
            logger.error(f"[DYNAMIC] Error adding {symbol}: {e}")
            # Ensure session is reactivated on error
            self.activate_session()
        
        finally:
            # 8. RESUME streaming/time advance
            logger.info("[DYNAMIC] Resuming streaming/time advance")
            self._stream_paused.set()

def _update_symbol_config(self, symbol: str):
    """Determine what gets loaded/streamed/generated/skipped.
    
    Reuses validation logic from StreamRequirementsCoordinator.
    """
    # Get base streams from session config
    streams = self.session_config.session_data_config.streams
    
    # Determine base interval (use existing logic)
    # For now, assume 1m base + derived from config
    base_interval = "1m"
    derived_intervals = self.session_config.session_data_config.data_upkeep.derived_intervals
    
    # Mark streams
    self._streamed_data[symbol] = [base_interval]
    self._generated_data[symbol] = derived_intervals.copy()
    
    # Add quotes if requested
    if "quotes" in streams:
        self._streamed_data[symbol].append("quotes")
    
    logger.debug(f"[DYNAMIC] {symbol} config: stream={self._streamed_data[symbol]}, "
                f"generate={self._generated_data[symbol]}")
```

### 2.3 Historical Data Load (Reuse Normal Process)

**Reuse existing `_load_historical_bars()` logic:**

**Implementation:**
```python
def _load_symbol_historical(self, symbol: str) -> bool:
    """Load historical data for symbol (reuse normal process).
    
    This is the SAME process used during session initialization.
    """
    # Get current session date
    current_date = self._time_manager.get_current_time().date()
    
    # Reuse existing historical load logic
    # (Same as what runs in _initialize_session for initial symbols)
    data_manager = self._system_manager.get_data_manager()
    
    # Load full day
    bars = data_manager.get_bars(
        session=None,
        symbol=symbol,
        start=datetime.combine(current_date, time.min),
        end=datetime.combine(current_date, time.max),
        interval="1m",
        regular_hours_only=False  # Get all data, filter later
    )
    
    if not bars:
        logger.error(f"[DYNAMIC] No data found for {symbol} on {current_date}")
        return False
    
    logger.info(f"[DYNAMIC] Loaded {len(bars)} bars for {symbol}")
    return True
```

### 2.4 Populate Stream Queue (Reuse Normal Process)

**Reuse existing queue population logic:**

**Implementation:**
```python
def _populate_symbol_queue(self, symbol: str):
    """Populate stream coordinator queue for symbol (reuse normal process).
    
    This is the SAME process used during session initialization.
    """
    # Get data from DataManager (already loaded in previous step)
    data_manager = self._system_manager.get_data_manager()
    current_date = self._time_manager.get_current_time().date()
    
    bars = data_manager.get_bars(
        session=None,
        symbol=symbol,
        start=datetime.combine(current_date, time.min),
        end=datetime.combine(current_date, time.max),
        interval="1m",
        regular_hours_only=False  # Get all, filter in next step
    )
    
    # Add to stream coordinator (same as normal startup)
    for bar in bars:
        self._stream_coordinator.add_bar(symbol, bar)
    
    logger.debug(f"[DYNAMIC] Populated queue for {symbol}: {len(bars)} bars")
```

### 2.5 Catch Up to Current Time (NEW - Unique Handling)

**This is the CRITICAL new logic specific to dynamic symbol addition:**

**Implementation:**
```python
def _catchup_symbol_to_current_time(self, symbol: str):
    """Advance symbol's data to current backtest time (WHILE CLOCK STOPPED).
    
    This is NEW logic specific to dynamic symbol addition.
    
    Process:
        1. Get current backtest time (clock is paused)
        2. Process symbol's queue chronologically
        3. Drop data outside regular hours (use TimeManager)
        4. Forward data within regular hours but before current time to session_data
        5. Leave data >= current time in queue (for normal streaming)
    
    Args:
        symbol: Symbol to catch up
    """
    current_time = self._time_manager.get_current_time()
    current_date = current_time.date()
    
    logger.info(f"[DYNAMIC] Catching up {symbol} to {current_time}")
    
    # Get trading session for today (for regular hours)
    trading_session = await self._time_manager.get_trading_session(
        session=db_session,
        date=current_date
    )
    
    if not trading_session or trading_session.is_holiday:
        logger.warning(f"[DYNAMIC] No trading session for {current_date}")
        return
    
    # Define regular hours for today
    market_open = datetime.combine(current_date, trading_session.regular_open)
    market_close = datetime.combine(current_date, trading_session.regular_close)
    
    logger.debug(f"[DYNAMIC] Regular hours: {market_open} to {market_close}")
    
    # Process queue chronologically (while clock is stopped)
    bars_dropped = 0
    bars_forwarded = 0
    bars_remaining = 0
    
    queue = self._stream_coordinator.get_symbol_queue(symbol)
    processed_bars = []
    
    while queue:
        bar = queue.popleft()  # Get oldest bar
        
        # 4.1 DROP: Outside regular hours
        if bar.timestamp < market_open or bar.timestamp >= market_close:
            bars_dropped += 1
            continue
        
        # 4.2 FORWARD: Within regular hours but before current time
        if bar.timestamp < current_time:
            self.session_data.add_bar(symbol, bar)
            bars_forwarded += 1
        else:
            # KEEP: At or after current time (for normal streaming)
            processed_bars.append(bar)
            bars_remaining += 1
    
    # Put remaining bars back in queue (chronologically ordered)
    for bar in processed_bars:
        queue.append(bar)
    
    logger.info(f"[DYNAMIC] Catchup complete for {symbol}:")
    logger.info(f"  Dropped (non-regular hours): {bars_dropped}")
    logger.info(f"  Forwarded (before current time): {bars_forwarded}")
    logger.info(f"  Remaining (for streaming): {bars_remaining}")
    logger.info(f"  Current backtest time: {current_time}")
```

### 2.6 Session Deactivation During Catchup

**Critical for real-world simulation:**

During catchup, we're processing historical data to reach current backtest time. This is NOT real-time trading - it's initialization. To properly simulate real-world behavior:

1. **Deactivate session** before catchup
2. **Block session_data access** (returns empty to AnalysisEngine)
3. **Drop DataProcessor notifications** (no AnalysisEngine updates)
4. **Reactivate session** after catchup completes

**Flow:**
```python
# 4. DEACTIVATE SESSION
self.deactivate_session()
# - Clears _session_active flag
# - Calls data_processor.pause_notifications()

# 5. CATCHUP (while deactivated)
self._catchup_symbol_to_current_time(symbol)
# - session_data.add_bar() still works (writes continue)
# - session_data.get_bars() returns [] (reads blocked)
# - DataProcessor notifications dropped
# - AnalysisEngine sees no data

# 6. REACTIVATE SESSION
self.activate_session()
# - Sets _session_active flag
# - Calls data_processor.resume_notifications()
# - AnalysisEngine can now see data
```

**Why this matters:**
```
WITHOUT deactivation (WRONG):
  Catchup adds bar at 09:30 → DataProcessor notifies → AnalysisEngine processes
  Catchup adds bar at 09:31 → DataProcessor notifies → AnalysisEngine processes
  ...
  [AnalysisEngine sees 100+ bars instantly, not realistic]

WITH deactivation (CORRECT):
  Catchup adds bars 09:30-11:30 (session deactivated)
  → DataProcessor sees empty from session_data (blocked)
  → No AnalysisEngine notifications
  Session reactivated at 11:30
  → AnalysisEngine starts seeing bars from 11:30 forward (realistic)
```

### 2.7 Resume Flow

**After catch-up and reactivation, resume normal operations:**

**Implementation:**
```python
# In _process_pending_symbol_additions (already shown above):
finally:
    # RESUME streaming/time advance
    logger.info("[DYNAMIC] Resuming streaming/time advance")
    self._stream_paused.set()

# Normal streaming resumes in _streaming_phase:
# - New symbol's remaining bars (>= current_time) are in queue
# - Will be processed chronologically with other symbols
# - Session is ACTIVE (AnalysisEngine can see data)
# - DataProcessor notifications ACTIVE (AnalysisEngine gets updates)
# - DataProcessor will detect new symbol and generate derivatives
# - QualityManager will detect new symbol and compute quality scores
```

**State after resume:**
- ✅ Streaming/time advance resumed
- ✅ Session active (reads allowed)
- ✅ Notifications active (AnalysisEngine receiving updates)
- ✅ New symbol integrated seamlessly
- ✅ AnalysisEngine sees data from current time forward (realistic)

---

## Phase 3: Live Mode Implementation

### 3.1 Flow Overview

**LIVE MODE FLOW:**
1. **Caller thread:** Update config, determine streams/generated/skipped
2. **Caller thread:** Load historical data (BLOCKING - caller waits)
3. **Caller thread:** Start stream from data API
4. **Caller thread:** Return
5. **SessionCoordinator thread:** Detects new queue, forwards data normally
6. **DataProcessor/QualityManager:** Handle gaps and derivatives

**Key Difference from Backtest:**
- No pause needed (real-time streams can't pause)
- Caller blocks for historical load (not session coordinator)
- Stream starts immediately, session coordinator adapts

### 3.2 Implementation

**Caller thread API:**
```python
def add_symbol(self, symbol: str, blocking: bool = True) -> bool:
    """Add symbol to live session (caller thread).
    
    Args:
        symbol: Symbol to add
        blocking: If True, wait for historical load; if False, return immediately
    
    Returns:
        True if successful
    """
    if self.mode == "live":
        logger.info(f"[DYNAMIC] Adding {symbol} (LIVE MODE)")
        
        try:
            # 1. UPDATE CONFIG (determine streams/generated/skipped)
            self._update_symbol_config(symbol)
            logger.debug(f"[DYNAMIC] Config updated for {symbol}")
            
            # 2. LOAD HISTORICAL DATA (caller thread blocks)
            logger.info(f"[DYNAMIC] Loading historical data for {symbol} (caller blocks)")
            success = self._load_symbol_historical_live(symbol)
            
            if not success:
                logger.warning(f"[DYNAMIC] Historical load failed for {symbol}")
                # Continue anyway - stream will handle gaps
            
            # 3. START STREAM FROM DATA API (caller thread)
            logger.info(f"[DYNAMIC] Starting stream for {symbol}")
            data_manager = self._system_manager.get_data_manager()
            
            # Start stream (returns immediately after setup)
            data_manager.start_stream(
                symbol=symbol,
                interval="1m",
                callback=self._on_live_data  # Existing callback
            )
            
            # Mark as active
            self._active_symbols.add(symbol)
            logger.info(f"[DYNAMIC] ✓ {symbol} stream started")
            
            # 4. RETURN
            # SessionCoordinator will detect new queue automatically
            # No notification needed - just starts appearing in data stream
            
            return True
            
        except Exception as e:
            logger.error(f"[DYNAMIC] Failed to add {symbol}: {e}")
            return False

# _update_symbol_config is shared with backtest (already defined above)
```

### 3.3 Historical Data Load (Caller Thread Blocks)

**Implementation:**
```python
def _load_symbol_historical_live(self, symbol: str) -> bool:
    """Load historical data for live symbol (caller blocks).
    
    This is the SAME process used during session initialization,
    but runs in CALLER THREAD instead of session coordinator thread.
    
    Args:
        symbol: Symbol to load
    
    Returns:
        True if loaded successfully
        
    Note:
        Caller thread blocks here.
        SessionCoordinator continues processing other symbols.
    """
    # Get trailing days from config (same as initial symbols)
    trailing_days = self.session_config.session_data_config.historical.trailing_days
    
    # Calculate date range
    time_mgr = self._time_manager
    current_date = time_mgr.get_current_time().date()
    
    # Go back trailing_days trading days (with buffer)
    start_date = current_date - timedelta(days=int(trailing_days * 1.5))
    
    # Fetch via DataManager
    data_manager = self._system_manager.get_data_manager()
    bars = data_manager.get_bars(
        session=None,
        symbol=symbol,
        start=datetime.combine(start_date, time.min),
        end=time_mgr.get_current_time(),
        interval="1m",
        regular_hours_only=True  # Only regular hours for live
    )
    
    if not bars:
        logger.error(f"[DYNAMIC] No historical data for {symbol}")
        return False
    
    # Add to session_data (direct insertion, bypassing queue)
    for bar in bars:
        self.session_data.add_bar(symbol, bar)
    
    logger.info(f"[DYNAMIC] Loaded {len(bars)} historical bars for {symbol}")
    return True
```

### 3.4 SessionCoordinator Auto-Detection

**SessionCoordinator automatically handles new symbol:**

**No code changes needed** - existing logic already works:
```python
# In _streaming_phase (existing code):
def _streaming_phase(self):
    while not self._stop_event.is_set():
        # Process all queues (including newly added symbols)
        for symbol in self._active_symbols:
            # Get next bar for this symbol
            bar = self._stream_coordinator.get_next_bar(symbol)
            
            if bar:
                # Forward to session_data (normal processing)
                self.session_data.add_bar(symbol, bar)
                
                # Notify processors (they auto-detect new symbols)
                self._notify_processors(symbol, bar)
```

**Key point:** When `start_stream()` creates a new queue, it's automatically 
detected and processed in the next iteration.

### 3.5 Gap Filling & Derivatives (Auto-Handled)

**Existing Infrastructure Works:**

**DataProcessor:**
- Iterates over `session_data.get_all_symbols()`
- Automatically detects new symbol
- Generates derivatives (5m, 15m, etc.)
- Handles gaps with retry logic

**QualityManager:**
- Monitors all symbols in session_data
- Automatically detects new symbol
- Computes quality scores
- Triggers gap-fill if needed (up to retry limit)

**No changes needed** - both components already auto-detect new symbols.

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
- [ ] Add session activation control (`_session_active` Event)
- [ ] Implement `add_symbol()` method (stub)
- [ ] Implement `remove_symbol()` method (stub)
- [ ] Add thread-safety locks
- [ ] Implement `deactivate_session()` / `activate_session()` / `is_session_active()`
- [ ] Write unit tests for state management

### Phase 2: SessionData Access Control (Week 2)
- [ ] Add `_session_coordinator` reference to SessionData
- [ ] Implement `_check_session_active()` helper
- [ ] Update all read methods to check session state:
  - [ ] `get_bars()`
  - [ ] `get_all_symbols()`
  - [ ] `get_latest_bar()`
  - [ ] `get_bars_since()`
  - [ ] `get_historical_bars()`
- [ ] Test that reads return empty when deactivated
- [ ] Verify writes still work when deactivated

### Phase 3: DataProcessor Notification Control (Week 3)
- [ ] Add `_notifications_paused` Event to DataProcessor
- [ ] Implement `pause_notifications()` / `resume_notifications()`
- [ ] Create `_notify_analysis_engine()` wrapper
- [ ] Update all notification call sites to use wrapper
- [ ] Test that notifications drop when paused
- [ ] Verify resume re-enables notifications

### Phase 4: Backtest Mode Catchup (Week 4)
- [ ] Implement pause mechanism (`_stream_paused` Event)
- [ ] Implement queue-based notification (`_pending_symbol_additions`)
- [ ] Implement `_process_pending_symbol_additions()`
- [ ] Implement `_load_symbol_historical()`
- [ ] Implement `_populate_symbol_queue()`
- [ ] Implement `_catchup_symbol_to_current_time()`
  - [ ] Use TimeManager for regular hours
  - [ ] Drop bars outside regular hours
  - [ ] Forward bars before current time to session_data
- [ ] Integrate session deactivation before catchup
- [ ] Integrate session reactivation after catchup
- [ ] Test pause/resume cycle with session control
- [ ] Verify AnalysisEngine sees no data during catchup
- [ ] Verify AnalysisEngine sees data after reactivation

### Phase 5: Live Mode (Week 5)
- [ ] Implement `_load_symbol_historical_live()`
- [ ] Implement stream start (caller thread)
- [ ] Handle concurrent operations
- [ ] Test with mock streams
- [ ] Verify gap filling works
- [ ] Verify SessionCoordinator auto-detection
- [ ] Test that no pause occurs (live continues)

### Phase 6: Symbol Removal (Week 6)
- [ ] Implement immediate removal
- [ ] Implement graceful removal
- [ ] Add queue drain detection
- [ ] Test removal scenarios
- [ ] Verify cleanup
- [ ] Test session_data cleanup (optional)

### Phase 7: Integration Testing (Week 7)
- [ ] Verify DataProcessor auto-detection
- [ ] Verify QualityManager auto-detection
- [ ] Add logging for new symbol detection
- [ ] Test derivative generation for new symbols
- [ ] Test quality scoring for new symbols
- [ ] Test session deactivation/reactivation cycle
- [ ] Test notification pause/resume

### Phase 8: CLI & UX (Week 8)
- [ ] Add CLI commands (`data symbol-add`, `data symbol-remove`, `data symbol-list`)
- [ ] Add command help text
- [ ] Test CLI integration
- [ ] Document user workflows
- [ ] Add examples
- [ ] Test blocking vs non-blocking modes

### Phase 9: Testing & Polish (Week 9)
- [ ] Write all unit tests
  - [ ] Session activation control
  - [ ] SessionData access blocking
  - [ ] DataProcessor notification dropping
  - [ ] Catchup logic
- [ ] Write integration tests
  - [ ] Full backtest flow with session control
  - [ ] Full live flow
  - [ ] Symbol removal flows
- [ ] Write E2E tests
  - [ ] Real backtest with dynamic symbol addition
  - [ ] Verify AnalysisEngine behavior
- [ ] Performance testing
- [ ] Documentation

### Phase 10: Production Ready (Week 10)
- [ ] Error handling review
  - [ ] Ensure session always reactivated (even on error)
  - [ ] Ensure notifications always resumed
- [ ] Thread safety audit
  - [ ] Verify all Event usage is safe
  - [ ] Verify lock usage is correct
- [ ] Logging audit
  - [ ] Add debug logs for session state changes
  - [ ] Add debug logs for notification drops
- [ ] Documentation complete
- [ ] Release notes

---

## Success Criteria

### Functional
- ✅ Can add symbol during active backtest session
- ✅ Can add symbol during live session
- ✅ New symbol data processed up to current time
- ✅ Session deactivated during backtest catchup
- ✅ AnalysisEngine sees no data during catchup (realistic simulation)
- ✅ Session reactivated after catchup
- ✅ AnalysisEngine sees data from current time forward (realistic)
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
- ⚠️ Session activation control (Phase 1)
  - `_session_active` Event
  - `deactivate_session()` / `activate_session()` / `is_session_active()`
- ⚠️ SessionData access blocking (Phase 2)
  - `_check_session_active()` in all read methods
- ⚠️ DataProcessor notification control (Phase 3)
  - `_notifications_paused` Event
  - `pause_notifications()` / `resume_notifications()`
  - `_notify_analysis_engine()` wrapper
- ⚠️ Backtest pause mechanism (Phase 4)
  - `_stream_paused` Event
  - `_pending_symbol_additions` Queue
- ⚠️ Catchup logic (Phase 4)
  - `_catchup_symbol_to_current_time()`
- ⚠️ Queue drain detection (Phase 6)
- ⚠️ CLI commands (Phase 8)

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Pause disrupts time consistency | HIGH | Verify time unchanged after resume |
| Session not reactivated on error | CRITICAL | Use try/finally, always reactivate |
| Notifications not resumed on error | CRITICAL | Use try/finally, always resume |
| AnalysisEngine sees catchup data | HIGH | Verify session deactivation works |
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
