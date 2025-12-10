"""
Data Quality Manager - Non-Blocking Quality Measurement & Gap Filling

This is a NEW COMPONENT for the session architecture (Phase 5).
Extracted from DataUpkeepThread quality/gap management code.

Key Responsibilities:
1. Measure data quality for streamed bars (gap detection, quality scoring)
2. Fill gaps in LIVE mode only (backtest = quality calculation only)
3. Copy quality from base bars to derived bars
4. Non-blocking background operation (doesn't gate other threads)

Architecture Reference: SESSION_ARCHITECTURE.md - Section 3 (Data Quality Manager Thread)

Thread Launch Sequence:
  SystemManager → Session Coordinator + DataProcessor + DataQualityManager → Analysis Engine

Dependencies (Phase 1, 2, 3, 4):
- SessionData (Phase 1.1) - Unified data store (zero-copy access)
- PerformanceMetrics (Phase 1.3) - Monitoring
- SessionConfig (Phase 2.1) - Configuration
- TimeManager (Phase 2.2) - Time/calendar operations
- SessionCoordinator (Phase 3) - Main orchestrator
- DataProcessor (Phase 4) - Derived bars

Key Design:
- Event-driven: Wait on notification queue (NOT periodic polling)
- Non-blocking: Does NOT gate coordinator or processor (best effort)
- No ready signals: Does NOT signal ready to any thread
- Mode-aware: Backtest (quality only) vs Live (quality + gap filling)
- Configuration-controlled: enable_session_quality flag (in gap_filler)
"""

import threading
import queue
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple, Set
from collections import defaultdict

# Logging
from app.logger import logger

# Phase 1, 2, 3, 4 components
from app.managers.data_manager.session_data import SessionData, get_session_data
from app.monitoring.performance_metrics import PerformanceMetrics
from app.models.session_config import SessionConfig

# Quality management utilities
from app.threads.quality import (
    GapInfo,
    detect_gaps,
    merge_overlapping_gaps
)
from app.threads.quality.quality_helpers import (
    parse_interval_to_minutes,
    calculate_quality_for_current_session
)

# Existing infrastructure
from app.models.database import SessionLocal


