# Session Activation Control - Critical Addition

**Date:** 2025-12-01  
**Feature:** Session deactivation during catchup for realistic simulation  
**Impact:** CRITICAL - Changes AnalysisEngine behavior during dynamic symbol addition

---

## Problem Statement

When dynamically adding a symbol during an active backtest session:

**WITHOUT session deactivation (WRONG):**
```
Time: 11:30 (current backtest time)
Add symbol TSLA:
  - Load full-day data (09:30 - 16:00)
  - Catchup: Process bars 09:30 - 11:30
    → Bar at 09:30 added → DataProcessor notifies → AnalysisEngine processes
    → Bar at 09:31 added → DataProcessor notifies → AnalysisEngine processes
    → Bar at 09:32 added → DataProcessor notifies → AnalysisEngine processes
    → ... (100+ bars instantly)
  - Resume streaming at 11:30

Result: AnalysisEngine sees 100+ bars instantly - NOT realistic simulation
```

**WITH session deactivation (CORRECT):**
```
Time: 11:30 (current backtest time)
Add symbol TSLA:
  - Load full-day data (09:30 - 16:00)
  - DEACTIVATE SESSION
    → session_data reads return empty
    → DataProcessor notifications dropped
  - Catchup: Process bars 09:30 - 11:30
    → Bars added to session_data (writes work)
    → DataProcessor sees empty (reads blocked)
    → No AnalysisEngine notifications
  - REACTIVATE SESSION
    → session_data reads work normally
    → DataProcessor notifications resume
  - Resume streaming at 11:30

Result: AnalysisEngine sees data from 11:30 forward - realistic simulation
```

---

## Solution: Three-Layer Control

### Layer 1: SessionCoordinator - Activation Control

**Location:** `session_coordinator.py`

```python
class SessionCoordinator:
    def __init__(self, ...):
        # NEW: Session activation state
        self._session_active = threading.Event()
        self._session_active.set()  # Initially active
    
    def deactivate_session(self):
        """Deactivate session (block access, drop notifications)."""
        logger.info("[SESSION] Deactivating session (catchup mode)")
        self._session_active.clear()
        
        # Notify DataProcessor to drop notifications
        if self.data_processor:
            self.data_processor.pause_notifications()
    
    def activate_session(self):
        """Reactivate session (resume access, resume notifications)."""
        logger.info("[SESSION] Reactivating session (normal mode)")
        self._session_active.set()
        
        # Notify DataProcessor to resume notifications
        if self.data_processor:
            self.data_processor.resume_notifications()
    
    def is_session_active(self) -> bool:
        """Check if session is active (not in catchup mode)."""
        return self._session_active.is_set()
```

**Usage in catchup:**
```python
try:
    # ... load and populate queue ...
    
    # DEACTIVATE before catchup
    self.deactivate_session()
    
    # CATCHUP (while deactivated)
    self._catchup_symbol_to_current_time(symbol)
    
    # REACTIVATE after catchup
    self.activate_session()
    
except Exception as e:
    # CRITICAL: Always reactivate on error
    self.activate_session()
```

---

### Layer 2: SessionData - Access Blocking

**Location:** `session_data.py`

```python
class SessionData:
    def __init__(self, session_coordinator=None):
        self._session_coordinator = session_coordinator
        # ... existing attributes
    
    def _check_session_active(self) -> bool:
        """Check if session is active before allowing access."""
        if self._session_coordinator is None:
            return True  # No coordinator, allow access
        
        return self._session_coordinator.is_session_active()
    
    # UPDATE: All read methods check session state
    def get_bars(self, symbol: str, interval: str = "1m") -> List[BarData]:
        """Get bars for symbol (if session active)."""
        if not self._check_session_active():
            logger.debug(f"[SESSION_DATA] Access blocked: get_bars({symbol}, {interval})")
            return []  # Return empty during catchup
        
        return self._bars.get((symbol, interval), [])
    
    def get_all_symbols(self) -> Set[str]:
        """Get all symbols (if session active)."""
        if not self._check_session_active():
            logger.debug("[SESSION_DATA] Access blocked: get_all_symbols()")
            return set()  # Return empty during catchup
        
        return set(self._symbols)
    
    # Similar for:
    # - get_latest_bar() → returns None when deactivated
    # - get_bars_since() → returns [] when deactivated
    # - get_historical_bars() → returns [] when deactivated
    
    # NOTE: Write methods (add_bar) DO NOT check - writes always work
    def add_bar(self, symbol: str, bar: BarData):
        """Add bar (works even when deactivated)."""
        # No check - writes always work
        self._bars[(symbol, bar.interval)].append(bar)
```

