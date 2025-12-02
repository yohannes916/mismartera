# Symbol Loading Flow Analysis
**Detailed comparison of initial session start vs mid-session dynamic addition**

---

## PART 1: INITIAL SESSION START FLOW (Before Streaming Begins)

### 1. System Start Trigger
**Location:** `backend/app/managers/system_manager/api.py::start()`

1.1. **Entry Point**
   - User runs: `system start` or `./start_cli.sh`
   - Calls: `SystemManager.start(config_file)`
   - **State Change:** `SystemState.STOPPED` → `SystemState.RUNNING`

1.2. **Configuration Loading**
   - Load `SessionConfig` from JSON file
   - Parse `session_data_config.symbols` (e.g., `["RIVN"]`)
   - Parse `data_streams` configuration
   - **Container:** `self._session_config: SessionConfig`

1.3. **Manager Initialization**
   - Create `TimeManager` (lazy singleton)
   - Create `DataManager` (lazy singleton)
   - Initialize backtest window in TimeManager
   - **Containers:** 
     - `self._time_manager: TimeManager`
     - `self._data_manager: DataManager`

1.4. **SessionData Creation**
   - Get `SessionData` singleton via `get_session_data()`
   - Creates unified data store for all threads
   - **Container:** `session_data: SessionData` (singleton)
   - **Initial State:** Empty, no symbols registered

1.5. **Thread Pool Creation**
   - Create 4 threads:
     - `SessionCoordinator` (main orchestrator)
     - `DataProcessor` (derived bars + indicators)
     - `DataQualityManager` (quality metrics)
     - `AnalysisEngine` (strategy execution)
   - **Containers:**
     - `self._coordinator: SessionCoordinator`
     - `self._data_processor: DataProcessor`
     - `self._quality_manager: DataQualityManager`
     - `self._analysis_engine: AnalysisEngine`

1.6. **Thread Wiring**
   - Wire threads with queues and subscriptions
   - Create `StreamSubscription` (coordinator → processor)
   - Create `Queue` (processor → analysis)
   - **Containers:**
     - `processor_subscription: StreamSubscription`
     - `analysis_queue: Queue`

1.7. **Thread Start Sequence**
   - Start threads in order:
     1. DataProcessor
     2. DataQualityManager
     3. AnalysisEngine
     4. SessionCoordinator (last, orchestrates others)

---

### 2. SessionCoordinator Initialization
**Location:** `backend/app/threads/session_coordinator.py::run()`

2.1. **Thread Start**
   - `SessionCoordinator.start()` creates thread
   - Calls `run()` method in new thread
   - **State Change:** `self._running = False` → `True`

2.2. **Coordinator Loop Entry**
   - Calls `_coordinator_loop()`
   - Enters main loop: `while not self._stop_event.is_set()`
   - **Flag:** `self._stop_event: threading.Event` (initially cleared)

---

### 3. Phase 1: Session Initialization
**Location:** `backend/app/threads/session_coordinator.py::_initialize_session()`

3.1. **Stream/Generate Marking (First Session Only)**
   - Checks: `if not self._streamed_data:`
   - Calls: `_validate_and_mark_streams()`
   - For each symbol in config:
     - Check if `1m` bars exist in Parquet (backtest mode)
     - Mark intervals as STREAMED or GENERATED
   - **Containers:**
     - `self._streamed_data: Dict[str, List[str]]` - e.g., `{"RIVN": ["1m"]}`
     - `self._generated_data: Dict[str, List[int]]` - e.g., `{"RIVN": [5, 15]}`
   - **State:** First-time-only operation, persists for all sessions

3.2. **Inform DataProcessor**
   - Calls: `data_processor.set_derived_intervals(self._generated_data)`
   - DataProcessor stores what intervals to compute
   - **Container in DataProcessor:** `self._derived_intervals: Dict[str, List[int]]`

3.3. **Reset Session State**
   - **State Changes:**
     - `self._session_active = False`
     - `self._session_start_time = None`

3.4. **Get Current Session Date**
   - Query: `current_time = self._time_manager.get_current_time()`
   - Extract: `current_date = current_time.date()`
   - **Variable:** `current_date: date` (e.g., `2025-07-02`)

---

