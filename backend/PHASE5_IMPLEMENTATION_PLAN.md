# Phase 5: Session Boundaries - Implementation Plan

## Objective

Implement automatic session boundary detection and management to enable fully autonomous session lifecycle with timeout handling and error flagging.

---

## Timeline

**Duration**: 2 weeks (estimated)  
**Actual Target**: 2-3 hours (based on Phases 1-4 performance)  
**Complexity**: Medium  
**Dependencies**: Phases 1-4 ✅

---

## Overview

Phase 5 completes the session management system by adding automatic detection of session boundaries, automatic session roll, timeout handling, and comprehensive error states.

### Problem Statement

**Current** (after Phase 4):
- Session roll is manual (`roll_session()` must be called)
- No automatic end-of-day detection
- No timeout handling for stale data
- No error states for session problems

**Solution** (Phase 5):
- Automatic session end detection
- Automatic session roll to next day
- Timeout detection and handling
- Error flagging and recovery

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────┐
│         Session Boundary Manager (NEW)              │
│                                                     │
│  ┌──────────────────┐      ┌──────────────────┐   │
│  │ Boundary Monitor │      │ Auto-Roll Engine │   │
│  │                  │      │                  │   │
│  │ • Detect end     │─────►│ • Trigger roll   │   │
│  │ • Timeout check  │      │ • Error recovery │   │
│  │ • State tracking │      │ • Validation     │   │
│  └──────────────────┘      └──────────────────┘   │
│           │                         │              │
│           └─────────┬───────────────┘              │
│                     ▼                              │
│              session_data                          │
│           (Auto-managed lifecycle)                 │
└─────────────────────────────────────────────────────┘
```

### Session States

```
State Machine:

NOT_STARTED ──► PRE_MARKET ──► ACTIVE ──► POST_MARKET ──► ENDED
                    │               │           │
                    │               ▼           │
                    │          TIMEOUT          │
                    │               │           │
                    └───────► ERROR ◄───────────┘
```

---

## Features to Implement

### 1. Session State Enum

**File**: `session_state.py` (NEW)

```python
from enum import Enum

class SessionState(Enum):
    """Session lifecycle states."""
    
    NOT_STARTED = "not_started"     # No session initialized
    PRE_MARKET = "pre_market"       # Before market open (< 9:30 AM)
    ACTIVE = "active"               # During market hours (9:30 AM - 4:00 PM)
    POST_MARKET = "post_market"     # After market close (> 4:00 PM)
    ENDED = "ended"                 # Session explicitly ended
    TIMEOUT = "timeout"             # No data received for timeout period
    ERROR = "error"                 # Error state requiring intervention
```

### 2. Session Boundary Manager

**File**: `session_boundary_manager.py` (NEW)

```python
class SessionBoundaryManager:
    """Manage automatic session boundaries and lifecycle.
    
    Responsibilities:
    - Detect session end automatically
    - Trigger automatic session roll
    - Monitor for timeouts
    - Track session state
    - Handle error conditions
    """
    
    def __init__(
        self,
        session_data: SessionData,
        session_detector: SessionDetector,
        auto_roll: bool = True
    ):
        self._session_data = session_data
        self._detector = session_detector
        self._auto_roll = auto_roll
        
        # State tracking
        self._current_state = SessionState.NOT_STARTED
        self._last_data_time: Optional[datetime] = None
        self._timeout_seconds = settings.SESSION_TIMEOUT_SECONDS
        
        # Monitoring thread
        self._thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
        self._running = False
    
    def get_current_state(self) -> SessionState:
        """Get current session state."""
        return self._current_state
    
    def update_state(self) -> SessionState:
        """Update and return current session state based on conditions."""
        if self._session_data.current_session_date is None:
            self._current_state = SessionState.NOT_STARTED
            return self._current_state
        
        now = datetime.now()
        current_date = now.date()
        session_date = self._session_data.current_session_date
        
        # Check for timeout
        if self._is_timeout():
            self._current_state = SessionState.TIMEOUT
            return self._current_state
        
        # Check if session ended (next day)
        if current_date > session_date:
            self._current_state = SessionState.ENDED
            return self._current_state
        
        # Check time of day
        current_time = now.time()
        
        if current_time < self._detector.MARKET_OPEN:
            self._current_state = SessionState.PRE_MARKET
        elif current_time <= self._detector.MARKET_CLOSE:
            self._current_state = SessionState.ACTIVE
        else:
            self._current_state = SessionState.POST_MARKET
        
        return self._current_state
    
    def should_roll_session(self) -> bool:
        """Determine if session should be rolled automatically."""
        if not self._auto_roll:
            return False
        
        state = self.update_state()
        
        # Roll if session ended or in post-market for too long
        if state == SessionState.ENDED:
            return True
        
        if state == SessionState.POST_MARKET:
            # Check if post-market has lasted too long
            now = datetime.now()
            post_market_duration = now.time() > time(17, 0)  # > 5 PM
            return post_market_duration
        
        return False
    
    async def check_and_roll(self) -> bool:
        """Check if roll needed and execute.
        
        Returns:
            True if roll was performed
        """
        if not self.should_roll_session():
            return False
        
        # Determine next session
        current_session = self._session_data.current_session_date
        next_session = self._detector.get_next_session(
            current_session,
            skip_today=True
        )
        
        if next_session is None:
            logger.error("No next session found for auto-roll")
            self._current_state = SessionState.ERROR
            return False
        
        # Execute roll
        try:
            logger.info(f"Auto-rolling session from {current_session} to {next_session}")
            await self._session_data.roll_session(next_session)
            self._current_state = SessionState.NOT_STARTED
            return True
        
        except Exception as e:
            logger.error(f"Error during auto-roll: {e}", exc_info=True)
            self._current_state = SessionState.ERROR
            return False
    
    def record_data_received(self, timestamp: datetime) -> None:
        """Record that data was received (for timeout tracking).
        
        Args:
            timestamp: When data was received
        """
        self._last_data_time = timestamp
    
    def _is_timeout(self) -> bool:
        """Check if session has timed out (no data received)."""
        if self._last_data_time is None:
            return False
        
        now = datetime.now()
        elapsed = (now - self._last_data_time).total_seconds()
        
        return elapsed > self._timeout_seconds
    
    def start_monitoring(self) -> None:
        """Start background monitoring thread."""
        if self._running:
            return
        
        self._shutdown.clear()
        self._running = True
        
        self._thread = threading.Thread(
            target=self._monitoring_worker,
            name="SessionBoundaryMonitor",
            daemon=True
        )
        self._thread.start()
        
        logger.info("SessionBoundaryManager monitoring started")
    
    def stop_monitoring(self) -> None:
        """Stop monitoring thread."""
        if not self._running:
            return
        
        self._shutdown.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        self._running = False
        
        logger.info("SessionBoundaryManager monitoring stopped")
    
    def _monitoring_worker(self) -> None:
        """Background worker for monitoring."""
        while not self._shutdown.is_set():
            try:
                # Check and potentially roll
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.check_and_roll())
                loop.close()
                
                # Sleep for check interval
                self._shutdown.wait(60)  # Check every minute
            
            except Exception as e:
                logger.error(f"Error in boundary monitoring: {e}")
                self._shutdown.wait(60)