**Key Points:**
- ✅ Reads blocked (return empty) when deactivated
- ✅ Writes continue (building state for later)
- ✅ AnalysisEngine sees empty during catchup

---

### Layer 3: DataProcessor - Notification Control

**Location:** `data_processor.py`

```python
class DataProcessor:
    def __init__(self, ...):
        # ... existing attributes
        
        # NEW: Notification control
        self._notifications_paused = threading.Event()
        self._notifications_paused.set()  # Initially active
    
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
        
        Single control point for all notifications.
        """
        # Check if paused
        if not self._notifications_paused.is_set():
            logger.debug(f"[PROCESSOR] Dropping notification: {event_type}")
            return  # Drop notification during catchup
        
        # Normal notification
        if self.analysis_engine:
            self.analysis_engine.on_data_update(event_type, data)
    
    # UPDATE: All notification call sites use wrapper
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
- ✅ All notifications go through single wrapper
- ✅ Notifications dropped (not queued) during catchup
- ✅ Resume after catchup completes

---

## Complete Flow

### Backtest Mode with Session Deactivation

```python
def _process_pending_symbol_additions(self):
    """Process pending symbol additions (SessionCoordinator thread)."""
    while not self._pending_symbol_additions.empty():
        symbol = self._pending_symbol_additions.get()
        
        logger.info(f"[DYNAMIC] Processing: {symbol}")
        
        try:
            # 1. Update config
            self._update_symbol_config(symbol)
            
            # 2. Load historical data (full day)
            success = self._load_symbol_historical(symbol)
            if not success:
                self._stream_paused.set()
                continue
            
            # 3. Populate stream queue
            self._populate_symbol_queue(symbol)
            
            # 4. DEACTIVATE SESSION (CRITICAL)
            self.deactivate_session()
            logger.info("[DYNAMIC] Session deactivated (catchup mode)")
            # State:
            # - _session_active = False
            # - session_data.get_*() returns empty
            # - data_processor notifications paused
            
            # 5. CATCHUP (while deactivated)
            self._catchup_symbol_to_current_time(symbol)
            # Behavior:
            # - Bars added to session_data (writes work)
            # - DataProcessor sees empty (reads blocked)
            # - No AnalysisEngine notifications (dropped)
            # - AnalysisEngine effectively blind to catchup
            
            # 6. REACTIVATE SESSION (CRITICAL)
            self.activate_session()
            logger.info("[DYNAMIC] Session reactivated (normal mode)")
            # State:
            # - _session_active = True
            # - session_data.get_*() works normally
            # - data_processor notifications resume
            # - AnalysisEngine can see data
            
            # 7. Mark active
            self._active_symbols.add(symbol)
            logger.info(f"[DYNAMIC] ✓ {symbol} ready")
            
        except Exception as e:
            logger.error(f"[DYNAMIC] Error: {e}")
            # CRITICAL: Always reactivate on error
            self.activate_session()
        
        finally:
            # 8. Resume streaming
            logger.info("[DYNAMIC] Resuming streaming")
            self._stream_paused.set()
```

---

## Error Handling - CRITICAL

### Always Reactivate Session

**WRONG (can leave session deactivated):**
```python
self.deactivate_session()
self._catchup_symbol_to_current_time(symbol)
self.activate_session()  # ❌ Skipped if catchup raises exception
```

**CORRECT (always reactivates):**
```python
try:
    self.deactivate_session()
    self._catchup_symbol_to_current_time(symbol)
    self.activate_session()
except Exception as e:
    logger.error(f"Error: {e}")
    self.activate_session()  # ✅ Always called
```

**BEST (using finally):**
```python
try:
    self.deactivate_session()
    self._catchup_symbol_to_current_time(symbol)
except Exception as e:
    logger.error(f"Error: {e}")
finally:
    self.activate_session()  # ✅ ALWAYS called (even on exception)
```

---

## Testing Requirements

### Phase 2: SessionData Access Blocking Tests

```python
def test_session_data_blocks_reads_when_deactivated():
    """Verify session_data returns empty when session deactivated."""
    session_data.add_bar("AAPL", bar_09_30)
    
    # Active: returns data
    assert len(session_data.get_bars("AAPL")) == 1
    
    # Deactivate
    coordinator.deactivate_session()
    
    # Blocked: returns empty
    assert len(session_data.get_bars("AAPL")) == 0
    assert len(session_data.get_all_symbols()) == 0
    
    # Reactivate
    coordinator.activate_session()
    
    # Active again: returns data
    assert len(session_data.get_bars("AAPL")) == 1

