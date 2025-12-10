# Phase 2.2 Complete: Scanner Manager

## ✅ Implemented

Created the Scanner Manager for orchestrating scanner lifecycle and execution.

---

## File Created

**`app/threads/scanner_manager.py`** (650+ lines)

Complete scanner orchestration system with:
- Scanner loading and instantiation
- Lifecycle execution (setup/scan/teardown)
- State machine tracking
- Schedule management
- Error handling

---

## Core Components

### 1. ScannerState Enum

```python
class ScannerState(Enum):
    """Scanner state machine states."""
    INITIALIZED = "initialized"
    SETUP_PENDING = "setup_pending"
    SETUP_COMPLETE = "setup_complete"
    SCAN_PENDING = "scan_pending"
    SCANNING = "scanning"
    SCAN_COMPLETE = "scan_complete"
    TEARDOWN_PENDING = "teardown_pending"
    TEARDOWN_COMPLETE = "teardown_complete"
    ERROR = "error"
```

**Purpose**: Track scanner lifecycle state.

---

### 2. ScannerInstance Dataclass

```python
@dataclass
class ScannerInstance:
    """Tracks a scanner instance and its state.
    
    Attributes:
        module: Module path (e.g., "scanners.gap_scanner")
        scanner: Loaded scanner instance
        config: Scanner configuration
        state: Current state in lifecycle
        pre_session: Whether to run pre-session scan
        regular_schedules: List of regular session schedules
        next_scan_time: Next scheduled scan time
        last_scan_time: Last completed scan time
        scan_count: Number of scans completed
        error: Error message if state is ERROR
        qualifying_symbols: Set of symbols found by this scanner
    """
```

**Purpose**: Track individual scanner state and metadata.

---

### 3. ScannerManager Class

```python
class ScannerManager:
    """Manages scanner lifecycle and execution."""
    
    def __init__(self, system_manager)
    def initialize(self) -> bool
    def setup_pre_session_scanners(self) -> bool
    def on_session_start(self) -> None
    def on_session_end(self) -> None
    def check_and_execute_scans(self) -> None
    def get_scanner_states(self) -> Dict[str, Dict[str, Any]]
    def shutdown(self) -> None
```

---

## Key Methods

### initialize()

```python
def initialize(self) -> bool:
    """Initialize scanner manager and load scanners.
    
    - Gets references to session_data and time_manager
    - Loads scanners from session config
    - Imports and instantiates scanner classes
    - Creates ScannerInstance for each scanner
    
    Returns:
        True if successful, False otherwise
    """
```

**What it does**:
1. Get system references
2. Read scanner configs from session config
3. Load each enabled scanner
4. Track in `_scanners` dict

---

### setup_pre_session_scanners()

```python
def setup_pre_session_scanners(self) -> bool:
    """Setup and run pre-session scanners.
    
    Called before session starts. Executes:
    1. setup() for all scanners
    2. scan() for pre-session scanners
    3. teardown() for pre-session-only scanners
    
    Returns:
        True if successful, False otherwise
    """
```

**Workflow**:
```
┌─────────────────────────────────────────────────────────┐
│ 1. Setup ALL scanners                                   │
│    for each scanner:                                    │
│      _execute_setup(scanner)                            │
│        ├─ Create ScanContext                            │
│        ├─ Call scanner.setup(context)                   │
│        └─ Update state to SETUP_COMPLETE                │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 2. Run PRE-SESSION scans                                │
│    for each scanner with pre_session=true:             │
│      _execute_scan(scanner, "pre-session")              │
│        ├─ Create ScanContext                            │
│        ├─ Call scanner.scan(context)                    │
│        ├─ Track qualifying symbols                      │
│        └─ Update state to SCAN_COMPLETE                 │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 3. Teardown PRE-SESSION-ONLY scanners                   │
│    for each scanner with pre_session=true AND           │
│                         no regular_schedules:           │
│      _execute_teardown(scanner)                         │
│        ├─ Create ScanContext                            │
│        ├─ Call scanner.teardown(context)                │
│        └─ Update state to TEARDOWN_COMPLETE             │
└─────────────────────────────────────────────────────────┘
```

