# Implementation Plan - Revised Session Flow

## Architecture Principles ✅

1. **Single Source of Truth**: TimeManager for all time, SessionData for all session state
2. **Infer from Structures**: Registration = creating structures, deregistration = deleting structures
3. **No Duplicate Tracking**: Don't maintain separate lists/dicts
4. **Code Reuse**: Move/reorganize existing code, minimize rewrites

## Phase-by-Phase Implementation

---

## BEFORE LOOP: Validation (Split Existing Code)

### NEW: `_validate_stream_requirements()` 
**Action**: EXTRACT from existing `_validate_and_mark_streams()` (lines 2581-2688)

**Keep** (validation logic):
```python
# Lines 2599-2640 - validation part
coordinator = StreamRequirementsCoordinator(...)
data_checker = create_data_manager_checker(data_manager)
result = coordinator.validate_requirements(data_checker)

if not result.valid:
    # Error handling
    return False

# Store results for later use
self._base_interval = result.required_base_interval
self._derived_intervals = result.derivable_intervals
self._streams_validated = True
```

**Remove** (registration part):
```python
# Lines 2642-2688 - MOVE to _register_symbols() instead
# Don't register here, just validate
```

**New Method**:
```python
def _validate_stream_requirements(self) -> bool:
    """Validate stream configuration and data availability (once only).
    
    REUSES: Lines 2599-2640 from _validate_and_mark_streams()
    Does NOT register symbols (that happens in Phase 2).
    """
    # [Copy validation logic from lines 2599-2640]
    # Store results in instance variables
    return True
```

---

## PHASE 1: TEARDOWN & CLEANUP

### NEW: `_teardown_and_cleanup()`
**Action**: CREATE new method (small amount of new code)

**Calls existing methods**:
```python
def _teardown_and_cleanup(self):
    """Phase 1: Clear all state and advance clock."""
    
    # Step 1a: Clear SessionData (EXISTING method)
    logger.info("Step 1a: Clearing SessionData")
    self.session_data.clear()  # ✅ Exists
    
    # Step 1b: Clear queues (simple dict operations)
    logger.info("Step 1b: Clearing stream queues")
    self._bar_queues.clear()
    self._quote_queues.clear() if hasattr(self, '_quote_queues') else None
    self._tick_queues.clear() if hasattr(self, '_tick_queues') else None
    self._symbol_check_counters.clear()
    
    # Step 1c: Teardown threads (NEW - call new teardown methods)
    logger.info("Step 1c: Tearing down threads")
    if hasattr(self.data_processor, 'teardown'):
        self.data_processor.teardown()
    if hasattr(self._quality_manager, 'teardown'):
        self._quality_manager.teardown()
    if hasattr(self._scanner_manager, 'teardown'):
        self._scanner_manager.teardown()
    # Add others as they implement teardown()
    
    # Step 2: Advance clock (EXISTING method - MOVE from _end_session)
    logger.info("Step 2: Advancing clock to next trading day")
    self._advance_to_next_trading_day()  # ✅ Exists (lines 2436-2494)
```

**Code Movement**:
- **MOVE** `_advance_to_next_trading_day()` call from `_end_session()` (line 2431) to here
- **KEEP** the method itself unchanged (lines 2436-2494) ✅

---

## PHASE 2: INITIALIZATION

### Step 3: NEW `_load_session_data()` 
**Action**: REORGANIZE existing methods into one coordinated call

**Reuses Existing Methods**:
```python
def _load_session_data(self):
    """Load ALL session data from config (unified step).
    
    REUSES existing methods:
    - _register_symbols() (NEW - extracted from _validate_and_mark_streams)
    - _manage_historical_data() (mostly unchanged)
    - _register_session_indicators() (NEW - call existing unified method)
    - _load_queues() (unchanged)
    """
    logger.info("=" * 70)
    logger.info("LOADING SESSION DATA FROM CONFIG")
    logger.info("=" * 70)
    
    # Sub-step 1: Register symbols
    logger.info("Step 3.1: Registering symbols")
    self._register_symbols()  # NEW - uses stored validation results
    
    # Sub-step 2-4: Load historical data and indicators
    logger.info("Step 3.2: Loading historical data and indicators")
    self._manage_historical_data()  # ✅ EXISTING (lines 1034-1113)
                                    # But MODIFY to skip pre-registration
    
    # Sub-step 5: Load stream queues
    logger.info("Step 3.3: Loading stream queues")
    self._load_queues()  # ✅ EXISTING (lines 1815-2087)
                        # UNCHANGED - already works
    
    # Sub-step 6: Calculate quality
    logger.info("Step 3.4: Calculating quality scores")
    self._calculate_historical_quality()  # ✅ EXISTING (lines 1257-1333)
                                          # UNCHANGED - already works
    
    logger.info("✓ Session data loaded")
```