def test_session_data_allows_writes_when_deactivated():
    """Verify session_data allows writes even when deactivated."""
    coordinator.deactivate_session()
    
    # Writes work
    session_data.add_bar("AAPL", bar_09_30)
    
    # Reads blocked
    assert len(session_data.get_bars("AAPL")) == 0
    
    # Reactivate
    coordinator.activate_session()
    
    # Now visible
    assert len(session_data.get_bars("AAPL")) == 1
```

### Phase 3: DataProcessor Notification Tests

```python
def test_data_processor_drops_notifications_when_paused():
    """Verify DataProcessor drops notifications when paused."""
    notifications = []
    
    def mock_notify(event_type, data):
        notifications.append(event_type)
    
    data_processor.analysis_engine = Mock()
    data_processor.analysis_engine.on_data_update = mock_notify
    
    # Active: notifications sent
    data_processor._notify_analysis_engine("bar_update", {})
    assert len(notifications) == 1
    
    # Pause
    data_processor.pause_notifications()
    
    # Paused: notifications dropped
    data_processor._notify_analysis_engine("bar_update", {})
    assert len(notifications) == 1  # No new notification
    
    # Resume
    data_processor.resume_notifications()
    
    # Active again: notifications sent
    data_processor._notify_analysis_engine("bar_update", {})
    assert len(notifications) == 2
```

### Phase 4: Integration Test

```python
def test_analysis_engine_sees_no_data_during_catchup():
    """Verify AnalysisEngine sees no data during catchup (realistic simulation)."""
    # Start session at 11:30
    time_manager.set_backtest_time(datetime(2025, 7, 2, 11, 30))
    
    # Track AnalysisEngine notifications
    notifications_during_catchup = []
    notifications_after_catchup = []
    
    # Add symbol dynamically
    coordinator.add_symbol("TSLA")
    # During add_symbol:
    # - Deactivate session
    # - Catchup processes 09:30-11:30 (120 bars)
    #   → session_data gets bars
    #   → DataProcessor sees empty
    #   → No AnalysisEngine notifications
    # - Reactivate session
    
    # Verify: No notifications during catchup
    assert len(notifications_during_catchup) == 0
    
    # Resume streaming
    # Bar at 11:30 arrives
    # → session_data gets bar
    # → DataProcessor sees bar
    # → AnalysisEngine notified
    
    # Verify: Notifications after reactivation
    assert len(notifications_after_catchup) > 0
    assert notifications_after_catchup[0]["symbol"] == "TSLA"
    assert notifications_after_catchup[0]["timestamp"] >= datetime(2025, 7, 2, 11, 30)
```

---

## Architecture Impact

### Before (WITHOUT Deactivation):
```
Catchup (09:30-11:30)
  ↓
  Bar 09:30 → session_data → DataProcessor → AnalysisEngine ❌
  Bar 09:31 → session_data → DataProcessor → AnalysisEngine ❌
  Bar 09:32 → session_data → DataProcessor → AnalysisEngine ❌
  ... (120 bars instantly)
  
AnalysisEngine: Sees 120 bars instantly (NOT realistic)
```

### After (WITH Deactivation):
```
Deactivate Session
  ↓
Catchup (09:30-11:30)
  ↓
  Bar 09:30 → session_data ✅ → DataProcessor (reads blocked) ✗
  Bar 09:31 → session_data ✅ → DataProcessor (reads blocked) ✗
  Bar 09:32 → session_data ✅ → DataProcessor (reads blocked) ✗
  ... (120 bars, writes work, reads blocked)
  ↓
Reactivate Session
  ↓
Resume Streaming (11:30 forward)
  ↓
  Bar 11:30 → session_data → DataProcessor → AnalysisEngine ✅
  Bar 11:31 → session_data → DataProcessor → AnalysisEngine ✅
  
AnalysisEngine: Sees bars from 11:30 forward (realistic simulation)
```

---

## Summary

### What Changed:
1. **SessionCoordinator**: Added activation control (`deactivate`/`activate`/`is_active`)
2. **SessionData**: Block reads when deactivated, allow writes
3. **DataProcessor**: Drop notifications when paused

### Why It Matters:
- ✅ **Realistic simulation**: AnalysisEngine sees data from current time forward
- ✅ **Clean state**: No intermediate catchup data visible
- ✅ **Proper behavior**: Mimics real-world trading (data appears when available)

### Critical Requirements:
- ⚠️ **Always reactivate**: Use try/finally to ensure session is reactivated
- ⚠️ **Always resume**: Use try/finally to ensure notifications resume
- ⚠️ **Test thoroughly**: Verify AnalysisEngine sees no data during catchup

---

**Status:** 📋 **DESIGN COMPLETE** - Ready for implementation  
**Priority:** 🔴 **CRITICAL** - Changes AnalysisEngine behavior  
**Impact:** 🎯 **HIGH** - Ensures realistic backtest simulation
