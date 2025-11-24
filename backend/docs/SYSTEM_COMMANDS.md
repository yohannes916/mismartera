# System Management Commands

SystemManager provides lifecycle control for the entire application through CLI commands.

## Commands

### `system start`
Start the system run. Initializes all managers and transitions to RUNNING state.

```bash
system start
```

**Output:**
```
✓ System started successfully
State: running
```

**Notes:**
- Can only start from STOPPED state
- Automatically initializes all managers if not already done
- If system is paused, use `system resume` instead

---

### `system pause`
Pause the system run while maintaining state.

```bash
system pause
```

**Output:**
```
✓ System paused
Use 'system resume' to continue
```

**Notes:**
- Can only pause from RUNNING state
- Managers suspend operations but keep state
- Data streams, strategies, etc. are paused

---

### `system resume`
Resume the system from paused state.

```bash
system resume
```

**Output:**
```
✓ System resumed
State: running
```

**Notes:**
- Can only resume from PAUSED state
- Continues operations from where they were paused
- All state is preserved

---

### `system stop`
Stop the system run completely.

```bash
system stop
```

**Output:**
```
✓ System stopped
State: stopped
```

**Notes:**
- Can stop from any state (RUNNING or PAUSED)
- Managers complete current operations and cleanup
- State is preserved but operations are halted

---

### `system status`
Show current system status and active managers.

```bash
system status
```

**Output:**
```
┌─────────────────── System Status ────────────────────┐
│ Property         │ Value                              │
├──────────────────┼────────────────────────────────────┤
│ State            │ RUNNING                            │
│ Initialized      │ Yes                                │
│ Active Managers  │ DataManager                        │
└──────────────────┴────────────────────────────────────┘

Use 'system pause' to pause or 'system stop' to stop
```

---

## State Transitions

```
STOPPED ──[start]──> RUNNING
RUNNING ──[pause]──> PAUSED
PAUSED ──[resume]──> RUNNING
RUNNING ──[stop]──> STOPPED
PAUSED ──[stop]──> STOPPED
```

## Use Cases

### Development & Testing
```bash
# Start system
system start

# ... test features ...

# Pause to examine state
system pause

# ... check logs, data, etc. ...

# Resume testing
system resume

# Stop when done
system stop
```

### Production Run
```bash
# Check status first
system status

# Start the system
system start

# System runs...

# Emergency pause
system pause

# Investigate issue, then resume or stop
system resume
# or
system stop
```

### Backtest Session
```bash
# Start system
system start

# Start data stream
data stream-bars 1m AAPL

# System processes backtest data...

# Pause to analyze results
system pause

# Check market status
market status

# Resume if needed
system resume

# Stop when backtest complete
system stop
```

## Manager Integration

Managers can check system state and respond accordingly:

```python
from app.managers import get_system_manager

system_mgr = get_system_manager()

# Check state
if system_mgr.is_running():
    # Process data
    pass
elif system_mgr.is_paused():
    # Wait or suspend
    pass
elif system_mgr.is_stopped():
    # Don't process
    pass
```

## Future Enhancements

### Planned Features
- [ ] Auto-save state on pause
- [ ] Checkpoint/restore functionality
- [ ] Graceful shutdown with timeout
- [ ] Manager health checks
- [ ] State persistence across restarts
- [ ] Event hooks (on_start, on_pause, etc.)
- [ ] Manager-specific pause/resume

### Manager-Specific Control
When managers implement start/pause/resume/stop hooks:

```python
class DataManager:
    def on_system_start(self):
        """Called when system starts."""
        pass
    
    def on_system_pause(self):
        """Called when system pauses."""
        # Suspend streaming, etc.
        pass
    
    def on_system_resume(self):
        """Called when system resumes."""
        # Resume streaming, etc.
        pass
    
    def on_system_stop(self):
        """Called when system stops."""
        # Cleanup resources
        pass
```

## See Also

- [SystemManager Architecture](ARCHITECTURE_SYSTEM_MANAGER.md)
- [Data Commands](../app/cli/data_commands.py)
- [System Manager Source](../app/managers/system_manager.py)
