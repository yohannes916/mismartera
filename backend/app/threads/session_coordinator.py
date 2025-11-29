"""
Session Coordinator - Central orchestrator for session lifecycle

This is a COMPLETE REWRITE for the new session architecture (Phase 3).
Old version backed up to: _backup/backtest_stream_coordinator.py.bak

Key Responsibilities:
1. Historical data loading and updating (EVERY SESSION)
2. Historical indicator calculation (EVERY SESSION)
3. Quality calculation for historical bars (EVERY SESSION)
4. Queue loading (backtest: prefetch_days; live: API streams)
5. Session activation signaling
6. Streaming phase with time advancement
7. End-of-session logic and next day advancement

Architecture Reference: SESSION_ARCHITECTURE.md - Section 3.2 & 3.3

Thread Launch Sequence:
  SystemManager → AnalysisEngine → SessionCoordinator → DataProcessor

Dependencies (Phase 1 & 2):
- SessionData (Phase 1.1) - Unified data store
- StreamSubscription (Phase 1.2) - Thread synchronization
- PerformanceMetrics (Phase 1.3) - Monitoring
- SessionConfig (Phase 2.1) - Configuration
- TimeManager (Phase 2.2) - Time/calendar with caching
"""

import asyncio
import logging
import threading
from datetime import datetime, date, time, timedelta
from typing import Optional, Dict, List, Any, Tuple
from collections import defaultdict

# Phase 1 & 2 components
from app.data.session_data import SessionData
from app.threads.sync.stream_subscription import StreamSubscription
from app.monitoring.performance_metrics import PerformanceMetrics
from app.models.session_config import SessionConfig