class DataQualityManager(threading.Thread):
    """Non-blocking background thread for data quality management.
    
    This manager runs in its own thread and performs quality measurement
    and gap filling operations without blocking the coordinator or processor.
    
    Responsibilities:
    1. Detect gaps in streamed bar data
    2. Calculate quality scores (0-100%)
    3. Fill gaps in LIVE mode (query API, store in DB, re-stream)
    4. Copy quality from base bars to derived bars
    
    Non-Blocking Design:
    - Does NOT use StreamSubscription (no ready signals)
    - Does NOT block coordinator or processor
    - Best-effort background updates
    - Quality updates appear in session_data as calculated
    
    Mode-Aware:
    - Backtest: Quality calculation ONLY (gap filling disabled)
    - Live: Quality calculation + gap filling
    
    Configuration (from session_data_config.gap_filler):
    - enable_session_quality: Enable/disable quality calculation
    - max_retries: Maximum gap fill retry attempts (live mode only)
    - retry_interval_seconds: Time between retry attempts (live mode only)
    """
    
    def __init__(
        self,
        session_data: SessionData,
        system_manager,
        metrics: PerformanceMetrics,
        data_manager=None
    ):
        """Initialize data quality manager.
        
        Args:
            session_data: Reference to SessionData for zero-copy access
            system_manager: Reference to SystemManager (single source of truth)
            metrics: Performance metrics tracker
            data_manager: Data manager for gap filling (Parquet fetching)
        """
        super().__init__(name="DataQualityManager", daemon=True)
        
        self.session_data = session_data
        self._system_manager = system_manager
        self.metrics = metrics
        self._data_manager = data_manager
        
        # Get TimeManager reference
        self._time_manager = system_manager.get_time_manager()
        
        # Thread control
        self._stop_event = threading.Event()
        self._running = False
        
        # Notification queue FROM coordinator (tuples: symbol, interval, timestamp)
        self._notification_queue: queue.Queue[Tuple[str, str, datetime]] = queue.Queue()
        
        # Configuration (extract from system_manager.session_config)
        gap_filler_config = system_manager.session_config.session_data_config.gap_filler
        self._enable_quality = gap_filler_config.enable_session_quality
        self._max_retries = gap_filler_config.max_retries
        self._retry_interval_seconds = gap_filler_config.retry_interval_seconds
        
        # Track failed gaps for retry
        self._failed_gaps: Dict[str, List[GapInfo]] = defaultdict(list)
        
        # Track last quality calculation per symbol (for throttling)
        self._last_quality_calc: Dict[str, datetime] = {}
        
        logger.info(
            f"DataQualityManager initialized: mode={self.mode}, "
            f"quality_enabled={self._enable_quality}, "
            f"gap_filling_enabled={self.gap_filling_enabled}, "
            f"max_retries={self._max_retries}"
        )
    
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
    
    @property
    def gap_filling_enabled(self) -> bool:
        """Determine if gap filling is enabled (computed from mode + config).
        
        Gap filling is only enabled in live mode with quality enabled.
        
        Returns:
            True if gap filling should run
        """
        return self.mode == "live" and self._enable_quality
    
    # =========================================================================
    # Public API
    # =========================================================================
    
    def notify_data_available(self, symbol: str, interval: str, timestamp: datetime):
        """Receive notification that new data is available.
        
        Called by session coordinator when new bars arrive.
        
        Args:
            symbol: Symbol with new data
            interval: Interval of new data
            timestamp: Timestamp of new data
        """
        # Only queue notifications for base intervals (streamed data)
        # Derived bars get quality copied from base bars
        if interval in ["1m", "1s", "1d"]:  # Streamed intervals
            self._notification_queue.put((symbol, interval, timestamp))
    
    def run(self):
        """Main thread entry point - starts event-driven processing loop."""
        self._running = True
        logger.info("DataQualityManager thread started")
        
        try:
            self._processing_loop()
        except Exception as e:
            logger.error(f"DataQualityManager thread crashed: {e}", exc_info=True)
        finally:
            self._running = False
            logger.info("DataQualityManager thread stopped")
    
    def stop(self):
        """Signal thread to stop."""
        logger.info("Stopping DataQualityManager...")
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
                logger.warning("DataQualityManager did not stop gracefully")
            else:
                logger.info("DataQualityManager stopped gracefully")
    
    # =========================================================================
    # Main Processing Loop
    # =========================================================================
    
    def _processing_loop(self):
        """Main event-driven processing loop.
        
        Waits for notifications about new data, then processes quality
        in the background without blocking other threads.
        
        Flow:
        1. Wait on notification queue (blocking with timeout)
        2. Calculate quality for symbol
        3. Fill gaps if in live mode
        4. Propagate quality to derived bars
        5. Continue (no ready signals, non-blocking)
        """
        logger.info("Starting event-driven quality management loop")
        
        # Track retry timing
        last_retry_check = self._time_manager.get_current_time()
        
        while not self._stop_event.is_set():
            try:
                # 1. Wait for notification (blocking with timeout for graceful shutdown)
                try:
                    notification = self._notification_queue.get(timeout=1.0)
                except queue.Empty:
                    # Timeout - check for retry opportunities
                    if self.gap_filling_enabled:
                        current_time = self._time_manager.get_current_time()
                        elapsed = (current_time - last_retry_check).total_seconds()
                        
                        if elapsed >= self._retry_interval_seconds:
                            self._retry_failed_gaps()
                            last_retry_check = current_time
                    
                    continue
                
                # Check for stop signal
                if notification is None or self._stop_event.is_set():
                    break
                
                symbol, interval, timestamp = notification
                
                # Skip if quality disabled
                if not self._enable_quality:
                    continue
                
                # 2. Calculate quality for symbol
                self._calculate_quality(symbol, interval)
                
                # 3. Fill gaps (live mode only)
                if self.gap_filling_enabled:
                    self._check_and_fill_gaps(symbol, interval)
                
                # 4. Propagate quality to derived bars
                self._propagate_quality_to_derived(symbol, interval)
                
            except Exception as e:
                logger.error(
                    f"Error processing quality notification: {e}",
                    exc_info=True
                )
        
        logger.info("Quality management loop exited")
    
    # =========================================================================
    # Quality Calculation
    # =========================================================================
    
    def _calculate_quality(self, symbol: str, interval: str):
        """Calculate quality score for CURRENT SESSION bars.
        
        Uses shared quality_helpers to ensure consistency with SessionCoordinator.
        
        CRITICAL Rules:
        - Gets current time from TimeManager (never datetime.now())
        - Gets trading hours from TimeManager (never hardcoded)
        - Only counts regular trading hours (not pre/post market)
        - Caps at market close time (don't count after-hours)
        
        Quality = (actual_bars / expected_bars_so_far) * 100
        
        Args:
            symbol: Symbol to calculate quality for
            interval: Interval to calculate quality for
        """
        try:
            # Get current time from TimeManager (single source of truth)
            current_time = self._time_manager.get_current_time()
            current_date = current_time.date()
        except ValueError:
            # Backtest time not set yet
            logger.debug(f"Cannot calculate quality for {symbol} - time not set")
            return
        
        # Get CURRENT SESSION bars only (not historical)
        # Session coordinator clears bars_base at start of each day, so these are today's bars
        symbol_data = self.session_data.get_symbol_data(symbol)
        if not symbol_data:
            logger.warning(f"No symbol data for {symbol}")
            return
        
        # Get current session bars based on interval
        # V2 structure: symbol_data.bars[interval] contains BarIntervalData
        # with derived flag, base source, and data for each interval
        
        # Get bars using new V2 structure
        interval_data = symbol_data.bars.get(interval)
        if interval_data:
            bars = list(interval_data.data)
        else:
            bars = []
        
        actual_bars = len(bars)
        
        # Calculate quality using shared helper
        # This handles: TimeManager queries, early closes, holidays, all intervals
        with SessionLocal() as db_session:
            quality = calculate_quality_for_current_session(
                time_manager=self._time_manager,
                db_session=db_session,
                symbol=symbol,
                interval=interval,
                current_time=current_time,
                actual_bars=actual_bars
            )
        
        if quality is None:
            logger.debug(f"Cannot calculate quality for {symbol} {interval}")
            return
        
        # Update quality in SessionData
        self.session_data.set_quality(symbol, interval, quality)
        
        # Detect and store gaps (using proper interval parsing)
        with SessionLocal() as db_session:
            trading_session = self._time_manager.get_trading_session(db_session, current_date)
            interval_minutes = parse_interval_to_minutes(interval, trading_session)
        
        if interval_minutes is None:
            logger.warning(f"Cannot parse interval {interval} for gap detection")
            gaps = []
        else:
            # Get trading hours for gap detection
            with SessionLocal() as db_session:
                from app.threads.quality.quality_helpers import get_regular_trading_hours
                hours = get_regular_trading_hours(self._time_manager, db_session, current_date)
            
            if hours:
                session_start_time, session_close_time = hours
                # Cap at close time for gap detection
                effective_end = min(current_time, session_close_time)
                
                gaps = detect_gaps(
                    symbol=symbol,
                    session_start=session_start_time,
                    current_time=effective_end,
                    existing_bars=bars,
                    interval_minutes=interval_minutes
                )
            else:
                gaps = []
        
        # Log quality update with detailed info
        first_bar_time = bars[0].timestamp.strftime('%H:%M') if bars else 'N/A'
        missing_bars = sum(g.bar_count for g in gaps)
        
        # Calculate expected bars for logging
        if hours:
            session_start_time, session_close_time = hours
            effective_end = min(current_time, session_close_time)
            elapsed_seconds = (effective_end - session_start_time).total_seconds()
            elapsed_minutes = elapsed_seconds / 60
            expected_bars = int(elapsed_minutes / interval_minutes) if interval_minutes else 0
        else:
            expected_bars = 0
        
        # Store gaps in SessionData
        self.session_data.set_gaps(symbol, interval, gaps)
        
        logger.info(
            f"{symbol} {interval} quality: {quality:.1f}% | "
            f"actual={actual_bars}, expected={expected_bars}, missing={missing_bars}, "
            f"first_bar={first_bar_time}, gaps={len(gaps)}"
        )
    
    # =========================================================================
    # Gap Filling (Live Mode Only)
    # =========================================================================
    
    def _check_and_fill_gaps(self, symbol: str, interval: str):
        """Detect and fill gaps in bar data.
        
        Only active in live mode.
        
        Args:
            symbol: Symbol to check
            interval: Interval to check
        """
        if not self.gap_filling_enabled:
            return
        
        try:
            # Get current time and session info
            current_time = self._time_manager.get_current_time()
            current_date = current_time.date()
        except ValueError:
            return
        
        # Get trading hours from TimeManager using shared helper
        with SessionLocal() as db_session:
            from app.threads.quality.quality_helpers import get_regular_trading_hours
            hours = get_regular_trading_hours(self._time_manager, db_session, current_date)
        
        if hours is None:
            return
        
        session_start_time, session_close_time = hours
        
        # Cap at close time
        effective_end = min(current_time, session_close_time)
        
        # Parse interval using shared helper
        with SessionLocal() as db_session:
            trading_session = self._time_manager.get_trading_session(db_session, current_date)
            interval_minutes = parse_interval_to_minutes(interval, trading_session)
        
        if interval_minutes is None:
            logger.warning(f"Cannot parse interval {interval} for gap filling")
            return
        
        # Detect gaps
        bars = list(self.session_data.get_bars(symbol, interval))
        gaps = detect_gaps(
            symbol=symbol,
            session_start=session_start_time,
            current_time=effective_end,
            existing_bars=bars,
            interval_minutes=interval_minutes
        )
        
        # Add previously failed gaps for retry
        gap_key = f"{symbol}_{interval}"
        if gap_key in self._failed_gaps:
            gaps.extend(self._failed_gaps[gap_key])
            gaps = merge_overlapping_gaps(gaps)
        
        if not gaps:
            return
        
        # Attempt to fill gaps
        filled_count = 0
        remaining_gaps = []
        
        for gap in gaps:
            if gap.retry_count >= self._max_retries:
                logger.warning(f"Max retries reached for {symbol} {interval}: {gap}")
                continue
            
            # Try to fill this gap
            try:
                count = self._fill_gap(symbol, interval, gap)
                filled_count += count
                
                if count < gap.bar_count:
                    # Partial fill or failure
                    gap.retry_count += 1
                    gap.last_retry = current_time
                    remaining_gaps.append(gap)
            except Exception as e:
                logger.error(f"Error filling gap for {symbol} {interval}: {e}", exc_info=True)
                gap.retry_count += 1
                gap.last_retry = current_time
                remaining_gaps.append(gap)
        
        # Update failed gaps
        self._failed_gaps[gap_key] = remaining_gaps
        
        if filled_count > 0:
            logger.info(f"Filled {filled_count} bars for {symbol} {interval}")
            # Recalculate quality after filling
            self._calculate_quality(symbol, interval)
    
    def _fill_gap(self, symbol: str, interval: str, gap: GapInfo) -> int:
        """Fill a single gap by fetching from Parquet storage.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval
            gap: Gap to fill
        
        Returns:
            Number of bars filled
        """
        if self._data_manager is None:
            logger.debug(f"No data_manager available, skipping gap fill for {symbol}")
            return 0
        
        logger.debug(f"Attempting to fill gap for {symbol} {interval}: {gap}")
        
        try:
            # Fetch bars from Parquet storage via data manager
            from app.managers.data_manager.parquet_storage import parquet_storage
            
            df = parquet_storage.read_bars(
                interval,
                symbol,
                start_date=gap.start_time,
                end_date=gap.end_time
            )
            
            if df.empty:
                logger.debug(f"No bars found in Parquet for {symbol} {interval} gap: {gap}")
                return 0
            
            # Convert DataFrame to BarData and add to SessionData
            from app.models.trading import BarData
            filled_count = 0
            
            for _, row in df.iterrows():
                bar = BarData(
                    symbol=row['symbol'],
                    timestamp=row['timestamp'],
                    open=row['open'],
                    high=row['high'],
                    low=row['low'],
                    close=row['close'],
                    volume=row['volume']
                )
                
                # Add bar to SessionData
                self.session_data.append_bar(symbol, interval, bar)
                filled_count += 1
            
            logger.debug(f"Filled {filled_count}/{gap.bar_count} bars for {symbol} {interval}")
            return filled_count
            
        except Exception as e:
            logger.error(f"Error reading from Parquet: {e}", exc_info=True)
            return 0
    
    def _retry_failed_gaps(self):
        """Retry filling previously failed gaps.
        
        Called periodically based on retry_interval_seconds.
        """
        if not self._failed_gaps:
            return
        
        logger.debug(f"Retrying {sum(len(gaps) for gaps in self._failed_gaps.values())} failed gaps")
        
        # Iterate through all symbols/intervals with failed gaps
        for gap_key, gaps in list(self._failed_gaps.items()):
            if not gaps:
                continue
            
            # Parse gap_key (format: "symbol_interval")
            parts = gap_key.rsplit('_', 1)
            if len(parts) != 2:
                continue
            
            symbol, interval = parts
            
            # Retry each gap
            remaining_gaps = []
            for gap in gaps:
                if gap.retry_count >= self._max_retries:
                    logger.warning(f"Abandoning gap after {self._max_retries} retries: {gap}")
                    continue
                
                # Check if enough time has passed since last retry
                current_time = self._time_manager.get_current_time()
                elapsed = (current_time - gap.last_retry).total_seconds()
                
                if elapsed < self._retry_interval_seconds:
                    # Not time to retry yet
                    remaining_gaps.append(gap)
                    continue
                
                # Attempt to fill
                try:
                    count = self._fill_gap(symbol, interval, gap)
                    
                    if count < gap.bar_count:
                        # Still incomplete
                        gap.retry_count += 1
                        gap.last_retry = current_time
                        remaining_gaps.append(gap)
                    else:
                        logger.info(f"Successfully filled gap on retry #{gap.retry_count}: {gap}")
                        # Recalculate quality
                        self._calculate_quality(symbol, interval)
                except Exception as e:
                    logger.error(f"Error retrying gap fill: {e}", exc_info=True)
                    gap.retry_count += 1
                    gap.last_retry = current_time
                    remaining_gaps.append(gap)
            
            # Update failed gaps for this symbol/interval
            if remaining_gaps:
                self._failed_gaps[gap_key] = remaining_gaps
            else:
                # All gaps resolved
                del self._failed_gaps[gap_key]
    
    # =========================================================================
    # Quality Propagation
    # =========================================================================
    
    def _propagate_quality_to_derived(self, symbol: str, interval: str):
        """Copy quality from base bars to derived bars.
        
        When 1m bar quality changes, copy to 5m, 15m, 30m, etc.
        Discovers derived intervals from session_data (no explicit config needed).
        
        ARCHITECTURE: Both session coordinator (historical) and data quality manager (current session)
        propagate quality from base to derived intervals.
        
        Args:
            symbol: Symbol with updated quality
            interval: Base interval (e.g., "1m")
        """
        # Only propagate from base intervals (1m, 1s, 1d)
        if interval not in ["1m", "1s", "1d"]:
            return
        
        # Get quality for base interval
        base_quality = self.session_data.get_quality_metric(symbol, interval)
        if base_quality is None:
            return
        
        # Get symbol data to discover what derived intervals exist
        symbol_data = self.session_data.get_symbol_data(symbol)
        if not symbol_data:
            return
        
        # Propagate to all derived intervals in V2 bars structure
        if symbol_data.bars:
            for interval_key, interval_data in symbol_data.bars.items():
                # Skip if it's not derived or if it's the same as base or has no data
                if not interval_data.derived or interval_key == interval or not interval_data.data:
                    continue
                
                # Copy base quality to derived interval
                self.session_data.set_quality(
                    symbol,
                    interval_key,
                    base_quality
                )
                
                logger.debug(
                    f"Propagated quality {base_quality:.1f}% from {symbol} {interval} "
                    f"to {interval_key}"
                )
    
    # =========================================================================
    # Helpers
    # =========================================================================
    
    def get_quality_stats(self) -> Dict[str, Any]:
        """Get quality statistics.
        
        Returns:
            Dictionary with quality stats per symbol
        """
        total_failed_gaps = sum(len(gaps) for gaps in self._failed_gaps.values())
        
        # Build per-symbol stats
        symbol_stats = {}
        for gap_key, gaps in self._failed_gaps.items():
            parts = gap_key.rsplit('_', 1)
            if len(parts) == 2:
                symbol, interval = parts
                if symbol not in symbol_stats:
                    symbol_stats[symbol] = {}
                symbol_stats[symbol][interval] = {
                    "failed_gaps": len(gaps),
                    "total_missing_bars": sum(g.bar_count for g in gaps)
                }
        
        return {
            "enabled": self._enable_quality,
            "gap_filling_enabled": self.gap_filling_enabled,
            "mode": self.mode,
            "total_failed_gaps": total_failed_gaps,
            "max_retries": self._max_retries,
            "retry_interval_seconds": self._retry_interval_seconds,
            "symbols": symbol_stats
        }
    
    def to_json(self, complete: bool = True) -> dict:
        """Export DataQualityManager state to JSON format.
        
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
        logger.debug("DataQualityManager.teardown() - resetting state")
        
        # Clear notification queue (drain any pending)
        while not self._notification_queue.empty():
            try:
                self._notification_queue.get_nowait()
            except queue.Empty:
                break
        
        # Clear any cached quality measurements
        # (Quality is recalculated each session, no persistence needed)
        
        # Note: Don't stop the thread, just reset state
        
        logger.debug("DataQualityManager teardown complete")
    
    def setup(self):
        """Initialize for new session (Phase 2).
        
        Called after data loaded, before session activated.
        Can access SessionData (symbols, bars, indicators).
        
        Allocates resources, registers subscriptions.
        """
        logger.debug("DataQualityManager.setup() - initializing for new session")
        
        # Ensure thread is running
        if not self.is_alive():
            logger.warning("DataQualityManager thread not running during setup")
        
        # No special initialization needed currently
        # Quality measurements happen on-demand when notified
        
        logger.debug("DataQualityManager setup complete")
