"""Strategy thread implementation.

Each strategy runs in its own thread with dedicated queue and synchronization.
"""
import threading
import queue
import time
from typing import Optional, Tuple
import logging

from app.strategies.base import BaseStrategy, StrategyContext
from app.threads.sync.stream_subscription import StreamSubscription

logger = logging.getLogger(__name__)


class StrategyThread(threading.Thread):
    """Thread for running a single strategy.
    
    Each strategy runs in its own thread with:
    - Dedicated notification queue
    - StreamSubscription for sync with DataProcessor
    - Performance metrics tracking
    - Mode-aware blocking behavior
    
    Attributes:
        strategy: Strategy instance
        mode: Execution mode ("data-driven", "clock-driven", "live")
        context: Strategy context
    """
    
    def __init__(
        self,
        strategy: BaseStrategy,
        context: StrategyContext,
        mode: str
    ):
        """Initialize strategy thread.
        
        Args:
            strategy: Strategy instance to run
            context: Strategy context
            mode: Execution mode (data-driven, clock-driven, live)
        """
        super().__init__(name=f"Strategy-{strategy.name}", daemon=True)
        
        self.strategy = strategy
        self.context = context
        self.mode = mode
        
        # Thread control
        self._stop_event = threading.Event()
        self._queue = queue.Queue()
        
        # Synchronization with DataProcessor
        self._subscription = StreamSubscription(
            mode=mode,
            stream_id=f"processor->strategy:{strategy.name}"
        )
        
        # Performance metrics
        self._notifications_processed = 0
        self._signals_generated = 0
        self._errors = 0
        self._total_processing_time = 0.0
        self._max_processing_time = 0.0
        
        logger.info(f"Created strategy thread: {strategy.name} (mode={mode})")
    
    # =========================================================================
    # Thread Lifecycle
    # =========================================================================
    
    def run(self):
        """Main thread loop."""
        logger.info(f"[{self.strategy.name}] Starting strategy thread")
        
        try:
            self._processing_loop()
        except Exception as e:
            logger.error(f"[{self.strategy.name}] Fatal error: {e}", exc_info=True)
        finally:
            logger.info(f"[{self.strategy.name}] Strategy thread exiting")
    
    def stop(self):
        """Signal thread to stop."""
        logger.info(f"[{self.strategy.name}] Stop requested")
        self._stop_event.set()
        # Put sentinel to unblock queue.get()
        try:
            self._queue.put(None, block=False)
        except queue.Full:
            pass
    
    def join(self, timeout=None):
        """Wait for thread to finish."""
        super().join(timeout=timeout)
        if self.is_alive():
            logger.warning(f"[{self.strategy.name}] Thread did not exit in time")
    
    # =========================================================================
    # Notification Queue
    # =========================================================================
    
    def notify(self, symbol: str, interval: str, data_type: str = "bars"):
        """Add notification to queue.
        
        Called by DataProcessor when subscribed data arrives.
        
        Args:
            symbol: Symbol with new data
            interval: Interval with new data
            data_type: Type of data ("bars", "quotes", etc.)
        """
        try:
            self._queue.put((symbol, interval, data_type), block=False)
        except queue.Full:
            logger.warning(f"[{self.strategy.name}] Queue full - dropping notification")
            self._errors += 1
    
    def get_queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()
    
    # =========================================================================
    # Main Processing Loop
    # =========================================================================
    
    def _processing_loop(self):
        """Main processing loop."""
        while not self._stop_event.is_set():
            try:
                # Wait for notification (with timeout for stop check)
                notification = self._queue.get(timeout=1.0)
                
                if notification is None:
                    # Sentinel value - exit
                    break
                
                # Process notification
                self._process_notification(notification)
                
            except queue.Empty:
                # Timeout - check stop event
                continue
            except Exception as e:
                logger.error(
                    f"[{self.strategy.name}] Error in processing loop: {e}",
                    exc_info=True
                )
                self._errors += 1
    
    def _process_notification(self, notification: Tuple[str, str, str]):
        """Process a single notification.
        
        Args:
            notification: (symbol, interval, data_type) tuple
        """
        symbol, interval, data_type = notification
        
        start_time = time.time()
        
        try:
            # Call strategy's on_bars method
            signals = self.strategy.on_bars(symbol, interval)
            
            # Track signals
            if signals:
                self._signals_generated += len(signals)
                logger.debug(
                    f"[{self.strategy.name}] Generated {len(signals)} signals "
                    f"for {symbol} {interval}"
                )
            
            # Update metrics
            self._notifications_processed += 1
            processing_time = time.time() - start_time
            self._total_processing_time += processing_time
            self._max_processing_time = max(self._max_processing_time, processing_time)
            
            # Signal ready to DataProcessor (mode-aware blocking)
            self._subscription.signal_ready()
            
        except Exception as e:
            logger.error(
                f"[{self.strategy.name}] Error processing {symbol} {interval}: {e}",
                exc_info=True
            )
            self._errors += 1
            
            # Still signal ready (don't block DataProcessor)
            self._subscription.signal_ready()
    
    # =========================================================================
    # Subscription Management
    # =========================================================================
    
    def get_subscription(self) -> StreamSubscription:
        """Get StreamSubscription for DataProcessor sync.
        
        Returns:
            StreamSubscription instance
        """
        return self._subscription
    
    # =========================================================================
    # Performance Metrics
    # =========================================================================
    
    def get_metrics(self) -> dict:
        """Get performance metrics.
        
        Returns:
            Dictionary of metrics
        """
        avg_time = (
            self._total_processing_time / self._notifications_processed
            if self._notifications_processed > 0
            else 0.0
        )
        
        overruns = (
            self._subscription._overrun_count 
            if hasattr(self._subscription, '_overrun_count') 
            else 0
        )
        
        return {
            'strategy_name': self.strategy.name,
            'running': self.is_alive(),
            'mode': self.mode,
            'notifications_processed': self._notifications_processed,
            'signals_generated': self._signals_generated,
            'errors': self._errors,
            'queue_size': self.get_queue_size(),
            'avg_processing_time_ms': avg_time * 1000,
            'max_processing_time_ms': self._max_processing_time * 1000,
            'overruns': overruns,
        }


# Export public API
__all__ = ['StrategyThread']
