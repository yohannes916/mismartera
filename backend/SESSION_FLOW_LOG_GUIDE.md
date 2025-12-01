# Session Flow Debug Log Guide

## Quick Reference

**Log Prefix**: `[SESSION_FLOW]`

**Purpose**: Track session initialization and execution progress through all phases

**Usage**:
```bash
# See only session flow logs
grep "\[SESSION_FLOW\]" backend/logs/app.log

# See last 30 session flow events
grep "\[SESSION_FLOW\]" backend/logs/app.log | tail -30

# Monitor in real-time
tail -f backend/logs/app.log | grep "\[SESSION_FLOW\]"

# Count how many phases completed
grep "\[SESSION_FLOW\].*Complete" backend/logs/app.log | wc -l
```

---

## Log Structure

### Level 1: Major Components
- `[SESSION_FLOW] 1: ...` - User action (if logged)
- `[SESSION_FLOW] 2: ...` - SystemManager operations
- `[SESSION_FLOW] 3: ...` - SessionCoordinator operations

### Level 2: Sub-Components
- `[SESSION_FLOW] 2.a: ...` - Load configuration
- `[SESSION_FLOW] 2.b: ...` - Initialize managers
- `[SESSION_FLOW] 2.g: ...` - Start coordinator thread

### Level 3: Phases
- `[SESSION_FLOW] 3.b.2.PHASE_1: ...` - Initialization phase
- `[SESSION_FLOW] 3.b.2.PHASE_2: ...` - Historical management
- `[SESSION_FLOW] 3.b.2.PHASE_3: ...` - Queue loading
- `[SESSION_FLOW] 3.b.2.PHASE_4: ...` - Session activation
- `[SESSION_FLOW] 3.b.2.PHASE_5: ...` - Streaming phase
- `[SESSION_FLOW] 3.b.2.PHASE_6: ...` - End-of-session

### Level 4: Sub-Steps
- `[SESSION_FLOW] PHASE_1.1: ...` - First session marking
- `[SESSION_FLOW] PHASE_1.2: ...` - Reset session state
- `[SESSION_FLOW] PHASE_2.1: ...` - Manage historical data
- `[SESSION_FLOW] PHASE_5.1: ...` - Market hours
- `[SESSION_FLOW] PHASE_5.SUMMARY: ...` - Streaming complete

---

## Complete Session Flow (Expected)

### SystemManager Initialization
```
[SESSION_FLOW] 2.a: SystemManager - Loading configuration
[SESSION_FLOW] 2.a: Complete - Config loaded: Example Trading Session
[SESSION_FLOW] 2.b: SystemManager - Initializing managers
[SESSION_FLOW] 2.b.1: TimeManager created
[SESSION_FLOW] 2.b.2: DataManager created
[SESSION_FLOW] 2.b: Complete - Managers initialized
[SESSION_FLOW] 2.c: SystemManager - Applying backtest configuration
[SESSION_FLOW] 2.c: Complete - Backtest window set: 2025-07-02 to 2025-07-07
[SESSION_FLOW] 2.d: SystemManager - Creating SessionData
[SESSION_FLOW] 2.d: Complete - SessionData created
[SESSION_FLOW] 2.e: SystemManager - Creating 4-thread pool
[SESSION_FLOW] 2.e: Complete - Thread pool created
[SESSION_FLOW] 2.f: SystemManager - Wiring threads together
[SESSION_FLOW] 2.f: Complete - Threads wired
[SESSION_FLOW] 2.g: SystemManager - Starting SessionCoordinator thread
[SESSION_FLOW] 2.g: Complete - SessionCoordinator thread started
[SESSION_FLOW] 2.h: SystemManager - State set to RUNNING
[SESSION_FLOW] 2: Complete - SystemManager.start() finished
```

### SessionCoordinator Thread
```
[SESSION_FLOW] 3: SessionCoordinator.run() - Thread started
[SESSION_FLOW] 3.a: SessionCoordinator - Starting backtest timing
[SESSION_FLOW] 3.a: Complete
[SESSION_FLOW] 3.b: SessionCoordinator - Entering coordinator loop
[SESSION_FLOW] 3.b.1: Coordinator loop started
```

### Per-Session Loop (Repeats for Each Trading Day)

