"""
Data Processor - Event-Driven Bar Generation & Indicator Calculation

This is a COMPLETE REWRITE for the new session architecture (Phase 4).
Old version backed up to: app/managers/data_manager/_backup/data_upkeep_thread.py.bak

Key Responsibilities:
1. Generate derivative bars (5m, 15m, 30m, etc. from 1m bars)
2. Calculate real-time indicators (NOT historical - coordinator handles those)
3. Notify subscribers (analysis engine) when data available
4. Bidirectional synchronization with session coordinator

Architecture Reference: SESSION_ARCHITECTURE.md - Section 2 (Data Processor Thread)

Thread Launch Sequence:
  SystemManager → Session Coordinator → DataProcessor → Analysis Engine

Dependencies (Phase 1, 2, 3):
- SessionData (Phase 1.1) - Unified data store (zero-copy access)
- StreamSubscription (Phase 1.2) - Thread synchronization
- PerformanceMetrics (Phase 1.3) - Monitoring
- SessionConfig (Phase 2.1) - Configuration
- TimeManager (Phase 2.2) - Time/calendar operations
- SessionCoordinator (Phase 3) - Main orchestrator

Key Design:
- Event-driven: Wait on notification queue (NOT periodic polling)
- Zero-copy: Read from session_data by reference, never copy
- Bidirectional sync: Receive notifications + signal ready
- Mode-aware: Data-driven (blocking) vs clock-driven (OverrunError)
- NO quality management (Phase 5: Data Quality Manager)
- NO session lifecycle (Phase 3: Session Coordinator)
- NO historical indicators (Phase 3: Session Coordinator)
"""

import logging
import threading
import queue
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from collections import defaultdict

# Phase 1, 2, 3 components
from app.data.session_data import SessionData
from app.threads.sync.stream_subscription import StreamSubscription
from app.monitoring.performance_metrics import PerformanceMetrics
from app.models.session_config import SessionConfig

# Derived bar computation (existing utility)
from app.managers.data_manager.derived_bars import (
    compute_derived_bars,
    compute_all_derived_intervals
)

# Existing infrastructure
from app.models.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class OverrunError(Exception):
    """Raised when data arrives before processor is ready in clock-driven mode."""
    pass


