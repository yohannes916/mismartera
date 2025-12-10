# Scanner Execution Model

## Core Principles

1. **Sequential Execution**: Scanner methods execute sequentially per scanner
2. **Blocking in Backtest**: All scanner calls block and stop clock
3. **Async in Live**: Scanner calls are async but sequential per scanner
4. **Teardown After Last Schedule**: Called when no more scans remain
5. **Clock Control**: Backtest clock stops during scanner execution

---

## Execution Guarantees

### Per-Scanner Sequential Execution

```
✅ GUARANTEED ORDER (per scanner):
   setup() completes → scan() can start
   scan() completes → next scan() can start
   last scan() completes → teardown() starts
   teardown() completes → scanner done

❌ NEVER HAPPENS:
   setup() running while scan() starts
   scan() running while another scan() for same scanner starts
   teardown() called before last scan() completes
```

### Cross-Scanner Parallel Execution

```
Scanner A and Scanner B can run in parallel:
   Scanner A: setup() → scan() → scan() → teardown()
                ↓         ↓
   Scanner B:   setup() → scan() → teardown()
   
This is OK because they are independent scanners.
```

---

## Backtest Mode (Blocking)

### Characteristics

- **Clock Stops**: Backtest clock paused during scanner execution
- **Blocking**: All scanner calls block thread
- **Sequential**: One scanner method completes before next starts
- **Deterministic**: Same results every run

### Example Timeline

```
TIME   ACTION                                  CLOCK
────────────────────────────────────────────────────
       Pre-session scanners start              STOPPED ⏸️
       
       gap_scanner.setup()                     STOPPED ⏸️
         (loads 500 symbols, takes 2s)
       gap_scanner.setup() returns
       
       gap_scanner.scan()                      STOPPED ⏸️
         (scans universe, takes 150ms)
         (finds 3 symbols, calls add_symbol)
       gap_scanner.scan() returns
       
       gap_scanner.teardown()                  STOPPED ⏸️
         (removes 497 unused symbols)
       gap_scanner.teardown() returns
       
       Process session_config requirements     STOPPED ⏸️
       
09:30  Start streaming                        RUNNING ▶️
       
09:35  momentum_scanner.scan()                STOPPED ⏸️
         (scans 500 symbols, takes 200ms)
       momentum_scanner.scan() returns
       
09:35  Continue streaming                     RUNNING ▶️
       
09:40  momentum_scanner.scan()                STOPPED ⏸️
       momentum_scanner.scan() returns
       
09:40  Continue streaming                     RUNNING ▶️
       
       ... (continues until last scan)
       
15:55  momentum_scanner.scan()                STOPPED ⏸️
         (LAST scheduled scan)
       momentum_scanner.scan() returns
       
15:55  momentum_scanner.teardown()            STOPPED ⏸️
         (cleanup unused symbols)
       momentum_scanner.teardown() returns
       
15:55  Continue streaming                     RUNNING ▶️
```

---

## Live Mode (Async)

### Characteristics

- **Clock Runs**: Real-time clock always running
- **Non-Blocking**: Scanner calls are async
- **Sequential per Scanner**: One call completes before next starts
- **Skip on Overlap**: If previous scan not done, skip next one

### Example Timeline

```
TIME   ACTION                                  CLOCK
────────────────────────────────────────────────────
       Pre-session scanners start              RUNNING ⏰
       
       async gap_scanner.setup()               RUNNING ⏰
         (loads 500 symbols)
         (runs in background)
       
       ... wait for setup to complete ...
       
       gap_scanner.setup() completes
       
       async gap_scanner.scan()                RUNNING ⏰
         (runs in background)
       
       gap_scanner.scan() completes
       
       async gap_scanner.teardown()            RUNNING ⏰
       gap_scanner.teardown() completes
       
       Process session_config requirements     RUNNING ⏰
       
09:30  Start streaming                        RUNNING ⏰
       
09:35  Check momentum_scanner schedule
       Previous scan done? YES
       
       async momentum_scanner.scan()           RUNNING ⏰
         (runs in background)
         (takes 200ms)
       
09:40  Check momentum_scanner schedule
       Previous scan done? YES
       
       async momentum_scanner.scan()           RUNNING ⏰
       
09:45  Check momentum_scanner schedule
       Previous scan done? NO (still running!)
       SKIP THIS SCAN ⏭️
       
09:50  Check momentum_scanner schedule
       Previous scan done? YES
       
       async momentum_scanner.scan()           RUNNING ⏰
       
       ... (continues until last scan)
       
15:55  momentum_scanner.scan()                RUNNING ⏰
         (LAST scheduled scan)
       momentum_scanner.scan() completes
       
       async momentum_scanner.teardown()       RUNNING ⏰
       momentum_scanner.teardown() completes
```

