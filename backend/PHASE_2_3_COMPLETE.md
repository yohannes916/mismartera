# Phase 2.3 Complete: SessionCoordinator Integration

## ✅ Implemented

Integrated Scanner Manager into SystemManager and SessionCoordinator for complete scanner lifecycle management.

---

## Files Modified

### 1. `/app/managers/system_manager/api.py`

**Added**:
- `_scanner_manager` attribute in `__init__`
- `get_scanner_manager()` method
- Scanner manager initialization in `start()` method

```python
# In __init__
self._scanner_manager: Optional['ScannerManager'] = None

# New method
def get_scanner_manager(self) -> 'ScannerManager':
    """Get ScannerManager singleton."""
    if self._scanner_manager is None:
        from app.threads.scanner_manager import ScannerManager
        self._scanner_manager = ScannerManager(self)
        logger.debug("ScannerManager created")
    return self._scanner_manager

# In start() method
scanner_manager = self.get_scanner_manager()
logger.info("[SESSION_FLOW] 2.b.3: ScannerManager created")

# Initialize scanner manager (load scanners from config)
success = scanner_manager.initialize()
if not success:
    raise RuntimeError("Scanner manager initialization failed")
logger.info("[SESSION_FLOW] 2.b.4: ScannerManager initialized")
```

---

### 2. `/app/threads/session_coordinator.py`

**Added**:
- `_scanner_manager` reference in `__init__`
- Pre-session scanner setup (Phase 2.5)
- Scanner on_session_start call (Phase 4)
- Scanner check_and_execute_scans in streaming loop (Phase 5)
- Scanner on_session_end call (Phase 6)

```python
# In __init__
self._scanner_manager = system_manager.get_scanner_manager()

# Phase 2.5: Pre-Session Scanner Setup (after historical management)
logger.info("[SESSION_FLOW] 3.b.2.PHASE_2.5: Pre-Session Scanner Setup phase starting")
logger.info("Phase 2.5: Pre-Session Scanner Setup")
success = self._scanner_manager.setup_pre_session_scanners()
if not success:
    logger.error("[SESSION_FLOW] 3.b.2.PHASE_2.5: Scanner setup FAILED")
    raise RuntimeError("Pre-session scanner setup failed")
logger.info("[SESSION_FLOW] 3.b.2.PHASE_2.5: Complete")

# Phase 4: Session Activation
def _activate_session(self):
    # ... existing code ...
    
    # Notify scanner manager that session has started
    self._scanner_manager.on_session_start()
    logger.info("[SESSION_FLOW] PHASE_4.1a: Scanner manager notified of session start")

# Phase 5: Streaming Phase (main loop)
while not self._stop_event.is_set():
    # ... existing code ...
    
    # CHECK: Execute scheduled scans (Scanner Framework)
    self._scanner_manager.check_and_execute_scans()

# Phase 6: End-of-Session
def _end_session(self):
    # ... existing code ...
    
    # Notify scanner manager that session has ended
    self._scanner_manager.on_session_end()
    logger.info("[SESSION_FLOW] PHASE_6.1a: Scanner manager notified of session end")
```

---

## Integration Flow

### System Startup

```
SystemManager.start()
  ├─ 1. Load configuration
  ├─ 2. Initialize managers
  │   ├─ TimeManager
  │   ├─ DataManager
  │   ├─ ScannerManager ← NEW!
  │   └─ ScannerManager.initialize()
  │       ├─ Load scanners from config
  │       ├─ Import scanner modules
  │       └─ Instantiate scanner classes
  ├─ 3. Apply backtest config
  ├─ 4. Get SessionData singleton
  ├─ 5. Create thread pool
  ├─ 6. Wire threads
  └─ 7. Start threads (SessionCoordinator, etc.)
```

---

### Session Lifecycle