#### Sub-method: NEW `_register_symbols()`
**Action**: EXTRACT from `_validate_and_mark_streams()` (lines 2642-2688)

```python
def _register_symbols(self):
    """Register symbols in SessionData using stored validation results.
    
    REUSES: Lines 2642-2688 from _validate_and_mark_streams()
    Uses self._base_interval and self._derived_intervals (from validation)
    """
    symbols_to_process = self.session_config.session_data_config.symbols
    
    # [Copy lines 2642-2688 - symbol registration logic]
    for symbol in symbols_to_process:
        bars = {
            self._base_interval: BarIntervalData(...),
            # Add derived intervals
        }
        symbol_data = SymbolSessionData(
            symbol=symbol,
            base_interval=self._base_interval,
            bars=bars
        )
        self.session_data.register_symbol_data(symbol_data)
```

#### Modify: `_manage_historical_data()`
**Action**: REMOVE pre-registration (lines 1068-1076), keep everything else

**Current** (lines 1068-1089):
```python
# PRE-REGISTER symbols so clear works properly
symbols_to_process = symbols or self.session_config.session_data_config.symbols
logger.info(f"[SESSION_FLOW] PHASE_2.1: Pre-registering {len(symbols_to_process)} symbols")
for symbol in symbols_to_process:
    if symbol not in self.session_data._symbols:  # ← DELETE THIS BLOCK
        self.session_data.register_symbol(symbol)
        logger.debug(f"Pre-registered symbol: {symbol}")
    else:
        logger.debug(f"Symbol {symbol} already registered")

# Clear data BEFORE loading
if symbols:
    # ... clear for specific symbols
else:
    logger.info("[SESSION_FLOW] PHASE_2.1: Clearing ALL session data (current + historical)")
    self.session_data.clear_session_bars()      # ← DELETE (already cleared in Phase 1)
    self.session_data.clear_historical_bars()   # ← DELETE (already cleared in Phase 1)
```

**Modified**:
```python
def _manage_historical_data(self, symbols: Optional[List[str]] = None):
    """Load historical data (assumes symbols already registered).
    
    MODIFIED: Remove pre-registration and clearing (done in Phase 1)
    KEEP: Everything else (lines 1092-1113)
    """
    # Remove lines 1068-1089 (pre-registration and clearing)
    
    # Keep lines 1092-1113 (historical loading)
    symbols_to_process = symbols or self.session_config.session_data_config.symbols
    
    for hist_data_config in historical_config.data:
        self._load_historical_data_config(...)  # ✅ Keep unchanged
    
    # Log statistics (unchanged)
    total_bars = 0
    for symbol_data in self.session_data._symbols.values():
        # ... existing logic
```

#### Add: Indicator Registration
**Action**: CALL existing unified `register_symbol()` method or extract indicator logic

**Option A** (Preferred - reuse existing unified method):
```python
def _register_session_indicators(self):
    """Register indicators for all symbols.
    
    REUSES: Existing _register_symbol_indicators() method (lines 505-556)
    """
    symbols = self.session_config.session_data_config.symbols
    
    for symbol in symbols:
        # Get historical bars for warmup
        symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
        historical_bars = self._get_historical_bars_for_warmup(symbol_data)
        
        # Call existing method
        self._register_symbol_indicators(
            symbol=symbol,
            historical_bars=historical_bars
        )  # ✅ EXISTING method (lines 505-556) - UNCHANGED
```

**Option B** (Alternative - if unified method has issues):
```python
# Extract just the indicator registration part from lines 516-540
# and call it here
```

### Step 4: NEW `_initialize_threads()`
**Action**: CREATE new method (calls new thread methods)

```python
def _initialize_threads(self):
    """Initialize all threads for new session.
    
    Calls setup() on each thread (NEW methods in each thread).
    """
    logger.info("Initializing threads for new session")
    
    # Initialize in order (if order matters)
    if hasattr(self.data_processor, 'setup'):
        logger.debug("Initializing data_processor")
        self.data_processor.setup()
    
    if hasattr(self._quality_manager, 'setup'):
        logger.debug("Initializing quality_manager")
        self._quality_manager.setup()
    
    if hasattr(self._scanner_manager, 'setup'):
        logger.debug("Initializing scanner_manager")
        self._scanner_manager.setup()
    
    # Add others as they implement setup()
    
    logger.info("All threads initialized")
```

