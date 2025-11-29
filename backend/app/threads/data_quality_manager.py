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
- Configuration-controlled: enable_session_quality flag
"""

import logging
import threading
import queue
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple, Set
from collections import defaultdict

# Phase 1, 2, 3, 4 components
from app.data.session_data import SessionData
from app.monitoring.performance_metrics import PerformanceMetrics
from app.models.session_config import SessionConfig

# Quality management utilities
from app.threads.quality import (
    GapInfo,
    detect_gaps,
    merge_overlapping_gaps
)

# Existing infrastructure
from app.models.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


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
    
    Configuration:
    - enable_session_quality: Enable/disable quality calculation
    - max_retries: Maximum gap fill retry attempts
    - retry_interval_seconds: Time between retry attempts
    """
    
    def __init__(
        self,
        session_data: SessionData,
        system_manager,
        session_config: SessionConfig,
        metrics: PerformanceMetrics,
        data_manager=None
    ):
        """Initialize data quality manager.
        
        Args:
            session_data: Reference to SessionData for zero-copy access
            system_manager: Reference to SystemManager for time/config
            session_config: Session configuration
            metrics: Performance metrics tracker
            data_manager: Data manager for gap filling (Parquet fetching)
        """
        super().__init__(name="DataQualityManager", daemon=True)
        
        self.session_data = session_data
        self._system_manager = system_manager
        self.session_config = session_config
        self.metrics = metrics
        self._data_manager = data_manager
        
        # Get TimeManager reference
        self._time_manager = system_manager.get_time_manager()
        
        # Thread control
        self._stop_event = threading.Event()
        self._running = False
        
        # Notification queue (for event-driven updates)
        self._notification_queue: queue.Queue[Tuple[str, str, datetime]] = queue.Queue()
        
        # Configuration
        gap_filler_config = session_config.session_data_config.gap_filler
        self._enable_session_quality = gap_filler_config.enable_session_quality
        self._max_retries = gap_filler_config.max_retries
        self._retry_interval_seconds = gap_filler_config.retry_interval_seconds
        
        # Mode detection
        self.mode = "backtest" if session_config.backtest_config else "live"
        self._gap_filling_enabled = (
            self.mode == "live" and self._enable_session_quality
        )
        
        # Track failed gaps for retry
        self._failed_gaps: Dict[str, List[GapInfo]] = defaultdict(list)
        
        # Track last quality calculation per symbol (for throttling)
        self._last_quality_calc: Dict[str, datetime] = {}
        
        # Derived intervals (for quality propagation)
        self._derived_intervals = session_config.session_data_config.data_upkeep.derived_intervals
        
        logger.info(
            f"DataQualityManager initialized: mode={self.mode}, "
            f"quality_enabled={self._enable_session_quality}, "
            f"gap_filling_enabled={self._gap_filling_enabled}, "
            f"max_retries={self._max_retries}"
        )
    
    def notify_data_available(self, symbol: str, interval: str, timestamp: datetime):
        """Receive notification that new data is available.
        
        Called by session coordinator when new bars arrive.
        
        Args:
            symbol: Symbol with new data
            interval: Interval with new data
            timestamp: Timestamp of new data
        """
        # Only process streamed bar intervals (not derived)
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
                    if self._gap_filling_enabled:
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
                
                # Skip if session quality disabled
                if not self._enable_session_quality:
                    continue
                
                logger.debug(
                    f"Processing quality for: {symbol} {interval} @ {timestamp.time()}"
                )
                
                # 2. Calculate quality for symbol
                self._calculate_quality(symbol, interval)
                
                # 3. Fill gaps (live mode only)
                if self._gap_filling_enabled:
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
        """Calculate quality score for a symbol/interval.
        
        Quality = (actual_bars / expected_bars) * 100
        
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
        
        # Get trading hours from TimeManager
        from app.models.database import AsyncSessionLocal
        import asyncio
        
        # Run async code in sync context
        async def get_trading_session():
            async with AsyncSessionLocal() as session:
                return await self._time_manager.get_trading_session(session, current_date)
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop in this thread, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        trading_session = loop.run_until_complete(get_trading_session())
        
        if trading_session is None or trading_session.is_holiday:
            # Market closed today (holiday)
            logger.debug(f"Cannot calculate quality for {symbol} - market closed/holiday")
            return
        
        # Get session start time from TradingSession
        session_start_time = trading_session.get_regular_open_datetime()
        if session_start_time is None:
            logger.warning(f"Cannot calculate quality for {symbol} - no session start time")
            return
        
        # Get bars for this symbol/interval (zero-copy)
        bars = list(self.session_data.get_bars(symbol, interval))
        
        # Detect gaps using gap detection module
        gaps = detect_gaps(
            symbol=symbol,
            session_start=session_start_time,
            current_time=current_time,
            existing_bars=bars
        )
        
        # Calculate expected bars based on interval
        interval_minutes = self._parse_interval_minutes(interval)
        elapsed_minutes = int((current_time - session_start_time).total_seconds() / 60)
        
        if elapsed_minutes <= 0:
            quality = 100.0  # Session hasn't started yet
        else:
            # Quality = (actual bars / expected bars) * 100
            expected_bars = elapsed_minutes // interval_minutes
            missing_bars = sum(g.bar_count for g in gaps)
            actual_bars = expected_bars - missing_bars
            
            if expected_bars > 0:
                quality = (actual_bars / expected_bars) * 100.0
            else:
                quality = 100.0
        
        # Update quality in SessionData
        self.session_data.set_quality_metric(symbol, interval, quality)
        
        # Log quality update
        logger.info(
            f"{symbol} {interval} quality: {quality:.1f}% | "
            f"bars={len(bars)}, expected={elapsed_minutes // interval_minutes}, "
            f"gaps={len(gaps)} ({sum(g.bar_count for g in gaps)} missing)"
        )
    
    def _parse_interval_minutes(self, interval: str) -> int:
        """Parse interval string to minutes.
        
        Args:
            interval: Interval string (e.g., "1m", "5m", "1d")
        
        Returns:
            Number of minutes in interval
        """
        if interval.endswith("m"):
            return int(interval[:-1])
        elif interval.endswith("s"):
            # 1s = 1/60 minute, but for quality we still count per minute
            return 1
        elif interval.endswith("d"):
            return 390  # 6.5 hour trading day
        else:
            logger.warning(f"Unknown interval format: {interval}, assuming 1m")
            return 1
    
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
        if not self._gap_filling_enabled:
            return
        
        try:
            # Get current time and session info
            current_time = self._time_manager.get_current_time()
            current_date = current_time.date()
        except ValueError:
            return
        
        # Get trading session from TimeManager
        from app.models.database import AsyncSessionLocal
        import asyncio
        
        async def get_trading_session():
            async with AsyncSessionLocal() as session:
                return await self._time_manager.get_trading_session(session, current_date)
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        trading_session = loop.run_until_complete(get_trading_session())
        
        if trading_session is None or trading_session.is_holiday:
            return
        
        session_start_time = trading_session.get_regular_open_datetime()
        if session_start_time is None:
            return
        
        # Detect gaps
        bars = list(self.session_data.get_bars(symbol, interval))
        gaps = detect_gaps(
            symbol=symbol,
            session_start=session_start_time,
            current_time=current_time,
            existing_bars=bars
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
        
        Args:
            symbol: Symbol with updated quality
            interval: Base interval (e.g., "1m")
        """
        # Only propagate from base intervals (1m, 1s, 1d)
        if interval not in ["1m", "1s", "1d"]:
            return
        
        # Get quality for base interval
        base_quality = self.session_data.get_quality_metric(symbol, interval)
        
        # Propagate to all derived intervals
        if self._derived_intervals:
            for derived_interval in self._derived_intervals:
                derived_interval_str = f"{derived_interval}m"
                
                # Copy base quality to derived interval
                self.session_data.set_quality_metric(
                    symbol,
                    derived_interval_str,
                    base_quality
                )
                
                logger.debug(
                    f"Propagated quality {base_quality:.1f}% from {symbol} {interval} "
                    f"to {derived_interval_str}"
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
            "enabled": self._enable_session_quality,
            "gap_filling_enabled": self._gap_filling_enabled,
            "mode": self.mode,
            "total_failed_gaps": total_failed_gaps,
            "max_retries": self._max_retries,
            "retry_interval_seconds": self._retry_interval_seconds,
            "symbols": symbol_stats
        }