---

### check_and_execute_scans()

```python
def check_and_execute_scans(self) -> None:
    """Check if any scanners need to run and execute them.
    
    Called periodically by SessionCoordinator during regular session.
    
    For each scanner with regular_schedules:
      - Check if current_time >= next_scan_time
      - Execute scan if due
      - Update next_scan_time
    """
```

**Schedule Checking**:
```python
current_time = time_manager.get_current_time()

for scanner in scanners:
    if scanner.next_scan_time and current_time >= scanner.next_scan_time:
        # Execute scan
        _execute_scan(scanner, "regular")
        
        # Update next scan time
        _update_next_scan_time(scanner)
```

---

### on_session_start()

```python
def on_session_start(self) -> None:
    """Notify scanner manager that session has started.
    
    - Sets _session_started flag
    - Initializes next_scan_time for all regular session scanners
    """
```

---

### on_session_end()

```python
def on_session_end(self) -> None:
    """Notify scanner manager that session has ended.
    
    - Sets _session_ended flag
    - Tears down all remaining scanners
    """
```

---

## Lifecycle Execution

### _execute_setup()

```python
def _execute_setup(self, instance: ScannerInstance) -> bool:
    """Execute scanner setup.
    
    1. Create ScanContext
    2. Call scanner.setup(context)
    3. Update state to SETUP_COMPLETE
    4. Log timing
    5. Handle errors
    """
```

**Example Output**:
```
[SCANNER_MANAGER] Setting up scanner: scanners.gap_scanner
[SCANNER_MANAGER] Setup complete for scanners.gap_scanner (123.45ms)
```

---

### _execute_scan()

```python
def _execute_scan(self, instance: ScannerInstance, scan_type: str) -> bool:
    """Execute scanner scan.
    
    1. Check if already scanning (skip if so)
    2. Create ScanContext
    3. Call scanner.scan(context)
    4. Update tracking (scan_count, qualifying_symbols)
    5. Update state to SCAN_COMPLETE
    6. Log results and timing
    """
```

**Example Output**:
```
[SCANNER_MANAGER] Scanning (pre-session): scanners.gap_scanner
[SCANNER_MANAGER] Scan complete for scanners.gap_scanner: 3 symbols, 456.78ms
[SCANNER_MANAGER] Qualifying symbols: ['TSLA', 'NVDA', 'AMD']
```

---

### _execute_teardown()

```python
def _execute_teardown(self, instance: ScannerInstance) -> bool:
    """Execute scanner teardown.
    
    1. Create ScanContext
    2. Call scanner.teardown(context)
    3. Update state to TEARDOWN_COMPLETE
    4. Log timing
    """
```

**Example Output**:
```
[SCANNER_MANAGER] Tearing down scanner: scanners.gap_scanner
[SCANNER_MANAGER] Teardown complete for scanners.gap_scanner (89.01ms)
```

---

## Schedule Management

### _update_next_scan_time()

```python
def _update_next_scan_time(self, instance: ScannerInstance) -> None:
    """Update next scan time for scanner based on schedules.
    
    For each schedule:
      - Check if current time is within schedule window (start-end)
      - Calculate next scan time based on interval
      - Select earliest next scan time across all schedules
      - Set to None if no more scans in any schedule
    """
```

**Example**:
```python
# Scanner with schedule: 09:35-15:55, interval=5m
# Current time: 10:15:00
# Next scan: 10:20:00

# Current time: 15:56:00
# Next scan: None (past end time)
```

---

### _parse_time()

```python
def _parse_time(self, time_str: str) -> dt_time:
    """Parse time string in HH:MM format.
    
    Args:
        time_str: "09:35"
    
    Returns:
        time(9, 35)
    """
```

---

## Scanner Loading

### _load_scanner()