---

## Teardown Phase

### When Teardown is Called

Teardown is called **after the last scheduled scan** for a scanner:

1. **Pre-session only scanner** (`pre_session: true, regular_session: null`)
   - setup() → scan() → **teardown()** ← Called immediately

2. **Regular session only scanner** (`pre_session: false, regular_session: [...]`)
   - setup() → ... → last scan() → **teardown()** ← Called after 15:55

3. **Hybrid scanner** (`pre_session: true, regular_session: [...]`)
   - setup() → scan() (pre-session) → ... → last scan() (15:55) → **teardown()** ← Called after all scans

### Teardown Purpose

```python
def teardown(self, context):
    """Cleanup after scanner completes.
    
    Use cases:
    1. Remove symbols that didn't qualify
    2. Free resources (close connections, etc.)
    3. Clean up temporary data
    4. Log scanner statistics
    """
    # Remove symbols without positions
    for symbol in self._universe:
        if not context.session_data.is_symbol_locked(symbol):
            if symbol not in qualifying_symbols:
                context.session_data.remove_symbol(symbol)
```

### What Happens After Teardown

**Pre-session scanner**:
```
teardown() completes
  ↓
Process session_config requirements
  ↓
Start streaming
  ↓
Advance clock
```

**Regular session scanner**:
```
teardown() completes
  ↓
Continue streaming
  ↓
Session continues (scanner done)
```

---

## Sequential Execution Flow

### Single Scanner Execution

```python
# Per-scanner state machine
class ScannerState:
    IDLE         # Initial state
    SETTING_UP   # setup() running
    READY        # setup() complete, can scan
    SCANNING     # scan() running
    TEARING_DOWN # teardown() running
    DONE         # All complete

# State transitions
IDLE → SETTING_UP → READY → SCANNING → READY → ... → TEARING_DOWN → DONE
```

### Enforcement Logic

```python
class ScannerManager:
    def __init__(self):
        self.scanner_states = {}  # {scanner_name: ScannerState}
        self.scanner_tasks = {}   # {scanner_name: asyncio.Task}
    
    def can_call_scan(self, scanner_name):
        """Check if scan() can be called."""
        state = self.scanner_states[scanner_name]
        
        # Must be READY (setup complete, not scanning)
        if state != ScannerState.READY:
            return False
        
        # In live mode, check if previous task done
        if self.mode == "live":
            task = self.scanner_tasks.get(scanner_name)
            if task and not task.done():
                return False  # Previous scan still running
        
        return True
    
    def execute_scan(self, scanner_name):
        """Execute scan with state tracking."""
        if not self.can_call_scan(scanner_name):
            logger.warning(f"Skipping {scanner_name} - not ready")
            return
        
        # Update state
        self.scanner_states[scanner_name] = ScannerState.SCANNING
        
        # Execute
        if self.mode == "backtest":
            # Blocking
            result = scanner.scan(context)
            self.scanner_states[scanner_name] = ScannerState.READY
        else:
            # Async
            task = asyncio.create_task(self._scan_async(scanner_name))
            self.scanner_tasks[scanner_name] = task
    
    async def _scan_async(self, scanner_name):
        """Async wrapper for live mode."""
        try:
            result = await scanner.scan(context)
        finally:
            self.scanner_states[scanner_name] = ScannerState.READY
```

---

## Complete Lifecycle Example