### 4. Phase 2: Historical Data Management
**Location:** `backend/app/threads/session_coordinator.py::_manage_historical_data()`

4.1. **Check Historical Configuration**
   - Check: `if self.session_config.historical_data:`
   - If no config: Skip this phase entirely
   - **Container:** `self.session_config.historical_data: List[HistoricalDataConfig]`

4.2. **For Each Historical Config:**

4.2.1. **Parse Configuration**
   - Extract `trailing_days` (e.g., `10`)
   - Extract `intervals` (e.g., `["1m"]`)
   - Resolve `apply_to` ("all" → all symbols, or specific list)
   - **Variables:**
     - `trailing_days: int`
     - `intervals: List[str]`
     - `symbols: List[str]`

4.2.2. **Calculate Date Range**
   - End date: `current_date - timedelta(days=1)` (yesterday)
   - Start date: Call `_get_start_date_for_trailing_days(end_date, trailing_days)`
     - Uses TimeManager to count back TRADING days
     - Skips weekends and holidays
   - **Variables:**
     - `start_date: date`
     - `end_date: date`

4.2.3. **Load Historical Bars**
   - For each `(symbol, interval)` pair:
     - Call: `_load_historical_bars(symbol, interval, start_date, end_date)`
       - **Method:** Uses existing infrastructure
       - Converts dates to datetimes (00:00 - 23:59:59)
       - Queries: `data_manager.get_bars(session, symbol, start, end, interval)`
       - Returns: `List[BarData]`
     - **Container:** `bars: List[BarData]`

4.2.4. **Store in SessionData**
   - For each bar in bars:
     - Call: `self.session_data.append_bar(symbol, interval, bar)`
     - Writes to `SessionData._symbols[symbol]`
   - **Container in SessionData:** 
     - `_symbols: Dict[str, SymbolSessionData]`
     - Each SymbolSessionData has:
       - `bars_1m: List[BarData]` (1m bars)
       - `bars_derived: Dict[int, List[BarData]]` (5m, 15m, etc.)
       - `historical_bars_1m: List[BarData]` (historical trailing data)
       - `historical_bars_derived: Dict[int, List[BarData]]`

---

### 5. Phase 3: Queue Loading
**Location:** `backend/app/threads/session_coordinator.py::_load_queues()`

5.1. **Mode Detection**
   - Check: `if self.mode == "backtest":`
   - Backtest: Call `_load_backtest_queues()`
   - Live: Call `_start_live_streams()` (not yet implemented)

5.2. **Load Backtest Queues**
**Location:** `_load_backtest_queues()`

5.2.1. **Get Current Session Date**
   - Query: `current_time = self._time_manager.get_current_time()`
   - Extract: `current_date = current_time.date()`
   - **Date Range:** `start_date = end_date = current_date` (single day only)

5.2.2. **For Each Symbol:**
   - Get streamed intervals: `self._get_streamed_intervals_for_symbol(symbol)`
   - Returns intervals marked as STREAMED (e.g., `["1m"]`)
   - **Container:** `streamed_intervals: List[str]`

5.2.3. **For Each (Symbol, Interval) Pair:**

5.2.3.1. **Load Bars from DataManager**
   - Convert dates to datetimes
   - Query: `data_manager.get_bars(session, symbol, start_dt, end_dt, interval, regular_hours_only=True)`
   - Filters to 09:30-16:00 only
   - **Container:** `bars: List[BarData]`
   - **Critical:** If no bars found, raise `RuntimeError` (cannot proceed)

5.2.3.2. **Create Queue**
   - Create deque: `deque(bars)`
   - Store in: `self._bar_queues[(symbol, interval)] = deque(bars)`
   - **Container:** `self._bar_queues: Dict[Tuple[str, str], deque]`
   - **Example:** `{("RIVN", "1m"): deque([bar1, bar2, ...])})`

5.2.3.3. **Queue Properties**
   - Bars are chronologically sorted (from database)
   - Deque allows efficient `popleft()` operations
   - Contains all bars for current session date (09:30-16:00)

---

### 6. Phase 4: Session Activation
**Location:** `backend/app/threads/session_coordinator.py::_activate_session()`