```

### 3. Configuration

**Add to `settings.py`**:

```python
# Session Boundary Configuration (Phase 5)
SESSION_AUTO_ROLL: bool = True
SESSION_TIMEOUT_SECONDS: int = 300          # 5 minutes without data = timeout
SESSION_BOUNDARY_CHECK_INTERVAL: int = 60   # Check every minute
SESSION_POST_MARKET_ROLL_DELAY: int = 30    # Minutes after close to auto-roll
```

---

## Integration Points

### 1. Enhance session_data

Add state tracking:

```python
# In SessionData class

@property
def session_state(self) -> SessionState:
    """Get current session state."""
    if hasattr(self, '_boundary_manager'):
        return self._boundary_manager.get_current_state()
    return SessionState.NOT_STARTED
```

### 2. DataManager Integration

```python
class DataManager:
    def __init__(self):
        # ... existing init ...
        
        # Add boundary manager (Phase 5)
        if settings.SESSION_AUTO_ROLL:
            from app.managers.data_manager.session_boundary_manager import (
                SessionBoundaryManager
            )
            from app.managers.data_manager.session_detector import SessionDetector
            
            detector = SessionDetector()
            self._boundary_manager = SessionBoundaryManager(
                session_data=self.session_data,
                session_detector=detector,
                auto_roll=True
            )
            self._boundary_manager.start_monitoring()
```

---

## Testing Strategy

### Unit Tests

**File**: `test_session_boundaries.py`

```python
@pytest.mark.asyncio
async def test_session_state_transitions():
    """Test state transitions through session lifecycle."""

@pytest.mark.asyncio
async def test_auto_roll_trigger():
    """Test automatic session roll triggering."""

@pytest.mark.asyncio
async def test_timeout_detection():
    """Test timeout detection when no data received."""

@pytest.mark.asyncio
async def test_error_state_handling():
    """Test error state and recovery."""
```

---

## Success Criteria

### Phase 5 Goals

- [ ] SessionState enum defined
- [ ] SessionBoundaryManager implemented
- [ ] Automatic state detection working
- [ ] Automatic session roll working
- [ ] Timeout detection working
- [ ] Error state handling
- [ ] Configuration added
- [ ] Unit tests (10-15 tests)
- [ ] Documentation complete

---

## Timeline Breakdown

### Session 1 (1-1.5 hours)
- Create SessionState enum
- Implement SessionBoundaryManager
- Add configuration

### Session 2 (1-1.5 hours)
- Unit tests
- Integration
- Documentation

**Total**: 2-3 hours

---

## Next: Phase 6

After Phase 5, Phase 6 will add:
- Derived bars polish
- Auto-activation improvements
- Performance optimization
- Production deployment prep

---

**Status**: 📋 Ready to implement  
**Prerequisites**: Phases 1-4 complete ✅  
**Timeline**: 2-3 hours  
**Complexity**: Medium