### Step 5: REUSE `_scanner_manager.setup_pre_session_scanners()`
**Action**: RENAME or KEEP existing method (lines 908-915)

**Current**:
```python
# Phase 2.5 (line 911)
success = self._scanner_manager.setup_pre_session_scanners()
```

**Modified**:
```python
def _run_pre_session_scans(self):
    """Run pre-session scans if configured.
    
    REUSES: Existing scanner_manager method (possibly renamed)
    """
    if not self._has_pre_session_scans():
        return
    
    logger.info("Running pre-session scans")
    success = self._scanner_manager.setup_pre_session_scanners()  # ✅ EXISTING
    if not success:
        raise RuntimeError("Pre-session scan failed")
```

**Code Movement**:
- **MOVE** this call from old Phase 2.5 (line 911) to new Phase 2 step 5

---

## PHASE 3: ACTIVE SESSION

### Step 6: REUSE `_activate_session()`
**Action**: KEEP unchanged (lines 2095-2113) ✅

```python
# Already exists and works correctly
# No changes needed
```

### Step 7: REUSE `_streaming_phase()`
**Action**: KEEP unchanged (lines 2115-2384) ✅

```python
# Already exists and works correctly
# No changes needed
```

---

## PHASE 4: END SESSION

### MODIFY: `_end_session()` → Rename to `_deactivate_session()`
**Action**: REMOVE cleanup logic (lines 2419-2421, 2429-2431)

**Current** (lines 2390-2434):
```python
def _end_session(self):
    # 1-3: Deactivation and metrics (KEEP)
    self._session_active = False
    self.session_data.set_session_active(False)
    self._scanner_manager.on_session_end()
    # ... metrics recording
    
    # 4. Clear session bars (REMOVE - wrong place!)
    self.session_data.clear_session_bars()  # ← DELETE
    logger.debug("Session bars cleared")     # ← DELETE
    
    # ... current date logging (KEEP)
    
    # 6. Advance to next trading day (REMOVE - moved to Phase 1!)
    if self.mode == "backtest":
        self._advance_to_next_trading_day(current_date)  # ← DELETE
    else:
        logger.info("Live mode: waiting for next trading day")  # ← DELETE
```

**Modified**:
```python
def _deactivate_session(self):
    """Phase 4: Deactivate session and record metrics.
    
    MODIFIED: Remove cleanup (moved to Phase 1)
    KEEP: Lines 2401-2417 (deactivation and metrics)
    """
    # Keep lines 2401-2417 (deactivation and metrics)
    self._session_active = False
    self.session_data.set_session_active(False)
    self._scanner_manager.on_session_end()
    
    logger.info("Session deactivated")
    
    if self._session_start_time is not None:
        self.metrics.record_session_duration(self._session_start_time)
    
    self.metrics.increment_trading_days()
    
    # Get current session date for logging
    current_time = self._time_manager.get_current_time()  # ✅ TimeManager
    current_date = current_time.date()
    
    logger.info(f"Session {current_date} ended - data preserved")
    
    # REMOVED: clear_session_bars() - moved to Phase 1
    # REMOVED: _advance_to_next_trading_day() - moved to Phase 1
```

---

## MAIN LOOP: RESTRUCTURE `_coordinator_loop()`

**Action**: REORGANIZE existing method (lines 871-968)

**Current Structure**:
```python
def _coordinator_loop(self):
    while not self._stop_event.is_set():
        # Phase 1: _initialize_session()
        # Phase 2: _manage_historical_data()
        # Phase 2.5: Scanner setup
        # Phase 3: _load_queues()
        # Phase 4: _activate_session()
        # Phase 5: _streaming_phase()
        # Phase 6: _end_session()
        # Check termination
```

