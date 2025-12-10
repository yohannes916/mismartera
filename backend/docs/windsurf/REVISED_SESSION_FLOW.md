# Revised Session Flow - Clean Architecture

## Your Corrected Flow ✅

```
FIRST-TIME SETUP (Before Loop)
===============================
0. Validate stream configuration (ONCE)
   - Check session_config format
   - Validate Parquet data availability (backtest)
   - Determine base interval and derived intervals
   - Set _streams_validated = True
   - Do NOT register anything yet

MAIN LOOP (while not last_day):
================================

PHASE 1: TEARDOWN & CLEANUP
============================
1. Clear all state and resources
   a) SessionData.clear() 
      - Remove all symbols
      - Reset to initial state
   b) Clear stream queues (SessionCoordinator)
      - self._bar_queues.clear()
      - self._quote_queues.clear() (if any)
      - self._tick_queues.clear() (if any)
   c) Teardown all threads (reset internal state)
      - session_coordinator.teardown()
      - data_processor.teardown()
      - data_quality_manager.teardown()
      - scanner_manager.teardown()
      - strategy_manager.teardown() (if exists)
      - Each teardown() deallocates resources, resets state
   
2. Advance clock to new trading day @ market open
   - Get next trading date from TimeManager
   - Get market open time from TimeManager
   - Set backtest time to new_date @ market_open

PHASE 2: INITIALIZATION
========================
3. Load session data from session_config (ALL IN ONE STEP)
   a) Register symbols in SessionData
   b) Load historical bars (trailing days)
   c) Register session indicators
   d) Calculate historical indicators
   e) Load stream queues for current day
   f) Calculate quality scores
   
   Note: This replaces old Phase 2 + Phase 3
   All data comes from session_config
   All done before session activation

4. Initialize all threads (call setup/init)
   - session_coordinator.setup()
   - data_processor.setup()
   - data_quality_manager.setup()
   - scanner_manager.setup()
   - strategy_manager.setup() (if exists)
   - Each setup() initializes resources, prepares for session

5. Run pre-session scan (if configured)
   - scanner_manager.run_pre_session_scans()
   - Pause is not needed (session not active yet)

PHASE 3: ACTIVE SESSION
========================
6. Activate session
   - Mark session as active
   - Signal all threads session is ready

7. Start streaming (clock advancement + data processing)
   - Advance clock (data-driven or clock-driven)
   - Process bars from queues
   - Update indicators
   - Run strategies
   - Pause for mid-session scans (coordinated)
   - Pause for mid-session insertions (coordinated)
   - Stop at market close (exactly)

PHASE 4: END SESSION (NO CLEANUP!)
===================================
8. Deactivate session
   - Mark session as inactive
   - Record metrics
   - Notify all threads session ended
   - Leave ALL data intact (for analysis)

9. Check if last backtesting day
   - If YES: Exit loop → System stops with last day's data ✅
   - If NO: Continue to next iteration → Phase 1 clears everything
```

## Comparison: Old vs New

### OLD (Broken)
```
Loop:
  Phase 1: _initialize_session()
    - Validate streams (first time only) → REGISTERS symbols ❌
    - Reset some state
  
  Phase 2: _manage_historical_data()
    - Pre-register symbols ❌ (duplicates Phase 1)
    - Clear bars (partial) ❌
    - Load historical data
  
  Phase 2.5: Scanner setup
  
  Phase 3: _load_queues()
    - Load backtest queues
  
  Phase 4: _activate_session()
  
  Phase 5: _streaming_phase()
  
  Phase 6: _end_session()
    - Clear session bars ❌ (wrong time!)
    - Advance clock ❌ (should be pre-session)
```

### NEW (Clean)
```
BEFORE LOOP:
  Validate streams (ONCE, no registration)

Loop:
  Phase 1: Teardown & Cleanup
    - Clear SessionData completely
    - Clear stream queues
    - Teardown all threads
    - Advance clock to new day
  
  Phase 2: Initialization
    - Load ALL session data (symbols, bars, indicators, queues) → ONE STEP
    - Initialize all threads
    - Run pre-session scans
  
  Phase 3: Active Session
    - Activate session
    - Stream data
  
  Phase 4: End Session
    - Deactivate
    - Keep data intact
    - Check if last day
```

## Key Changes

### 1. Separate Validation from Registration

**OLD**:
```python
def _validate_and_mark_streams(self):
    # Validates AND registers symbols ❌
    for symbol in symbols:
        symbol_data = SymbolSessionData(...)
        self.session_data.register_symbol_data(symbol_data)
```