# Existing infrastructure
from app.models.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class SessionCoordinator(threading.Thread):
    """Central orchestrator for session lifecycle management.
    
    This coordinator runs in its own thread and manages the complete
    session lifecycle from initialization through historical data management,
    queue loading, streaming, and end-of-session logic.
    
    Lifecycle Phases:
    1. Initialization - Setup for new session
    2. Historical Management - Load/update historical data & indicators
    3. Queue Loading - Load queues with data (backtest) or start streams (live)
    4. Session Activation - Signal session is active
    5. Streaming Phase - Time advancement and data processing
    6. End-of-Session - Cleanup and advance to next day
    
    Thread Safety:
    - Runs in own thread (managed by SystemManager)
    - Uses StreamSubscription for coordination with DataProcessor
    - Thread-safe access to SessionData (read-only from other threads)
    """
    
    def __init__(
        self,
        system_manager,
        data_manager,
        session_config: SessionConfig,
        mode: str = "backtest"
    ):
        """Initialize Session Coordinator.
        
        Args:
            system_manager: Reference to SystemManager
            data_manager: Reference to DataManager
            session_config: Session configuration (Phase 2.1)
            mode: Operation mode ("backtest" or "live")
        """
        super().__init__(name="SessionCoordinator", daemon=True)
        
        # Core dependencies
        self._system_manager = system_manager
        self._data_manager = data_manager
        self._time_manager = system_manager.get_time_manager()
        self.session_config = session_config
        self.mode = mode
        
        # Phase 1 & 2 components (NEW architecture)
        self.session_data = SessionData()
        self.metrics = PerformanceMetrics()
        self.subscriptions: Dict[str, StreamSubscription] = {}
        
        # Phase 4 & 5: DataProcessor and DataQualityManager (wired by SystemManager)
        self.data_processor: Optional[object] = None  # DataProcessor instance
        self.quality_manager: Optional[object] = None  # DataQualityManager instance
        self._processor_subscription: Optional[StreamSubscription] = None  # For coordinator-processor sync
        
        # Thread control
        self._stop_event = threading.Event()
        self._running = False
        
        # Session state
        self._session_active = False
        self._session_start_time: Optional[float] = None
        self._gap_start_time: Optional[float] = None
        self._backtest_complete = False
        
        # Stream/Generate marking (populated during init)
        self._streamed_data: Dict[str, List[str]] = {}  # {symbol: [intervals]}
        self._generated_data: Dict[str, List[str]] = {}  # {symbol: [intervals]}
        
        logger.info(
            f"SessionCoordinator initialized (mode={mode}, "
            f"symbols={len(session_config.session_data_config.symbols)})"
        )
    
    def run(self):
        """Main coordinator loop (runs in own thread).
        
        Lifecycle:
        1. Start backtest (set metrics timer)
        2. Loop until complete:
           a. Initialize session
           b. Manage historical data & indicators
           c. Load queues
           d. Activate session
           e. Streaming phase
           f. End session
        3. End backtest (record metrics)
        """
        self._running = True
        logger.info("SessionCoordinator thread started")
        
        try:
            # Start backtest timing
            self.metrics.start_backtest()
            
            # Main coordinator loop
            asyncio.run(self._coordinator_loop())
            
            # End backtest timing
            self.metrics.end_backtest()
            
            # Log final report
            report = self.metrics.format_report('backtest')
            logger.info(f"\n{report}")
            
        except Exception as e:
            logger.error(f"SessionCoordinator error: {e}", exc_info=True)
        finally:
            self._running = False
            logger.info("SessionCoordinator thread stopped")
    
    async def _coordinator_loop(self):
        """Main coordinator loop with all lifecycle phases.
        
        This is the heart of the session coordinator. Each iteration
        represents one trading session (day in backtest, continuous in live).
        """
        while not self._stop_event.is_set():
            try:
                # Phase 1: Initialization
                logger.info("=" * 70)
                logger.info("Phase 1: Initialization")
                await self._initialize_session()
                
                # Phase 2: Historical Management
                logger.info("Phase 2: Historical Management")
                gap_start = self.metrics.start_timer()
                await self._manage_historical_data()
                await self._calculate_historical_indicators()
                self._calculate_historical_quality()
                self.metrics.record_session_gap(gap_start)
                
                # Phase 3: Queue Loading
                logger.info("Phase 3: Queue Loading")
                await self._load_queues()
                
                # Phase 4: Session Activation
                logger.info("Phase 4: Session Activation")
                self._activate_session()
                
                # Phase 5: Streaming Phase
                logger.info("Phase 5: Streaming Phase")
                await self._streaming_phase()
                
                # Phase 6: End-of-Session
                logger.info("Phase 6: End-of-Session")
                await self._end_session()
                
                # Check termination
                if self._should_terminate():
                    logger.info("Backtest complete, terminating coordinator")
                    break
                
            except Exception as e:
                logger.error(f"Error in coordinator loop: {e}", exc_info=True)
                break
    
    def stop(self):
        """Stop the coordinator thread gracefully."""
        logger.info("Stopping SessionCoordinator...")
        self._stop_event.set()
    
    # =========================================================================
    # Phase 1: Initialization
    # =========================================================================
    
    async def _initialize_session(self):
        """Initialize session (called at start of each session).
        
        Tasks:
        - Mark stream/generate data types (first time only)
        - Reset session state
        - Log session info
        """
        # Mark stream/generate on first session only
        if not self._streamed_data:
            self._mark_stream_generate()
        
        # Reset session state
        self._session_active = False
        self._session_start_time = None
        
        # Get current session date
        current_time = self._time_manager.get_current_time()
        current_date = current_time.date()
        
        # Log session info
        logger.info(f"Initializing session for {current_date}")
        logger.info(
            f"Streamed data: {sum(len(v) for v in self._streamed_data.values())} streams, "
            f"Generated data: {sum(len(v) for v in self._generated_data.values())} types"
        )
        
        logger.info("Session initialization complete")
    
    # =========================================================================
    # Phase 2: Historical Management
    # =========================================================================
    
    async def _manage_historical_data(self):
        """Manage historical data before session starts.
        
        Tasks:
        - Load historical bars (trailing days)
        - Calculate historical indicators
        - Calculate quality scores
        
        Reference: SESSION_ARCHITECTURE.md lines 1650-1655
        """
        logger.info("Managing historical data")
        
        # Start timing for historical data management
        start_time = self.metrics.start_timer()
        
        # Load historical data configuration
        historical_config = self.session_config.session_data_config.historical
        
        if not historical_config.data:
            logger.info("No historical data configured, skipping")
            return
        
        # Get current session date
        current_time = self._time_manager.get_current_time()
        current_date = current_time.date()
        
        logger.info(f"Loading historical data for session {current_date}")
        
        # Clear existing historical data and reload fresh
        # (Simple approach: full reload each session ensures data consistency)
        self.session_data.clear_historical_bars()
        
        # Process each historical data configuration
        for hist_data_config in historical_config.data:
            await self._load_historical_data_config(
                hist_data_config,
                current_date
            )
        
        # Log statistics
        total_bars = sum(
            len(bars)
            for symbol_data in self.session_data._bars.values()
            for bars in symbol_data.values()
        )
        
        # Record timing
        elapsed = self.metrics.elapsed_time(start_time)
        logger.info(
            f"Historical data loaded: {total_bars} total bars across "
            f"{len(historical_config.data)} configs ({elapsed:.3f}s)"
        )
    
    async def _calculate_historical_indicators(self):
        """Calculate all historical indicators before EVERY session.
        
        Tasks:
        - For each indicator in config:
          - Calculate based on type (trailing_average, trailing_max, trailing_min)
          - Store in session_data with indexed access
        
        Reference: SESSION_ARCHITECTURE.md lines 380-440
        """
        indicators = self.session_config.session_data_config.historical.indicators
        
        if not indicators:
            logger.info("No historical indicators configured, skipping")
            return
        
        start_time = self.metrics.start_timer()
        logger.info(f"Calculating {len(indicators)} historical indicators")
        
        for indicator_name, indicator_config in indicators.items():
            try:
                indicator_type = indicator_config['type']
                
                if indicator_type == 'trailing_average':
                    result = await self._calculate_trailing_average(
                        indicator_name,
                        indicator_config
                    )
                elif indicator_type == 'trailing_max':
                    result = await self._calculate_trailing_max(
                        indicator_name,
                        indicator_config
                    )
                elif indicator_type == 'trailing_min':
                    result = await self._calculate_trailing_min(
                        indicator_name,
                        indicator_config
                    )
                else:
                    logger.error(
                        f"Unknown indicator type '{indicator_type}' for {indicator_name}"
                    )
                    continue
                
                # Store in session_data with indexed access
                self.session_data.set_historical_indicator(indicator_name, result)
                
                logger.debug(
                    f"Calculated indicator '{indicator_name}' (type={indicator_type})"
                )
                
            except Exception as e:
                logger.error(
                    f"Error calculating indicator '{indicator_name}': {e}",
                    exc_info=True
                )
        
        elapsed = self.metrics.elapsed_time(start_time)
        logger.info(f"Historical indicators calculated ({elapsed:.3f}s)")
    
    def _calculate_historical_quality(self):
        """Calculate quality scores for historical bars.
        
        Tasks:
        - Check historical.enable_quality config
        - If disabled: Assign 100% quality to all historical bars
        - If enabled: Calculate actual quality (gap detection)
        
        Quality Score:
        - 100% = No gaps, perfect data
        - 0% = All data missing
        - Between = Percentage of expected bars present
        """
        enable_quality = self.session_config.session_data_config.historical.enable_quality
        
        if not enable_quality:
            # Disabled: Assign 100% quality to all bars
            logger.info("Quality calculation disabled, assigning 100% to all historical bars")
            self._assign_perfect_quality()
            return
        
        # Enabled: Calculate actual quality with gap detection
        logger.info("Calculating historical bar quality with gap detection")
        start_time = self.metrics.start_timer()
        
        total_symbols = 0
        total_quality = 0.0
        
        # Calculate quality for each symbol/interval
        for symbol in self.session_config.session_data_config.symbols:
            for interval in ["1m", "5m", "15m", "30m", "1h", "1d"]:
                quality = self._calculate_bar_quality(symbol, interval)
                
                if quality is not None:
                    total_symbols += 1
                    total_quality += quality
                    
                    logger.debug(
                        f"{symbol} {interval} quality: {quality:.1f}%"
                    )
        
        # Log summary
        if total_symbols > 0:
            avg_quality = total_quality / total_symbols
            elapsed = self.metrics.elapsed_time(start_time)
            logger.info(
                f"Historical quality calculated: {avg_quality:.1f}% average "
                f"across {total_symbols} symbol/interval pairs ({elapsed:.3f}s)"
            )
        else:
            logger.info("No historical bars found for quality calculation")
    
    def _assign_perfect_quality(self):
        """Assign 100% quality to all historical bars (when quality disabled)."""
        # Set quality to 100% for all symbols/intervals in session_data
        for symbol in self.session_config.session_data_config.symbols:
            for interval in ["1m", "5m", "15m", "30m", "1h", "1d"]:
                # TODO: SessionData API for setting quality
                # self.session_data.set_quality(symbol, interval, 100.0)
                pass
        
        logger.debug("Assigned 100% quality to all historical bars")
    
    def _calculate_bar_quality(self, symbol: str, interval: str) -> Optional[float]:
        """Calculate quality score for a symbol/interval.
        
        Quality = (actual_bars / expected_bars) * 100
        
        Args:
            symbol: Symbol to check
            interval: Interval to check
        
        Returns:
            Quality percentage (0-100) or None if no data
        """
        # TODO: Get bars from SessionData
        # bars = self.session_data.get_bars(symbol, interval)
        # if not bars:
        #     return None
        
        # TODO: Calculate expected bars based on interval and time range
        # For now, return placeholder
        # expected_bars = self._calculate_expected_bars(interval, start_date, end_date)
        # actual_bars = len(bars)
        # 
        # # Check for gaps
        # gaps = self._detect_gaps(bars, interval)
        # 
        # # Quality = (actual - gaps) / expected * 100
        # quality = ((actual_bars - gaps) / expected_bars) * 100 if expected_bars > 0 else 100.0
        # 
        # # Store quality in SessionData
        # self.session_data.set_quality(symbol, interval, quality)
        # 
        # return quality
        
        return None  # Placeholder until SessionData API ready
    
    def _detect_gaps(self, bars: List, interval: str) -> int:
        """Detect gaps in bar data.
        
        A gap is when consecutive bars are not exactly interval apart.
        
        Args:
            bars: List of bars (sorted by timestamp)
            interval: Bar interval (1m, 5m, etc.)
        
        Returns:
            Number of missing bars (gaps)
        """
        if len(bars) < 2:
            return 0
        
        # Parse interval to timedelta
        interval_td = self._parse_interval_to_timedelta(interval)
        if interval_td is None:
            return 0
        
        gaps = 0
        for i in range(1, len(bars)):
            prev_bar = bars[i - 1]
            curr_bar = bars[i]
            
            # Expected timestamp
            expected_ts = prev_bar.timestamp + interval_td
            
            # If current bar is later than expected, we have gap(s)
            if curr_bar.timestamp > expected_ts:
                # Calculate how many bars are missing
                time_diff = curr_bar.timestamp - expected_ts
                missing_bars = int(time_diff / interval_td)
                gaps += missing_bars
        
        return gaps
    
    def _parse_interval_to_timedelta(self, interval: str):
        """Parse interval string to timedelta.
        
        Args:
            interval: Interval string (1m, 5m, 1h, 1d)
        
        Returns:
            timedelta or None if invalid
        """
        from datetime import timedelta
        
        interval = interval.lower().strip()
        
        if interval.endswith('m'):
            # Minutes
            minutes = int(interval[:-1])
            return timedelta(minutes=minutes)
        elif interval.endswith('h'):
            # Hours
            hours = int(interval[:-1])
            return timedelta(hours=hours)
        elif interval.endswith('d'):
            # Days
            days = int(interval[:-1])
            return timedelta(days=days)
        else:
            logger.error(f"Invalid interval format: {interval}")
            return None
    
    # =========================================================================
    # Phase 3: Queue Loading
    # =========================================================================
    
    async def _load_queues(self):
        """Load queues with data for streaming phase.
        
        Backtest: Load prefetch_days of data into queues
        Live: Start API streams
        
        Uses stream/generate marking from _mark_stream_generate() to know
        what data to load vs what will be generated by data_processor.
        """
        start_time = self.metrics.start_timer()
        
        if self.mode == "backtest":
            await self._load_backtest_queues()
        else:  # live mode
            await self._start_live_streams()
        
        elapsed = self.metrics.elapsed_time(start_time)
        logger.info(f"Queues loaded ({elapsed:.3f}s)")
    
    # =========================================================================
    # Phase 4: Session Activation
    # =========================================================================
    
    def _activate_session(self):
        """Signal session is active and ready for streaming."""
        self._session_active = True
        self._session_start_time = self.metrics.start_timer()
        self.session_data.set_session_active(True)
        logger.info("Session activated")
    
    # =========================================================================
    # Phase 5: Streaming Phase
    # =========================================================================
    
    async def _streaming_phase(self):
        """Main streaming loop with time advancement.
        
        This is the most complex phase. Handles:
        - Time advancement based on next queue data
        - End-of-session detection
        - Data-driven and clock-driven modes
        - Multiple symbol interleaving
        
        Reference: SESSION_ARCHITECTURE.md lines 1656-1662
        
        CRITICAL RULES:
        1. Time must stay within trading hours: open_time <= time <= close_time
        2. Never exceed market_close (if time > close, it's an error)
        3. Data exhaustion: advance to market_close
        4. Support data-driven (speed=0) and clock-driven (speed>0)
        """
        # Get trading session for today
        current_time = self._time_manager.get_current_time()
        current_date = current_time.date()
        
        async with AsyncSessionLocal() as session:
            trading_session = await self._time_manager.get_trading_session(
                session,
                current_date,
                exchange=self.session_config.exchange_group
            )
        
        if not trading_session or trading_session.is_holiday:
            logger.warning(f"No trading session for {current_date}, skipping streaming")
            return
        
        # Get market hours
        market_open = datetime.combine(
            current_date,
            trading_session.regular_open
        )
        market_close = datetime.combine(
            current_date,
            trading_session.regular_close
        )
        
        logger.info(
            f"Streaming phase: {market_open.time()} to {market_close.time()}"
        )
        
        # Streaming loop
        iteration = 0
        total_bars_processed = 0
        
        while not self._stop_event.is_set():
            iteration += 1
            current_time = self._time_manager.get_current_time()
            
            # CRITICAL CHECK: End-of-session detection
            if current_time >= market_close:
                logger.info(
                    f"Market close reached ({current_time.time()} >= "
                    f"{market_close.time()}), ending session"
                )
                break
            
            # CRITICAL CHECK: Time must not exceed market close
            if current_time > market_close:
                logger.error(
                    f"CRITICAL ERROR: Time {current_time} exceeds market close "
                    f"{market_close}! This should never happen in backtest."
                )
                raise RuntimeError(
                    f"Time exceeded market close: {current_time} > {market_close}"
                )
            
            # Get next data timestamp from queues
            next_timestamp = await self._get_next_queue_timestamp()
            
            if next_timestamp is None:
                # No more data - advance to market close and end
                logger.info("No more data in queues, advancing to market close")
                self._time_manager.set_backtest_time(market_close)
                break
            
            # Check if next data is beyond market close
            if next_timestamp > market_close:
                # Advance to market close and end
                logger.info(
                    f"Next data ({next_timestamp.time()}) beyond market close "
                    f"({market_close.time()}), advancing to close"
                )
                self._time_manager.set_backtest_time(market_close)
                break
            
            # Advance time to next data timestamp
            logger.debug(
                f"[{iteration}] Advancing time: {current_time.time()} -> "
                f"{next_timestamp.time()}"
            )
            self._time_manager.set_backtest_time(next_timestamp)
            
            # Process data at this timestamp
            bars_processed = await self._process_queue_data_at_timestamp(
                next_timestamp
            )
            total_bars_processed += bars_processed
            
            if bars_processed > 0:
                logger.debug(f"Processed {bars_processed} bars at {next_timestamp.time()}")
            
            # Clock-driven delay (if speed_multiplier > 0)
            if self.mode == "backtest" and self.session_config.backtest_config:
                speed_multiplier = self.session_config.backtest_config.speed_multiplier
                if speed_multiplier > 0:
                    await self._apply_clock_driven_delay(speed_multiplier)
            
            # Periodic logging (every 100 iterations)
            if iteration % 100 == 0:
                current_time = self._time_manager.get_current_time()
                logger.info(
                    f"Streaming iteration {iteration}: {current_time.time()}"
                )
        
        # Final time check and metrics
        final_time = self._time_manager.get_current_time()
        logger.info(
            f"Streaming phase complete: {iteration} iterations, "
            f"{total_bars_processed} bars processed, "
            f"final time = {final_time.time()}"
        )
        
        # Record streaming metrics
        self.metrics.increment_bars_processed(total_bars_processed)
        self.metrics.increment_iterations(iteration)
    
    # =========================================================================
    # Phase 6: End-of-Session
    # =========================================================================
    
    async def _end_session(self):
        """End current session and prepare for next.
        
        Tasks:
        - Deactivate session
        - Record metrics
        - Clear session data (keep historical)
        - Advance to next trading day
        
        Reference: SESSION_ARCHITECTURE.md lines 1663-1666
        """
        # 1. Deactivate session
        self._session_active = False
        self.session_data.set_session_active(False)
        logger.info("Session deactivated")
        
        # 2. Record session metrics
        if self._session_start_time is not None:
            self.metrics.record_session_duration(self._session_start_time)
            logger.debug("Session duration recorded")
        
        # 3. Increment trading days counter
        self.metrics.increment_trading_days()
        
        # 4. Clear session bars (keep historical data for next session)
        self.session_data.clear_session_bars()
        logger.debug("Session bars cleared")
        
        # 5. Get current session date
        current_time = self._time_manager.get_current_time()
        current_date = current_time.date()
        
        logger.info(f"Session {current_date} ended")
        
        # 6. Advance to next trading day (if in backtest mode)
        if self.mode == "backtest":
            await self._advance_to_next_trading_day(current_date)
        else:
            # Live mode: just wait for next day (handled by system)
            logger.info("Live mode: waiting for next trading day")
    
    async def _advance_to_next_trading_day(self, current_date: date):
        """Advance time to next trading day's market open.
        
        Args:
            current_date: Current session date
        """
        # Find next trading date
        async with AsyncSessionLocal() as session:
            next_date = await self._time_manager.get_next_trading_date(
                session,
                current_date,
                n=1,
                exchange=self.session_config.exchange_group
            )
        
        if next_date is None:
            # No more trading days - backtest complete
            logger.info("No more trading days, backtest complete")
            self._backtest_complete = True
            return
        
        # Check if we've exceeded backtest end date
        from datetime import datetime
        end_date = datetime.strptime(
            self.session_config.backtest_config.end_date,
            "%Y-%m-%d"
        ).date()
        
        if next_date > end_date:
            logger.info(
                f"Next trading date {next_date} exceeds backtest end {end_date}, "
                "backtest complete"
            )
            self._backtest_complete = True
            return
        
        # Get next session's market open time
        async with AsyncSessionLocal() as session:
            next_session = await self._time_manager.get_trading_session(
                session,
                next_date,
                exchange=self.session_config.exchange_group
            )
        
        if not next_session or next_session.is_holiday:
            logger.warning(
                f"Next date {next_date} is not a trading day, searching further"
            )
            # Recursively find next valid trading day
            await self._advance_to_next_trading_day(next_date)
            return
        
        # Set time to market open of next day
        next_open = datetime.combine(
            next_date,
            next_session.regular_open
        )
        
        self._time_manager.set_backtest_time(next_open)
        
        logger.info(
            f"Advanced to next trading day: {next_date} at {next_open.time()}"
        )
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _should_terminate(self) -> bool:
        """Check if coordinator should terminate.
        
        Returns:
            True if backtest complete or stop requested
        """
        # Check stop event
        if self._stop_event.is_set():
            logger.info("Stop event set, terminating")
            return True
        
        # Check backtest completion
        if self.mode == "backtest" and self._backtest_complete:
            logger.info("Backtest complete, terminating")
            return True
        
        # Check if we've exceeded end date
        if self.mode == "backtest" and self.session_config.backtest_config:
            current_time = self._time_manager.get_current_time()
            current_date = current_time.date()
            
            from datetime import datetime
            end_date = datetime.strptime(
                self.session_config.backtest_config.end_date,
                "%Y-%m-%d"
            ).date()
            
            if current_date > end_date:
                logger.info(
                    f"Current date {current_date} exceeds backtest end {end_date}, "
                    "terminating"
                )
                return True
        
        return False
    
    def get_session_data(self) -> SessionData:
        """Get reference to session data (for Analysis Engine access).
        
        Returns:
            SessionData instance (thread-safe for reads)
        """
        return self.session_data
    
    def get_metrics(self) -> PerformanceMetrics:
        """Get reference to performance metrics.
        
        Returns:
            PerformanceMetrics instance
        """
        return self.metrics
    
    def is_session_active(self) -> bool:
        """Check if session is currently active.
        
        Returns:
            True if streaming phase is active
        """
        return self._session_active
    
    # =========================================================================
    # Phase 4 & 5 Integration: DataProcessor and DataQualityManager
    # =========================================================================
    
    def set_data_processor(self, processor, subscription: StreamSubscription):
        """Set data processor and subscription (called by SystemManager).
        
        Args:
            processor: DataProcessor instance
            subscription: StreamSubscription for coordinator-processor sync
        """
        self.data_processor = processor
        self._processor_subscription = subscription
        logger.info("Data processor wired to coordinator")
    
    def set_quality_manager(self, quality_manager):
        """Set quality manager (called by SystemManager).
        
        Args:
            quality_manager: DataQualityManager instance
        """
        self.quality_manager = quality_manager
        logger.info("Quality manager wired to coordinator")
    
    def _mark_stream_generate(self):
        """Mark which data types are STREAMED vs GENERATED vs IGNORED.
        
        Called once at startup. Determines for each symbol/stream:
        - STREAMED: Data comes from coordinator (queues or API)
        - GENERATED: Data computed by data_processor
        - IGNORED: Not available, not generated
        
        Rules (SESSION_ARCHITECTURE.md lines 196-208):
        
        Backtest Mode:
        - Stream ONLY smallest available interval per symbol (1s > 1m > 1d)
        - Stream quotes if available in database
        - NEVER stream ticks (ignored)
        - Generate all derivatives (5m, 10m, 15m, etc.)
        
        Live Mode:
        - Stream whatever API provides
        - Generate what's not available from API
        """
        symbols = self.session_config.session_data_config.symbols
        streams = self.session_config.session_data_config.streams
        
        logger.info(f"Marking stream/generate for {len(symbols)} symbols, {len(streams)} streams")
        
        if self.mode == "backtest":
            self._mark_backtest_streams(symbols, streams)
        else:  # live mode
            self._mark_live_streams(symbols, streams)
        
        # Log results
        total_streamed = sum(len(v) for v in self._streamed_data.values())
        total_generated = sum(len(v) for v in self._generated_data.values())
        logger.info(f"Marked {total_streamed} STREAMED, {total_generated} GENERATED")
        logger.debug(f"Streamed: {dict(self._streamed_data)}")
        logger.debug(f"Generated: {dict(self._generated_data)}")
    
    def _mark_backtest_streams(self, symbols: List[str], streams: List[str]):
        """Mark streams for backtest mode.
        
        Args:
            symbols: List of symbols
            streams: List of requested streams
        """
        # Separate bar intervals from other types
        bar_intervals = []
        has_quotes = False
        has_ticks = False
        
        for stream in streams:
            if stream == "quotes":
                has_quotes = True
            elif stream == "ticks":
                has_ticks = True
            else:
                # It's a bar interval (1s, 1m, 5m, etc.)
                bar_intervals.append(stream)
        
        # For each symbol
        for symbol in symbols:
            self._streamed_data[symbol] = []
            self._generated_data[symbol] = []
            
            # Determine smallest interval to stream (1s > 1m > 1d)
            if bar_intervals:
                # Priority order
                priority = ["1s", "1m", "1d"]
                smallest = None
                for interval in priority:
                    if interval in bar_intervals:
                        smallest = interval
                        break
                
                if smallest:
                    # Stream smallest
                    self._streamed_data[symbol].append(smallest)
                    
                    # Generate all others
                    for interval in bar_intervals:
                        if interval != smallest:
                            self._generated_data[symbol].append(interval)
            
            # Quotes: stream if requested (we'll check availability later)
            if has_quotes:
                self._streamed_data[symbol].append("quotes")
            
            # Ticks: IGNORED in backtest (no action needed)
            if has_ticks:
                logger.debug(f"{symbol}: ticks IGNORED in backtest mode")
    
    def _mark_live_streams(self, symbols: List[str], streams: List[str]):
        """Mark streams for live mode.
        
        In live mode, we stream whatever the API provides.
        For now, assume API can provide all requested streams.
        TODO: Check API capabilities and mark accordingly.
        
        Args:
            symbols: List of symbols
            streams: List of requested streams
        """
        for symbol in symbols:
            # In live mode, initially mark all as streamed
            # (DataManager will handle what's actually available)
            self._streamed_data[symbol] = streams.copy()
            self._generated_data[symbol] = []
            
            logger.debug(
                f"{symbol}: All streams marked as STREAMED in live mode "
                "(API capabilities check TODO)"
            )
    
    async def _load_historical_data_config(
        self,
        hist_config,
        current_date: date
    ):
        """Load historical data for one configuration.
        
        Args:
            hist_config: HistoricalDataConfig instance
            current_date: Current session date
        """
        trailing_days = hist_config.trailing_days
        intervals = hist_config.intervals
        symbols = self._resolve_symbols(hist_config.apply_to)
        
        logger.info(
            f"Loading {trailing_days} days of {intervals} for "
            f"{len(symbols)} symbols"
        )
        
        # Calculate date range
        # End date is yesterday (we don't include current day in historical)
        end_date = current_date - timedelta(days=1)
        
        # Start date: count back trailing_days of TRADING days
        start_date = await self._get_start_date_for_trailing_days(
            end_date,
            trailing_days
        )
        
        if start_date is None:
            logger.warning(
                f"Could not calculate start date for {trailing_days} trading days, "
                "skipping historical data load"
            )
            return
        
        logger.debug(
            f"Historical date range: {start_date} to {end_date} "
            f"({trailing_days} trading days)"
        )
        
        # Load bars for each symbol and interval
        for symbol in symbols:
            for interval in intervals:
                bars = await self._load_historical_bars(
                    symbol,
                    interval,
                    start_date,
                    end_date
                )
                
                # Store in session_data
                for bar in bars:
                    self.session_data.append_bar(symbol, interval, bar)
                
                logger.debug(
                    f"Loaded {len(bars)} {interval} bars for {symbol} "
                    f"({start_date} to {end_date})"
                )
    
    def _resolve_symbols(self, apply_to) -> List[str]:
        """Resolve 'all' or specific symbol list.
        
        Args:
            apply_to: Either "all" or list of symbols
        
        Returns:
            List of symbols to apply to
        """
        if isinstance(apply_to, str) and apply_to == "all":
            return self.session_config.session_data_config.symbols
        elif isinstance(apply_to, list):
            return apply_to
        else:
            logger.warning(
                f"Invalid apply_to value: {apply_to}, defaulting to all symbols"
            )
            return self.session_config.session_data_config.symbols
    
    async def _get_start_date_for_trailing_days(
        self,
        end_date: date,
        trailing_days: int
    ) -> Optional[date]:
        """Calculate start date for trailing window.
        
        Counts back trailing_days TRADING days from end_date.
        Uses TimeManager to skip weekends and holidays.
        
        Args:
            end_date: End date (inclusive)
            trailing_days: Number of trading days to include
        
        Returns:
            Start date (inclusive) or None if calculation fails
        """
        if trailing_days <= 0:
            logger.error(f"Invalid trailing_days: {trailing_days}")
            return None
        
        # If we want N trading days, we need to go back N-1 days
        # (end_date is day 1, so we need N-1 more days before it)
        days_to_go_back = trailing_days - 1
        
        if days_to_go_back == 0:
            # Single day: start = end
            return end_date
        
        # Use TimeManager to count back trading days
        async with AsyncSessionLocal() as session:
            start_date = await self._time_manager.get_previous_trading_date(
                session,
                end_date,
                n=days_to_go_back,
                exchange=self.session_config.exchange_group
            )
        
        if start_date is None:
            logger.error(
                f"Could not find trading date {days_to_go_back} days "
                f"before {end_date}"
            )
            return None
        
        logger.debug(
            f"Trailing window: {trailing_days} days = "
            f"{start_date} to {end_date}"
        )
        
        return start_date
    
    async def _load_historical_bars(self,
        symbol: str,
        interval: str,
        start_date: date,
        end_date: date
    ) -> List[Any]:
        """Load historical bars from database.
        
        Args:
            symbol: Symbol to load
            interval: Bar interval (e.g., "1m", "5m", "1d")
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
        
        Returns:
            List of bar objects (from DataManager)
        """
        try:
            # Query via DataManager
            # TODO: DataManager API for historical bar loading
            # For now, return empty list (will implement when DataManager ready)
            logger.debug(
                f"Loading {symbol} {interval} bars from {start_date} to {end_date} "
                "(DataManager API TODO)"
            )
            
            # Placeholder: Return empty list
            # In real implementation:
            # bars = await self._data_manager.get_historical_bars(
            #     symbol, interval, start_date, end_date
            # )
            bars = []
            
            return bars
            
        except Exception as e:
            logger.error(
                f"Error loading {symbol} {interval} bars: {e}",
                exc_info=True
            )
            return []
    
    # =========================================================================
    # Historical Indicator Calculation
    # =========================================================================
    
    async def _calculate_trailing_average(
        self,
        indicator_name: str,
        config: Dict[str, Any]
    ) -> Any:
        """Calculate trailing average indicator.
        
        Supports two granularities:
        - Daily: Single value (average over N trading days)
        - Minute: Array of 390 values (average for each minute)
        
        Args:
            indicator_name: Name of indicator
            config: Indicator configuration
        
        Returns:
            Single value (daily) or list of 390 values (minute)
        """
        period = config['period']
        granularity = config['granularity']
        field = config['field']
        skip_early_close = config.get('skip_early_close', False)
        
        # Parse period (e.g., "10d" -> 10 days)
        period_days = self._parse_period_to_days(period)
        
        logger.debug(
            f"Calculating {indicator_name}: {field} avg over {period} "
            f"({granularity} granularity)"
        )
        
        if granularity == 'daily':
            # Daily: one value per day, return average
            result = await self._calculate_daily_average(
                field, period_days, skip_early_close
            )
        elif granularity == 'minute':
            # Minute: average for each minute of trading day
            result = await self._calculate_intraday_average(
                field, period_days
            )
        else:
            raise ValueError(f"Unknown granularity: {granularity}")
        
        return result
    
    async def _calculate_trailing_max(
        self,
        indicator_name: str,
        config: Dict[str, Any]
    ) -> float:
        """Calculate trailing maximum value.
        
        Args:
            indicator_name: Name of indicator
            config: Indicator configuration
        
        Returns:
            Maximum value over period
        """
        period = config['period']
        field = config['field']
        
        period_days = self._parse_period_to_days(period)
        
        logger.debug(
            f"Calculating {indicator_name}: max {field} over {period}"
        )
        
        # Get all bars for the period
        max_value = await self._calculate_field_max(field, period_days)
        
        return max_value
    
    async def _calculate_trailing_min(
        self,
        indicator_name: str,
        config: Dict[str, Any]
    ) -> float:
        """Calculate trailing minimum value.
        
        Args:
            indicator_name: Name of indicator
            config: Indicator configuration
        
        Returns:
            Minimum value over period
        """
        period = config['period']
        field = config['field']
        
        period_days = self._parse_period_to_days(period)
        
        logger.debug(
            f"Calculating {indicator_name}: min {field} over {period}"
        )
        
        # Get all bars for the period
        min_value = await self._calculate_field_min(field, period_days)
        
        return min_value
    
    def _parse_period_to_days(self, period: str) -> int:
        """Parse period string to number of days.
        
        Supports:
        - "Nd" = N days (e.g., "10d" = 10 days)
        - "Nw" = N weeks (e.g., "52w" = 364 days)
        - "Nm" = N months (e.g., "3m" = 90 days)
        - "Ny" = N years (e.g., "1y" = 365 days)
        
        Args:
            period: Period string
        
        Returns:
            Number of days
        """
        period = period.strip().lower()
        
        if period.endswith('d'):
            # Days
            return int(period[:-1])
        elif period.endswith('w'):
            # Weeks (7 days per week)
            return int(period[:-1]) * 7
        elif period.endswith('m'):
            # Months (approximate as 30 days)
            return int(period[:-1]) * 30
        elif period.endswith('y'):
            # Years (365 days)
            return int(period[:-1]) * 365
        else:
            raise ValueError(f"Invalid period format: {period}")
    
    async def _calculate_daily_average(
        self,
        field: str,
        period_days: int,
        skip_early_close: bool = False
    ) -> float:
        """Calculate daily average (one value).
        
        Args:
            field: OHLCV field to average
            period_days: Number of days to include
            skip_early_close: If True, exclude early close days
        
        Returns:
            Average value
        """
        # TODO: Query historical bars and calculate average
        # For now, return placeholder
        logger.debug(
            f"Calculating daily average for {field} over {period_days} days "
            f"(skip_early_close={skip_early_close}) - TODO"
        )
        
        # Placeholder: return 0.0
        # Real implementation would:
        # 1. Get all daily bars for period
        # 2. Extract field values
        # 3. Filter out early close days if requested
        # 4. Calculate average
        
        return 0.0
    
    async def _calculate_intraday_average(
        self,
        field: str,
        period_days: int
    ) -> List[float]:
        """Calculate intraday average (390 values, one per minute).
        
        Args:
            field: OHLCV field to average
            period_days: Number of days to include
        
        Returns:
            List of 390 values (one per minute of trading day)
        """
        # TODO: Query historical 1m bars and calculate minute-by-minute average
        # For now, return placeholder
        logger.debug(
            f"Calculating intraday average for {field} over {period_days} days - TODO"
        )
        
        # Placeholder: return array of 390 zeros
        # Real implementation would:
        # 1. Get all 1m bars for period
        # 2. Group by minute of day (9:30, 9:31, ..., 15:59)
        # 3. Calculate average for each minute across all days
        # 4. Return 390 values
        
        return [0.0] * 390
    
    async def _calculate_field_max(
        self,
        field: str,
        period_days: int
    ) -> float:
        """Calculate maximum value of field over period.
        
        Args:
            field: OHLCV field
            period_days: Number of days
        
        Returns:
            Maximum value
        """
        # TODO: Query historical bars and find maximum
        logger.debug(
            f"Calculating max {field} over {period_days} days - TODO"
        )
        
        # Placeholder: return 0.0
        # Real implementation would:
        # 1. Get all bars for period
        # 2. Extract field values
        # 3. Return maximum
        
        return 0.0
    
    async def _calculate_field_min(
        self,
        field: str,
        period_days: int
    ) -> float:
        """Calculate minimum value of field over period.
        
        Args:
            field: OHLCV field
            period_days: Number of days
        
        Returns:
            Minimum value
        """
        # TODO: Query historical bars and find minimum
        logger.debug(
            f"Calculating min {field} over {period_days} days - TODO"
        )
        
        # Placeholder: return 0.0
        # Real implementation would:
        # 1. Get all bars for period
        # 2. Extract field values
        # 3. Return minimum
        
        return 0.0
    
    # =========================================================================
    # Queue Loading
    # =========================================================================
    
    async def _load_backtest_queues(self):
        """Load queues with prefetch_days of data for backtest mode.
        
        For each symbol:
        - Load ONLY STREAMED intervals (not generated ones)
        - Load prefetch_days worth of data
        - Store in DataManager queues (via start_bar_stream API)
        
        Reference: SESSION_ARCHITECTURE.md lines 1651-1654
        """
        prefetch_days = self.session_config.backtest_config.prefetch_days
        current_time = self._time_manager.get_current_time()
        current_date = current_time.date()
        
        logger.info(
            f"Loading backtest queues: {prefetch_days} days from {current_date}"
        )
        
        # Calculate date range for prefetch
        start_date = current_date
        end_date = await self._get_date_plus_trading_days(
            start_date,
            prefetch_days - 1  # -1 because start_date is day 1
        )
        
        if end_date is None:
            logger.error(
                f"Could not calculate end date for prefetch ({prefetch_days} days)"
            )
            return
        
        logger.info(
            f"Prefetch range: {start_date} to {end_date} "
            f"({prefetch_days} trading days)"
        )
        
        # Load queues for each symbol
        total_streams = 0
        for symbol in self.session_config.session_data_config.symbols:
            # Get STREAMED intervals only (not generated)
            streamed_intervals = self._get_streamed_intervals_for_symbol(symbol)
            
            if not streamed_intervals:
                logger.warning(f"{symbol}: No streamed intervals to load")
                continue
            
            # Load each streamed interval
            for interval in streamed_intervals:
                try:
                    # Use DataManager API to load bars into queue
                    # TODO: DataManager API for queue loading
                    logger.debug(
                        f"Loading {symbol} {interval} queue: "
                        f"{start_date} to {end_date} (DataManager API TODO)"
                    )
                    
                    # Placeholder: In real implementation:
                    # await self._data_manager.start_bar_stream(
                    #     symbol, interval, start_date, end_date
                    # )
                    
                    total_streams += 1
                    
                except Exception as e:
                    logger.error(
                        f"Error loading {symbol} {interval} queue: {e}",
                        exc_info=True
                    )
        
        logger.info(f"Loaded {total_streams} backtest streams")
    
    async def _start_live_streams(self):
        """Start live API streams for live mode.
        
        For each symbol:
        - Start streams for STREAMED data types only
        - Uses API to subscribe to real-time data
        - DataManager handles connection and queueing
        """
        logger.info("Starting live streams")
        
        total_streams = 0
        for symbol in self.session_config.session_data_config.symbols:
            # Get STREAMED data types (not generated)
            streamed_types = self._get_streamed_intervals_for_symbol(symbol)
            
            if not streamed_types:
                logger.warning(f"{symbol}: No streamed data types to start")
                continue
            
            # Start each stream
            for stream_type in streamed_types:
                try:
                    # Use DataManager API to start live stream
                    # TODO: DataManager API for live streaming
                    logger.debug(
                        f"Starting {symbol} {stream_type} live stream "
                        "(DataManager API TODO)"
                    )
                    
                    # Placeholder: In real implementation:
                    # await self._data_manager.start_live_stream(
                    #     symbol, stream_type
                    # )
                    
                    total_streams += 1
                    
                except Exception as e:
                    logger.error(
                        f"Error starting {symbol} {stream_type} stream: {e}",
                        exc_info=True
                    )
        
        logger.info(f"Started {total_streams} live streams")
    
    def _get_streamed_intervals_for_symbol(self, symbol: str) -> List[str]:
        """Get list of STREAMED intervals for a symbol.
        
        Returns only intervals marked as STREAMED (not GENERATED).
        Uses the stream/generate marking from _mark_stream_generate().
        
        Args:
            symbol: Symbol to query
        
        Returns:
            List of streamed intervals (e.g., ["1m", "quotes"])
        """
        return self._streamed_data.get(symbol, [])
    
    async def _get_date_plus_trading_days(
        self,
        start_date: date,
        num_days: int
    ) -> Optional[date]:
        """Calculate date N trading days after start_date.
        
        Uses TimeManager to skip weekends and holidays.
        
        Args:
            start_date: Starting date (inclusive)
            num_days: Number of trading days to add (0 = same day)
        
        Returns:
            End date (inclusive) or None if calculation fails
        """
        if num_days < 0:
            logger.error(f"Invalid num_days: {num_days}")
            return None
        
        if num_days == 0:
            # Same day
            return start_date
        
        # Use TimeManager to count forward trading days
        async with AsyncSessionLocal() as session:
            end_date = await self._time_manager.get_next_trading_date(
                session,
                start_date,
                n=num_days,
                exchange=self.session_config.exchange_group
            )
        
        if end_date is None:
            logger.error(
                f"Could not find trading date {num_days} days "
                f"after {start_date}"
            )
            return None
        
        logger.debug(
            f"Date range: {start_date} + {num_days} trading days = {end_date}"
        )
        
        return end_date
    
    # =========================================================================
    # Streaming Phase Helpers
    # =========================================================================
    
    async def _get_next_queue_timestamp(self) -> Optional[datetime]:
        """Get earliest timestamp across all queues.
        
        Queries DataManager for the next available data timestamp across
        all symbol/interval queues.
        
        Returns:
            Next timestamp or None if all queues empty
        """
        # TODO: Query DataManager for next timestamp across all queues
        # For now, return None (placeholder)
        logger.debug("Getting next queue timestamp (DataManager API TODO)")
        
        # Placeholder: In real implementation:
        # next_timestamps = []
        # for symbol in self.session_config.session_data_config.symbols:
        #     for interval in self._get_streamed_intervals_for_symbol(symbol):
        #         ts = await self._data_manager.peek_queue_timestamp(symbol, interval)
        #         if ts:
        #             next_timestamps.append(ts)
        # 
        # if not next_timestamps:
        #     return None
        # 
        # return min(next_timestamps)  # Earliest timestamp
        
        return None
    
    async def _process_queue_data_at_timestamp(
        self,
        timestamp: datetime
    ) -> int:
        """Process all queue data at the given timestamp.
        
        For each symbol/interval:
        1. Peek at queue head
        2. If timestamp matches, consume and add to session_data
        3. Repeat until no more data at this timestamp
        
        Args:
            timestamp: Timestamp to process
        
        Returns:
            Number of bars processed
        """
        bars_processed = 0
        
        # TODO: Implement queue consumption logic
        # For now, just log (placeholder)
        logger.debug(f"Processing queue data at {timestamp.time()} (DataManager API TODO)")
        
        # Placeholder: In real implementation:
        # for symbol in self.session_config.session_data_config.symbols:
        #     for interval in self._get_streamed_intervals_for_symbol(symbol):
        #         while True:
        #             # Peek at queue head
        #             bar = await self._data_manager.peek_queue(symbol, interval)
        #             if not bar:
        #                 break
        #             
        #             # Check if timestamp matches
        #             if bar.timestamp != timestamp:
        #                 break
        #             
        #             # Consume and add to session_data
        #             bar = await self._data_manager.consume_queue(symbol, interval)
        #             self.session_data.append_bar(symbol, interval, bar)
        #             bars_processed += 1
        #             
        #             # Notify data processor (Phase 4 integration)
        #             if self.data_processor:
        #                 self.data_processor.notify_data_available(symbol, interval, bar.timestamp)
        #                 
        #                 # Wait for processor in data-driven mode
        #                 if self.mode == "backtest" and self.session_config.backtest_config:
        #                     speed = self.session_config.backtest_config.speed_multiplier
        #                     if speed == 0 and self._processor_subscription:
        #                         # Data-driven: block until processor ready
        #                         self._processor_subscription.wait_until_ready()
        #             
        #             # Notify quality manager (Phase 5 integration - non-blocking)
        #             if self.quality_manager:
        #                 self.quality_manager.notify_data_available(symbol, interval, bar.timestamp)
        
        return bars_processed
    
    async def _apply_clock_driven_delay(self, speed_multiplier: float):
        """Apply clock-driven delay based on speed multiplier.
        
        In clock-driven mode, we simulate real-time by adding delays.
        speed_multiplier controls the speed:
        - 1.0 = real-time (1 minute of market time = 1 minute real time)
        - 360.0 = fast (1 minute of market time = 0.167 seconds real time)
        - 0.0 = data-driven (no delays, process as fast as possible)
        
        Args:
            speed_multiplier: Speed multiplier from config
        """
        if speed_multiplier <= 0:
            # Data-driven mode: no delay
            return
        
        # Calculate delay for 1 minute of market time
        # 1 minute = 60 seconds
        # delay = 60 / speed_multiplier
        delay_seconds = 60.0 / speed_multiplier
        
        # Cap delay to reasonable value (max 60 seconds)
        delay_seconds = min(delay_seconds, 60.0)
        
        if delay_seconds > 0.001:  # Only sleep if > 1ms
            await asyncio.sleep(delay_seconds)