#### Phase 1: Initialization
```
[SESSION_FLOW] 3.b.2.PHASE_1: Initialization phase starting
[SESSION_FLOW] PHASE_1.1: Checking if first session (for stream/generate marking)
[SESSION_FLOW] PHASE_1.1: First session - marking STREAMED/GENERATED/IGNORED
[SESSION_FLOW] PHASE_1.1: Stream/generate marking complete
[SESSION_FLOW] PHASE_1.1: Informing DataProcessor of derived intervals
[SESSION_FLOW] PHASE_1.1: DataProcessor informed
[SESSION_FLOW] PHASE_1.2: Resetting session state
[SESSION_FLOW] PHASE_1.3: Getting current session date from TimeManager
[SESSION_FLOW] PHASE_1.3: Current session date: 2025-07-02, time: 09:30:00
[SESSION_FLOW] PHASE_1.4: Session initialization complete
[SESSION_FLOW] 3.b.2.PHASE_1: Complete
```

#### Phase 2: Historical Management
```
[SESSION_FLOW] 3.b.2.PHASE_2: Historical Management phase starting
[SESSION_FLOW] PHASE_2.1: Managing historical data
[SESSION_FLOW] PHASE_2.1: Loading historical data for session 2025-07-02
[SESSION_FLOW] PHASE_2.1: Clearing existing historical data
[SESSION_FLOW] PHASE_2.1: Historical data cleared
[SESSION_FLOW] PHASE_2.1: Complete - 0 bars loaded in 0.001s
[SESSION_FLOW] 3.b.2.PHASE_2: Complete
```

#### Phase 3: Queue Loading
```
[SESSION_FLOW] 3.b.2.PHASE_3: Queue Loading phase starting
[SESSION_FLOW] PHASE_3.1: Loading queues (mode=backtest)
[SESSION_FLOW] PHASE_3.1: Backtest mode - loading backtest queues
[SESSION_FLOW] PHASE_3.1: Backtest queues loaded
[SESSION_FLOW] PHASE_3.1: Complete - Queues loaded in 0.002s
[SESSION_FLOW] 3.b.2.PHASE_3: Complete
```

#### Phase 4: Session Activation
```
[SESSION_FLOW] 3.b.2.PHASE_4: Session Activation phase starting
[SESSION_FLOW] PHASE_4.1: Activating session
[SESSION_FLOW] PHASE_4.1: Complete - Session active
[SESSION_FLOW] 3.b.2.PHASE_4: Complete
```

#### Phase 5: Streaming
```
[SESSION_FLOW] 3.b.2.PHASE_5: Streaming phase starting
[SESSION_FLOW] PHASE_5.1: Market hours: 09:30:00 to 16:00:00
[SESSION_FLOW] PHASE_5.WARNING: No more data in queues
[SESSION_FLOW] PHASE_5.END: Exiting streaming (no data)
[SESSION_FLOW] PHASE_5.SUMMARY: 1 iterations, 0 bars, final time = 16:00:00
[SESSION_FLOW] 3.b.2.PHASE_5: Complete
```

#### Phase 6: End-of-Session
```
[SESSION_FLOW] 3.b.2.PHASE_6: End-of-Session phase starting
[SESSION_FLOW] 3.b.2.PHASE_6: Complete
```

#### Loop Control
```
[SESSION_FLOW] 3.b.2.CHECK: Checking if should terminate
[SESSION_FLOW] 3.b.2.CHECK: Termination condition met
```
OR
```
[SESSION_FLOW] 3.b.2.CHECK: Continuing to next session
```
(Then loops back to PHASE_1 for next trading day)

### Coordinator Exit
```
[SESSION_FLOW] 3.b: Complete - Coordinator loop exited
[SESSION_FLOW] 3.c: SessionCoordinator - Ending backtest timing
```

---

## Troubleshooting Guide

### System Stops at Phase 2
**Last Log**: `[SESSION_FLOW] PHASE_2.1: Complete - 0 bars loaded`

**Cause**: Historical data loading returns empty (DataManager API TODO)

**Status**: Expected in Phase 3 skeleton

**Next Steps**: Implement DataManager Parquet API

---

### System Stops at Phase 5
**Last Log**: `[SESSION_FLOW] PHASE_5.WARNING: No more data in queues`

**Cause**: Queue loading returns no data (DataManager stream API TODO)

**Status**: Expected in Phase 3 skeleton

**Next Steps**: Implement DataManager queue APIs

---

### System Repeats Phases for Multiple Days
**Logs Show**: PHASE_1 → PHASE_6 → CHECK: Continuing → PHASE_1 again

**Cause**: Multi-day backtest working correctly

**Status**: Expected behavior - each trading day gets fresh historical data

**Verify**: Check different dates in `PHASE_1.3: Current session date`

---

### Missing PHASE_1.1 on Second Session
**First Session**: Shows `PHASE_1.1: marking STREAMED/GENERATED/IGNORED`  
**Second Session**: Skips `PHASE_1.1`

**Cause**: Stream/generate marking only done once (first session)