```
SessionCoordinator.run()
  │
  ├─ Phase 1: Initialization
  │   └─ _initialize_session()
  │
  ├─ Phase 2: Historical Management
  │   ├─ _manage_historical_data()
  │   ├─ _calculate_historical_indicators()
  │   └─ _calculate_historical_quality()
  │
  ├─ Phase 2.5: Pre-Session Scanner Setup ← NEW!
  │   └─ scanner_manager.setup_pre_session_scanners()
  │       ├─ setup() for all scanners
  │       ├─ scan() for pre-session scanners
  │       └─ teardown() for pre-session-only scanners
  │
  ├─ Phase 3: Queue Loading
  │   └─ _load_queues()
  │
  ├─ Phase 4: Session Activation
  │   └─ _activate_session()
  │       ├─ Set session_active = True
  │       └─ scanner_manager.on_session_start() ← NEW!
  │           └─ Initialize next_scan_time for regular scanners
  │
  ├─ Phase 5: Streaming Phase
  │   └─ while session_active:
  │       ├─ Process pending symbols
  │       ├─ scanner_manager.check_and_execute_scans() ← NEW!
  │       │   ├─ Check if current_time >= next_scan_time
  │       │   ├─ Execute scan() if due
  │       │   └─ Update next_scan_time
  │       ├─ Check if paused
  │       ├─ Check end-of-session
  │       ├─ Find next bar
  │       ├─ Advance time
  │       └─ Publish bar
  │
  └─ Phase 6: End-of-Session
      └─ _end_session()
          ├─ Deactivate session
          ├─ scanner_manager.on_session_end() ← NEW!
          │   └─ teardown() for remaining scanners
          ├─ Record metrics
          ├─ Clear session bars
          └─ Advance to next day
```

---

## Scanner Lifecycle Details

### Pre-Session Only Scanner

```
Example: Gap Scanner (runs before market opens)

Config:
{
  "module": "scanners.gap_scanner",
  "pre_session": true,
  "regular_session": null
}

Lifecycle:
┌──────────────────────────────────────────────────┐
│ Phase 2.5: Pre-Session Scanner Setup            │
│   1. setup()                                     │
│      └─ Load universe, provision lightweight data│
│   2. scan()                                      │
│      └─ Find gaps, promote qualifying symbols    │
│   3. teardown()                                  │
│      └─ Remove unqualified symbols               │
└──────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────┐
│ Phase 3-6: Regular Session                      │
│   Scanner is complete, no further action        │
└──────────────────────────────────────────────────┘
```

---

### Regular Session Only Scanner

```
Example: Momentum Scanner (runs during market hours)

Config:
{
  "module": "scanners.momentum_scanner",
  "pre_session": false,
  "regular_session": [
    {"start": "09:35", "end": "15:55", "interval": "5m"}
  ]
}

Lifecycle:
┌──────────────────────────────────────────────────┐
│ Phase 2.5: Pre-Session Scanner Setup            │
│   1. setup()                                     │
│      └─ Load universe, provision lightweight data│
└──────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────┐
│ Phase 4: Session Activation                     │
│   on_session_start()                             │
│      └─ next_scan_time = 09:35:00                │
└──────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────┐
│ Phase 5: Streaming Phase                        │
│   while session_active:                          │
│     check_and_execute_scans()                    │
│       ├─ 09:35:00: scan() → next = 09:40:00     │
│       ├─ 09:40:00: scan() → next = 09:45:00     │
│       ├─ ... (every 5 minutes)                   │
│       └─ 15:55:00: scan() → next = None          │
└──────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────┐
│ Phase 6: End-of-Session                          │
│   on_session_end()                               │
│      └─ teardown()                                │
│         └─ Remove unqualified symbols             │
└──────────────────────────────────────────────────┘
```

---

### Hybrid Scanner (Both)

