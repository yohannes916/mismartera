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

import threading
import queue
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from collections import defaultdict

# Logging
from app.logger import logger

# Phase 1, 2, 3 components
from app.managers.data_manager.session_data import SessionData, get_session_data
from app.threads.sync.stream_subscription import StreamSubscription
from app.monitoring.performance_metrics import PerformanceMetrics
from app.models.session_config import SessionConfig

# Derived bar computation (existing utility)
from app.managers.data_manager.derived_bars import (
    compute_derived_bars,
    compute_all_derived_intervals
)


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
        metrics: PerformanceMetrics,
        indicator_manager=None,
        strategy_manager=None
    ):
        """Initialize data processor.
        
        Args:
            session_data: Reference to SessionData for zero-copy access
            system_manager: Reference to SystemManager (single source of truth)
            metrics: Performance metrics tracker
            indicator_manager: Reference to IndicatorManager (Phase 6)
            strategy_manager: Reference to StrategyManager for strategy notifications
        """
        super().__init__(name="DataProcessor", daemon=True)
        
        self.session_data = session_data
        self._system_manager = system_manager
        self.metrics = metrics
        self.indicator_manager = indicator_manager  # Phase 6
        
        # Get TimeManager reference
        self._time_manager = system_manager.get_time_manager()
        
        # Thread control
        self._stop_event = threading.Event()
        self._running = False
        
        # Notification queue FROM coordinator
        self._notification_queue: queue.Queue[Tuple[str, str, datetime]] = queue.Queue()
        
        # Subscription for signaling ready TO coordinator
        self._coordinator_subscription: Optional[StreamSubscription] = None
        
        # Notification queue TO analysis engine
        self._analysis_engine_queue: Optional[queue.Queue] = None
        
        # Subscription for waiting on analysis engine (Phase 7)
        self._analysis_subscription: Optional[StreamSubscription] = None
        
        # Strategy manager reference (NEW)
        self._strategy_manager = strategy_manager
        
        # Note: Derived intervals now queried from SessionData (no separate tracking)
        # Query session_data.get_symbols_with_derived() to find work
        # Indicator calculation delegated to IndicatorManager (wired during init)
        # Indicators also stored in SessionData.SymbolSessionData.indicators (no separate tracking)
        
        # Auto-computation flag (always enabled for now)
        self._auto_compute_derived = True
        
        # Performance tracking
        self._processing_times = []
        
        # Notification control (Phase 3: Dynamic symbol management)
        self._notifications_paused = threading.Event()
        self._notifications_paused.set()  # Initially NOT paused (active)
        
        logger.info(f"DataProcessor initialized: mode={self.mode}")
    
    # =========================================================================
    # Properties - Single Source of Truth via SystemManager
    # =========================================================================
    
    @property
    def mode(self) -> str:
        """Get operation mode from SystemManager (single source of truth).
        
        Fast O(1) access - SystemManager stores mode as attribute.
        
        Returns:
            'live' or 'backtest'
        """
        return self._system_manager.mode.value
    
    @property
    def session_config(self) -> SessionConfig:
        """Get session config from SystemManager (single source of truth).
        
        Returns:
            SessionConfig instance
        """
        return self._system_manager.session_config
    
    # =========================================================================
    # Public API
    # =========================================================================
    
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
    
    def set_analysis_subscription(self, subscription: StreamSubscription):
        """Set subscription for waiting on analysis engine (data-driven mode).
        
        Args:
            subscription: StreamSubscription for analysis engine sync
        """
        self._analysis_subscription = subscription
        logger.debug("Analysis engine subscription configured")
    
    def pause_notifications(self):
        """Pause AnalysisEngine notifications (during catchup).
        
        Used during dynamic symbol addition to prevent AnalysisEngine from
        seeing intermediate state during catchup phase.
        
        When paused:
        - All calls to _notify_analysis_engine() are dropped (not queued)
        - DataProcessor continues to process data normally
        - Notifications resume after catchup completes
        
        Thread-safe via Event object.
        """
        logger.info("[PROCESSOR] Pausing AnalysisEngine notifications (catchup mode)")
        self._notifications_paused.clear()  # Clear = paused
    
    def resume_notifications(self):
        """Resume AnalysisEngine notifications (after catchup).
        
        Called after dynamic symbol catchup completes to resume normal
        notification flow to AnalysisEngine.
        
        Thread-safe via Event object.
        """
        logger.info("[PROCESSOR] Resuming AnalysisEngine notifications (normal mode)")
        self._notifications_paused.set()  # Set = active
    
    def set_derived_intervals(self, generated_data: Dict[str, List[str]]):
        """DEPRECATED: Derived intervals now queried from SessionData.
        
        This method is kept for backward compatibility but does nothing.
        DataProcessor queries session_data.get_symbols_with_derived() instead.
        
        Args:
            generated_data: Map of symbol -> list of intervals (IGNORED)
        """
        logger.debug(
            "[DEPRECATED] set_derived_intervals() called but ignored. "
            "DataProcessor queries SessionData directly."
        )
    
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
                
                # 4. Notify analysis engine (only if session is active)
                # Check session_active to prevent notifications during lag/catchup
                if self.session_data._session_active:
                    self._notify_analysis_engine(symbol, interval)
                    
                    # In data-driven mode, wait for analysis engine to finish
                    # before signaling ready to coordinator
                    if self._should_wait_for_analysis():
                        logger.debug("[DATA-DRIVEN] Waiting for analysis engine...")
                        if self._analysis_subscription:
                            self._analysis_subscription.wait_until_ready()
                            self._analysis_subscription.reset()
                        logger.debug("[DATA-DRIVEN] Analysis engine ready")
                    
                    # 4b. Notify strategy manager (NEW)
                    self._notify_strategy_manager(symbol, interval)
                    
                    # Wait for strategies in data-driven mode
                    if self._should_wait_for_analysis():
                        logger.debug("[DATA-DRIVEN] Waiting for strategies...")
                        if self._strategy_manager:
                            success = self._strategy_manager.wait_for_strategies(timeout=None)
                            if not success:
                                logger.warning("[DATA-DRIVEN] Strategy timeout")
                        logger.debug("[DATA-DRIVEN] Strategies ready")
                else:
                    logger.debug(
                        f"[PROCESSOR] Skipping notification (session inactive): {symbol} {interval}"
                    )
                
                # 5. Signal ready to coordinator (mode-aware)
                # Only after analysis engine finishes (in data-driven mode)
                self._signal_ready_to_coordinator()
                
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
        if not self._auto_compute_derived:
            return
        
        try:
            # Get symbol data (includes bar structure)
            symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
            if not symbol_data:
                return
            
            # Get derived intervals for this symbol from bar structure
            symbol_intervals = [
                interval for interval, interval_data in symbol_data.bars.items()
                if interval_data.derived
            ]
            
            if not symbol_intervals:
                return
            
            # 1. Read base bars from session_data (ZERO-COPY: direct reference)
            # Use base_interval from symbol data
            base_interval = symbol_data.base_interval
            base_interval_data = symbol_data.bars.get(base_interval)
            
            if not base_interval_data or not base_interval_data.data:
                logger.debug(f"No {base_interval} bars available for {symbol}")
                return
            
            # Convert to list only for processing (small overhead, required for compute_derived_bars)
            bars_base = list(base_interval_data.data)
            
            # 2. Progressive computation: Process intervals in ascending order
            # This ensures we compute 5m as soon as 5 bars exist, 15m when 15 exist, etc.
            # Parse intervals to int for sorting and comparison
            intervals_parsed = []
            for interval_str in symbol_intervals:
                if interval_str.endswith('m'):
                    interval_int = int(interval_str[:-1])
                    intervals_parsed.append(interval_int)
            
            sorted_intervals = sorted(intervals_parsed)
            
            for interval in sorted_intervals:
                # Check if we have enough bars for this interval
                if len(bars_base) < interval:
                    logger.debug(
                        f"Skipping {interval}m bars for {symbol}: "
                        f"only {len(bars_base)} of {interval} {base_interval} bars available"
                    )
                    continue
                
                # 3. Compute derived bars for this interval
                derived_bars = compute_derived_bars(
                    bars_base,
                    source_interval="1m",
                    target_interval=f"{interval}m"
                )
                
                if not derived_bars:
                    continue
                
                # 4. Get existing derived bars from bar structure
                interval_str = f"{interval}m"
                interval_data = symbol_data.bars.get(interval_str)
                
                if not interval_data:
                    logger.warning(f"No interval data for {interval_str} on {symbol}")
                    continue
                
                # 5. Add only new bars (skip duplicates)
                new_bar_count = 0
                for derived_bar in derived_bars:
                    # Check if bar already exists
                    exists = any(
                        bar.timestamp == derived_bar.timestamp
                        for bar in interval_data.data
                    )
                    
                    if not exists:
                        # Append to derived bars (list)
                        interval_data.data.append(derived_bar)
                        new_bar_count += 1
                
                # Set updated flag if new bars were added
                if new_bar_count > 0:
                    interval_data.updated = True
                    logger.debug(
                        f"Generated {new_bar_count} new {interval}m bars for {symbol} "
                        f"(total {len(derived_bars)})"
                    )
                    
                    # Phase 6b: Update indicators for this derived interval
                    if self.indicator_manager:
                        # Get all bars for this interval
                        all_bars = list(interval_data.data)
                        self.indicator_manager.update_indicators(
                            symbol=symbol,
                            interval=interval_str,
                            bars=all_bars
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
        
        This calculates indicators for the BASE interval (e.g., 1m) when new data arrives.
        Indicators for DERIVED intervals (5m, 15m, etc.) are calculated in 
        _generate_derived_bars() after bars are generated.
        
        Real-time indicators include: RSI, SMA, EMA, MACD, Bollinger Bands, VWAP, etc.
        
        Args:
            symbol: Symbol to calculate indicators for
            interval: Interval to calculate indicators for (e.g., "1m", "5m")
        """
        if not self.indicator_manager:
            return
        
        try:
            # Get bars for this interval from session_data
            symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
            if not symbol_data:
                return
            
            # Get the interval data
            interval_data = symbol_data.bars.get(interval)
            if not interval_data or not interval_data.data:
                return
            
            # Get all bars for this interval
            all_bars = list(interval_data.data)
            
            # Update indicators for this interval
            self.indicator_manager.update_indicators(
                symbol=symbol,
                interval=interval,
                bars=all_bars
            )
            
            logger.debug(
                f"{symbol}: Updated indicators for {interval} "
                f"({len(all_bars)} bars)"
            )
            
        except Exception as e:
            logger.error(
                f"Error calculating indicators for {symbol} {interval}: {e}",
                exc_info=True
            )
    
    # =========================================================================
    # Synchronization
    # =========================================================================
    
    def _should_wait_for_analysis(self) -> bool:
        """Determine if we should wait for analysis engine based on mode.
        
        In data-driven mode, we wait for the entire chain:
        Coordinator → Processor → Analysis Engine → (all subscribers)
        
        In clock-driven/live, we don't block - analysis runs async.
        
        Returns:
            True if should wait for analysis engine, False otherwise
        """
        if self.mode == "live":
            return False
        
        if self.mode == "backtest" and self.session_config.backtest_config:
            # Wait only in data-driven mode (speed = 0)
            return self.session_config.backtest_config.speed_multiplier == 0
        
        return False
    
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
        
        Note:
            Notifications are dropped (not queued) when paused during dynamic
            symbol catchup. This prevents AnalysisEngine from seeing intermediate
            state during initialization.
        """
        # Check if notifications are paused (Phase 3: Dynamic symbol management)
        if not self._notifications_paused.is_set():
            logger.debug(
                f"[PROCESSOR] Dropping notification (paused): {symbol} {interval}"
            )
            return  # Drop notification during catchup
        
        if not self._analysis_engine_queue:
            return
        
        try:
            # Notify about derived bars (if base interval bar triggered generation)
            symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
            if symbol_data and interval == symbol_data.base_interval:
                # Get derived intervals for this symbol
                derived_intervals = [
                    iv for iv, iv_data in symbol_data.bars.items()
                    if iv_data.derived
                ]
                
                for derived_interval in derived_intervals:
                    self._analysis_engine_queue.put(
                        (symbol, derived_interval, "bars")
                    )
                    logger.debug(
                        f"Notified analysis engine: {symbol} {derived_interval} bars"
                    )
            
            # Notify about indicators (query from SessionData, no separate tracking)
            symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
            if symbol_data and symbol_data.indicators:
                for indicator_name in symbol_data.indicators.keys():
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
    # Strategy Manager Notification (NEW)
    # =========================================================================
    
    def _notify_strategy_manager(self, symbol: str, interval: str):
        """Notify strategy manager that data is available.
        
        Routes notifications only to strategies subscribed to (symbol, interval).
        Strategies read data from SessionData (zero-copy).
        
        Args:
            symbol: Symbol with new data
            interval: Interval with new data
        """
        # Check if notifications are paused
        if not self._notifications_paused.is_set():
            logger.debug(
                f"[PROCESSOR] Dropping strategy notification (paused): {symbol} {interval}"
            )
            return
        
        if not self._strategy_manager:
            return
        
        try:
            # Get symbol data
            symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
            if not symbol_data:
                return
            
            # Notify about base interval (1m bars)
            if interval == symbol_data.base_interval:
                self._strategy_manager.notify_strategies(symbol, interval, "bars")
                logger.debug(f"Notified strategies: {symbol} {interval}")
            
            # Notify about derived intervals
            if interval == symbol_data.base_interval:
                derived_intervals = [
                    iv for iv, iv_data in symbol_data.bars.items()
                    if iv_data.derived
                ]
                
                for derived_interval in derived_intervals:
                    self._strategy_manager.notify_strategies(
                        symbol, derived_interval, "bars"
                    )
                    logger.debug(
                        f"Notified strategies: {symbol} {derived_interval} (derived)"
                    )
        
        except Exception as e:
            logger.error(
                f"Error notifying strategy manager: {e}",
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
    
    def to_json(self, complete: bool = True) -> dict:
        """Export DataProcessor state to JSON format.
        
        Args:
            complete: If True, return full data. If False, return delta from last export.
                     (Note: Delta mode not yet implemented, returns full data)
        
        Returns:
            Dictionary with thread info and state
        """
        return {
            "thread_info": {
                "name": self.name,
                "is_alive": self.is_alive(),
                "daemon": self.daemon
            },
            "_running": self._running
        }
    
    # =========================================================================
    # Session Lifecycle (Phase 1 & 2 of Revised Flow)
    # =========================================================================
    
    def teardown(self):
        """Reset to initial state and deallocate resources (Phase 1).
        
        Called at START of new session (before data loaded).
        Clears caches, resets flags, prepares for fresh session.
        
        Must be idempotent (safe to call multiple times).
        """
        logger.debug("DataProcessor.teardown() - resetting state")
        
        # Clear notification queue (drain any pending)
        while not self._notification_queue.empty():
            try:
                self._notification_queue.get_nowait()
            except queue.Empty:
                break
        
        # Reset processing times (statistics)
        if hasattr(self, '_processing_times'):
            self._processing_times.clear()
        
        # Clear subscriptions will be rebuilt in setup()
        # Note: Don't stop the thread, just reset state
        
        logger.debug("DataProcessor teardown complete")
    
    def setup(self):
        """Initialize for new session (Phase 2).
        
        Called after data loaded, before session activated.
        Can access SessionData (symbols, bars, indicators).
        
        Allocates resources, registers subscriptions.
        """
        logger.debug("DataProcessor.setup() - initializing for new session")
        
        # Ensure thread is running
        if not self.is_alive():
            logger.warning("DataProcessor thread not running during setup")
        
        # Register subscriptions if needed (placeholder for now)
        # This will be expanded in Phase 7 if needed
        
        logger.debug("DataProcessor setup complete")