**New Structure**:
```python
def _coordinator_loop(self):
    """Main coordinator loop.
    
    REORGANIZES existing phases, minimal new code.
    """
    # FIRST-TIME VALIDATION (NEW - before loop)
    if not self._streams_validated:
        logger.info("First-time stream validation")
        if not self._validate_stream_requirements():  # NEW
            raise RuntimeError("Stream validation failed")
    
    # Initialize session counter
    session_count = 0
    
    # MAIN LOOP (reorganized)
    while not self._stop_event.is_set():
        try:
            # PHASE 1: Teardown & Cleanup (NEW)
            if session_count > 0:  # Skip on first iteration
                logger.info("=" * 70)
                logger.info("PHASE 1: TEARDOWN & CLEANUP")
                logger.info("=" * 70)
                self._teardown_and_cleanup()  # NEW
            else:
                # First iteration: just advance to start date
                logger.info("First session - advancing to start date")
                current_time = self._time_manager.get_current_time()
                logger.info(f"Starting at {current_time}")
            
            # PHASE 2: Initialization (REORGANIZED)
            logger.info("=" * 70)
            logger.info("PHASE 2: INITIALIZATION")
            logger.info("=" * 70)
            
            # Step 3: Load ALL session data (NEW - calls existing methods)
            self._load_session_data()
            
            # Step 4: Initialize threads (NEW)
            self._initialize_threads()
            
            # Step 5: Pre-session scans (MOVED from old Phase 2.5)
            self._run_pre_session_scans()
            
            # PHASE 3: Active Session (UNCHANGED)
            logger.info("=" * 70)
            logger.info("PHASE 3: ACTIVE SESSION")
            logger.info("=" * 70)
            
            # Step 6: Activate (EXISTING - line 926)
            self._activate_session()  # ✅ Unchanged
            
            # Step 7: Stream (EXISTING - line 932)
            self._streaming_phase()  # ✅ Unchanged
            
            # PHASE 4: End Session (MODIFIED)
            logger.info("=" * 70)
            logger.info("PHASE 4: END SESSION")
            logger.info("=" * 70)
            
            # Step 8: Deactivate (MODIFIED - no cleanup)
            self._deactivate_session()  # MODIFIED from _end_session()
            
            # Step 9: Check if last day (MODIFIED - use TimeManager)
            current_time = self._time_manager.get_current_time()  # ✅ TimeManager
            current_date = current_time.date()
            end_date = self._time_manager.backtest_end_date  # ✅ TimeManager
            
            if current_date >= end_date:
                logger.info(f"Last backtesting day ({current_date}), exiting loop")
                break
            
            # Increment counter
            session_count += 1
            
        except Exception as e:
            logger.error(f"Error in coordinator loop: {e}", exc_info=True)
            break
```

---

## THREAD MODIFICATIONS

### NEW: Add `teardown()` and `setup()` to Each Thread

**Pattern** (apply to each thread):
```python
class DataProcessor:
    # Existing __init__ and methods...
    
    def teardown(self):
        """Reset to initial state (Phase 1).
        
        NEW method - clear caches, reset flags.
        """
        # Clear any caches
        if hasattr(self, '_bar_cache'):
            self._bar_cache.clear()
        
        # Reset flags
        self._initialized = False
        
        # Clear subscriptions (if any)
        if hasattr(self, '_subscriptions'):
            self._subscriptions.clear()
        
        logger.debug("DataProcessor torn down")
    
    def setup(self):
        """Initialize for new session (Phase 2).
        
        NEW method - allocate resources, register subscriptions.
        """
        # Mark as initialized
        self._initialized = True
        
        # Register subscriptions
        self._register_subscriptions()
        
        logger.debug("DataProcessor initialized")
    
    # Existing methods unchanged...
```

**Threads to Modify**:
1. `data_processor.py` - Add teardown/setup
2. `quality_manager.py` or similar - Add teardown/setup
3. `scanner_manager.py` - Add teardown/setup
4. `strategy_manager.py` (if exists) - Add teardown/setup

---

## SUMMARY: Code Reuse Analysis

### ✅ REUSED (Unchanged)
- `_streaming_phase()` (lines 2115-2384) - 100% reuse
- `_activate_session()` (lines 2095-2113) - 100% reuse
- `_load_queues()` (lines 1815-2087) - 100% reuse
- `_calculate_historical_quality()` (lines 1257-1333) - 100% reuse
- `_advance_to_next_trading_day()` (lines 2436-2494) - 100% reuse
- `_register_symbol_indicators()` (lines 505-556) - 100% reuse

### 📦 EXTRACTED (Split Existing)
- `_validate_stream_requirements()` - Extract from `_validate_and_mark_streams()` (validation part)
- `_register_symbols()` - Extract from `_validate_and_mark_streams()` (registration part)

### ✏️ MODIFIED (Minimal Changes)
- `_manage_historical_data()` - Remove pre-registration block (lines 1068-1089)
- `_end_session()` → `_deactivate_session()` - Remove cleanup (lines 2419-2421, 2429-2431)
- `_coordinator_loop()` - Reorganize phase order, add new phase calls