```
Example: Hybrid Scanner (pre-session + regular session)

Config:
{
  "module": "scanners.hybrid_scanner",
  "pre_session": true,
  "regular_session": [
    {"start": "10:00", "end": "15:00", "interval": "15m"}
  ]
}

Lifecycle:
┌──────────────────────────────────────────────────┐
│ Phase 2.5: Pre-Session Scanner Setup            │
│   1. setup()                                     │
│   2. scan() (pre-session)                        │
│   (NO teardown - has regular schedule)          │
└──────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────┐
│ Phase 4: Session Activation                     │
│   on_session_start()                             │
│      └─ next_scan_time = 10:00:00                │
└──────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────┐
│ Phase 5: Streaming Phase                        │
│   while session_active:                          │
│     check_and_execute_scans()                    │
│       ├─ 10:00:00: scan() → next = 10:15:00     │
│       ├─ 10:15:00: scan() → next = 10:30:00     │
│       ├─ ... (every 15 minutes)                  │
│       └─ 15:00:00: scan() → next = None          │
└──────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────┐
│ Phase 6: End-of-Session                          │
│   on_session_end()                               │
│      └─ teardown()                                │
└──────────────────────────────────────────────────┘
```

---

## Logging Output Example

```
[SESSION_FLOW] 2.b: SystemManager - Initializing managers
[SESSION_FLOW] 2.b.1: TimeManager created
[SESSION_FLOW] 2.b.2: DataManager created
[SESSION_FLOW] 2.b.3: ScannerManager created
[SCANNER_MANAGER] Initialized
[SCANNER_MANAGER] Loading 2 scanners
[SCANNER_MANAGER] Loading scanner: scanners.gap_scanner
[SCANNER_MANAGER] Instantiated GapScannerComplete
[SCANNER_MANAGER] Loaded scanner: scanners.gap_scanner
[SCANNER_MANAGER] Loading scanner: scanners.momentum_scanner
[SCANNER_MANAGER] Instantiated MomentumScanner
[SCANNER_MANAGER] Loaded scanner: scanners.momentum_scanner
[SCANNER_MANAGER] Loaded 2 scanners
[SESSION_FLOW] 2.b.4: ScannerManager initialized
[SESSION_FLOW] 2.b: Complete - Managers initialized

... (historical management) ...

[SESSION_FLOW] 3.b.2.PHASE_2.5: Pre-Session Scanner Setup phase starting
Phase 2.5: Pre-Session Scanner Setup
[SCANNER_MANAGER] === PRE-SESSION SCANNER SETUP ===
[SCANNER_MANAGER] Setting up scanner: scanners.gap_scanner
[GAP_SCANNER] Loading universe from: data/universes/sp500_sample.txt
[GAP_SCANNER] Loaded 500 symbols
[SCANNER_MANAGER] Setup complete for scanners.gap_scanner (2345.67ms)
[SCANNER_MANAGER] Setting up scanner: scanners.momentum_scanner
[SCANNER_MANAGER] Setup complete for scanners.momentum_scanner (890.12ms)
[SCANNER_MANAGER] Running pre-session scan: scanners.gap_scanner
[SCANNER_MANAGER] Scanning (pre-session): scanners.gap_scanner
[GAP_SCANNER] Found 3 qualifying symbols
[SCANNER_MANAGER] Scan complete for scanners.gap_scanner: 3 symbols, 456.78ms
[SCANNER_MANAGER] Qualifying symbols: ['TSLA', 'NVDA', 'AMD']
[SCANNER_MANAGER] Tearing down pre-session-only scanner: scanners.gap_scanner
[SCANNER_MANAGER] Tearing down scanner: scanners.gap_scanner
[SCANNER_MANAGER] Teardown complete for scanners.gap_scanner (234.56ms)
[SCANNER_MANAGER] Pre-session scanner setup complete
[SESSION_FLOW] 3.b.2.PHASE_2.5: Complete

... (queue loading) ...

[SESSION_FLOW] 3.b.2.PHASE_4: Session Activation phase starting
[SESSION_FLOW] PHASE_4.1: Activating session
[SCANNER_MANAGER] Session started
[SCANNER_MANAGER] Next scan for scanners.momentum_scanner: 2024-01-02 09:35:00
[SESSION_FLOW] PHASE_4.1a: Scanner manager notified of session start
Session activated

... (streaming phase) ...

[SCANNER_MANAGER] Scheduled scan triggered: scanners.momentum_scanner at 2024-01-02 09:35:00
[SCANNER_MANAGER] Scanning (regular): scanners.momentum_scanner
[MOMENTUM_SCANNER] Found 2 momentum stocks
[SCANNER_MANAGER] Scan complete for scanners.momentum_scanner: 2 symbols, 123.45ms
[SCANNER_MANAGER] Qualifying symbols: ['AAPL', 'MSFT']

... (more scans every 5 minutes) ...

[SESSION_FLOW] 3.b.2.PHASE_6: End-of-Session phase starting
[SCANNER_MANAGER] Session ended, tearing down scanners
[SCANNER_MANAGER] Tearing down scanner: scanners.momentum_scanner
[SCANNER_MANAGER] Teardown complete for scanners.momentum_scanner (156.78ms)
[SESSION_FLOW] PHASE_6.1a: Scanner manager notified of session end
Session deactivated
```