**NEW**:
```python
# BEFORE LOOP (once)
def _validate_stream_requirements(self):
    """Validate configuration and data availability.
    
    Does NOT register anything, just validates:
    - Config format correct
    - Data available in Parquet
    - Base interval determined
    """
    coordinator = StreamRequirementsCoordinator(...)
    result = coordinator.validate_requirements(data_checker)
    
    if not result.valid:
        raise RuntimeError("Stream validation failed")
    
    # Store results for later use
    self._base_interval = result.required_base_interval
    self._derived_intervals = result.derivable_intervals
    self._streams_validated = True

# IN LOOP (every session)
def _load_session_data(self):
    """Load ALL session data from config.
    
    Uses validation results from first-time validation.
    Registers symbols, loads bars, indicators, queues.
    """
    # Register symbols using stored validation results
    for symbol in symbols:
        symbol_data = SymbolSessionData(
            symbol=symbol,
            base_interval=self._base_interval,
            bars=self._create_bar_structure()
        )
        self.session_data.register_symbol_data(symbol_data)
    
    # Load historical bars
    self._load_historical_bars()
    
    # Register indicators
    self._register_indicators()
    
    # Load stream queues
    self._load_stream_queues()
```

### 2. Thread Teardown/Setup Pattern

**Each thread implements**:
```python
class DataProcessor:
    def teardown(self):
        """Reset to initial state, deallocate resources.
        
        Called at START of new session (Phase 1).
        """
        # Clear caches
        self._processed_bars.clear()
        
        # Reset flags
        self._initialized = False
        
        # Clear subscriptions
        self._subscriptions.clear()
        
        # Deallocate resources
        if self._some_resource:
            self._some_resource.close()
            self._some_resource = None
    
    def setup(self):
        """Initialize for new session.
        
        Called after data loaded (Phase 2 step 4).
        """
        # Allocate resources
        self._some_resource = Resource()
        
        # Set flags
        self._initialized = True
        
        # Register subscriptions
        self._register_subscriptions()
```

### 3. Unified Data Loading

**NEW**: One method that does everything
```python
def _load_session_data(self):
    """Load ALL session data in one coordinated step.
    
    This replaces:
    - Old Phase 2: _manage_historical_data()
    - Old Phase 3: _load_queues()
    - Scattered indicator registration
    
    Everything comes from session_config.
    """
    logger.info("=" * 70)
    logger.info("LOADING SESSION DATA")
    logger.info("=" * 70)
    
    # 1. Register symbols (using stored validation results)
    logger.info("Step 1: Registering symbols")
    self._register_symbols()
    
    # 2. Load historical bars
    logger.info("Step 2: Loading historical bars")
    self._load_historical_bars()
    
    # 3. Register session indicators
    logger.info("Step 3: Registering session indicators")
    self._register_session_indicators()
    
    # 4. Calculate historical indicators
    logger.info("Step 4: Calculating historical indicators")
    self._calculate_historical_indicators()
    
    # 5. Load stream queues for current day
    logger.info("Step 5: Loading stream queues")
    self._load_stream_queues()
    
    # 6. Calculate quality scores
    logger.info("Step 6: Calculating quality scores")
    self._calculate_quality_scores()
    
    logger.info("=" * 70)
    logger.info("✓ SESSION DATA LOADED")
    logger.info("=" * 70)
```

### 4. Clear Queues in Phase 1

**NEW**:
```python
def _teardown_and_cleanup(self):
    """Phase 1: Clear all state and resources."""
    
    # 1a. Clear SessionData
    logger.info("Step 1a: Clearing SessionData")
    self.session_data.clear()
    
    # 1b. Clear stream queues
    logger.info("Step 1b: Clearing stream queues")
    self._bar_queues.clear()
    self._quote_queues.clear()
    self._tick_queues.clear()
    self._symbol_check_counters.clear()
    
    # 1c. Teardown all threads
    logger.info("Step 1c: Tearing down threads")
    self.data_processor.teardown()
    self._quality_manager.teardown()
    self._scanner_manager.teardown()
    # Add others as needed
    
    # 2. Advance clock to new day
    logger.info("Step 2: Advancing clock to new trading day")
    self._advance_to_next_trading_day()
```

## Updated Loop Structure