```python
def _load_scanner(self, scanner_config) -> bool:
    """Load a scanner from module path.
    
    1. Import module (e.g., "scanners.gap_scanner")
    2. Find BaseScanner subclass in module
    3. Instantiate scanner with config
    4. Create ScannerInstance tracker
    5. Add to _scanners dict
    """
```

**Module Discovery**:
```python
# Import module
module = importlib.import_module("scanners.gap_scanner")

# Find BaseScanner subclass
for attr_name in dir(module):
    attr = getattr(module, attr_name)
    if (isinstance(attr, type) and 
        issubclass(attr, BaseScanner) and 
        attr is not BaseScanner):
        scanner_class = attr
        break

# Instantiate
scanner = scanner_class(config=scanner_config.config)
```

---

## State Tracking

### get_scanner_states()

```python
def get_scanner_states(self) -> Dict[str, Dict[str, Any]]:
    """Get current state of all scanners.
    
    Returns:
        {
          "scanners.gap_scanner": {
            "state": "scan_complete",
            "scan_count": 1,
            "last_scan_time": "2024-01-02T09:30:00",
            "next_scan_time": null,
            "qualifying_symbols": ["TSLA", "NVDA"],
            "error": null
          }
        }
    """
```

**Purpose**: Monitoring and debugging.

---

## Integration Points

### SystemManager Integration

```python
class SystemManager:
    def __init__(self):
        # Create scanner manager
        self._scanner_manager = ScannerManager(self)
    
    def get_scanner_manager(self):
        return self._scanner_manager
    
    async def initialize(self):
        # Initialize scanner manager
        success = self._scanner_manager.initialize()
        if not success:
            raise RuntimeError("Scanner manager initialization failed")
```

---

### SessionCoordinator Integration

```python
class SessionCoordinator:
    def _initialize_session(self):
        # Setup pre-session scanners
        scanner_mgr = self._system_manager.get_scanner_manager()
        success = scanner_mgr.setup_pre_session_scanners()
        if not success:
            raise RuntimeError("Pre-session scanner setup failed")
    
    def _activate_session(self):
        # Notify scanner manager
        scanner_mgr = self._system_manager.get_scanner_manager()
        scanner_mgr.on_session_start()
    
    def _run_session_loop(self):
        scanner_mgr = self._system_manager.get_scanner_manager()
        
        while session_active:
            # Check for scheduled scans
            scanner_mgr.check_and_execute_scans()
            
            # ... rest of loop
    
    def _deactivate_session(self):
        # Notify scanner manager
        scanner_mgr = self._system_manager.get_scanner_manager()
        scanner_mgr.on_session_end()
```

---

## Execution Model

### Backtest Mode (Blocking)

```python
# Clock STOPPED during scanner operations

# Pre-session (clock stopped)
scanner_manager.setup_pre_session_scanners()
  → setup() for all scanners (blocking)
  → scan() for pre-session scanners (blocking)
  → teardown() for pre-session-only (blocking)

# Regular session (clock advances between scans)
while session_active:
    scanner_manager.check_and_execute_scans()
      → scan() if scheduled (blocking, clock stops)
    
    # Clock advances
    process_next_bar()

# End of session (clock stopped)
scanner_manager.on_session_end()
  → teardown() for remaining scanners (blocking)
```

---

### Live Mode (Async)

```python
# Clock RUNNING during scanner operations

# Pre-session (clock running)
await scanner_manager.setup_pre_session_scanners()
  → setup() for all scanners (async)
  → scan() for pre-session scanners (async)
  → teardown() for pre-session-only (async)

# Regular session (clock running)
while session_active:
    await scanner_manager.check_and_execute_scans()
      → scan() if scheduled (async, clock running)
    
    # Clock continues
    await asyncio.sleep(1)

# End of session (clock running)
await scanner_manager.on_session_end()
  → teardown() for remaining scanners (async)
```

**Note**: Current implementation is synchronous. Async support will be added in Phase 3.

---

## Error Handling

### Scanner Failure Scenarios

