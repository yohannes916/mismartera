"""
StreamSubscription - Event-based one-shot thread synchronization.

This module provides event-based synchronization between threads using
threading.Event with mode-aware behavior and overrun detection.

Usage Pattern:
    Producer (e.g., session_coordinator):
        subscription.signal_ready()
    
    Consumer (e.g., data_processor):
        start = time.perf_counter()
        subscription.wait_until_ready(timeout=1.0)
        duration = time.perf_counter() - start
        subscription.reset()  # Prepare for next cycle

Key Features:
1. One-shot pattern: signal → wait → reset → repeat
2. Mode-aware waiting: blocking (data-driven) vs timeout (clock-driven/live)
3. Overrun detection: Warns if consumer hasn't processed previous data
4. Thread-safe: Uses threading.Event internally

Reference: SESSION_ARCHITECTURE.md - Thread Synchronization
"""

import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class StreamSubscription:
    """Event-based one-shot subscription for thread synchronization.
    
    Modes:
        - data-driven: Blocks indefinitely until ready (backtest speed=0)
        - clock-driven: Timeout-based with overrun detection (backtest speed>0)
        - live: Timeout-based (real-time market data)
    
    One-Shot Pattern:
        Each signal/wait cycle must be explicitly reset for next cycle.
        This prevents race conditions and ensures sequential processing.
    
    Overrun Detection:
        In clock-driven mode, if signal_ready() is called before the previous
        ready event was consumed (reset), it indicates the consumer is too slow.
    """
    
    def __init__(self, mode: str, stream_id: str):
        """Initialize stream subscription.
        
        Args:
            mode: Operating mode ('data-driven', 'clock-driven', or 'live')
            stream_id: Identifier for debugging (e.g., "coordinator->data_processor")
        
        Raises:
            ValueError: If mode is not one of the valid modes
        """
        if mode not in ('data-driven', 'clock-driven', 'live'):
            raise ValueError(
                f"Invalid mode '{mode}'. Must be 'data-driven', 'clock-driven', or 'live'"
            )
        
        self._ready_event = threading.Event()
        self._mode = mode
        self._stream_id = stream_id
        self._overrun_count = 0
        self._lock = threading.Lock()  # Protect overrun_count
        
        logger.debug(f"StreamSubscription created: {stream_id} (mode={mode})")
    
    def signal_ready(self) -> None:
        """Signal that data is ready for consumer.
        
        Called by producer thread when data is available.
        
        In clock-driven mode, detects overruns (consumer too slow):
            - If event already set: Consumer hasn't reset yet (overrun)
            - Increments overrun counter and logs warning
        
        Thread-safe: Can be called from any thread.
        """
        # Check for overrun (clock-driven mode only)
        if self._ready_event.is_set() and self._mode == 'clock-driven':
            with self._lock:
                self._overrun_count += 1
                logger.warning(
                    f"Overrun detected for {self._stream_id}: "
                    f"Previous data not consumed. Total overruns: {self._overrun_count}"
                )
        
        # Signal ready
        self._ready_event.set()
        logger.debug(f"{self._stream_id}: Signaled ready")
    
    def wait_until_ready(self, timeout: Optional[float] = None) -> bool:
        """Wait for ready signal from producer.
        
        Called by consumer thread to wait for data availability.
        
        Args:
            timeout: Maximum time to wait in seconds.
                     Only used in clock-driven and live modes.
                     Ignored in data-driven mode (blocks indefinitely).
        
        Returns:
            True if ready signal received, False if timeout (only in timeout modes)
        
        Mode Behavior:
            - data-driven: Blocks indefinitely (timeout ignored)
            - clock-driven: Uses timeout, returns False on timeout
            - live: Uses timeout, returns False on timeout
        
        Thread-safe: Can be called from any thread.
        
        Note: After wait returns True, consumer should call reset() before
              processing completes to prepare for next cycle.
        """
        if self._mode == 'data-driven':
            # Block indefinitely in data-driven mode
            self._ready_event.wait()
            logger.debug(f"{self._stream_id}: Ready event received (data-driven)")
            return True
        else:
            # Timeout-based for clock-driven and live
            result = self._ready_event.wait(timeout=timeout)
            if result:
                logger.debug(f"{self._stream_id}: Ready event received ({self._mode})")
            else:
                logger.warning(
                    f"{self._stream_id}: Timeout waiting for ready event "
                    f"(timeout={timeout}s, mode={self._mode})"
                )
            return result
    
    def reset(self) -> None:
        """Reset event for next cycle (one-shot pattern).
        
        Called by consumer after processing data to prepare for next signal.
        
        Critical: Must be called after each wait_until_ready() to ensure
                 one-shot behavior and prevent race conditions.
        
        Thread-safe: Can be called from any thread.
        """
        self._ready_event.clear()
        logger.debug(f"{self._stream_id}: Reset for next cycle")
    
    def get_overrun_count(self) -> int:
        """Get total number of overruns detected.
        
        Returns:
            Number of times signal_ready() was called before previous
            event was consumed (reset). Only relevant in clock-driven mode.
        
        Thread-safe: Returns atomic counter value.
        """
        with self._lock:
            return self._overrun_count
    
    def is_ready(self) -> bool:
        """Check if ready event is currently set (non-blocking).
        
        Returns:
            True if ready event is set, False otherwise
        
        Note: This is a snapshot check. Event may change immediately after.
        """
        return self._ready_event.is_set()
    
    def get_mode(self) -> str:
        """Get operating mode.
        
        Returns:
            Operating mode ('data-driven', 'clock-driven', or 'live')
        """
        return self._mode
    
    def get_stream_id(self) -> str:
        """Get stream identifier.
        
        Returns:
            Stream identifier for debugging
        """
        return self._stream_id
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"StreamSubscription("
            f"id='{self._stream_id}', "
            f"mode='{self._mode}', "
            f"ready={self._ready_event.is_set()}, "
            f"overruns={self._overrun_count}"
            f")"
        )