class DataProcessor(threading.Thread):
    """Event-driven processor for derived bars and real-time indicators.
    
    This processor runs in its own thread and waits for notifications from
    the session coordinator. When notified, it:
    1. Reads data from session_data (zero-copy)
    2. Generates derived bars (5m, 15m, etc. from 1m)
    3. Calculates real-time indicators
    4. Signals ready to coordinator
    5. Notifies analysis engine
    
    Synchronization:
    - FROM Coordinator: Notification queue + subscriptions
    - TO Coordinator: Ready signals (one-shot)
    - TO Analysis Engine: Data available notifications
    
    Scope:
    - Derived bars: Yes
    - Real-time indicators: Yes
    - Historical indicators: No (coordinator does these)
    - Quality management: No (data quality manager does this)
    - Session lifecycle: No (coordinator does this)
    """
    
    def __init__(
        self,
        session_data: SessionData,
        system_manager,
        session_config: SessionConfig,
        metrics: PerformanceMetrics
    ):
        """Initialize data processor.
        
        Args:
            session_data: Reference to SessionData for zero-copy access
            system_manager: Reference to SystemManager for time/config
            session_config: Session configuration
            metrics: Performance metrics tracker
        """
        super().__init__(name="DataProcessor", daemon=True)
        
        self.session_data = session_data
        self._system_manager = system_manager
        self.session_config = session_config
        self.metrics = metrics
        
        # Get TimeManager reference
        self._time_manager = system_manager.get_time_manager()
        
        # Thread control
        self._stop_event = threading.Event()
        self._running = False
        
        # Notification queue FROM coordinator
        self._notification_queue: queue.Queue[Tuple[str, str, datetime]] = queue.Queue()
        
        # Subscription TO coordinator (for ready signals)
        self._coordinator_subscription: Optional[StreamSubscription] = None
        
        # Notification queue TO analysis engine
        self._analysis_engine_queue: Optional[queue.Queue] = None
        
        # Configuration
        upkeep_config = session_config.session_data_config.data_upkeep
        self._derived_intervals = upkeep_config.derived_intervals
        self._auto_compute_derived = upkeep_config.auto_compute_derived
        self._realtime_indicators = []  # TODO: From config when indicator config added
        
        # Mode detection
        self.mode = "backtest" if session_config.backtest_config else "live"
        
        # Performance tracking
        self._processing_times = []
        
        logger.info(
            f"DataProcessor initialized: mode={self.mode}, "
            f"derived_intervals={self._derived_intervals}, "
            f"auto_compute={self._auto_compute_derived}"
        )
    
    def set_coordinator_subscription(self, subscription: StreamSubscription):
        """Set subscription for signaling ready to coordinator.
        
        Args:
            subscription: StreamSubscription to signal ready
        """
        self._coordinator_subscription = subscription
        logger.debug("Coordinator subscription configured")
    
    def set_analysis_engine_queue(self, queue_ref: queue.Queue):
        """Set notification queue for analysis engine.
        
        Args:
            queue_ref: Queue to send notifications to analysis engine
        """
        self._analysis_engine_queue = queue_ref
        logger.debug("Analysis engine notification queue configured")
    
    def notify_data_available(self, symbol: str, interval: str, timestamp: datetime):
        """Receive notification from coordinator that data is available.
        
        This is called by the session coordinator when new data arrives.
        
        Args:
            symbol: Symbol with new data
            interval: Interval with new data
            timestamp: Timestamp of new data
        """
        self._notification_queue.put((symbol, interval, timestamp))
    
    def run(self):
        """Main thread entry point - starts event-driven processing loop."""
        self._running = True
        logger.info("DataProcessor thread started")
        
        try:
            self._processing_loop()
        except Exception as e:
            logger.error(f"DataProcessor thread crashed: {e}", exc_info=True)
        finally:
            self._running = False
            logger.info("DataProcessor thread stopped")
    
    def stop(self):
        """Signal thread to stop."""
        logger.info("Stopping DataProcessor...")
        self._stop_event.set()
        
        # Unblock queue if waiting
        self._notification_queue.put(None)
    
    def join(self, timeout=None):
        """Wait for thread to stop.
        
        Args:
            timeout: Maximum time to wait (seconds)
        """
        if self.is_alive():
            super().join(timeout)
            if self.is_alive():
                logger.warning("DataProcessor did not stop gracefully")
            else:
                logger.info("DataProcessor stopped gracefully")
    
    # =========================================================================
    # Main Processing Loop
    # =========================================================================
    
    def _processing_loop(self):
        """Main event-driven processing loop.
        
        Waits for notifications from coordinator, processes data, signals ready.
        
        Flow:
        1. Wait on notification queue (blocking with timeout)
        2. Read data from session_data (zero-copy)
        3. Generate derived bars
        4. Calculate real-time indicators
        5. Signal ready to coordinator
        6. Notify analysis engine
        """
        logger.info("Starting event-driven processing loop")
        
        while not self._stop_event.is_set():
            try:
                # 1. Wait for notification (blocking with timeout for graceful shutdown)
                try:
                    notification = self._notification_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Check for stop signal
                if notification is None or self._stop_event.is_set():
                    break
                
                # Start timing
                start_time = self.metrics.start_timer()
                
                symbol, interval, timestamp = notification
                logger.debug(
                    f"Processing notification: {symbol} {interval} @ {timestamp.time()}"
                )
                
                # 2. Process based on interval
                if interval == "1m":
                    # Generate derived bars from 1m bars
                    self._generate_derived_bars(symbol)
                
                # 3. Calculate real-time indicators
                self._calculate_realtime_indicators(symbol, interval)
                
                # 4. Signal ready to coordinator (mode-aware)
                self._signal_ready_to_coordinator()
                
                # 5. Notify analysis engine
                self._notify_analysis_engine(symbol, interval)
                
                # 6. Record timing and metrics
                elapsed = self.metrics.elapsed_time(start_time)
                self._processing_times.append(elapsed)
                
                # Record in performance metrics
                self.metrics.record_data_processor(start_time)
                
                logger.debug(f"Processed {symbol} {interval} in {elapsed:.3f}s")
                
            except Exception as e:
                logger.error(
                    f"Error processing notification: {e}",
                    exc_info=True
                )
        
        logger.info("Processing loop exited")
    
    # =========================================================================
    # Derived Bar Generation
    # =========================================================================
    
    def _generate_derived_bars(self, symbol: str):
        """Generate derived bars for a symbol.
        
        Reads 1m bars from session_data and generates configured derived
        intervals (5m, 15m, 30m, etc.) using progressive computation.
        
        Progressive: Computes each interval as soon as enough bars available.
        - 5m bars: Generated as soon as 5 1m bars exist
        - 15m bars: Generated when 15 1m bars exist
        - etc.
        
        Args:
            symbol: Symbol to generate derived bars for
        """
        if not self._auto_compute_derived or not self._derived_intervals:
            return
        
        try:
            # 1. Read 1m bars from session_data (zero-copy)
            bars_1m_deque = self.session_data.get_bars(symbol, "1m")
            
            if not bars_1m_deque:
                logger.debug(f"No 1m bars available for {symbol}")
                return
            
            # Convert deque to list for processing
            bars_1m = list(bars_1m_deque)
            
            # 2. Progressive computation: Process intervals in ascending order
            # This ensures we compute 5m as soon as 5 bars exist, 15m when 15 exist, etc.
            sorted_intervals = sorted(self._derived_intervals)
            
            for interval in sorted_intervals:
                # Check if we have enough bars for this interval
                if len(bars_1m) < interval:
                    logger.debug(
                        f"Skipping {interval}m bars for {symbol}: "
                        f"only {len(bars_1m)} of {interval} 1m bars available"
                    )
                    continue
                
                # 3. Compute derived bars for this interval
                derived_bars = compute_derived_bars(bars_1m, interval)
                
                if not derived_bars:
                    continue
                
                # 4. Get existing derived bars (to avoid duplicates)
                existing_derived = list(self.session_data.get_bars(symbol, f"{interval}m"))
                
                # 5. Add only new bars (skip duplicates)
                new_bar_count = 0
                for derived_bar in derived_bars:
                    # Check if bar already exists
                    exists = any(
                        bar.timestamp == derived_bar.timestamp
                        for bar in existing_derived
                    )
                    
                    if not exists:
                        self.session_data.add_bar(symbol, f"{interval}m", derived_bar)
                        new_bar_count += 1
                
                if new_bar_count > 0:
                    logger.debug(
                        f"Generated {new_bar_count} new {interval}m bars for {symbol} "
                        f"(total {len(derived_bars)})"
                    )
            
        except Exception as e:
            logger.error(
                f"Error generating derived bars for {symbol}: {e}",
                exc_info=True
            )
    
    # =========================================================================
    # Real-Time Indicator Calculation
    # =========================================================================
    
    def _calculate_realtime_indicators(self, symbol: str, interval: str):
        """Calculate real-time indicators for a symbol/interval.
        
        NOTE: This only calculates indicators when NEW data arrives.
        Historical indicators are calculated by session coordinator before
        session starts.
        
        Real-time indicators include: RSI, SMA, EMA, MACD, Bollinger Bands, etc.
        Configuration will come from session_config.realtime_indicators when
        indicator config is added.
        
        Implementation Status: DEFERRED
        Reason: Indicator configuration system not yet designed
        Priority: Can be added after Phase 4 core functionality complete
        
        Args:
            symbol: Symbol to calculate indicators for
            interval: Interval to calculate indicators for
        """
        if not self._realtime_indicators:
            return
        
        try:
            # TODO: Implement when indicator configuration is designed
            # Planned approach:
            #   1. Read bars from session_data (zero-copy)
            #   2. For each configured indicator:
            #      - Calculate indicator value (RSI, SMA, EMA, etc.)
            #      - Store result in session_data
            #   3. Log computation
            
            # Example indicators:
            # - RSI (Relative Strength Index)
            # - SMA (Simple Moving Average)
            # - EMA (Exponential Moving Average)
            # - MACD (Moving Average Convergence Divergence)
            # - Bollinger Bands
            # - ATR (Average True Range)
            
            logger.debug(
                f"Real-time indicator calculation for {symbol} {interval} "
                f"(deferred until indicator config designed)"
            )
            
        except Exception as e:
            logger.error(
                f"Error calculating indicators for {symbol} {interval}: {e}",
                exc_info=True
            )
    
    # =========================================================================
    # Synchronization
    # =========================================================================
    
    def _signal_ready_to_coordinator(self):
        """Signal ready to coordinator (mode-aware).
        
        Mode-Aware Behavior:
        - Data-driven (speed=0): Blocking - coordinator waits for ready signal
        - Clock-driven (speed>0 or live): Non-blocking - raises OverrunError if not ready
        
        The coordinator checks if processor is ready before sending next notification.
        In clock-driven mode, if processor isn't ready when data arrives, system
        raises OverrunError to indicate threads can't keep up with speed.
        """
        if not self._coordinator_subscription:
            return
        
        try:
            # Signal ready (coordinator will unblock if waiting)
            self._coordinator_subscription.signal_ready()
            
            logger.debug("Signaled ready to coordinator")
            
        except Exception as e:
            logger.error(
                f"Error signaling ready to coordinator: {e}",
                exc_info=True
            )
    
    # =========================================================================
    # Analysis Engine Notification
    # =========================================================================
    
    def _notify_analysis_engine(self, symbol: str, interval: str):
        """Notify analysis engine that data is available.
        
        Sends lightweight notifications (tuples) to analysis engine queue.
        Analysis engine reads actual data from SessionData (zero-copy).
        
        Args:
            symbol: Symbol with new data
            interval: Interval with new data
        """
        if not self._analysis_engine_queue:
            return
        
        try:
            # Notify about derived bars (if 1m bar triggered generation)
            if interval == "1m" and self._derived_intervals:
                for derived_interval in self._derived_intervals:
                    self._analysis_engine_queue.put(
                        (symbol, f"{derived_interval}m", "bars")
                    )
                    logger.debug(
                        f"Notified analysis engine: {symbol} {derived_interval}m bars"
                    )
            
            # Notify about indicators (if configured)
            if self._realtime_indicators:
                for indicator_name in self._realtime_indicators:
                    self._analysis_engine_queue.put(
                        (symbol, indicator_name, "indicator")
                    )
                    logger.debug(
                        f"Notified analysis engine: {symbol} {indicator_name}"
                    )
            
        except Exception as e:
            logger.error(
                f"Error notifying analysis engine: {e}",
                exc_info=True
            )
    
    # =========================================================================
    # Helpers
    # =========================================================================
    
    def get_processing_stats(self) -> Dict[str, float]:
        """Get processing statistics.
        
        Returns:
            Dictionary with min, max, avg processing times
        """
        if not self._processing_times:
            return {"min": 0.0, "max": 0.0, "avg": 0.0, "count": 0}
        
        return {
            "min": min(self._processing_times),
            "max": max(self._processing_times),
            "avg": sum(self._processing_times) / len(self._processing_times),
            "count": len(self._processing_times)
        }