**Status**: Expected - marking is reused for subsequent sessions

---

### Error: No DataProcessor Wired
**Log**: `[SESSION_FLOW] PHASE_1.1: No DataProcessor wired!`

**Cause**: SystemManager didn't wire DataProcessor to Coordinator

**Fix**: Check `_wire_threads()` in SystemManager

---

### Error: No Trading Session
**Log**: `[SESSION_FLOW] PHASE_5.ERROR: No trading session for 2025-07-02`

**Cause**: Date is weekend/holiday or missing from MarketHours DB

**Fix**: 
1. Check if date is valid trading day
2. Verify MarketHours table has data
3. Run `time import-holidays` command

---

## Performance Monitoring

### Count Iterations Per Session
```bash
grep "PHASE_5.SUMMARY" backend/logs/app.log | grep -oP '\d+ iterations'
```

### Track Session Timing
```bash
grep "PHASE.*Complete.*s$" backend/logs/app.log
```

Example output:
```
PHASE_2.1: Complete - 1250 bars loaded in 0.234s
PHASE_3.1: Complete - Queues loaded in 0.045s
```

### Identify Slowest Phase
```bash
grep "PHASE.*Complete.*[0-9]\+\.[0-9]\+s" backend/logs/app.log | sort -t'in' -k2 -n
```

---

## Current Phase 3 Behavior

**What Works**:
1. ✅ SystemManager initialization
2. ✅ Thread pool creation
3. ✅ SessionCoordinator lifecycle
4. ✅ Phase structure
5. ✅ TimeManager integration
6. ✅ Stream/generate marking

**What's Placeholder**:
1. 📋 Historical data loading (returns empty)
2. 📋 Queue loading (no data)
3. 📋 Streaming (exits immediately - no data)
4. 📋 Indicator calculation (returns zeros)

**Expected Logs** (Phase 3):
- System starts successfully
- Reaches `PHASE_5.WARNING: No more data in queues`
- Terminates cleanly

**This is correct behavior** for Phase 3 skeleton awaiting data integration.

---

## Next Phase Development

When implementing **Phase 4 (Data Pipeline)**:

1. **Implement DataManager APIs** → Logs will show actual data counts
2. **Streaming will process bars** → `PHASE_5.SUMMARY` will show `> 0 bars`
3. **Multi-day backtests will work** → Multiple iterations of PHASE_1-6
4. **Historical indicators calculated** → PHASE_2 will show non-zero results

Watch for these log changes:
```diff
- [SESSION_FLOW] PHASE_2.1: Complete - 0 bars loaded in 0.001s
+ [SESSION_FLOW] PHASE_2.1: Complete - 1250 bars loaded in 0.234s

- [SESSION_FLOW] PHASE_5.WARNING: No more data in queues
+ [SESSION_FLOW] PHASE_5.SUMMARY: 390 iterations, 780 bars, final time = 16:00:00
```

---

## Log Analysis Scripts

### Quick Health Check
```bash
#!/bin/bash
# session_health_check.sh

echo "=== Session Flow Health Check ==="
echo ""

echo "1. System Started:"
grep -c "SESSION_FLOW.*2.h.*RUNNING" backend/logs/app.log

echo "2. Coordinator Started:"
grep -c "SESSION_FLOW.*3:.*Thread started" backend/logs/app.log

echo "3. Sessions Attempted:"
grep -c "SESSION_FLOW.*PHASE_1:.*starting" backend/logs/app.log

echo "4. Sessions Completed:"
grep -c "SESSION_FLOW.*PHASE_6:.*Complete" backend/logs/app.log

echo "5. Last Phase Reached:"
grep "SESSION_FLOW.*PHASE" backend/logs/app.log | tail -1

echo ""
echo "=== Recent Errors ==="
grep "SESSION_FLOW.*ERROR\|SESSION_FLOW.*WARNING" backend/logs/app.log | tail -5
```

### Session Timeline
```bash
#!/bin/bash
# session_timeline.sh

grep "\[SESSION_FLOW\]" backend/logs/app.log | \
  awk '{print $1, $2, $NF}' | \
  sed 's/\[SESSION_FLOW\] //' | \
  column -t
```

---

## File Locations

- **SystemManager**: `/app/managers/system_manager/api.py`
- **SessionCoordinator**: `/app/threads/session_coordinator.py`
- **Logs**: `/backend/logs/app.log`
- **Analysis Doc**: `/backend/docs/SESSION_ARCHITECTURE_DEVIATION_ANALYSIS.md`

---

**Last Updated**: November 30, 2025  
**Version**: Phase 3 Skeleton with Full Debug Logging