1. **Import Error**:
```python
# Module not found
logger.error("Failed to import module scanners.nonexistent: No module named 'scanners.nonexistent'")
return False
```

2. **No Scanner Class**:
```python
# No BaseScanner subclass in module
logger.error("No BaseScanner subclass found in scanners.empty_module")
return False
```

3. **Setup Failure**:
```python
# setup() returned False or raised exception
instance.state = ScannerState.ERROR
instance.error = "Setup returned False"
logger.error("Setup failed for scanners.bad_scanner")
```

4. **Scan Failure**:
```python
# scan() raised exception
instance.state = ScannerState.ERROR
instance.error = str(exception)
logger.error("Scan exception for scanners.bad_scanner: ...", exc_info=True)
```

---

## Thread Safety

### Locking Strategy

```python
class ScannerManager:
    def __init__(self):
        self._lock = threading.RLock()
    
    def get_scanner_states(self):
        with self._lock:
            # Safe access to scanner states
            return states
```

**Note**: Scanner operations are serialized (one at a time per scanner).

---

## Usage Example

### Configuration

```json
{
  "session_data_config": {
    "scanners": [
      {
        "module": "scanners.gap_scanner",
        "enabled": true,
        "pre_session": true,
        "regular_session": null,
        "config": {
          "universe": "data/universes/sp500_sample.txt"
        }
      },
      {
        "module": "scanners.momentum_scanner",
        "enabled": true,
        "pre_session": false,
        "regular_session": [
          {
            "start": "09:35",
            "end": "15:55",
            "interval": "5m"
          }
        ],
        "config": {
          "universe": "data/universes/nasdaq100_sample.txt"
        }
      }
    ]
  }
}
```

---

### Execution Flow

```python
# System startup
system_manager = SystemManager()
await system_manager.initialize()

# Scanner manager initializes
scanner_manager = system_manager.get_scanner_manager()
scanner_manager.initialize()
  → Loads scanners.gap_scanner
  → Loads scanners.momentum_scanner

# SessionCoordinator starts
session_coordinator = SessionCoordinator(system_manager)
session_coordinator.initialize_session()
  → scanner_manager.setup_pre_session_scanners()
    ├─ gap_scanner.setup()
    ├─ momentum_scanner.setup()
    ├─ gap_scanner.scan() (pre-session)
    └─ gap_scanner.teardown() (pre-session only)

# Session becomes active
session_coordinator.activate_session()
  → scanner_manager.on_session_start()
    └─ momentum_scanner.next_scan_time = 09:35:00

# Session loop
while session_active:
    scanner_manager.check_and_execute_scans()
      → if current_time == 09:35:00:
          momentum_scanner.scan()
      → if current_time == 09:40:00:
          momentum_scanner.scan()
      → ... (every 5 minutes until 15:55)
    
    process_bars()

# Session ends
session_coordinator.deactivate_session()
  → scanner_manager.on_session_end()
    └─ momentum_scanner.teardown()
```

---

## Monitoring

### Scanner States

```python
# Get scanner states
states = scanner_manager.get_scanner_states()

# Example output
{
  "scanners.gap_scanner": {
    "state": "teardown_complete",
    "scan_count": 1,
    "last_scan_time": "2024-01-02T09:30:00",
    "next_scan_time": null,
    "qualifying_symbols": ["TSLA", "NVDA", "AMD"],
    "error": null
  },
  "scanners.momentum_scanner": {
    "state": "scan_complete",
    "scan_count": 78,
    "last_scan_time": "2024-01-02T15:55:00",
    "next_scan_time": null,
    "qualifying_symbols": ["AAPL", "MSFT", "GOOGL", "AMZN"],
    "error": null
  }
}
```

---

## Logging Output Example