### 🆕 NEW (Small Additions)
- `_teardown_and_cleanup()` - Simple method calling existing clears
- `_load_session_data()` - Coordination method calling existing loaders
- `_initialize_threads()` - Simple loop calling thread.setup()
- `_run_pre_session_scans()` - Wrapper for existing scanner method
- Thread `teardown()` methods - Small cleanup methods
- Thread `setup()` methods - Small initialization methods

### 📊 Code Reuse Percentage
- **~85% reused** (existing methods kept or moved)
- **~10% extracted** (split existing code)
- **~5% new** (coordination and thread lifecycle)

---

## IMPLEMENTATION ORDER

### Phase 1: Preparation (No Breaking Changes)
1. Add instance variables: `_streams_validated`, `_base_interval`, `_derived_intervals`
2. Add `teardown()` and `setup()` methods to threads (can be empty stubs initially)
3. Test: Verify system still works with empty stub methods

### Phase 2: Extract and Split
1. Create `_validate_stream_requirements()` by extracting validation logic
2. Create `_register_symbols()` by extracting registration logic
3. Test: Verify validation and registration work separately

### Phase 3: Create New Coordination Methods
1. Create `_teardown_and_cleanup()` (calls existing methods)
2. Create `_load_session_data()` (calls existing methods)
3. Create `_initialize_threads()` (calls new stub methods)
4. Test: Verify each coordination method works

### Phase 4: Modify Existing Methods
1. Modify `_manage_historical_data()` - remove pre-registration
2. Modify `_end_session()` - remove cleanup, rename to `_deactivate_session()`
3. Test: Verify modified methods work correctly

### Phase 5: Restructure Loop
1. Update `_coordinator_loop()` with new phase structure
2. Add first-time validation before loop
3. Update phase order and calls
4. Test: Run single-day backtest

### Phase 6: Multi-Day Testing
1. Run multi-day backtest
2. Verify data cleared between sessions
3. Verify last day's data preserved
4. Verify indicators registered each session

### Phase 7: Implement Full Thread Lifecycle
1. Fill in `teardown()` methods (clear caches, reset state)
2. Fill in `setup()` methods (allocate resources, register subscriptions)
3. Test: Verify proper resource management across sessions

---

## TESTING CHECKLIST

### Single Session
- [ ] Stream validation works (once only)
- [ ] Symbols registered correctly
- [ ] Historical data loaded
- [ ] Indicators registered and calculated
- [ ] Queues loaded
- [ ] Session activates
- [ ] Streaming works
- [ ] Session deactivates
- [ ] Data preserved at end

### Multi-Day Backtest
- [ ] Day 1 data cleared at start of Day 2
- [ ] Day 2 symbols registered fresh
- [ ] Day 2 indicators registered
- [ ] Clock advances correctly (TimeManager)
- [ ] Last day's data preserved
- [ ] Indicators appear in final JSON export

### Thread Lifecycle
- [ ] Teardown clears thread state
- [ ] Setup initializes thread properly
- [ ] Resources allocated/deallocated correctly
- [ ] No memory leaks across sessions

### Edge Cases
- [ ] First session (no previous data to clear)
- [ ] Mid-session symbol insertion
- [ ] Scanner pause coordination
- [ ] Error handling (setup failure)
- [ ] Early backtest termination

---

## FILES TO MODIFY

### Primary Files
1. `/app/threads/session_coordinator.py` - Main restructuring
2. `/app/threads/data_processor.py` - Add teardown/setup
3. `/app/threads/quality_manager.py` - Add teardown/setup
4. `/app/threads/scanner_manager.py` - Add teardown/setup

### Supporting Files
5. `/app/managers/data_manager/session_data.py` - Verify clear() method
6. `/app/managers/time_manager/api.py` - Verify TimeManager methods used correctly

### Documentation
7. `/docs/windsurf/REVISED_SESSION_FLOW.md` - Reference document
8. `/docs/windsurf/IMPLEMENTATION_PLAN.md` - This document

---

## NOTES

### TimeManager Usage (All Date/Time Operations)
- ✅ `get_current_time()` - Current session time
- ✅ `get_next_trading_date()` - Find next trading day
- ✅ `get_trading_session()` - Get market open/close times
- ✅ `set_backtest_time()` - Advance clock
- ✅ `backtest_end_date` - Check if last day

### Single Source of Truth
- SessionData: All symbols, bars, indicators (inferred from structures)
- TimeManager: All date/time information
- session_config: All configuration data

### No Duplicate Tracking
- Don't maintain `_registered_symbols` list (infer from `session_data._symbols`)
- Don't maintain `_active_indicators` list (infer from `symbol_data.indicators`)
- Don't store `current_date` (query from `time_manager.get_current_time()`)