6.1. **Activate SessionData**
   - Call: `self.session_data.activate_session()`
   - **State Change in SessionData:** `self._session_active = False` → `True`
   - **Effect:** Read operations now return data (not None)

6.2. **Set Session Active Flag**
   - **State Change:** `self._session_active = True`
   - **Variable:** `self._session_start_time = self._time_manager.get_current_time()`

6.3. **Log Session Info**
   - Log active symbols, streamed/generated data counts

---

### 7. Phase 5: Streaming Phase
**Location:** `backend/app/threads/session_coordinator.py::_streaming_phase()`

7.1. **Initialize Streaming**
   - Set: `self._stream_paused = threading.Event()`
   - Set event: `self._stream_paused.set()` (streaming enabled)
   - **Flag:** `self._stream_paused: threading.Event` (controls pause/resume)

7.2. **Streaming Loop**
   - Loop: `while self._session_active and not self._stop_event.is_set():`
   - Check: `if not self._stream_paused.is_set():` (pause detection)
   - Process pending symbol additions: `_process_pending_symbol_additions()`

7.3. **Bar Processing**
   - Pop oldest bar from queues
   - For each symbol's 1m queue:
     - Peek: `bar = self._bar_queues[queue_key][0]`
     - Check trading hours (skip if outside)
     - Forward to SessionData: `session_data.append_bar(symbol, "1m", bar)`
     - Advance time: `time_manager.set_backtest_time(next_time)`
     - Notify subscribers (DataProcessor, AnalysisEngine)

---

## PART 2: DYNAMIC SYMBOL ADDITION FLOW (Mid-Session)

### 1. Addition Trigger
**Location:** `backend/app/cli/data_commands.py::add_symbol_command()`

1.1. **User Command**
   - User runs: `data add-symbol AAPL`
   - CLI calls: `add_symbol_command("AAPL", streams=None)`

1.2. **Get SessionCoordinator**
   - Access: `system_mgr._coordinator`
   - Check: System must be RUNNING
   - Check: Coordinator must be initialized

1.3. **Queue Addition Request**
   - Call: `coordinator.add_symbol("AAPL", streams=["1m"], blocking=False)`
   - **Entry Point:** `SessionCoordinator.add_symbol()`

---

### 2. Symbol Addition API Call
**Location:** `backend/app/threads/session_coordinator.py::add_symbol()`

2.1. **Validate Input**
   - Uppercase symbol: `symbol = symbol.upper()`
   - Check not already dynamic: `if symbol in self._dynamic_symbols:`
   - Default streams: `streams = streams or ["1m"]`

2.2. **Mode Routing**
   - Check: `if self.mode == "backtest":`
   - Backtest: Call `_add_symbol_backtest(symbol, streams, blocking)`
   - Live: Call `_add_symbol_live(symbol, streams, blocking)` (stub)

---

### 3. Backtest Mode Addition
**Location:** `backend/app/threads/session_coordinator.py::_add_symbol_backtest()`

3.1. **Queue Addition Request**
   - Create request dict: `{"symbol": "AAPL", "streams": ["1m"]}`
   - Put in queue: `self._pending_symbol_additions.put(request)`
   - **Container:** `self._pending_symbol_additions: queue.Queue`
   - **Thread Safety:** Queue is thread-safe (CLI thread → Coordinator thread)

3.2. **Return Immediately**
   - Return: `True` (non-blocking)
   - Actual processing happens in coordinator thread during streaming

---

### 4. Pending Addition Processing
**Location:** `backend/app/threads/session_coordinator.py::_process_pending_symbol_additions()`

**Called from:** Streaming loop (Phase 5) on each iteration

4.1. **Check for Pending Requests**
   - Check: `if self._pending_symbol_additions.empty():`
   - If empty: Return immediately (no-op)
   - If not empty: Process all pending additions

4.2. **Pause Streaming**
   - Clear event: `self._stream_paused.clear()`
   - **Flag State:** `_stream_paused: Event` (cleared = paused)
   - Sleep 0.1s to let streaming loop detect pause
   - **Effect:** Streaming loop stops processing bars, clock frozen

4.3. **Deactivate Session**
   - Call: `self.session_data.deactivate_session()`
   - **State Change:** `session_data._session_active = True` → `False`
   - **Effect:** Read operations return None (AnalysisEngine blocked)