```
[SCANNER_MANAGER] Initialized
[SCANNER_MANAGER] Loading 2 scanners
[SCANNER_MANAGER] Loading scanner: scanners.gap_scanner
[SCANNER_MANAGER] Instantiated GapScannerComplete
[SCANNER_MANAGER] Loaded scanner: scanners.gap_scanner
[SCANNER_MANAGER] Loading scanner: scanners.momentum_scanner
[SCANNER_MANAGER] Instantiated MomentumScanner
[SCANNER_MANAGER] Loaded scanner: scanners.momentum_scanner
[SCANNER_MANAGER] Loaded 2 scanners
[SCANNER_MANAGER] === PRE-SESSION SCANNER SETUP ===
[SCANNER_MANAGER] Setting up scanner: scanners.gap_scanner
[GAP_SCANNER] Loading universe from: data/universes/sp500_sample.txt
[GAP_SCANNER] Loaded 500 symbols
[GAP_SCANNER] Provisioning data for 500 symbols (this may take a moment)
[SCANNER_MANAGER] Setup complete for scanners.gap_scanner (2345.67ms)
[SCANNER_MANAGER] Setting up scanner: scanners.momentum_scanner
[MOMENTUM_SCANNER] Loaded 100 symbols
[SCANNER_MANAGER] Setup complete for scanners.momentum_scanner (890.12ms)
[SCANNER_MANAGER] Running pre-session scan: scanners.gap_scanner
[SCANNER_MANAGER] Scanning (pre-session): scanners.gap_scanner
[GAP_SCANNER] Scanning 500 symbols for gaps...
[GAP_SCANNER] Found 3 qualifying symbols
[SCANNER_MANAGER] Scan complete for scanners.gap_scanner: 3 symbols, 456.78ms
[SCANNER_MANAGER] Qualifying symbols: ['TSLA', 'NVDA', 'AMD']
[SCANNER_MANAGER] Tearing down pre-session-only scanner: scanners.gap_scanner
[SCANNER_MANAGER] Tearing down scanner: scanners.gap_scanner
[GAP_SCANNER] Removing 497 symbols that didn't qualify
[SCANNER_MANAGER] Teardown complete for scanners.gap_scanner (234.56ms)
[SCANNER_MANAGER] Pre-session scanner setup complete
[SCANNER_MANAGER] Session started
[SCANNER_MANAGER] Next scan for scanners.momentum_scanner: 2024-01-02 09:35:00
[SCANNER_MANAGER] Scheduled scan triggered: scanners.momentum_scanner at 2024-01-02 09:35:00
[SCANNER_MANAGER] Scanning (regular): scanners.momentum_scanner
[MOMENTUM_SCANNER] Found 2 momentum stocks
[SCANNER_MANAGER] Scan complete for scanners.momentum_scanner: 2 symbols, 123.45ms
[SCANNER_MANAGER] Qualifying symbols: ['AAPL', 'MSFT']
```

---

## Files Modified/Created

1. ✅ Created `/home/yohannes/mismartera/backend/app/threads/scanner_manager.py` (650+ lines)
2. ✅ Universe files already exist:
   - `/home/yohannes/mismartera/backend/data/universes/sp500_sample.txt`
   - `/home/yohannes/mismartera/backend/data/universes/nasdaq100_sample.txt`

---

## Next Steps: Phase 2.3

**SessionCoordinator Integration**

What's needed:
- Add scanner_manager initialization in SystemManager
- Add scanner_manager calls in SessionCoordinator:
  - setup_pre_session_scanners() before session start
  - on_session_start() when session activates
  - check_and_execute_scans() in session loop
  - on_session_end() when session ends
- Handle scanner failures gracefully
- Add scanner state to monitoring/diagnostics

**Estimated Time**: 2-3 hours

---

## Summary

✅ **Phase 2.2 Complete**: Scanner Manager implemented  
✅ **State Machine**: Full lifecycle tracking  
✅ **Schedule Management**: Regular session scans  
✅ **Error Handling**: Comprehensive error tracking  
✅ **Module Loading**: Dynamic scanner instantiation  
✅ **Integration Ready**: Clean API for SessionCoordinator  

**Ready for Phase 2.3: SessionCoordinator Integration!** 🚀