### Pre-Session Scanner

```python
# Configuration
{
  "module": "scanners.gap_scanner",
  "pre_session": true,
  "regular_session": null
}

# Execution (Backtest)
SessionCoordinator starts
  ↓
ScannerManager.load_scanners()
  ↓ (clock STOPPED)
gap_scanner.setup(context)
  - Provisions 500 symbols with historical bars
  - Returns True
  ↓ (clock STOPPED)
gap_scanner.scan(context)
  - Scans 500 symbols
  - Finds 3 qualifying
  - Calls add_symbol() for each
  - Returns ScanResult(["TSLA", "NVDA", "AMD"])
  ↓ (clock STOPPED)
gap_scanner.teardown(context)
  - Removes 497 non-qualifying symbols
  - Keeps 3 qualifying symbols + config symbols
  - Returns
  ↓ (clock STOPPED)
Process session_config requirements
  - Load indicators for qualifying symbols
  ↓ (clock STOPPED)
Activate session
  ↓
Clock advances to 09:30
  ↓ (clock RUNNING)
Streaming starts
```

### Regular Session Scanner

```python
# Configuration
{
  "module": "scanners.momentum_scanner",
  "pre_session": false,
  "regular_session": [{
    "start": "09:35",
    "end": "15:55",
    "interval": "5m"
  }]
}

# Execution (Backtest)
SessionCoordinator starts
  ↓ (clock STOPPED)
momentum_scanner.setup(context)
  - Provisions 500 symbols with live bars
  - Returns True
  ↓ (clock STOPPED)
Activate session
  ↓
Clock advances to 09:30
  ↓ (clock RUNNING)
Streaming starts
  ↓
Clock reaches 09:35
  ↓ (clock STOPPED)
momentum_scanner.scan(context)
  - Scans 500 symbols
  - Finds 2 qualifying
  - Returns ScanResult(["TSLA", "AMD"])
  ↓ (clock RUNNING)
Continue streaming
  ↓
Clock reaches 09:40
  ↓ (clock STOPPED)
momentum_scanner.scan(context)
  ↓ (clock RUNNING)
...
  ↓
Clock reaches 15:55 (LAST scheduled scan)
  ↓ (clock STOPPED)
momentum_scanner.scan(context)
  ↓ (clock STOPPED)
momentum_scanner.teardown(context)
  - Removes unused symbols
  ↓ (clock RUNNING)
Continue streaming until session end
```

---

## Error Handling

### Setup Failure

```python
try:
    success = scanner.setup(context)
except Exception as e:
    logger.error(f"Scanner setup failed: {e}")
    scanner_states[name] = ScannerState.DONE  # Disable scanner
    # Scanner will NOT run scan() or teardown()
```

### Scan Failure

```python
try:
    result = scanner.scan(context)
except Exception as e:
    logger.error(f"Scanner scan failed: {e}")
    # Continue with next scheduled scan
    # teardown() will still be called after last schedule
```

### Teardown Failure

```python
try:
    scanner.teardown(context)
except Exception as e:
    logger.error(f"Scanner teardown failed: {e}")
    # Log but don't crash session
```

---

## Summary

### Execution Model

✅ **Sequential per scanner** - One method completes before next starts  
✅ **Blocking in backtest** - Clock stops during scanner execution  
✅ **Async in live** - Non-blocking but skip if previous not done  
✅ **Teardown after last** - Called when no more schedules  
✅ **State machine** - IDLE → SETTING_UP → READY → SCANNING → TEARING_DOWN → DONE  

### Clock Behavior

**Backtest**:
- ⏸️ Clock STOPS during scanner calls
- ▶️ Clock RUNS between scanner calls

**Live**:
- ⏰ Clock ALWAYS RUNS
- Scanner calls are async background tasks

### Teardown Guarantees

✅ Called **exactly once** per scanner  
✅ Called **after last scheduled scan**  
✅ Called **even if scanner disabled mid-session**  
✅ Gives scanner chance to **cleanup resources**  

This execution model ensures deterministic, reliable scanner behavior! 🎯