4.4. **Pause Notifications**
   - Call: `self.data_processor.pause_notifications()`
   - **State Change in DataProcessor:** Notifications disabled
   - **Effect:** AnalysisEngine receives no updates during catchup

---

### 5. Symbol Processing Loop
**Location:** Inside `_process_pending_symbol_additions()` try block

5.1. **Dequeue Request**
   - Get: `request = self._pending_symbol_additions.get_nowait()`
   - Extract: `symbol = request["symbol"]`, `streams = request["streams"]`

5.2. **Step 1: Load Historical Data**
**Location:** `_load_symbol_historical(symbol, streams)`

5.2.1. **Register Symbol**
   - Get current date: `current_date = self._time_manager.get_current_time().date()`
   - Call: `self.session_data.register_symbol(symbol)`
   - **Effect:** Creates `SymbolSessionData` structure in `session_data._symbols[symbol]`
   - **Container:** Empty structure ready for bars

5.2.2. **Note:** 
   - Does NOT load historical trailing days (different from initial start)
   - Only registers symbol, historical loading is optional

5.3. **Step 2: Populate Queues**
**Location:** `_populate_symbol_queues(symbol, streams)`

5.3.1. **Get Current Date**
   - Query: `current_date = self._time_manager.get_current_time().date()`

5.3.2. **For Each Stream (typically ["1m"]):**

5.3.2.1. **Create Queue**
   - Key: `queue_key = (symbol, stream)` (e.g., `("AAPL", "1m")`)
   - Create: `self._bar_queues[queue_key] = deque()`
   - **Container:** New empty deque in `_bar_queues`

5.3.2.2. **Load Bars Using Existing Method**
   - **REUSED CODE:** Calls `self._load_historical_bars(symbol, "1m", current_date, current_date)`
   - **Same method** used in Phase 2 (Historical Management)
   - Converts dates to datetimes
   - Queries DataManager
   - Returns: `List[BarData]`

5.3.2.3. **Populate Queue**
   - For each bar in bars:
     - Append: `self._bar_queues[queue_key].append(bar)`
   - **Result:** Queue contains all bars for current session date (00:00-23:59)

5.4. **Step 3: Catchup to Current Time**
**Location:** `_catchup_symbol_to_current_time(symbol)`

5.4.1. **Get Current Backtest Time**
   - Query: `current_time = self._time_manager.get_current_time()`
   - **Example:** `12:06:00` (clock is frozen at this time)

5.4.2. **Get Trading Session**
   - Query TimeManager for trading session
   - Extract: `market_open`, `market_close` (e.g., 09:30, 16:00)
   - Strip timezone info for comparison (make all naive)

5.4.3. **Process Queue Until Current Time**
   - Get queue: `bar_queue = self._bar_queues[(symbol, "1m")]`
   - Initialize counters: `bars_processed = 0`, `bars_dropped = 0`

5.4.4. **Catchup Loop**
   ```python
   while bar_queue:
       # Peek at oldest bar
       bar = bar_queue[0]
       bar_ts = bar.timestamp.replace(tzinfo=None) if bar.timestamp.tzinfo else bar.timestamp
       
       # Check if reached current time
       if bar_ts >= current_time:  # e.g., >= 12:06
           break  # Stop processing
       
       # Pop the bar
       bar_queue.popleft()
       
       # Check trading hours
       if bar_ts < market_open or bar_ts >= market_close:
           bars_dropped += 1
           continue  # Drop pre/post-market bars
       
       # Write to SessionData
       self.session_data.append_bar(symbol, "1m", bar)
       bars_processed += 1
   ```

5.4.5. **Result:**
   - Bars from 09:30 to 12:05: **WRITTEN** to session_data
   - Bars from 12:06 onwards: **REMAIN** in queue for streaming
   - Bars before 09:30 or after 16:00: **DROPPED**
   - **State:** Symbol now has complete history from market open to current time
   - **Clock:** Never advanced during catchup

5.5. **Step 4: Mark as Dynamic**
   - Lock: `with self._symbol_operation_lock:`
   - Add: `self._dynamic_symbols.add(symbol)`
   - **Container:** `self._dynamic_symbols: Set[str]`
   - **Thread Safety:** Lock protects set during concurrent access