```python
def _coordinator_loop(self):
    """Main coordinator loop."""
    
    # FIRST-TIME VALIDATION (before loop)
    if not self._streams_validated:
        logger.info("First-time stream validation")
        self._validate_stream_requirements()  # No registration!
    
    # MAIN LOOP
    while not self._stop_event.is_set():
        try:
            # PHASE 1: Teardown & Cleanup
            logger.info("=" * 70)
            logger.info("PHASE 1: TEARDOWN & CLEANUP")
            logger.info("=" * 70)
            
            if self._session_count > 0:  # Skip on first iteration
                self._teardown_and_cleanup()
            else:
                # First iteration: just advance to first day
                self._advance_to_first_trading_day()
            
            # PHASE 2: Initialization
            logger.info("=" * 70)
            logger.info("PHASE 2: INITIALIZATION")
            logger.info("=" * 70)
            
            # Step 3: Load ALL session data
            self._load_session_data()
            
            # Step 4: Initialize threads
            self._initialize_threads()
            
            # Step 5: Pre-session scans
            if self._has_pre_session_scans():
                self._run_pre_session_scans()
            
            # PHASE 3: Active Session
            logger.info("=" * 70)
            logger.info("PHASE 3: ACTIVE SESSION")
            logger.info("=" * 70)
            
            # Step 6: Activate session
            self._activate_session()
            
            # Step 7: Stream data
            self._streaming_phase()
            
            # PHASE 4: End Session
            logger.info("=" * 70)
            logger.info("PHASE 4: END SESSION")
            logger.info("=" * 70)
            
            # Step 8: Deactivate (no cleanup!)
            self._deactivate_session()
            
            # Step 9: Check if last day
            if self._is_last_day():
                logger.info("Last backtesting day - exiting loop")
                break
            
            # Increment counter
            self._session_count += 1
            
        except Exception as e:
            logger.error(f"Error in coordinator loop: {e}", exc_info=True)
            break
```

## Thread Interface

Each thread must implement:

```python
class ThreadInterface:
    def teardown(self):
        """Reset to initial state, deallocate resources.
        
        Called at START of new session (before data loaded).
        Must be idempotent (safe to call multiple times).
        """
        raise NotImplementedError
    
    def setup(self):
        """Initialize for new session.
        
        Called after data loaded, before session activated.
        Can access SessionData (symbols, bars, indicators).
        """
        raise NotImplementedError
    
    def on_session_end(self):
        """Notification that session ended.
        
        Called when session deactivates.
        Do NOT clear state here (happens in next teardown).
        """
        raise NotImplementedError
```

## Benefits of This Approach

1. **Clean Separation**: Validation (once) vs Registration (every session)

2. **Single Responsibility**: Each phase has one clear job
   - Phase 1: Clean up
   - Phase 2: Load and initialize
   - Phase 3: Run session
   - Phase 4: Deactivate and check

3. **Thread Lifecycle**: Explicit teardown/setup for ALL threads

4. **Data Integrity**: Last day's data preserved (no cleanup in Phase 4)

5. **Resource Management**: Proper allocation/deallocation

6. **Testability**: Each phase can be tested independently

7. **Debugging**: Clear phase boundaries in logs

## Migration Path

### Files to Modify

1. **session_coordinator.py**
   - Add `_validate_stream_requirements()` (before loop)
   - Add `_teardown_and_cleanup()` (Phase 1)
   - Add `_load_session_data()` (Phase 2, step 3)
   - Add `_initialize_threads()` (Phase 2, step 4)
   - Update `_end_session()` → `_deactivate_session()` (no cleanup)
   - Restructure `_coordinator_loop()`

2. **data_processor.py**
   - Add `teardown()` method
   - Add `setup()` method
   - Update `on_session_end()` if exists

3. **quality_manager.py** (or similar)
   - Add `teardown()` method
   - Add `setup()` method

4. **scanner_manager.py**
   - Add `teardown()` method
   - Add `setup()` method
   - Update `setup_pre_session_scanners()` → `run_pre_session_scans()`

5. **strategy_manager.py** (if exists)
   - Add `teardown()` method
   - Add `setup()` method

## Questions to Address

1. **First iteration special case**: Skip teardown on first session (no previous data)

2. **Thread initialization order**: Does order matter? (Probably not if properly designed)

3. **Error handling**: If setup() fails, should we teardown? (Yes, for consistency)

4. **Mid-session insertion**: How does it interact with teardown/setup? (Should pause, insert, resume)

5. **Scanner pause**: Does it need special handling? (Probably coordinate with stream pause)
