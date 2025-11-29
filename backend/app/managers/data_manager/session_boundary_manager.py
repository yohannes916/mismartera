"""Session Boundary Manager for Automatic Session Lifecycle

Manages automatic detection and handling of session boundaries, including:
- Session state tracking
- Automatic session roll
- Timeout detection
- Error handling

Enables fully autonomous session management without manual intervention.
"""
import threading
import asyncio
from datetime import datetime, time, timedelta
from typing import Optional

from app.config import settings
from app.logger import logger
from app.managers.data_manager.session_state import SessionState, is_valid_transition
from app.managers.data_manager.session_detector import SessionDetector
# Time manager is accessed via system_manager


class SessionBoundaryManager:
    """Manage automatic session boundaries and lifecycle.
    
    Responsibilities:
    - Track current session state
    - Detect session end automatically
    - Trigger automatic session roll
    - Monitor for data timeouts
    - Handle error conditions
    """
    
    def __init__(
        self,
        session_data,
        session_detector: Optional[SessionDetector] = None,
        auto_roll: bool = True
    ):
        """Initialize session boundary manager.
        
        Args:
            session_data: SessionData singleton
            session_detector: SessionDetector instance (default: new instance)
            auto_roll: Enable automatic session rolling
        """
        self._session_data = session_data
        self._detector = session_detector or SessionDetector()
        self._auto_roll = auto_roll
        
        # State tracking
        self._current_state = SessionState.NOT_STARTED
        self._last_data_time: Optional[datetime] = None
        self._last_state_change: Optional[datetime] = None
        
        # Configuration
        self._timeout_seconds = settings.SESSION_TIMEOUT_SECONDS
        self._check_interval = settings.SESSION_BOUNDARY_CHECK_INTERVAL
        self._post_market_delay = settings.SESSION_POST_MARKET_ROLL_DELAY * 60  # Convert to seconds
        
        # Monitoring thread
        self._thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
        self._running = False
        
        logger.info(
            f"SessionBoundaryManager initialized: "
            f"auto_roll={auto_roll}, timeout={self._timeout_seconds}s"
        )
    
    def get_current_state(self) -> SessionState:
        """Get current session state.
        
        Returns:
            Current SessionState
        """
        return self._current_state
    
    def update_state(self) -> SessionState:
        """Update and return current session state based on conditions.
        
        Checks various conditions and transitions state appropriately.
        
        Returns:
            Updated SessionState
        """
        old_state = self._current_state
        
        # No session started?
        if self._session_data.current_session_date is None:
            new_state = SessionState.NOT_STARTED
            self._transition_state(old_state, new_state)
            return new_state
        
        # Use TimeManager as single source of truth for time
        from app.managers.system_manager import get_system_manager
        system_mgr = get_system_manager()
        time_mgr = system_mgr.get_time_manager()
        now = time_mgr.get_current_time()
        current_date = now.date()
        session_date = self._session_data.current_session_date
        
        # Check for timeout first (highest priority)
        if self._is_timeout():
            new_state = SessionState.TIMEOUT
            self._transition_state(old_state, new_state)
            return new_state
        
        # Check if session ended (next day reached)
        if current_date > session_date:
            new_state = SessionState.ENDED
            self._transition_state(old_state, new_state)
            return new_state
        
        # Same day - check time of day
        current_time = now.time()
        
        if current_time < self._detector.MARKET_OPEN:
            new_state = SessionState.PRE_MARKET
        elif current_time <= self._detector.MARKET_CLOSE:
            new_state = SessionState.ACTIVE
        else:
            new_state = SessionState.POST_MARKET
        
        self._transition_state(old_state, new_state)
        return new_state
    
    def _transition_state(self, old_state: SessionState, new_state: SessionState) -> None:
        """Transition to new state with validation and logging.
        
        Args:
            old_state: Previous state
            new_state: New state
        """
        if old_state == new_state:
            return
        
        # Validate transition
        if not is_valid_transition(old_state, new_state):
            logger.warning(
                f"Invalid state transition: {old_state.name} → {new_state.name}"
            )
        
        # Log transition
        logger.info(f"Session state: {old_state.name} → {new_state.name}")
        
        # Update state
        self._current_state = new_state
        from app.managers.system_manager import get_system_manager
        system_mgr = get_system_manager()
        time_mgr = system_mgr.get_time_manager()
        self._last_state_change = time_mgr.get_current_time()
    
    def should_roll_session(self) -> bool:
        """Determine if session should be rolled automatically.
        
        Returns:
            True if session should be rolled
        """
        if not self._auto_roll:
            return False
        
        state = self.update_state()
        
        # Roll if session ended
        if state == SessionState.ENDED:
            return True
        
        # Roll if in post-market for configured delay
        if state == SessionState.POST_MARKET:
            from app.managers.system_manager import get_system_manager
            system_mgr = get_system_manager()
            time_mgr = system_mgr.get_time_manager()
            now = time_mgr.get_current_time()
            
            # Check if we've been in post-market long enough
            if self._last_state_change:
                post_market_duration = (now - self._last_state_change).total_seconds()
                return post_market_duration >= self._post_market_delay
        
        return False
    
    def check_and_roll(self) -> bool:
        """Check if roll needed and execute.
        
        Returns:
            True if roll was performed
        """
        if not self.should_roll_session():
            return False
        
        # Determine next session
        current_session = self._session_data.current_session_date
        if current_session is None:
            logger.warning("Cannot roll: no current session")
            return False
        
        next_session = self._detector.get_next_session(
            current_session,
            skip_today=True
        )
        
        if next_session is None:
            logger.error("No next session found for auto-roll")
            self._transition_state(self._current_state, SessionState.ERROR)
            return False
        
        # Execute roll
        try:
            logger.info(
                f"Auto-rolling session: {current_session} → {next_session}"
            )
            
            self._session_data.roll_session(next_session)
            
            # Reset state
            self._transition_state(self._current_state, SessionState.NOT_STARTED)
            self._last_data_time = None
            
            logger.info(f"Session auto-rolled successfully to {next_session}")
            return True
        
        except Exception as e:
            logger.error(f"Error during auto-roll: {e}", exc_info=True)
            self._transition_state(self._current_state, SessionState.ERROR)
            return False
    
    def record_data_received(self, timestamp: Optional[datetime] = None) -> None:
        """Record that data was received (for timeout tracking).
        
        Args:
            timestamp: When data was received (default: current time from TimeManager)
        """
        from app.managers.system_manager import get_system_manager
        system_mgr = get_system_manager()
        time_mgr = system_mgr.get_time_manager()
        self._last_data_time = timestamp or time_mgr.get_current_time()
        
        # If we were in timeout, recover to active
        if self._current_state == SessionState.TIMEOUT:
            logger.info("Recovered from timeout - data received")
            self._transition_state(SessionState.TIMEOUT, SessionState.ACTIVE)
    
    def _is_timeout(self) -> bool:
        """Check if session has timed out (no data received).
        
        Returns:
            True if timeout detected
        """
        # Only check timeout if we're in an active session
        if not self._current_state.is_active():
            return False
        
        if self._last_data_time is None:
            # No data ever received - check if session just started
            if self._last_state_change:
                from app.managers.system_manager import get_system_manager
                system_mgr = get_system_manager()
                time_mgr = system_mgr.get_time_manager()
                elapsed = (time_mgr.get_current_time() - self._last_state_change).total_seconds()
                return elapsed > self._timeout_seconds
            return False
        
        # Check elapsed time since last data
        from app.managers.system_manager import get_system_manager
        system_mgr = get_system_manager()
        time_mgr = system_mgr.get_time_manager()
        now = time_mgr.get_current_time()
        elapsed = (now - self._last_data_time).total_seconds()
        
        return elapsed > self._timeout_seconds
    
    def start_monitoring(self) -> None:
        """Start background monitoring thread."""
        if self._running:
            logger.warning("SessionBoundaryManager already monitoring")
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
    
    def stop_monitoring(self, timeout: float = 5.0) -> None:
        """Stop monitoring thread.
        
        Args:
            timeout: Maximum seconds to wait for thread to stop
        """
        if not self._running:
            return
        
        logger.info("Stopping SessionBoundaryManager monitoring...")
        
        self._shutdown.set()
        
        if self._thread:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("SessionBoundaryManager did not stop within timeout")
            else:
                logger.info("SessionBoundaryManager monitoring stopped")
        
        self._running = False
    
    def _monitoring_worker(self) -> None:
        """Background worker for boundary monitoring."""
        logger.info("SessionBoundaryManager worker started")
        
        try:
            while not self._shutdown.is_set():
                try:
                    # Update state
                    self.update_state()
                    
                    # Check and potentially roll
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    try:
                        rolled = loop.run_until_complete(self.check_and_roll())
                        if rolled:
                            logger.info("Auto-roll completed")
                    finally:
                        loop.close()
                    
                    # Sleep for check interval
                    self._shutdown.wait(self._check_interval)
                
                except Exception as e:
                    logger.error(f"Error in boundary monitoring: {e}", exc_info=True)
                    self._transition_state(self._current_state, SessionState.ERROR)
                    self._shutdown.wait(self._check_interval)
        
        except Exception as e:
            logger.critical(f"SessionBoundaryManager worker crashed: {e}", exc_info=True)
        
        finally:
            logger.info("SessionBoundaryManager worker exiting")
    
    def get_status(self) -> dict:
        """Get current status information.
        
        Returns:
            Dictionary with status details
        """
        return {
            "current_state": self._current_state.name,
            "state_value": self._current_state.value,
            "auto_roll_enabled": self._auto_roll,
            "monitoring_active": self._running,
            "last_data_time": self._last_data_time,
            "last_state_change": self._last_state_change,
            "timeout_seconds": self._timeout_seconds,
            "check_interval": self._check_interval,
            "current_session_date": self._session_data.current_session_date,
            "is_timeout": self._is_timeout(),
            "should_roll": self.should_roll_session()
        }
    
    def force_state(self, new_state: SessionState) -> None:
        """Force transition to new state (for testing/manual control).
        
        Args:
            new_state: State to force
        """
        logger.warning(f"Forcing state transition to {new_state.name}")
        self._transition_state(self._current_state, new_state)
    
    def clear_error(self) -> None:
        """Clear error state and return to appropriate state."""
        if self._current_state != SessionState.ERROR:
            return
        
        logger.info("Clearing error state")
        
        # Determine appropriate recovery state
        state = self.update_state()
        logger.info(f"Recovered to state: {state.name}")


# Singleton instance management
_boundary_manager_instance: Optional[SessionBoundaryManager] = None


def get_boundary_manager(
    session_data,
    session_detector: Optional[SessionDetector] = None,
    auto_roll: bool = True
) -> SessionBoundaryManager:
    """Get or create the global SessionBoundaryManager instance.
    
    Args:
        session_data: SessionData singleton
        session_detector: Optional SessionDetector instance
        auto_roll: Enable automatic session rolling
        
    Returns:
        SessionBoundaryManager instance
    """
    global _boundary_manager_instance
    if _boundary_manager_instance is None:
        _boundary_manager_instance = SessionBoundaryManager(
            session_data,
            session_detector,
            auto_roll
        )
    return _boundary_manager_instance


def reset_boundary_manager() -> None:
    """Reset the global boundary manager instance (for testing)."""
    global _boundary_manager_instance
    if _boundary_manager_instance and _boundary_manager_instance._running:
        _boundary_manager_instance.stop_monitoring()
    _boundary_manager_instance = None