---

### 6. Reactivation (Finally Block)
**Location:** `_process_pending_symbol_additions()` finally block

6.1. **Always Executes** (even on error)

6.2. **Reactivate Session**
   - Call: `self.session_data.activate_session()`
   - **State Change:** `_session_active = False` → `True`
   - **Effect:** Read operations work again

6.3. **Resume Notifications**
   - Call: `self.data_processor.resume_notifications()`
   - **Effect:** AnalysisEngine will receive updates

6.4. **Resume Streaming**
   - Set event: `self._stream_paused.set()`
   - **Flag State:** Event is set (streaming enabled)
   - **Effect:** Streaming loop resumes processing bars, clock advances

---

## PART 3: COMPARISON & ANALYSIS

### Shared Infrastructure (Reused Code)

#### 1. `_load_historical_bars(symbol, interval, start_date, end_date)`
**Reused By:**
- Initial start: Phase 2 (Historical Management)
- Dynamic addition: `_populate_symbol_queues()`

**Functionality:**
- Converts dates to datetimes
- Calls `data_manager.get_bars()`
- Returns `List[BarData]`
- **Result:** Same bars loading logic for both flows

#### 2. `session_data.append_bar(symbol, interval, bar)`
**Reused By:**
- Initial start: Phase 2 (writing historical bars)
- Dynamic addition: `_catchup_symbol_to_current_time()` (writing catchup bars)

**Functionality:**
- Validates bar
- Appends to appropriate list in `SymbolSessionData`
- Updates high/low/volume tracking
- **Result:** Same bar writing logic for both flows

#### 3. `TimeManager` queries
**Reused By:**
- Both flows use `get_current_time()`
- Both flows use `get_trading_session()` for market hours

#### 4. `DataManager.get_bars()` API
**Reused By:**
- Both flows query same DataManager method
- Both use same parameters: `(session, symbol, start, end, interval)`

---

### Duplicated Code (Opportunities for Refactoring)

#### 1. Date-to-Datetime Conversion
**Appears In:**
- `_load_historical_bars()` (line 1820-1822)
- `_load_backtest_queues()` (line 922-923)
- `_populate_symbol_queues()` (implicit in call to `_load_historical_bars()`)

**Pattern:**
```python
start_dt = datetime.combine(start_date, time(0, 0))
end_dt = datetime.combine(end_date, time(23, 59, 59))
```

**Potential Refactor:** Extract to helper method

#### 2. Queue Creation Pattern
**Appears In:**
- `_load_backtest_queues()` (line 965)
- `_populate_symbol_queues()` (line 2795-2796)

**Pattern:**
```python
queue_key = (symbol, interval)
self._bar_queues[queue_key] = deque(bars)
```

**Note:** Not duplicated, but similar. Could extract to `_create_queue(symbol, interval, bars)`

#### 3. Trading Hours Validation
**Appears In:**
- `_load_backtest_queues()` (uses `regular_hours_only=True` in DataManager call)
- `_catchup_symbol_to_current_time()` (manual validation with market_open/close)

**Difference:**
- Initial start: Filter happens in DataManager (database query level)
- Dynamic addition: Filter happens in coordinator (after loading all bars)

**Potential Refactor:** Consistent approach - either always filter in DataManager or always filter in coordinator

---

### Key Differences Between Flows

#### 1. Historical Data Loading

**Initial Start (Phase 2):**
- **Loads:** Trailing days (e.g., 10 days of historical bars)
- **Target:** `session_data` historical containers
- **Timing:** Before session activation
- **Purpose:** Indicator calculation, context

**Dynamic Addition:**
- **Loads:** Current session date only
- **Target:** `_bar_queues` first, then session_data during catchup
- **Timing:** During active session (session deactivated temporarily)
- **Purpose:** Catchup to current time

#### 2. Queue Population

**Initial Start (Phase 3):**
- **Source:** Database query for current date
- **Timing:** Before session activation
- **All Symbols:** Populates queues for all configured symbols
- **Clock:** Not yet started

**Dynamic Addition:**
- **Source:** Database query for current date (same)
- **Timing:** During active session (streaming paused)
- **Single Symbol:** Only populates queue for new symbol
- **Clock:** Frozen at current time