---

## Integration Points Summary

### 1. SystemManager

```python
# Initialization
scanner_manager = system_manager.get_scanner_manager()
scanner_manager.initialize()  # Loads and instantiates scanners

# Access
scanner_manager = system_manager.get_scanner_manager()
```

---

### 2. SessionCoordinator

```python
# Initialization
self._scanner_manager = system_manager.get_scanner_manager()

# Phase 2.5: Pre-Session Setup
self._scanner_manager.setup_pre_session_scanners()
  → setup() for all
  → scan() for pre-session
  → teardown() for pre-session-only

# Phase 4: Session Start
self._scanner_manager.on_session_start()
  → Initialize next_scan_time

# Phase 5: Streaming Loop
self._scanner_manager.check_and_execute_scans()
  → Check schedules
  → Execute scans if due
  → Update next_scan_time

# Phase 6: Session End
self._scanner_manager.on_session_end()
  → teardown() for remaining scanners
```

---

## Error Handling

### Scanner Initialization Failure

```python
success = scanner_manager.initialize()
if not success:
    raise RuntimeError("Scanner manager initialization failed")
```

**Causes**:
- Scanner module not found
- No BaseScanner subclass in module
- Scanner config invalid

---

### Pre-Session Setup Failure

```python
success = self._scanner_manager.setup_pre_session_scanners()
if not success:
    logger.error("[SESSION_FLOW] 3.b.2.PHASE_2.5: Scanner setup FAILED")
    raise RuntimeError("Pre-session scanner setup failed")
```

**Causes**:
- Scanner setup() returned False
- Scanner setup() raised exception
- Scanner scan() raised exception

---

## Testing

### Manual Testing

```bash
# 1. Start system with scanner config
./start_cli.sh
system@mismartera: system start session_configs/scanner_example.json

# 2. Watch logs for scanner activity
# - Scanner loading
# - Pre-session setup/scan/teardown
# - Regular session scans (every 5 minutes)
# - End-of-session teardown

# 3. Verify scanner state
system@mismartera: system status  # TODO: Add scanner state display
```

---

### Expected Behavior

✅ **Pre-session scanner**:
- setup() called once
- scan() called once
- teardown() called immediately
- No activity during regular session

✅ **Regular session scanner**:
- setup() called once
- No pre-session scan
- scan() called every N minutes during session
- teardown() called at end of session

✅ **Hybrid scanner**:
- setup() called once
- scan() called once pre-session
- scan() called every N minutes during session
- teardown() called at end of session

---

## Summary

✅ **Phase 2.3 Complete**: Scanner Manager integrated into session lifecycle  
✅ **SystemManager**: Scanner manager singleton created and initialized  
✅ **SessionCoordinator**: 4 integration points added  
✅ **Pre-Session**: Setup/scan/teardown before session starts  
✅ **Regular Session**: Scheduled scans during session  
✅ **End-of-Session**: Cleanup and teardown  
✅ **Error Handling**: Failures halt system startup  

**Scanner Framework Implementation Complete!** 🎉

---

## Phase 2 Complete Summary

**Phase 2.1**: Scanner base classes ✅  
**Phase 2.2**: Scanner manager ✅  
**Phase 2.3**: SessionCoordinator integration ✅  

**Total Phase 2**: Scanner Framework fully operational! 🚀