#### 3. Bar Writing to SessionData

**Initial Start:**
- **Phase 2:** Writes historical trailing bars to `historical_bars_1m`
- **Phase 5:** Writes streaming bars to `bars_1m` during normal streaming
- **Notifications:** Enabled after activation

**Dynamic Addition:**
- **Catchup:** Writes bars to `bars_1m` (not historical)
- **Range:** From market open to current time
- **Notifications:** Disabled during catchup, enabled after

#### 4. Session State Management

**Initial Start:**
- **Activation:** Single activation call in Phase 4
- **State:** `STOPPED` → `RUNNING` (linear progression)

**Dynamic Addition:**
- **Deactivation:** Temporarily deactivate during catchup
- **Reactivation:** Always reactivate in finally block
- **State:** `ACTIVE` → `DEACTIVATED` → `ACTIVE` (temporary pause)

---

### State Variables & Containers Summary

#### SystemManager State
```python
_state: SystemState = STOPPED | RUNNING
_session_config: SessionConfig
_coordinator: SessionCoordinator
_data_processor: DataProcessor
_time_manager: TimeManager
_data_manager: DataManager
```

#### SessionCoordinator State
```python
# Thread control
_running: bool = False | True
_stop_event: threading.Event

# Session state
_session_active: bool = False | True
_session_start_time: Optional[datetime]

# Stream/generate marking (persistent across sessions)
_streamed_data: Dict[str, List[str]] = {"RIVN": ["1m"]}
_generated_data: Dict[str, List[int]] = {"RIVN": [5, 15]}

# Queue containers
_bar_queues: Dict[Tuple[str, str], deque] = {
    ("RIVN", "1m"): deque([bar1, bar2, ...]),
    ("AAPL", "1m"): deque([bar1, bar2, ...])  # Added dynamically
}

# Dynamic symbols
_dynamic_symbols: Set[str] = {"AAPL"}  # Added mid-session
_symbol_operation_lock: threading.Lock  # Protects _dynamic_symbols
_pending_symbol_additions: queue.Queue  # Thread-safe request queue

# Streaming control
_stream_paused: threading.Event  # set() = enabled, clear() = paused
```

#### SessionData State
```python
_session_active: bool = False | True  # Controls read access
_lock: threading.RLock  # Protects symbol data
_symbols: Dict[str, SymbolSessionData] = {
    "RIVN": SymbolSessionData(...),
    "AAPL": SymbolSessionData(...)  # Added dynamically
}
```

#### SymbolSessionData State (per symbol)
```python
# Current session bars
bars_1m: List[BarData]
bars_derived: Dict[int, List[BarData]]  # {5: [...], 15: [...]}

# Historical bars (trailing days)
historical_bars_1m: List[BarData]
historical_bars_derived: Dict[int, List[BarData]]

# Aggregated stats
session_high: float
session_low: float
session_volume: int
```

---

### Critical Flags & Control Flow

#### 1. Session Activation Control
- **Flag:** `session_data._session_active`
- **Effect:** When `False`, all reads return `None`
- **Used By:** Dynamic addition to hide intermediate state from AnalysisEngine

#### 2. Streaming Pause Control
- **Flag:** `_stream_paused: threading.Event`
- **States:**
  - `set()`: Streaming enabled
  - `clear()`: Streaming paused
- **Checked By:** Streaming loop every iteration
- **Used By:** Dynamic addition to freeze clock during catchup

#### 3. Stop Event
- **Flag:** `_stop_event: threading.Event`
- **Effect:** When set, exits coordinator loop
- **Thread Safety:** Event objects are thread-safe

#### 4. Thread Operation Lock
- **Lock:** `_symbol_operation_lock: threading.Lock`
- **Protects:** `_dynamic_symbols` set
- **Critical Sections:** Add/remove operations on set

---

### Flow Sequence Numbers

#### Initial Start Complete Sequence

1. **SystemManager.start()**
   1.1. Load config
   1.2. Create managers
   1.3. Create SessionData singleton
   1.4. Create thread pool
   1.5. Wire threads
   1.6. Start threads
   1.7. Set state to RUNNING

2. **SessionCoordinator.run()**
   2.1. Enter coordinator loop
   2.2. **Phase 1:** Initialize session
      2.2.1. Mark streams/generate (first time only)
      2.2.2. Reset session state
      2.2.3. Get current date
   2.3. **Phase 2:** Historical management
      2.3.1. Load trailing days historical bars
      2.3.2. Write to session_data historical containers
   2.4. **Phase 3:** Queue loading
      2.4.1. Query bars for current session date
      2.4.2. Create deques in _bar_queues
      2.4.3. Populate with bars
   2.5. **Phase 4:** Session activation
      2.5.1. Activate session_data
      2.5.2. Set _session_active = True
   2.6. **Phase 5:** Streaming phase
      2.6.1. Enter streaming loop
      2.6.2. Process bars from queues
      2.6.3. Advance clock
      2.6.4. Notify subscribers

#### Dynamic Addition Complete Sequence

1. **User Command:** `data add-symbol AAPL`
   1.1. CLI calls add_symbol_command()
   1.2. Get coordinator from system_mgr
   1.3. Call coordinator.add_symbol()

2. **SessionCoordinator.add_symbol()**
   2.1. Validate symbol
   2.2. Route to _add_symbol_backtest()
   2.3. Queue request in _pending_symbol_additions
   2.4. Return immediately

3. **Streaming Loop Detects Pending Addition**
   3.1. Check queue in _process_pending_symbol_additions()
   3.2. Pause streaming (clear _stream_paused)
   3.3. Deactivate session_data
   3.4. Pause data_processor notifications

4. **Process Addition**
   4.1. Dequeue request
   4.2. **Step 1:** Register symbol in session_data
   4.3. **Step 2:** Populate queues
      4.3.1. Create queue for (symbol, "1m")
      4.3.2. Load bars using _load_historical_bars()
      4.3.3. Append bars to queue
   4.4. **Step 3:** Catchup to current time
      4.4.1. Get current time (frozen)
      4.4.2. Get trading hours from TimeManager
      4.4.3. Process queue until current time
      4.4.4. Write bars to session_data (09:30 to current)
      4.4.5. Drop bars outside trading hours
      4.4.6. Leave future bars in queue
   4.5. **Step 4:** Mark as dynamic symbol

5. **Reactivation (Finally Block)**
   5.1. Reactivate session_data
   5.2. Resume notifications
   5.3. Resume streaming (set _stream_paused)
   5.4. Return to streaming loop

---

## PART 4: CODE REUSE OPPORTUNITIES

### Already Reused (Good)
✅ `_load_historical_bars()` - Both flows use same method
✅ `session_data.append_bar()` - Both flows use same API
✅ `TimeManager` queries - Both flows use same service
✅ `DataManager.get_bars()` - Both flows use same API

### Could Be Extracted (Minor)
⚠️ Date-to-datetime conversion - Appears in multiple places
⚠️ Queue creation pattern - Similar code in two places
⚠️ Trading hours validation - Two different approaches

### Major Differences (By Design)
❌ Historical trailing days - Only initial start loads these
❌ Catchup logic - Only dynamic addition needs this
❌ Session pause/resume - Only dynamic addition needs this

---

## PART 5: SUMMARY

### Initial Start Purpose
Load all configured symbols with historical context before starting streaming.

### Dynamic Addition Purpose
Add new symbol mid-session, catching up to current state without interrupting other symbols.

### Key Insight
Dynamic addition reuses the same bar loading infrastructure (`_load_historical_bars`) but adds catchup logic to write bars up to current time while keeping clock frozen. This ensures new symbol appears to have been there from the start, maintaining consistent state for AnalysisEngine.

### Design Quality
- ✅ Good code reuse for core functionality
- ✅ Clear separation between normal flow and dynamic flow
- ✅ Thread-safe communication via queues and locks
- ✅ Proper state management with flags and events
- ⚠️ Minor duplication that could be extracted to helpers
- ✅ Dynamic flow properly handles edge cases (timezone, trading hours)

---

**Last Updated:** 2025-12-02 03:45 PST
**Files Analyzed:** 
- `backend/app/managers/system_manager/api.py`
- `backend/app/threads/session_coordinator.py`
