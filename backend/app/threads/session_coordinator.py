"""
Session Coordinator - Central orchestrator for session lifecycle

This is a COMPLETE REWRITE for the new session architecture (Phase 3).
Old version backed up to: _backup/backtest_stream_coordinator.py.bak

Key Responsibilities:
1. Historical data loading and updating (EVERY SESSION)
2. Historical indicator calculation (EVERY SESSION)
3. Quality calculation for historical bars (EVERY SESSION)
4. Queue loading (backtest: current day data; live: API streams)
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

import threading
import queue
from datetime import datetime, date, time, timedelta
from typing import Optional, Dict, List, Any, Tuple, Set
from collections import defaultdict
from collections import deque
from dataclasses import dataclass, field

# Logging
from app.logger import logger

# Phase 1 & 2 components
from app.managers.data_manager.session_data import (
    SessionData, 
    get_session_data,
    SymbolSessionData,
    BarIntervalData
)
from app.threads.sync.stream_subscription import StreamSubscription
from app.monitoring.performance_metrics import PerformanceMetrics
from app.models.session_config import SessionConfig

# Existing infrastructure
from app.models.database import SessionLocal

# Stream requirements validation (Phase 1-4)
from app.threads.quality.stream_requirements_coordinator import StreamRequirementsCoordinator
from app.threads.quality.parquet_data_checker import create_data_manager_checker

# Quality calculation helpers
from app.threads.quality.quality_helpers import (
    parse_interval_to_minutes,
    calculate_quality_for_historical_date
)

# Indicator system (Phase 1-5)
from app.indicators import (
    IndicatorManager,
    IndicatorConfig,
    IndicatorType,
    list_indicators
)
from app.models.indicator_config import (
    SessionIndicatorConfig,
    HistoricalIndicatorConfig
)


@dataclass
class SymbolValidationResult:
    """Result of per-symbol validation for loading.
    
    Used by Step 0 validation to determine if a symbol can proceed to Step 3 loading.
    """
    symbol: str
    can_proceed: bool = False
    reason: str = ""
    
    # Data source validation
    data_source_available: bool = False
    data_source: Optional[str] = None  # "alpaca", "schwab", "parquet"
    
    # Interval validation
    intervals_supported: List[str] = field(default_factory=list)
    base_interval: Optional[str] = None
    
    # Historical data validation
    has_historical_data: bool = False
    historical_date_range: Optional[Tuple[date, date]] = None
    
    # Requirements validation
    meets_config_requirements: bool = False


@dataclass
class ProvisioningRequirements:
    """Unified requirements for any addition operation (symbol, bar, indicator).
    
    Phase 5a: Core Infrastructure for Unified Provisioning Architecture
    
    This dataclass represents the complete analysis of what's needed for ANY
    addition operation (symbol, bar, or indicator) from ANY source (config,
    scanner, or strategy).
    
    Three-Phase Pattern:
        1. REQUIREMENT ANALYSIS → Creates this object
        2. VALIDATION → Populates validation fields
        3. PROVISIONING → Uses provisioning_steps to execute
    
    Attributes:
        operation_type: What are we adding? ("symbol", "bar", "indicator")
        source: Who is adding? ("config", "scanner", "strategy")
        symbol: Symbol to operate on
        
        # Existing state (from session_data)
        symbol_exists: bool - Does symbol already exist?
        symbol_data: Optional[SymbolSessionData] - Existing symbol data if present
        
        # Interval requirements (INFERRED from operation)
        required_intervals: List[str] - All intervals needed (base + derived)
        base_interval: Optional[str] - Base interval (if derived needed)
        intervals_exist: Dict[str, bool] - Which intervals already exist?
        
        # Historical requirements (INFERRED from config/indicator)
        needs_historical: bool - Does operation need historical data?
        historical_days: int - Calendar days of historical data needed
        historical_bars: int - Number of bars needed (for indicators)
        
        # Session requirements
        needs_session: bool - Does operation need session/streaming data?
        
        # Indicator requirements (if operation_type="indicator")
        indicator_config: Optional[IndicatorConfig] - Indicator configuration
        indicator_requirements: Optional[IndicatorRequirements] - From analyzer
        
        # Validation results (from Step 0 validation)
        validation_result: Optional[SymbolValidationResult] - Full validation result
        can_proceed: bool - Can we proceed with provisioning?
        validation_errors: List[str] - Why validation failed
        
        # Provisioning plan (determined by analysis)
        provisioning_steps: List[str] - Steps to execute (e.g., "create_symbol")
        
        # Metadata (for SymbolSessionData creation/update)
        meets_session_config_requirements: bool - Full or adhoc?
        added_by: str - Source identifier ("config", "scanner", "strategy")
        auto_provisioned: bool - Was symbol auto-created?
        
        # Explanation
        reason: str - Human-readable explanation of requirements
    """
    # Operation identification
    operation_type: str  # "symbol", "bar", "indicator"
    source: str  # "config", "scanner", "strategy"
    symbol: str
    
    # Existing state
    symbol_exists: bool = False
    symbol_data: Optional[Any] = None  # SymbolSessionData if exists
    
    # Interval requirements
    required_intervals: List[str] = field(default_factory=list)
    base_interval: Optional[str] = None
    intervals_exist: Dict[str, bool] = field(default_factory=dict)
    
    # Historical requirements
    needs_historical: bool = False
    historical_days: int = 0
    historical_bars: int = 0
    
    # Session requirements
    needs_session: bool = False
    
    # Indicator requirements (if applicable)
    indicator_config: Optional[Any] = None  # IndicatorConfig
    indicator_requirements: Optional[Any] = None  # IndicatorRequirements
    
    # Validation results
    validation_result: Optional[SymbolValidationResult] = None
    can_proceed: bool = False
    validation_errors: List[str] = field(default_factory=list)
    
    # Provisioning plan
    provisioning_steps: List[str] = field(default_factory=list)
    
    # Metadata
    meets_session_config_requirements: bool = False
    added_by: str = "adhoc"
    auto_provisioned: bool = False
    
    # Explanation
    reason: str = ""


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
        data_manager
    ):
        """Initialize Session Coordinator.
        
        Args:
            system_manager: Reference to SystemManager (single source of truth)
            data_manager: Reference to DataManager
        """
        super().__init__(name="SessionCoordinator", daemon=True)
        
        # Core dependencies
        self._system_manager = system_manager
        self._data_manager = data_manager
        self._time_manager = system_manager.get_time_manager()
        self._scanner_manager = system_manager.get_scanner_manager()
        
        # Phase 1 & 2 components (NEW architecture)
        self.session_data = get_session_data()  # Use singleton
        self.metrics = PerformanceMetrics()
        self.subscriptions: Dict[str, StreamSubscription] = {}
        
        # Phase 3-5: Indicator manager
        self.indicator_manager = IndicatorManager(self.session_data)
        logger.info(
            f"IndicatorManager initialized with {len(list_indicators())} "
            f"registered indicators"
        )
        
        # Extract immutable config values during init (performance optimization)
        session_config = self._system_manager.session_config
        self._symbols = session_config.session_data_config.symbols
        self._streams = session_config.session_data_config.streams
        
        # Derived intervals are determined from the streams config
        # The coordinator will mark which intervals are STREAMED vs GENERATED
        # This is computed later in _determine_stream_sources()
        self._derived_intervals = []  # Will be populated during stream determination
        
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
        
        # Queue storage for backtest streaming
        # Structure: {(symbol, interval): deque of BarData}
        self._bar_queues: Dict[Tuple[str, str], 'deque'] = {}
        
        # Symbol management (thread-safe)
        self._symbol_operation_lock = threading.Lock()
        # Note: _loaded_symbols removed - query session_data.get_active_symbols() instead
        # Note: _streamed_data/_generated_data removed - stored in bars[interval].derived flag
        self._pending_symbols: Set[str] = set()  # Symbols waiting to be loaded
        
        # Stream control
        self._stream_paused = threading.Event()  # Pause control for backtest mode
        self._stream_paused.set()  # Initially not paused
        
        # Streaming configuration (lag-based session control)
        self._catchup_threshold = 60  # Will be set from config
        self._catchup_check_interval = 10  # Will be set from config
        self._symbol_check_counters: Dict[str, int] = defaultdict(int)  # Per-symbol lag check counters
        
        # Load streaming configuration
        if self.session_config.session_data_config.streaming:
            streaming_config = self.session_config.session_data_config.streaming
            self._catchup_threshold = streaming_config.catchup_threshold_seconds
            self._catchup_check_interval = streaming_config.catchup_check_interval
            logger.info(
                f"[CONFIG] Streaming: catchup_threshold={self._catchup_threshold}s, "
                f"check_interval={self._catchup_check_interval} bars"
            )
        
        # Parse indicator configs from session config (Phase 5)
        self._indicator_configs = self._parse_indicator_configs()
        session_ind_count = len(self._indicator_configs.get('session', []))
        hist_ind_count = len(self._indicator_configs.get('historical', []))
        logger.info(
            f"[CONFIG] Indicators: {session_ind_count} session, "
            f"{hist_ind_count} historical"
        )
        
        # Revised Flow: Stream validation state (Phase 1 implementation)
        self._streams_validated = False  # First-time validation flag
        self._base_interval: Optional[str] = None  # Stored from validation
        self._derived_intervals_validated: List[str] = []  # Stored from validation
        self._session_count = 0  # Track number of sessions run
        
        logger.info(
            f"SessionCoordinator initialized (mode={session_config.mode}, "
            f"symbols={len(session_config.session_data_config.symbols)})"
        )
    
    def _parse_indicator_configs(self) -> Dict[str, List[IndicatorConfig]]:
        """Parse indicator configs from session config.
        
        Converts SessionIndicatorConfig/HistoricalIndicatorConfig to IndicatorConfig.
        
        Returns:
            Dict with 'session' and 'historical' indicator configs
        """
        session_config = self._system_manager.session_config
        indicators_config = session_config.session_data_config.indicators
        
        result = {
            'session': [],
            'historical': []
        }
        
        # Parse session indicators
        for ind_cfg in indicators_config.session:
            try:
                # Convert SessionIndicatorConfig to IndicatorConfig
                config = IndicatorConfig(
                    name=ind_cfg.name,
                    type=IndicatorType(ind_cfg.type),
                    period=ind_cfg.period,
                    interval=ind_cfg.interval,
                    params=ind_cfg.params.copy() if ind_cfg.params else {}
                )
                result['session'].append(config)
                logger.debug(f"Parsed session indicator: {config.make_key()}")
            except Exception as e:
                logger.error(
                    f"Failed to parse session indicator {ind_cfg.name}: {e}",
                    exc_info=True
                )
        
        # Parse historical indicators
        for ind_cfg in indicators_config.historical:
            try:
                # Convert HistoricalIndicatorConfig to IndicatorConfig
                config = IndicatorConfig(
                    name=ind_cfg.name,
                    type=IndicatorType(ind_cfg.type),
                    period=ind_cfg.period,
                    interval=ind_cfg.interval,
                    params=ind_cfg.params.copy() if ind_cfg.params else {}
                )
                result['historical'].append(config)
                logger.debug(f"Parsed historical indicator: {config.make_key()}")
            except Exception as e:
                logger.error(
                    f"Failed to parse historical indicator {ind_cfg.name}: {e}",
                    exc_info=True
                )
        
        return result
    
    # =========================================================================
    # Unified Symbol Registration (Phase 6c)
    # =========================================================================
    
    async def register_symbol(
        self,
        symbol: str,
        load_historical: bool = True,
        calculate_indicators: bool = True
    ) -> bool:
        """Register symbol with unified routine.
        
        This single method handles:
        - Pre-session initialization (during coordinator startup)
        - Mid-session insertion (dynamic symbol addition)
        
        Args:
            symbol: Symbol to register
            load_historical: Load historical bars for warmup
            calculate_indicators: Register and calculate indicators
            
        Returns:
            True if successful
            
        Design:
            - Parameterized for reuse
            - Works for all intervals (s, m, d, w)
            - Uses requirement_analyzer for consistency
            - No special cases for pre vs mid-session
        """
        try:
            logger.info(f"{symbol}: Registering symbol (unified routine)")
            
            # 1. Determine requirements (unified)
            requirements = await self._determine_symbol_requirements(symbol)
            
            # 2. Load historical data (unified)
            historical_bars = {}
            if load_historical and requirements['needs_historical']:
                historical_bars = await self._load_historical_bars(
                    symbol=symbol,
                    requirements=requirements
                )
            
            # 3. Register with SessionData (unified)
            self._register_symbol_data(
                symbol=symbol,
                requirements=requirements,
                historical_bars=historical_bars
            )
            
            # 4. Register indicators (unified)
            if calculate_indicators:
                self._register_symbol_indicators(
                    symbol=symbol,
                    historical_bars=historical_bars
                )
            
            # 5. Log success
            logger.info(
                f"{symbol}: Registration complete "
                f"(base: {requirements['base_interval']}, "
                f"derived: {len(requirements['derived_intervals'])})"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"{symbol}: Registration failed: {e}", exc_info=True)
            return False
    
    async def _determine_symbol_requirements(self, symbol: str) -> dict:
        """Determine what's needed for this symbol.
        
        Uses requirement_analyzer to determine:
        - Base interval (1s, 1m, 1d)
        - Derived intervals (5m, 15m, 1w, etc.)
        - Historical days needed (for indicators)
        
        Returns:
            Dict with requirements
        """
        from app.threads.quality.requirement_analyzer import analyze_session_requirements
        
        # Get all intervals needed (streams + indicators)
        all_intervals = set(self._streams)
        
        # Add indicator intervals
        for ind in self._indicator_configs['session']:
            all_intervals.add(ind.interval)
        for ind in self._indicator_configs['historical']:
            all_intervals.add(ind.interval)
        
        # Analyze requirements
        requirements = analyze_session_requirements(
            streams=list(all_intervals)
        )
        
        # Determine historical days needed
        max_historical_days = self._calculate_max_historical_days()
        
        return {
            'symbol': symbol,
            'base_interval': requirements.required_base_interval,
            'derived_intervals': requirements.derivable_intervals,
            'historical_days': max_historical_days,
            'needs_historical': (max_historical_days > 0)
        }
    
    def _calculate_max_historical_days(self) -> int:
        """Calculate maximum historical days needed for indicators.
        
        Returns:
            Max days needed (from config or calculated from indicators)
        """
        # Get from historical config
        session_config = self._system_manager.session_config
        max_days = 0
        
        if session_config.session_data_config.historical.data:
            for hist_config in session_config.session_data_config.historical.data:
                max_days = max(max_days, hist_config.trailing_days)
        
        # Also check indicator periods (convert to days if needed)
        for ind in self._indicator_configs['historical']:
            if ind.period > 0:
                # Rough estimate: period in days
                max_days = max(max_days, ind.period * 2)  # 2x for safety
        
        return max_days if max_days > 0 else 20  # Default 20 days
    
    async def _load_historical_bars(
        self,
        symbol: str,
        requirements: dict
    ) -> dict:
        """Load historical bars for symbol.
        
        Unified method that:
        - Loads base interval from parquet
        - Generates derived intervals
        - Works for all intervals (s, m, d, w)
        
        Args:
            symbol: Symbol to load
            requirements: Requirements from analyzer
            
        Returns:
            Dict of {interval: [bars]}
        """
        from app.managers.data_manager.derived_bars import compute_all_derived_intervals
        
        historical_bars = {}
        
        # Load base interval
        base_interval = requirements['base_interval']
        historical_days = requirements['historical_days']
        
        # Get historical bars from data_manager
        try:
            base_bars = await self._data_manager.load_historical_bars(
                symbol=symbol,
                interval=base_interval,
                days=historical_days
            )
            
            if base_bars:
                # Store base interval bars
                historical_bars[base_interval] = base_bars
                logger.debug(
                    f"{symbol}: Loaded {len(base_bars)} {base_interval} bars "
                    f"({historical_days} days)"
                )
                
                # Generate derived intervals if needed
                if requirements['derived_intervals']:
                    derived_data = compute_all_derived_intervals(
                        base_bars=base_bars,
                        base_interval=base_interval,
                        target_intervals=requirements['derived_intervals']
                    )
                    
                    for interval, bars in derived_data.items():
                        historical_bars[interval] = bars
                        logger.debug(
                            f"{symbol}: Generated {len(bars)} {interval} bars "
                            f"from {base_interval}"
                        )
            else:
                logger.debug(
                    f"{symbol}: No historical bars found, "
                    f"indicators will warm up from live data"
                )
                
        except Exception as e:
            logger.warning(
                f"{symbol}: Error loading historical bars: {e}, "
                f"indicators will warm up from live data"
            )
        
        return historical_bars
    
    def _register_symbol_data(
        self,
        symbol: str,
        requirements: dict,
        historical_bars: dict
    ):
        """Register symbol with SessionData.
        
        Creates SymbolSessionData and stores historical bars.
        
        Args:
            symbol: Symbol to register
            requirements: Requirements from analyzer
            historical_bars: Pre-loaded historical bars
        """
        from app.managers.data_manager.session_data import SymbolSessionData
        from collections import deque
        
        # Check if already registered
        if self.session_data.get_symbol_data(symbol):
            logger.warning(f"{symbol}: Already registered in SessionData")
            return
        
        # Register symbol
        symbol_data = self.session_data.register_symbol(symbol)
        
        # Set base interval
        symbol_data.base_interval = requirements['base_interval']
        
        # Store historical bars if any
        if historical_bars:
            from app.managers.data_manager.session_data import BarIntervalData
            
            for interval, bars in historical_bars.items():
                is_base = (interval == requirements['base_interval'])
                
                symbol_data.bars[interval] = BarIntervalData(
                    derived=(not is_base),
                    base=requirements['base_interval'] if not is_base else None,
                    data=deque(bars)
                )
            
            logger.debug(
                f"{symbol}: Stored {len(historical_bars)} intervals of historical bars"
            )
        
        logger.debug(
            f"{symbol}: Registered in SessionData "
            f"(base: {requirements['base_interval']})"
        )
    
    def _register_symbol_indicators(
        self,
        symbol: str,
        historical_bars: dict
    ):
        """Register indicators for symbol.
        
        Uses IndicatorManager to register all indicators.
        Historical bars used for warmup.
        
        Args:
            symbol: Symbol to register indicators for
            historical_bars: Pre-loaded bars for warmup
        """
        # Combine session + historical indicators
        all_indicators = (
            self._indicator_configs['session'] +
            self._indicator_configs['historical']
        )
        
        if not all_indicators:
            logger.warning(f"{symbol}: No indicators configured - skipping indicator registration")
            return
        
        # DEBUG: Log what we're about to register
        logger.info(
            f"{symbol}: About to register {len(all_indicators)} indicators "
            f"({len(self._indicator_configs['session'])} session, "
            f"{len(self._indicator_configs['historical'])} historical)"
        )
        
        # Register with indicator manager
        self.indicator_manager.register_symbol_indicators(
            symbol=symbol,
            indicators=all_indicators,
            historical_bars=historical_bars  # For warmup
        )
        
        # DEBUG: Verify registration in session_data
        symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
        if symbol_data:
            actual_count = len(symbol_data.indicators)
            logger.info(
                f"{symbol}: Post-registration check - "
                f"symbol_data.indicators has {actual_count} entries"
            )
            if actual_count == 0:
                logger.error(
                    f"{symbol}: CRITICAL - Indicators registered but symbol_data.indicators is EMPTY!"
                )
        else:
            logger.error(f"{symbol}: CRITICAL - symbol_data not found after indicator registration!")
    
    async def add_symbol_mid_session(self, symbol: str) -> bool:
        """Add symbol during active session.
        
        Uses SAME unified routine as pre-session!
        
        Args:
            symbol: Symbol to add
            
        Returns:
            True if successful
        """
        # Validate not already registered
        if self.session_data.get_symbol_data(symbol):
            logger.warning(f"{symbol}: Already registered")
            return False
        
        logger.info(f"{symbol}: Adding symbol mid-session")
        
        # Use unified registration (SAME CODE!)
        success = await self.register_symbol(
            symbol=symbol,
            load_historical=True,  # Need historical for indicator warmup
            calculate_indicators=True
        )
        
        if success:
            # Note: Streaming setup for mid-session insertion
            # This is a minor enhancement for future live trading when symbols
            # need to be added dynamically. For backtests, symbols are known at
            # session start. Implementation would involve:
            # 1. Adding symbol to stream_coordinator's symbol list
            # 2. Creating queues for this symbol's intervals
            # 3. Starting data feed subscription
            # Current functionality (registration + indicators) is complete.
            logger.info(
                f"{symbol}: Added mid-session successfully "
                f"(streaming setup pending for live mode)"
            )
            
            # Notify strategies of new symbol (NEW)
            strategy_manager = self._system_manager.get_strategy_manager()
            if strategy_manager:
                logger.debug(f"{symbol}: Notifying strategies of new symbol")
                strategy_manager.notify_symbol_added(symbol)
        
        return success
    
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
        logger.info("[SESSION_FLOW] 3: SessionCoordinator.run() - Thread started")
        logger.info("SessionCoordinator thread started")
        
        try:
            # Start backtest timing
            logger.info("[SESSION_FLOW] 3.a: SessionCoordinator - Starting backtest timing")
            self.metrics.start_backtest()
            logger.info("[SESSION_FLOW] 3.a: Complete")
            
            # Main coordinator loop (synchronous)
            logger.info("[SESSION_FLOW] 3.b: SessionCoordinator - Entering coordinator loop")
            self._coordinator_loop()
            logger.info("[SESSION_FLOW] 3.b.1: Coordinator loop exited")
            logger.info("[SESSION_FLOW] 3.b: Complete - Coordinator loop exited")
            
            # Set system state to STOPPED
            if self._system_manager:
                from app.managers.system_manager.api import SystemState
                self._system_manager._state = SystemState.STOPPED
                logger.info("[SESSION_FLOW] 3.b.FINAL: SystemManager state set to STOPPED")
                
            # End backtest timing
            logger.info("[SESSION_FLOW] 3.c: SessionCoordinator - Ending backtest timing")
            self.metrics.end_backtest()
                
            # Log final report
            report = self.metrics.format_report('backtest')
            logger.info(f"\n{report}")
            
        except Exception as e:
            logger.error(f"SessionCoordinator error: {e}", exc_info=True)
        finally:
            self._running = False
            logger.info("SessionCoordinator thread stopped")
    
    def stop(self):
        """Stop the coordinator thread gracefully."""
        logger.info("Stopping SessionCoordinator...")
        self._stop_event.set()
    
    def pause_backtest(self):
        """Pause backtest streaming/time advancement.
        
        Works for both data-driven and clock-driven modes:
        - Data-driven: Stops jumping to next bar timestamp
        - Clock-driven: Stops 1-minute interval advancement
        
        The pause happens at the top of the streaming loop, before:
        - Time advancement
        - Bar processing
        - Processor synchronization
        - Clock delays
        
        Thread-safe: Can be called from any thread.
        Only applies to backtest mode (ignored in live mode).
        """
        if self.mode == "backtest":
            logger.info("[BACKTEST] Pausing streaming/time advancement")
            self._stream_paused.clear()
        else:
            logger.warning("[LIVE] Pause ignored - only applies to backtest mode")
    
    def resume_backtest(self):
        """Resume backtest streaming/time advancement.
        
        Unblocks the streaming loop to continue processing.
        
        Thread-safe: Can be called from any thread.
        Only applies to backtest mode (ignored in live mode).
        """
        if self.mode == "backtest":
            logger.info("[BACKTEST] Resuming streaming/time advancement")
            self._stream_paused.set()
        else:
            logger.warning("[LIVE] Resume ignored - only applies to backtest mode")
    
    def is_paused(self) -> bool:
        """Check if backtest is currently paused.
        
        Returns:
            True if paused (event cleared), False if running (event set)
        """
        return not self._stream_paused.is_set()
    
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
    # Public API - Thread-Safe Accessors
    # =========================================================================
    
    def get_loaded_symbols(self) -> Set[str]:
        """Get currently loaded symbols (thread-safe).
        
        Returns:
            Set of symbols that are fully loaded and streaming
        """
        # Query from SessionData (single source of truth)
        return self.session_data.get_active_symbols()
    
    def get_pending_symbols(self) -> Set[str]:
        """Get symbols waiting to be loaded (thread-safe).
        
        Returns:
            Set of symbols waiting to be processed
        """
        with self._symbol_operation_lock:
            return self._pending_symbols.copy()
    
    def get_generated_data(self) -> Dict[str, List[str]]:
        """Get intervals that need generation per symbol (thread-safe).
        
        Returns:
            Dictionary mapping symbol to list of intervals to generate
        """
        # Query from SessionData (single source of truth)
        return self.session_data.get_symbols_with_derived()
    
    def get_streamed_data(self) -> Dict[str, List[str]]:
        """Get data types being streamed per symbol (thread-safe).
        
        Returns:
            Dictionary mapping symbol to list of streamed data types
        """
        # Query from SessionData (single source of truth)
        result = {}
        for symbol in self.session_data.get_active_symbols():
            symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
            if symbol_data:
                streamed = [interval for interval, data in symbol_data.bars.items() if not data.derived]
                if streamed:
                    result[symbol] = streamed
        return result
    
    # =========================================================================
    # Symbol Management - Thread-Safe Operations
    # =========================================================================
    
    def add_symbol(self, symbol: str, streams: Optional[List[str]] = None, added_by: str = "strategy") -> bool:
        """Add symbol to session with unified three-phase pattern (thread-safe).
        
        Phase 5c: Updated to use unified provisioning pattern.
        
        Uses the three-phase pattern (analyze → validate → provision) for
        consistent, robust symbol addition. This replaces the Phase 4 approach
        with the complete unified architecture.
        
        Three-Phase Pattern:
            1. REQUIREMENT ANALYSIS → What's needed?
            2. VALIDATION → Can we proceed?
            3. PROVISIONING → Execute plan
        
        Args:
            symbol: Symbol to add
            streams: Data streams (default: ["1m"] for backtest) - DEPRECATED
            added_by: Source of addition ("strategy", "scanner", "manual")
        
        Returns:
            True if validated and provisioned, False if validation failed or already exists
        
        Code Reuse:
            - REUSES: _analyze_requirements() from Phase 5a
            - REUSES: _execute_provisioning() from Phase 5b
            - REUSES: All validation and loading from Phases 1-4
        """
        streams = streams or ["1m"]  # For backward compatibility
        
        with self._symbol_operation_lock:
            symbol = symbol.upper()
            
            logger.info(f"[UNIFIED] add_symbol({symbol}, added_by={added_by})")
            
            try:
                # Phase 1: Analyze requirements
                req = self._analyze_requirements(
                    operation_type="symbol",
                    symbol=symbol,
                    source=added_by
                )
                
                # Phase 2: Validate (done in analyze_requirements)
                if not req.can_proceed:
                    logger.error(
                        f"[UNIFIED] {symbol}: Cannot add symbol - {req.validation_errors}"
                    )
                    return False
                
                logger.info(f"[UNIFIED] {symbol}: Validation passed ✅")
                
                # Phase 3: Provision
                success = self._execute_provisioning(req)
                
                if success:
                    # Add to config (single source of truth)
                    if symbol not in self.session_config.session_data_config.symbols:
                        self.session_config.session_data_config.symbols.append(symbol)
                    
                    # Add to streams config
                    if "1m" not in self.session_config.session_data_config.streams:
                        self.session_config.session_data_config.streams.append("1m")
                    
                    logger.success(
                        f"[UNIFIED] {symbol}: Added successfully "
                        f"(added_by={added_by})"
                    )
                else:
                    logger.error(f"[UNIFIED] {symbol}: Provisioning failed")
                
                return success
                
            except Exception as e:
                logger.error(f"[UNIFIED] {symbol}: Exception adding symbol: {e}")
                logger.exception(e)
                return False
    
    def remove_symbol(self, symbol: str) -> bool:
        """Remove symbol from session (thread-safe, can be called from any thread).
        
        Removes symbol from config, clears all queues, removes from session_data.
        Other threads naturally adapt by polling config.
        
        Args:
            symbol: Symbol to remove
        
        Returns:
            True if removed, False if not found
        """
        with self._symbol_operation_lock:
            # Check if exists
            if symbol not in self.session_config.session_data_config.symbols:
                logger.warning(f"[SYMBOL] {symbol} not in session")
                return False
            
            logger.info(f"[SYMBOL] Removing {symbol} from session")
            
            # Remove from config (single source of truth)
            self.session_config.session_data_config.symbols.remove(symbol)
            
            # Remove from pending (if was pending)
            self._pending_symbols.discard(symbol)
            
            # Clear and remove all queues for symbol
            queues_to_remove = [
                key for key in self._bar_queues.keys() 
                if key[0] == symbol
            ]
            for key in queues_to_remove:
                del self._bar_queues[key]
                logger.debug(f"[SYMBOL] Removed queue {key}")
            
            # Clean up lag check counter
            self._symbol_check_counters.pop(symbol, None)
            
            # Note: Symbol data and intervals tracked in SessionData now
            
            logger.info(
                f"[SYMBOL] Removed {symbol} - "
                f"cleared {len(queues_to_remove)} queues"
            )
        
        # Remove from session_data (has its own lock)
        removed = self.session_data.remove_symbol(symbol)
        
        if removed:
            logger.info(f"[SYMBOL] Successfully removed {symbol} from session")
        else:
            logger.warning(f"[SYMBOL] {symbol} not found in session_data")
        
        return True
    
    # =========================================================================
    # Revised Flow: Coordination Methods (Phase 3 Implementation)
    # =========================================================================
    
    def _teardown_and_cleanup(self):
        """Phase 1: Teardown & Cleanup - Clear all state and advance clock.
        
        Called at START of new session (except first session).
        
        Steps:
        1a. Clear SessionData completely (remove all symbols)
        1b. Clear stream queues
        1c. Teardown all threads (reset state)
        2.  Advance clock to next trading day @ market open
        """
        logger.info("=" * 70)
        logger.info("PHASE 1: TEARDOWN & CLEANUP")
        logger.info("=" * 70)
        
        # Step 1a: Clear SessionData
        logger.info("Step 1a: Clearing SessionData")
        self.session_data.clear()
        logger.debug(f"SessionData cleared - removed all symbols")
        
        # Step 1b: Clear stream queues
        logger.info("Step 1b: Clearing stream queues")
        self._bar_queues.clear()
        if hasattr(self, '_quote_queues'):
            self._quote_queues.clear()
        if hasattr(self, '_tick_queues'):
            self._tick_queues.clear()
        self._symbol_check_counters.clear()
        logger.debug("Stream queues cleared")
        
        # Step 1c: Teardown all threads
        logger.info("Step 1c: Tearing down threads")
        if hasattr(self.data_processor, 'teardown'):
            self.data_processor.teardown()
        if hasattr(self.quality_manager, 'teardown'):
            self.quality_manager.teardown()
        if hasattr(self._scanner_manager, 'teardown'):
            self._scanner_manager.teardown()
        logger.debug("All threads torn down")
        
        # Step 2: Advance clock to next trading day
        logger.info("Step 2: Advancing clock to next trading day")
        current_time = self._time_manager.get_current_time()
        current_date = current_time.date()
        self._advance_to_next_trading_day(current_date)
        
        new_time = self._time_manager.get_current_time()
        logger.info(f"Clock advanced: {current_date} → {new_time.date()} @ {new_time.time()}")
        
        logger.info("✓ Phase 1 complete")
    
    def _load_session_data(self):
        """Phase 2 - Step 3: Load ALL session data from config (unified step).
        
        Phase 4 Enhancement: Added per-symbol validation (Step 0) before loading.
        
        Coordinates:
        - STEP 0: Per-symbol validation (NEW - Phase 4)
        - Symbols (registration)
        - Historical bars
        - Session indicators
        - Historical indicators
        - Stream queues
        - Quality scores
        
        All data comes from session_config.
        """
        logger.info("=" * 70)
        logger.info("LOADING SESSION DATA FROM CONFIG")
        logger.info("=" * 70)
        
        # STEP 0: Validate symbols (NEW - Phase 4)
        logger.info("Step 0: Validating symbols")
        config_symbols = self.session_config.session_data_config.symbols
        validated_symbols = self._validate_symbols_for_loading(config_symbols)
        logger.info(f"Step 0: {len(validated_symbols)}/{len(config_symbols)} symbols validated")
        
        # STEP 3: Load validated symbols only
        # Sub-step 1: Register symbols
        logger.info("Step 3.1: Registering symbols")
        for symbol in validated_symbols:
            self._register_single_symbol(
                symbol,
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False
            )
        
        # Sub-step 2-4: Load historical data and indicators
        logger.info("Step 3.2: Loading historical data and indicators")
        self._manage_historical_data(symbols=validated_symbols)
        
        # Sub-step 3.5: Register session indicators
        logger.info("Step 3.3: Registering session indicators")
        self._register_session_indicators(symbols=validated_symbols)
        
        # Sub-step 5: Load stream queues
        logger.info("Step 3.4: Loading stream queues")
        self._load_queues(symbols=validated_symbols)
        
        # Sub-step 6: Calculate quality
        logger.info("Step 3.5: Calculating quality scores")
        self._calculate_historical_quality(symbols=validated_symbols)
        
        logger.info("=" * 70)
        logger.info(f"✓ SESSION DATA LOADED ({len(validated_symbols)} symbols)")
        logger.info("=" * 70)
    
    def _initialize_threads(self):
        """Phase 2 - Step 4: Initialize all threads for new session.
        
        Calls setup() on each thread (Phase 1 stub methods).
        """
        logger.info("Initializing threads for new session")
        
        # Initialize in order
        if hasattr(self.data_processor, 'setup'):
            logger.debug("Initializing data_processor")
            self.data_processor.setup()
        
        if hasattr(self.quality_manager, 'setup'):
            logger.debug("Initializing quality_manager")
            self.quality_manager.setup()
        
        if hasattr(self._scanner_manager, 'setup'):
            logger.debug("Initializing scanner_manager")
            self._scanner_manager.setup()
        
        logger.info("✓ All threads initialized")
    
    def _register_session_indicators(self, symbols: Optional[List[str]] = None):
        """Register session indicators for specified symbols (or all if None).
        
        Calls existing _register_symbol_indicators method for each symbol.
        Used by both pre-session initialization and mid-session insertion.
        
        Args:
            symbols: List of symbols to process, or None for all symbols from config
        """
        if symbols is None:
            symbols = self.session_config.session_data_config.symbols
        
        for symbol in symbols:
            # Get historical bars for warmup
            symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
            if not symbol_data:
                logger.warning(f"{symbol}: Symbol data not found, skipping indicator registration")
                continue
            
            # Get historical bars for this symbol
            historical_bars = {}
            for interval_key, interval_data in symbol_data.historical.bars.items():
                # Flatten data_by_date into single list
                all_bars = []
                for date_bars in interval_data.data_by_date.values():
                    all_bars.extend(date_bars)
                if all_bars:
                    historical_bars[interval_key] = all_bars
            
            # Call existing method
            self._register_symbol_indicators(
                symbol=symbol,
                historical_bars=historical_bars
            )  # EXISTING method (lines 505-556)
        
        logger.info(f"Registered indicators for {len(symbols)} symbols")
    
    def _coordinator_loop(self):
        """Main coordinator loop - REVISED FLOW (Phase 5 implementation).
        
        Revised Session Lifecycle:
        BEFORE LOOP:
          0. Validate stream configuration (once)
        
        MAIN LOOP (each trading day):
          PHASE 1: Teardown & Cleanup
            1. Clear all state and resources
            2. Advance clock to new trading day
          
          PHASE 2: Initialization
            3. Load ALL session data from config
            4. Initialize all threads
            5. Run pre-session scans
          
          PHASE 3: Active Session
            6. Activate session
            7. Start streaming
          
          PHASE 4: End Session
            8. Deactivate session (data preserved)
            9. Check if last day
        
        Reference: /docs/windsurf/REVISED_SESSION_FLOW.md
        """
        logger.info("=" * 70)
        logger.info("COORDINATOR LOOP STARTED")
        logger.info("=" * 70)
        
        # =====================================================================
        # BEFORE LOOP: First-time validation
        # =====================================================================
        if not self._streams_validated:
            logger.info("=" * 70)
            logger.info("PHASE 0: VALIDATION & PREP (First-time only)")
            logger.info("=" * 70)
            
            if not self._validate_stream_requirements():
                raise RuntimeError("Stream validation failed - cannot start backtest")
            
            logger.info("✓ Phase 0 complete - streams validated")
        
        # =====================================================================
        # MAIN LOOP
        # =====================================================================
        while not self._stop_event.is_set():
            try:
                # =============================================================
                # PHASE 1: TEARDOWN & CLEANUP (skip on first session)
                # =============================================================
                if self._session_count > 0:
                    self._teardown_and_cleanup()  # NEW coordination method
                else:
                    # First session: just log starting info
                    current_time = self._time_manager.get_current_time()
                    logger.info("=" * 70)
                    logger.info(f"FIRST SESSION - Starting at {current_time}")
                    logger.info("=" * 70)
                
                # =============================================================
                # PHASE 2: INITIALIZATION
                # =============================================================
                logger.info("=" * 70)
                logger.info("PHASE 2: INITIALIZATION")
                logger.info("=" * 70)
                
                # Step 3: Load ALL session data
                gap_start = self.metrics.start_timer()
                self._load_session_data()  # NEW coordination method
                self.metrics.record_session_gap(gap_start)
                
                # Step 4: Initialize threads
                self._initialize_threads()  # NEW coordination method
                
                # Step 5: Pre-session scans
                if self._scanner_manager.has_pre_session_scanners():
                    logger.info("Running pre-session scans")
                    success = self._scanner_manager.setup_pre_session_scanners()
                    if not success:
                        raise RuntimeError("Pre-session scan failed")
                
                logger.info("✓ Phase 2 complete")
                
                # =============================================================
                # PHASE 3: ACTIVE SESSION
                # =============================================================
                logger.info("=" * 70)
                logger.info("PHASE 3: ACTIVE SESSION")
                logger.info("=" * 70)
                
                # Step 6: Activate session
                self._activate_session()  # EXISTING method (unchanged)
                
                # Step 7: Stream data
                self._streaming_phase()  # EXISTING method (unchanged)
                
                logger.info("✓ Phase 3 complete")
                
                # =============================================================
                # PHASE 4: END SESSION
                # =============================================================
                logger.info("=" * 70)
                logger.info("PHASE 4: END SESSION")
                logger.info("=" * 70)
                
                # Step 8: Deactivate (no cleanup!)
                self._deactivate_session()  # MODIFIED method
                
                # Step 9: Check if last day
                current_time = self._time_manager.get_current_time()
                current_date = current_time.date()
                end_date = self._time_manager.backtest_end_date
                
                if current_date >= end_date:
                    logger.info("=" * 70)
                    logger.info(f"LAST BACKTEST DAY ({current_date})")
                    logger.info("Data preserved for analysis - exiting loop")
                    logger.info("=" * 70)
                    break
                
                logger.info("✓ Phase 4 complete")
                
                # Increment session counter
                self._session_count += 1
                logger.info(f"Session {self._session_count} complete, continuing to next day")
                
            except Exception as e:
                logger.error(f"Error in coordinator loop: {e}", exc_info=True)
                break
        
        logger.info("=" * 70)
        logger.info("COORDINATOR LOOP EXITED")
        logger.info(f"Total sessions completed: {self._session_count}")
        logger.info("=" * 70)
    
    # =========================================================================
    # Phase 1: Initialization
    # =========================================================================
    
    def _initialize_session(self):
        """Initialize session (called at start of each session).
        
        Tasks:
        - Mark stream/generate data types (first time only)
        - Reset session state
        - Log session info
        """
        logger.info("[SESSION_FLOW] PHASE_1.1: Checking if first session (for stream/generate marking)")
        # Mark stream/generate on first session only
        # Check if SessionData has any symbols registered
        if len(self.session_data.get_active_symbols()) == 0:
            logger.info("[SESSION_FLOW] PHASE_1.1: First session - validating and marking streams")
            
            # Validate and mark streams (with Parquet validation in backtest mode)
            validation_success = self._validate_and_mark_streams()
            
            if not validation_success:
                logger.error("[SESSION_FLOW] PHASE_1.1: Stream validation FAILED - cannot start session")
                raise RuntimeError(
                    "Stream requirements validation failed. "
                    "Check logs for details. Required data may be missing."
                )
            
            logger.info("[SESSION_FLOW] PHASE_1.1: Stream validation and marking complete")
            logger.info("[SESSION_FLOW] PHASE_1.1: DataProcessor will query SessionData for derived intervals")
        
        # Reset session state
        logger.info("[SESSION_FLOW] PHASE_1.2: Resetting session state")
        self._session_active = False
        self._session_start_time = None
        
        # Get current session date
        logger.info("[SESSION_FLOW] PHASE_1.3: Getting current session date from TimeManager")
        current_time = self._time_manager.get_current_time()
        current_date = current_time.date()
        logger.info(f"[SESSION_FLOW] PHASE_1.3: Current session date: {current_date}, time: {current_time.time()}")
        
        # Increment trading days counter for performance metrics
        self.metrics.increment_trading_days()
        logger.debug(f"[SESSION_FLOW] PHASE_1.3: Incremented trading days counter (now: {self.metrics.backtest_trading_days})")
        
        # Log session info
        logger.info(f"Initializing session for {current_date}")
        # Query SessionData for counts
        active_symbols = self.session_data.get_active_symbols()
        derived_symbols = self.session_data.get_symbols_with_derived()
        total_derived = sum(len(intervals) for intervals in derived_symbols.values())
        logger.info(
            f"Active symbols: {len(active_symbols)}, "
            f"Derived intervals: {total_derived} types"
        )
        
        logger.info("[SESSION_FLOW] PHASE_1.4: Session initialization complete")
        logger.info("Session initialization complete")
    
    # =========================================================================
    # Phase 2: Historical Management
    # =========================================================================
    
    def _manage_historical_data(self, symbols: Optional[List[str]] = None):
        """Load historical data (assumes symbols already registered).
        
        MODIFIED (Phase 4): Removed pre-registration and clearing logic.
        - Symbols are registered in Phase 2 (_register_symbols)
        - Clearing happens in Phase 1 (_teardown_and_cleanup)
        
        Tasks:
        - Load historical bars (trailing days)
        - Calculate historical indicators
        
        Args:
            symbols: Symbols to process. If None, uses all from config.
        """
        logger.info("Loading historical data")
        
        # Start timing
        start_time = self.metrics.start_timer()
        
        # Load historical data configuration
        historical_config = self.session_config.session_data_config.historical
        
        if not historical_config.data:
            logger.info("No historical data configured, skipping")
            return
        
        # Get current session date (from TimeManager)
        current_time = self._time_manager.get_current_time()
        current_date = current_time.date()
        
        logger.info(f"Loading historical data for session {current_date}")
        
        # Get symbols to process (already registered)
        symbols_to_process = symbols or self.session_config.session_data_config.symbols
        
        # Process each historical data configuration
        for hist_data_config in historical_config.data:
            self._load_historical_data_config(
                hist_data_config,
                current_date,
                symbols_filter=symbols_to_process  # Pass symbols filter
            )
        
        # Log statistics
        total_bars = 0
        for symbol_data in self.session_data._symbols.values():
            for interval_data in symbol_data.historical.bars.values():
                for bars_list in interval_data.data_by_date.values():
                    total_bars += len(bars_list)
        
        # Record timing
        elapsed = self.metrics.elapsed_time(start_time)
        logger.info(
            f"Historical data loaded: {total_bars} total bars across "
            f"{len(historical_config.data)} configs ({elapsed:.3f}s)"
        )
        logger.info(
            f"[SESSION_FLOW] PHASE_2.1: Complete - {total_bars} bars loaded in {elapsed:.3f}s"
        )
    
    def _generate_indicator_key(self, base_name: str, config: Dict[str, Any]) -> str:
        """Generate descriptive storage key for an indicator.
        
        Format: {base_name}_{period}
        Examples:
        - "avg_volume" + period "2d" → "avg_volume_2d"
        - "avg_volume" + period "10d" → "avg_volume_10d"
        - "max_price" + period "5d" → "max_price_5d"
        - "avg_volume" + period "390m" → "avg_volume_390m" (intraday)
        
        This allows multiple indicators with same base name but different periods.
        
        Args:
            base_name: Base indicator name from config
            config: Indicator configuration dict
        
        Returns:
            Descriptive storage key
        """
        period = config.get('period', '')
        
        if period:
            # Parse period to normalize format
            period_str = period.replace('d', 'd').replace('m', 'm')  # Keep as-is
            return f"{base_name}_{period_str}"
        else:
            # No period specified, use base name only
            return base_name
    
    def _calculate_historical_indicators(self, symbols: Optional[List[str]] = None):
        """Calculate historical indicators for specified symbols (or all if None).
        
        Tasks:
        - For each indicator in config:
          - Calculate based on type (trailing_average, trailing_max, trailing_min)
          - Store in session_data with indexed access
        - Auto-generates descriptive keys (e.g., "avg_volume_2d")
        
        Used by both pre-session initialization and mid-session insertion.
        
        Args:
            symbols: List of symbols to process, or None for all symbols from config
        
        Reference: SESSION_ARCHITECTURE.md lines 380-440
        """
        indicators = self.session_config.session_data_config.historical.indicators
        
        if not indicators:
            logger.debug("No historical indicators configured, skipping")
            return
        
        if symbols is None:
            symbols = self.session_config.session_data_config.symbols
        
        # Debug: Check what symbols are registered
        logger.debug(f"Registered symbols in session_data: {list(self.session_data._symbols.keys())}")
        
        start_time = self.metrics.start_timer()
        logger.info(f"Calculating {len(indicators)} historical indicators for {len(symbols)} symbols")
        
        # Calculate indicators per symbol
        for symbol in symbols:
            for indicator_name, indicator_config in indicators.items():
                try:
                    indicator_type = indicator_config['type']
                    period = indicator_config.get('period', '')
                    
                    # Generate descriptive storage key: base_name + period
                    # Examples: "avg_volume_2d", "max_price_10d", "avg_volume_390m"
                    storage_key = self._generate_indicator_key(indicator_name, indicator_config)
                    
                    if indicator_type == 'trailing_average':
                        result = self._calculate_trailing_average(
                            symbol,
                            indicator_name,
                            indicator_config
                        )
                    elif indicator_type == 'trailing_max':
                        result = self._calculate_trailing_max(
                            symbol,
                            indicator_name,
                            indicator_config
                        )
                    elif indicator_type == 'trailing_min':
                        result = self._calculate_trailing_min(
                            symbol,
                            indicator_name,
                            indicator_config
                        )
                    else:
                        logger.error(
                            f"Unknown indicator type '{indicator_type}' for {indicator_name}"
                        )
                        continue
                    
                    # Store in session_data with symbol and descriptive key
                    self.session_data.set_historical_indicator(symbol, storage_key, result)
                    
                    logger.info(
                        f"✓ Calculated indicator for {symbol}: '{storage_key}' = {result:.2f} "
                        f"(config_name={indicator_name}, type={indicator_type}, period={period})"
                    )
                    
                    # Verify it was stored
                    stored_value = self.session_data.get_historical_indicator(symbol, storage_key)
                    logger.debug(f"Verified stored value for {symbol}.{storage_key}: {stored_value}")
                    
                except Exception as e:
                    logger.error(
                        f"Error calculating indicator '{indicator_name}' for {symbol}: {e}",
                        exc_info=True
                    )
        
        elapsed = self.metrics.elapsed_time(start_time)
        logger.info(f"Historical indicators calculated ({elapsed:.3f}s)")
    
    def _calculate_historical_quality(self, symbols: Optional[List[str]] = None):
        """Calculate quality scores for HISTORICAL bars for specified symbols (or all if None).
        
        ARCHITECTURE:
        - Session Coordinator (this): Calculate quality on HISTORICAL bars (Phase 2)
        - Data Quality Manager: Calculate quality on CURRENT SESSION bars (during streaming)
        
        This method calculates quality on historical bars loaded from database.
        Current session bars quality is handled by DataQualityManager during streaming.
        
        Used by both pre-session initialization and mid-session insertion.
        
        Args:
            symbols: List of symbols to process, or None for all symbols from config
        """
        if symbols is None:
            symbols = self.session_config.session_data_config.symbols
        
        enable_quality = self.session_config.session_data_config.historical.enable_quality
        
        if not enable_quality:
            # Disabled: Assign 100% quality to all historical bars
            logger.info("[SESSION_FLOW] PHASE_2.3: Quality disabled, assigning 100% to historical bars")
            self._assign_perfect_quality(symbols=symbols)
            return
        
        # Enabled: Calculate actual quality and gaps on HISTORICAL bars
        logger.info(f"[SESSION_FLOW] PHASE_2.3: Calculating quality and gaps for {len(symbols)} symbols")
        start_time = self.metrics.start_timer()
        
        # Calculate quality and gaps for base intervals ONLY (1m, 1s, 1d)
        # Then propagate to derived intervals (5m, 15m, etc.)
        base_intervals = ["1m", "1s", "1d"]
        
        # Use shared method for quality and gap calculation
        for symbol in symbols:
            # Calculate quality and gaps using shared method
            self._calculate_quality_and_gaps_for_symbol(symbol, base_intervals)
            
            # Propagate base quality to derived intervals
            for interval in base_intervals:
                quality = self._get_historical_quality(symbol, interval)
                if quality is not None:
                    self._propagate_quality_to_derived_historical(symbol, interval, quality)
        
        # Calculate average quality for logging
        total_symbols = 0
        total_quality = 0.0
        for symbol in symbols:
            for interval in base_intervals:
                quality = self._get_historical_quality(symbol, interval)
                if quality is not None:
                    total_symbols += 1
                    total_quality += quality
        
        # Log summary
        if total_symbols > 0:
            avg_quality = total_quality / total_symbols
            elapsed = self.metrics.elapsed_time(start_time)
            logger.info(
                f"[SESSION_FLOW] PHASE_2.3: Historical quality/gaps: {avg_quality:.1f}% average "
                f"across {total_symbols} symbol/interval pairs ({elapsed:.3f}s)"
            )
        else:
            logger.info("[SESSION_FLOW] PHASE_2.3: No historical bars found for quality calculation")
        
        # PHASE 2.4: Generate derived historical bars from base historical bars
        # DISABLED: Historical should only contain intervals specified in historical config
        # Derived intervals (5m, 10m, etc.) are for streaming/session data, not historical
        # logger.info("[SESSION_FLOW] PHASE_2.4: Generating derived historical bars")
        # self._generate_derived_historical_bars()
        # logger.info("[SESSION_FLOW] PHASE_2.4: Complete - Derived historical bars generated")
        logger.info("[SESSION_FLOW] PHASE_2.4: Skipping derived historical bars (only load configured intervals)")
    
    def _assign_perfect_quality(self, symbols: Optional[List[str]] = None):
        """Assign 100% quality to historical bars for specified symbols (or all if None).
        
        Args:
            symbols: List of symbols to process, or None for all symbols from config
        """
        if symbols is None:
            symbols = self.session_config.session_data_config.symbols
        
        logger.info(f"[SESSION_FLOW] PHASE_2.3: Assigning perfect quality (100%) to {len(symbols)} symbols")
        
        # Set quality to 100% for all symbols/intervals in session_data
        count = 0
        for symbol in symbols:
            for interval in ["1m", "5m", "15m", "30m", "1h", "1d"]:
                self.session_data.set_quality(symbol, interval, 100.0)
                count += 1
        
        logger.info(f"[SESSION_FLOW] PHASE_2.3: Assigned 100% quality to {count} symbol/interval pairs")
        logger.debug("Assigned 100% quality to all historical bars")
    
    def _calculate_bar_quality(self, symbol: str, interval: str) -> Optional[float]:
        """Calculate quality score for HISTORICAL bars.
        
        Uses shared quality_helpers to ensure consistency with DataQualityManager.
        
        Called during Phase 2 (before session starts) to calculate quality on
        pre-loaded historical bars from database.
        
        CRITICAL Rules:
        - Gets trading hours from TimeManager for EACH historical date (never hardcoded)
        - Handles early closes and holidays correctly
        - Only counts regular trading hours
        - Uses shared interval parsing logic
        
        Quality = (actual_bars / expected_bars_full_day) * 100
        
        Args:
            symbol: Symbol to check
            interval: Interval to check (e.g., "1m", "5m", "1d")
        
        Returns:
            Quality percentage (0-100) or None if no data
        """
        logger.debug(f"[SESSION_FLOW] PHASE_2.3: Calculating quality for {symbol} {interval}")
        
        # Get historical bars (internal=True since session not active yet)
        symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
        if not symbol_data:
            logger.debug(f"No symbol data for {symbol}, quality = None")
            return None
        
        # Parse interval to get minutes equivalent (for accessing historical_bars dict)
        # Historical bars are stored by interval in minutes
        interval_minutes = None
        if isinstance(interval, int):
            interval_minutes = interval
        elif isinstance(interval, str):
            # Quick parse just to get the dict key
            if interval.endswith('m'):
                interval_minutes = int(interval[:-1])
            elif interval.endswith('s'):
                # Seconds: not stored in historical_bars (only minute+ intervals)
                logger.debug(f"Skipping quality for {symbol} {interval} (seconds not in historical)")
                return None
            elif interval.endswith('h'):
                interval_minutes = int(interval[:-1]) * 60
            elif interval.endswith('d'):
                interval_minutes = int(interval[:-1]) * 1440
            else:
                try:
                    interval_minutes = int(interval)
                except ValueError:
                    logger.warning(f"Cannot parse interval '{interval}' for {symbol}")
                    return None
        
        if interval_minutes is None:
            logger.warning(f"Cannot determine interval minutes for {symbol} {interval}")
            return None
        
        # Get historical bars for this interval
        # For daily bars, use "1d" key, not "1440m"
        if interval.endswith('d'):
            interval_key = "1d"
        else:
            interval_key = f"{interval_minutes}m" if interval_minutes else interval
        historical_interval_data = symbol_data.historical.bars.get(interval_key)
        
        if not historical_interval_data or not historical_interval_data.data_by_date:
            logger.debug(f"No historical bars for {symbol} {interval}, quality = None")
            return None
        
        if len(historical_interval_data.data_by_date) == 0:
            logger.debug(f"No historical bars for {symbol} {interval}, quality = None")
            return None
        
        # Calculate quality
        # Daily bars use different logic: (actual trading days / expected trading days) * 100
        if interval.endswith('d'):
            # For daily bars, quality = % of expected trading days that have bars
            dates_with_bars = sorted(historical_interval_data.data_by_date.keys())
            
            if len(dates_with_bars) >= 2:
                with SessionLocal() as db_session:
                    start_date = dates_with_bars[0]
                    end_date = dates_with_bars[-1]
                    
                    # Count expected trading days using unified API
                    from datetime import datetime
                    start_dt = datetime.combine(start_date, datetime.min.time())
                    end_dt = datetime.combine(end_date, datetime.max.time())
                    expected_days = self._time_manager.count_trading_time(
                        db_session,
                        start_dt,
                        end_dt,
                        unit='days',
                        exchange=self.session_config.exchange_group
                    )
                    
                    actual_days = len(dates_with_bars)
                    
                    if expected_days > 0:
                        quality = (actual_days / expected_days) * 100.0
                    else:
                        quality = 0.0
            elif len(dates_with_bars) == 1:
                # Only one day - assume 100% quality
                quality = 100.0
            else:
                logger.debug(f"No dates for {symbol} {interval}")
                return None
        else:
            # Intraday bars: calculate quality for each date, then aggregate
            total_actual_bars = 0
            total_quality_sum = 0.0
            dates_counted = 0
            
            with SessionLocal() as db_session:
                for hist_date, date_bars in historical_interval_data.data_by_date.items():
                    actual_bars_for_date = len(date_bars)
                    total_actual_bars += actual_bars_for_date
                    
                    # Calculate quality for this specific date using shared helper
                    date_quality = calculate_quality_for_historical_date(
                        time_manager=self._time_manager,
                        db_session=db_session,
                        symbol=symbol,
                        interval=interval,
                        target_date=hist_date,
                        actual_bars=actual_bars_for_date
                    )
                    
                    if date_quality is not None:
                        total_quality_sum += date_quality
                        dates_counted += 1
            
            # Calculate average quality across all dates
            if dates_counted > 0:
                quality = total_quality_sum / dates_counted
            else:
                # No dates with calculable quality (all holidays?)
                logger.debug(f"No valid trading dates for {symbol} {interval} quality")
                return None
        
        # Store quality in SessionData
        self.session_data.set_quality(symbol, interval, quality)
        
        if interval.endswith('d'):
            logger.debug(
                f"Quality for {symbol} {interval}: {quality:.1f}% "
                f"({len(dates_with_bars)} days)"
            )
        else:
            logger.debug(
                f"Quality for {symbol} {interval}: {quality:.1f}% "
                f"({total_actual_bars} bars across {dates_counted} trading dates)"
            )
        return quality
    
    def _get_historical_quality(self, symbol: str, interval: str) -> Optional[float]:
        """Get quality for historical bars from HistoricalBarIntervalData.
        
        Args:
            symbol: Symbol to check
            interval: Interval to check
        
        Returns:
            Quality percentage or None if not found
        """
        symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
        if not symbol_data:
            return None
        
        # Get interval key
        interval_key = interval
        if isinstance(interval, str):
            if interval.endswith('m'):
                interval_minutes = int(interval[:-1])
                interval_key = f"{interval_minutes}m"
            elif interval.endswith('d'):
                interval_key = "1d"
        
        hist_interval_data = symbol_data.historical.bars.get(interval_key)
        if hist_interval_data:
            return hist_interval_data.quality
        
        return None
    
    def _calculate_quality_and_gaps_for_symbol(self, symbol: str, intervals: Optional[List[str]] = None):
        """Calculate quality and detect gaps for historical bars of a symbol.
        
        This is a shared method used by both:
        - _calculate_historical_quality() (initial load, all symbols)
        - _process_pending_symbols() (mid-session add, specific symbols)
        
        For each interval:
        1. Calculate quality percentage
        2. Detect gaps in the data
        3. Store quality in HistoricalBarIntervalData.quality
        4. Store gaps in HistoricalBarIntervalData.gaps
        
        Args:
            symbol: Symbol to process
            intervals: Intervals to process. If None, uses ["1m", "1d"] (base intervals)
        """
        from app.threads.quality.gap_detection import detect_gaps
        from app.threads.quality.quality_helpers import (
            get_regular_trading_hours,
            parse_interval_to_minutes
        )
        
        # Default to base intervals if not specified
        if intervals is None:
            intervals = ["1m", "1s", "1d"]
        
        symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
        if not symbol_data:
            logger.debug(f"No symbol data for {symbol}, skipping quality/gaps")
            return
        
        for interval in intervals:
            # Calculate quality using existing method
            quality = self._calculate_bar_quality(symbol, interval)
            
            if quality is None:
                logger.debug(f"Cannot calculate quality for {symbol} {interval}")
                continue
            
            # Get historical interval data
            interval_key = interval
            if isinstance(interval, str):
                if interval.endswith('m'):
                    interval_minutes = int(interval[:-1])
                    interval_key = f"{interval_minutes}m"
                elif interval.endswith('d'):
                    interval_key = "1d"
            
            hist_interval_data = symbol_data.historical.bars.get(interval_key)
            if not hist_interval_data or not hist_interval_data.data_by_date:
                logger.debug(f"No historical bars for {symbol} {interval}")
                continue
            
            # Store quality directly in HistoricalBarIntervalData
            hist_interval_data.quality = quality
            logger.debug(f"Set historical quality for {symbol} {interval}: {quality:.1f}%")
            
            # Detect gaps
            all_gaps = []
            
            # Daily bars use different gap detection (missing trading days)
            if interval == "1d" or interval.endswith('d'):
                # For daily bars, check for missing trading days in the sequence
                dates_with_bars = sorted(hist_interval_data.data_by_date.keys())
                
                if len(dates_with_bars) >= 2:
                    with SessionLocal() as db_session:
                        # Count expected trading days between first and last date
                        start_date = dates_with_bars[0]
                        end_date = dates_with_bars[-1]
                        
                        from datetime import datetime
                        start_dt = datetime.combine(start_date, datetime.min.time())
                        end_dt = datetime.combine(end_date, datetime.max.time())
                        expected_days = self._time_manager.count_trading_time(
                            db_session, 
                            start_dt, 
                            end_dt,
                            unit='days',
                            exchange=self.session_config.exchange_group
                        )
                        actual_days = len(dates_with_bars)
                        missing_days = expected_days - actual_days
                        
                        if missing_days > 0:
                            # Create a single gap representing missing trading days
                            from app.threads.quality.gap_detection import GapInfo
                            from datetime import datetime, time
                            
                            gap = GapInfo(
                                symbol=symbol,
                                start_time=datetime.combine(start_date, time(0, 0)),
                                end_time=datetime.combine(end_date, time(23, 59)),
                                bar_count=missing_days
                            )
                            all_gaps.append(gap)
                            
                            logger.debug(
                                f"{symbol} {interval}: {missing_days} missing trading days "
                                f"between {start_date} and {end_date}"
                            )
            else:
                # Intraday bars (minute intervals) - detect gaps within each day
                with SessionLocal() as db_session:
                    for hist_date, bars in hist_interval_data.data_by_date.items():
                        if not bars:
                            continue
                        
                        # Get trading hours for this date
                        hours = get_regular_trading_hours(self._time_manager, db_session, hist_date)
                        
                        if not hours:
                            logger.debug(f"No trading hours for {symbol} on {hist_date}")
                            continue
                        
                        session_start, session_end = hours
                        
                        # Parse interval to minutes
                        trading_session = self._time_manager.get_trading_session(db_session, hist_date)
                        interval_minutes = parse_interval_to_minutes(interval, trading_session)
                        
                        if interval_minutes is None:
                            logger.warning(f"Cannot parse interval {interval} for gap detection")
                            continue
                        
                        # Detect gaps for this date
                        date_gaps = detect_gaps(
                            symbol=symbol,
                            session_start=session_start,
                            current_time=session_end,
                            existing_bars=bars,
                            interval_minutes=interval_minutes
                        )
                        
                        all_gaps.extend(date_gaps)
            
            # Store gaps in HistoricalBarIntervalData
            hist_interval_data.gaps = all_gaps
            
            if all_gaps:
                total_missing = sum(g.bar_count for g in all_gaps)
                logger.info(
                    f"{symbol} {interval} historical: {quality:.1f}% quality | "
                    f"{len(all_gaps)} gaps ({total_missing} missing bars)"
                )
            else:
                logger.info(f"{symbol} {interval} historical: {quality:.1f}% quality | No gaps")
    
    def _generate_derived_historical_bars(self):
        """Generate derived historical bars from base historical bars.
        
        For each symbol with historical base bars (1m):
        1. Get all 1m historical bars across all dates
        2. Generate derived intervals (5m, 10m, etc.) if in _generated_data
        3. Store in historical_bars with same date structure
        4. Quality already set by _propagate_quality_to_derived_historical
        """
        from app.managers.data_manager.derived_bars import compute_derived_bars
        
        for symbol in self.session_config.session_data_config.symbols:
            # internal=True since session not active yet (Phase 2)
            symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
            if not symbol_data:
                continue
            
            # Get intervals we should generate for this symbol (query from SessionData)
            intervals_to_generate = [interval for interval, data in symbol_data.bars.items() if data.derived]
            if not intervals_to_generate:
                continue
            
            # Get 1m historical bars (base for derived generation)
            hist_1m_data = symbol_data.historical.bars.get("1m")
            if not hist_1m_data or not hist_1m_data.data_by_date:
                logger.debug(f"No 1m historical bars for {symbol}, skipping derived generation")
                continue
            
            # Generate each derived interval
            for interval_str in intervals_to_generate:
                if not interval_str.endswith('m'):
                    continue  # Skip non-minute intervals
                
                interval_int = int(interval_str[:-1])
                if interval_int == 1:
                    continue  # Skip 1m itself
                
                # For each date, generate derived bars from that date's 1m bars
                for hist_date, bars_1m in hist_1m_data.data_by_date.items():
                    if not bars_1m:
                        continue
                    
                    # Generate derived bars for this date
                    derived_bars = compute_derived_bars(
                        bars_1m,
                        source_interval="1m",
                        target_interval=f"{interval_int}m"
                    )
                    
                    if derived_bars:
                        # Store in historical.bars with same date structure
                        interval_key = f"{interval_int}m"
                        if interval_key not in symbol_data.historical.bars:
                            from app.managers.data_manager.session_data import HistoricalBarIntervalData
                            symbol_data.historical.bars[interval_key] = HistoricalBarIntervalData()
                        symbol_data.historical.bars[interval_key].data_by_date[hist_date] = derived_bars
                        
                        logger.debug(
                            f"Generated {len(derived_bars)} {interval_str} historical bars "
                            f"for {symbol} on {hist_date}"
                        )
    
    def _propagate_quality_to_derived_historical(self, symbol: str, base_interval: str, base_quality: float):
        """Copy quality from base historical bars to derived historical bars.
        
        ARCHITECTURE: Derived bars get quality copied from base bars.
        Session coordinator propagates for historical bars, data quality manager for current session.
        
        Args:
            symbol: Symbol to propagate quality for
            base_interval: Base interval (e.g., "1m")
            base_quality: Quality percentage from base interval
        """
        # internal=True since session not active yet (Phase 2)
        symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
        if not symbol_data:
            return
        
        # Derived intervals to propagate to (if they exist in historical_bars)
        derived_intervals = ["5m", "15m", "30m", "1h"]
        
        for derived_interval in derived_intervals:
            # Parse to int for historical_bars dict key
            if derived_interval.endswith('m'):
                interval_int = int(derived_interval[:-1])
            elif derived_interval.endswith('h'):
                interval_int = int(derived_interval[:-1]) * 60
            else:
                continue
            
            # Check if this derived interval has historical data
            interval_key = f"{interval_int}m"
            hist_interval_data = symbol_data.historical.bars.get(interval_key)
            if hist_interval_data and hist_interval_data.data_by_date:
                # Copy base quality to derived interval
                self.session_data.set_quality(symbol, derived_interval, base_quality)
                logger.debug(
                    f"Propagated historical quality {base_quality:.1f}% from {symbol} {base_interval} "
                    f"to {derived_interval}"
                )
    
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
    
    def _load_queues(self, symbols: Optional[List[str]] = None):
        """Load queues with data for streaming phase (for specified symbols or all).
        
        Backtest: Load current session day data into queues
        Live: Start API streams
        
        Uses stream/generate marking from _mark_stream_generate() to know
        what data to load vs what will be generated by data_processor.
        
        Used by both pre-session initialization and mid-session insertion.
        
        Args:
            symbols: List of symbols to load, or None for all symbols from config
        """
        if symbols is None:
            symbols_desc = "all symbols"
        else:
            symbols_desc = f"{len(symbols)} symbols"
        
        logger.info(f"[SESSION_FLOW] PHASE_3.1: Loading queues for {symbols_desc} (mode={self.mode})")
        start_time = self.metrics.start_timer()
        
        if self.mode == "backtest":
            logger.info(f"[SESSION_FLOW] PHASE_3.1: Backtest mode - loading queues for {symbols_desc}")
            self._load_backtest_queues(symbols=symbols)
            logger.info("[SESSION_FLOW] PHASE_3.1: Backtest queues loaded")
        else:  # live mode
            logger.info("[SESSION_FLOW] PHASE_3.1: Live mode - starting live streams")
            self._start_live_streams(symbols=symbols)
            logger.info("[SESSION_FLOW] PHASE_3.1: Live streams started")
        
        elapsed = self.metrics.elapsed_time(start_time)
        logger.info(f"Queues loaded ({elapsed:.3f}s)")
        logger.info(f"[SESSION_FLOW] PHASE_3.1: Complete - Queues loaded in {elapsed:.3f}s")
    
    def _load_backtest_queues(self, symbols: Optional[List[str]] = None):
        """Load current session day data into queues for backtest mode.
        
        This method populates queues with bar data from the database
        for the current trading day.
        
        Uses DataManager to fetch bars for each symbol and interval
        that is marked as STREAMED.
        
        Args:
            symbols: Symbols to process. If None, uses all from config.
        
        Reference: SESSION_ARCHITECTURE.md lines 1738-1747
        """
        from collections import deque
        from datetime import datetime, time
        from app.models.database import SessionLocal
        
        logger.info("[SESSION_FLOW] PHASE_3.2: Loading backtest queues")
        
        current_time = self._time_manager.get_current_time()
        current_date = current_time.date()
        
        # BACKTEST: Only load current session date (not prefetch days)
        # Simpler and cleaner - load one day at a time
        start_date = current_date
        end_date = current_date  # Only today's bars
        
        symbols_to_process = symbols or self.session_config.session_data_config.symbols
        
        logger.info(
            f"[SESSION_FLOW] PHASE_3.2: Loading queue for {len(symbols_to_process)} symbols on {current_date}"
        )
        logger.info(
            f"Loading backtest queue: {current_date} (single day)"
        )
        
        # Load bars for each streamed symbol/interval
        total_streams = 0
        total_bars = 0
        
        for symbol in symbols_to_process:
            streamed_intervals = self._get_streamed_intervals_for_symbol(symbol)
            
            if not streamed_intervals:
                logger.warning(f"{symbol}: No streamed intervals to load")
                continue
            
            # Load each streamed interval
            for interval in streamed_intervals:
                try:
                    # Classify interval type
                    is_bar_interval = interval in ["1s", "1m", "5m", "15m", "30m", "1h", "1d"]
                    is_quotes = interval == "quotes"
                    is_ticks = interval == "ticks"
                    
                    # Skip non-data types
                    if not (is_bar_interval or is_quotes or is_ticks):
                        logger.warning(
                            f"[SESSION_FLOW] PHASE_3.2: Unknown interval type {symbol} {interval}"
                        )
                        continue
                    
                    # Ticks not supported in backtest (should already be filtered)
                    if is_ticks:
                        logger.debug(
                            f"[SESSION_FLOW] PHASE_3.2: Skipping ticks {symbol} (not supported in backtest)"
                        )
                        continue
                    
                    logger.info(
                        f"[SESSION_FLOW] PHASE_3.2: Loading {symbol} {interval} queue: "
                        f"{start_date} to {end_date}"
                    )
                    
                    # Convert dates to datetimes (naive - timezone handled by data_manager)
                    start_dt = datetime.combine(start_date, time(0, 0))
                    end_dt = datetime.combine(end_date, time(23, 59, 59))
                    
                    # Load data from DataManager
                    with SessionLocal() as db_session:
                        if is_bar_interval:
                            bars = self._data_manager.get_bars(
                                session=db_session,
                                symbol=symbol,
                                start=start_dt,
                                end=end_dt,
                                interval=interval,
                                regular_hours_only=True  # Filter to 09:30-16:00 only
                            )
                        elif is_quotes:
                            # TODO: Implement quotes loading when available
                            logger.warning(
                                f"[SESSION_FLOW] PHASE_3.2: Quotes loading not yet implemented for {symbol}, skipping"
                            )
                            continue
                    
                    # Check availability
                    if not bars:
                        if is_bar_interval:
                            # Bar intervals REQUIRED - abort if missing
                            error_msg = (
                                f"CRITICAL: Bar interval {interval} requested for {symbol} "
                                f"but NO DATA available in database for range {start_date} to {end_date}. "
                                f"Backtest cannot proceed without base bar data."
                            )
                            logger.error(f"[SESSION_FLOW] PHASE_3.2.ERROR: {error_msg}")
                            raise RuntimeError(error_msg)
                        elif is_quotes:
                            # Quotes OPTIONAL - warn and continue
                            logger.warning(
                                f"[SESSION_FLOW] PHASE_3.2: Quotes requested for {symbol} "
                                f"but not available in database, continuing without quotes"
                            )
                            continue
                    
                    
                    # Store in queue (deque for efficient popleft)
                    queue_key = (symbol, interval)
                    self._bar_queues[queue_key] = deque(bars)
                    
                    # DEBUG: Log each bar loaded into queue
                    logger.info(
                        f"[SESSION_FLOW] PHASE_3.2: Loaded {len(bars)} bars for {symbol} {interval}"
                    )
                    logger.info(f"[QUEUE_LOAD] {symbol} {interval}: Loading {len(bars)} bars into queue")
                    
                    prev_ts = None
                    for idx, bar in enumerate(bars, 1):
                        marker = " ⚠️ DUPLICATE!" if bar.timestamp == prev_ts else ""
                        logger.debug(
                            f"[QUEUE_LOAD] {symbol} {interval} #{idx}: {bar.timestamp}{marker}"
                        )
                        prev_ts = bar.timestamp
                    
                    total_streams += 1
                    total_bars += len(bars)
                    
                except Exception as e:
                    logger.error(
                        f"[SESSION_FLOW] PHASE_3.2.ERROR: Failed to load {symbol} {interval}: {e}"
                    )
                    # Re-raise to abort backtest on critical errors
                    raise
        
        logger.info(f"[SESSION_FLOW] PHASE_3.2: Complete - Loaded {total_bars} bars across {total_streams} streams")
        logger.info(f"Loaded {total_streams} backtest streams with {total_bars} total bars")
    
    def _start_live_streams(self):
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
                    # self._data_manager.start_live_stream(
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
        Now queries SessionData for base intervals (those with derived=False).
        
        Args:
            symbol: Symbol to query
        
        Returns:
            List of streamed intervals (e.g., ["1m"])
        """
        # Query SessionData for base (non-derived) intervals
        symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
        if not symbol_data:
            return []
        
        # Return intervals that are not derived (i.e., streamed)
        streamed = [interval for interval, data in symbol_data.bars.items() if not data.derived]
        return streamed
    
    def _get_date_plus_trading_days(
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
        with SessionLocal() as session:
            end_date = self._time_manager.get_next_trading_date(
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
    # Phase 4: Session Activation
    # =========================================================================
    
    def _activate_session(self):
        """Signal session is active and ready for streaming."""
        logger.info("[SESSION_FLOW] PHASE_4.1: Activating session")
        self._session_active = True
        self._session_start_time = self.metrics.start_timer()
        self.session_data.set_session_active(True)
        
        # Notify scanner manager that session has started
        self._scanner_manager.on_session_start()
        logger.info("[SESSION_FLOW] PHASE_4.1a: Scanner manager notified of session start")
        
        logger.info("Session activated")
        logger.info("[SESSION_FLOW] PHASE_4.1: Complete - Session active")
    
    # =========================================================================
    # Symbol Processing - Pending Symbols
    # =========================================================================
    
    def _load_symbols_mid_session(
        self,
        symbols: List[str],
        added_by: str = "strategy"
    ):
        """Load specific symbols mid-session (mirrors _load_session_data).
        
        Phase 7 Enhancement: FULL CODE REUSE with pre-session initialization!
        Phase 8: Enhanced with metadata tracking.
        
        This is IDENTICAL to Phase 2 initialization, just for specific symbols.
        Uses exact same coordination methods with optional symbols parameter.
        
        Args:
            symbols: List of symbols to load
            added_by: Source of addition ("strategy", "scanner", "manual")
        """
        logger.info(f"Loading {len(symbols)} symbols mid-session (using coordination methods, added_by={added_by})")
        
        # Step 1: Register symbols with full session-config metadata
        for symbol in symbols:
            # Check if upgrading from adhoc
            existing = self.session_data.get_symbol_data(symbol)
            if existing and not existing.meets_session_config_requirements:
                logger.info(f"{symbol}: Upgrading from adhoc to full session-config")
                # Update metadata on existing object
                existing.meets_session_config_requirements = True
                existing.upgraded_from_adhoc = True
                existing.added_by = added_by
            else:
                # New symbol - register with full metadata
                self._register_single_symbol(
                    symbol,
                    meets_session_config_requirements=True,
                    added_by=added_by,
                    auto_provisioned=False
                )
        
        # Step 2: Load historical data (REUSE!)
        self._manage_historical_data(symbols=symbols)
        
        # Step 3: Register indicators (REUSE!)
        self._register_session_indicators(symbols=symbols)
        
        # Step 4: Calculate historical indicators (REUSE!)
        self._calculate_historical_indicators(symbols=symbols)
        
        # Step 5: Load queues (REUSE!)
        self._load_queues(symbols=symbols)  # Wrapper that calls _load_backtest_queues
        
        # Step 6: Calculate quality (REUSE!)
        self._calculate_historical_quality(symbols=symbols)
        
        logger.info(f"✓ Loaded {len(symbols)} symbols mid-session (100% code reuse, meets_config_req=True)")
    
    def _process_pending_symbols(self):
        """Process pending symbols using FULL COORDINATION METHOD REUSE (Phase 7 final).
        
        Uses exact same flow as Phase 2 initialization via _load_symbols_mid_session().
        Maximum code reuse: 98% shared with pre-session flow.
        
        No manual session deactivation - streaming loop handles it automatically
        based on data lag.
        """
        # Get pending (thread-safe)
        with self._symbol_operation_lock:
            pending = list(self._pending_symbols)
            self._pending_symbols.clear()
        
        if not pending:
            return
        
        logger.info(f"[SYMBOL] Processing {len(pending)} pending symbols: {pending}")
        
        # Pause streaming to safely modify queues
        self._stream_paused.clear()
        import time
        time.sleep(0.1)
        
        try:
            # Call coordination method (100% REUSE!)
            gap_start = self.metrics.start_timer()
            self._load_symbols_mid_session(pending)
            self.metrics.record_session_gap(gap_start)
            
            logger.info(f"[SYMBOL] ✓ Loaded {len(pending)} symbols (full coordination method reuse)")
            
        except Exception as e:
            logger.error(f"[SYMBOL] Error loading symbols: {e}", exc_info=True)
        finally:
            # Resume streaming
            self._stream_paused.set()
            logger.info("[SYMBOL] Streaming resumed - lag detection will manage session state")
    
    # =========================================================================
    # Phase 5: Streaming Phase
    # =========================================================================
    
    def _streaming_phase(self):
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
        # Get current time and date from TimeManager
        current_time = self._time_manager.get_current_time()
        current_date = current_time.date()
        
        # Get market hours from TimeManager (timezone-aware datetime objects)
        with SessionLocal() as session:
            market_hours = self._time_manager.get_market_hours_datetime(
                session,
                current_date,
                exchange=self.session_config.exchange_group
            )
        
        if not market_hours:
            logger.warning(f"[SESSION_FLOW] PHASE_5.ERROR: No trading session for {current_date}")
            logger.warning(f"No trading session for {current_date}, skipping streaming")
            return
        
        market_open, market_close = market_hours
        
        # Store market hours for filtering during bar processing
        self._market_open = market_open
        self._market_close = market_close
        
        logger.info(
            f"[SESSION_FLOW] PHASE_5.1: Market hours: {market_open.time()} to {market_close.time()}"
        )
        logger.info(
            f"Streaming phase: {market_open.time()} to {market_close.time()}"
        )
        
        # Clock-driven mode: Set time to market open and drop pre-market data
        if self.mode == "backtest" and self.session_config.backtest_config:
            speed_multiplier = self.session_config.backtest_config.speed_multiplier
            if speed_multiplier > 0:
                logger.info(
                    f"[SESSION_FLOW] PHASE_5.2: Clock-driven mode (speed={speed_multiplier}x) - "
                    f"setting time to market open and dropping pre-market data"
                )
                
                # Set time to market open
                self._time_manager.set_backtest_time(market_open)
                logger.info(f"[SESSION_FLOW] PHASE_5.2: Time set to market open: {market_open.time()}")
                
                # Drop any queue data before market open
                dropped_count = self._drop_pre_market_data(market_open)
                if dropped_count > 0:
                    logger.info(
                        f"[SESSION_FLOW] PHASE_5.2: Dropped {dropped_count} bars before market open"
                    )
                else:
                    logger.info("[SESSION_FLOW] PHASE_5.2: No pre-market data to drop")
        
        # Streaming loop
        iteration = 0
        total_bars_processed = 0
        
        while not self._stop_event.is_set():
            iteration += 1
            current_time = self._time_manager.get_current_time()
            
            # CHECK: Process pending symbols (Phase 3: Dynamic symbols)
            if self.mode == "backtest":
                self._process_pending_symbols()
            
            # CHECK: Execute scheduled scans (Scanner Framework)
            self._scanner_manager.check_and_execute_scans()
            
            # CHECK: Wait if streaming is paused (Phase 4: Dynamic symbols)
            if self.mode == "backtest":
                # Wait until resume signal (blocks until _stream_paused is set)
                self._stream_paused.wait()
            
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
            
            # Determine next time based on mode
            if self.mode == "backtest" and self.session_config.backtest_config:
                speed_multiplier = self.session_config.backtest_config.speed_multiplier
                
                if speed_multiplier == 0:
                    # DATA-DRIVEN: Jump to next bar timestamp
                    next_timestamp = self._get_next_queue_timestamp()
                    
                    if next_timestamp is None:
                        # All queues exhausted - advance to market close and end
                        logger.info(
                            f"[{iteration}] Data-driven: All queues empty, advancing to market close"
                        )
                        self._time_manager.set_backtest_time(market_close)
                        break
                    
                    # Advance to next bar timestamp
                    # Bar timestamp is CLOSE time: bar at 09:35 = period [09:30-09:35)
                    # Setting time to 09:35 means the bar is complete and ready to process
                    next_time = next_timestamp
                    logger.debug(
                        f"[{iteration}] Data-driven advance: {current_time.time()} -> "
                        f"{next_time.time()}"
                    )
                else:
                    # CLOCK-DRIVEN: Advance by fixed 1-minute intervals
                    next_time = current_time + timedelta(minutes=1)
                    logger.debug(
                        f"[{iteration}] Clock-driven advance: {current_time.time()} -> "
                        f"{next_time.time()}"
                    )
            else:
                # Default: 1-minute intervals
                next_time = current_time + timedelta(minutes=1)
            
            # Check if next time exceeds market close
            if next_time > market_close:
                # Advance to market close and end
                logger.info(
                    f"Next time ({next_time.time()}) beyond market close "
                    f"({market_close.time()}), advancing to close"
                )
                self._time_manager.set_backtest_time(market_close)
                break
            
            # Advance time
            self._time_manager.set_backtest_time(next_time)
            
            # Process ALL bars with timestamp <= next_time
            # This handles gaps gracefully (processes multiple bars if they exist,
            # processes none if data gap)
            bars_processed = self._process_queue_data_at_timestamp(
                next_time
            )
            total_bars_processed += bars_processed
            
            if bars_processed > 0:
                logger.debug(f"Processed {bars_processed} bars at {next_time.time()}")
            
            # Mode-specific behavior after processing
            if self.mode == "backtest" and self.session_config.backtest_config:
                speed_multiplier = self.session_config.backtest_config.speed_multiplier
                
                if speed_multiplier == 0:
                    # DATA-DRIVEN: Wait for processor to finish before continuing
                    # This ensures synchronization - coordinator doesn't push more data
                    # until processor signals it's ready
                    if bars_processed > 0 and self._processor_subscription:
                        logger.debug(
                            f"[DATA-DRIVEN] Waiting for processor to finish "
                            f"{bars_processed} bars..."
                        )
                        # Block until processor signals ready
                        self._processor_subscription.wait_until_ready()
                        self._processor_subscription.reset()
                        logger.debug("[DATA-DRIVEN] Processor ready, continuing")
                else:
                    # CLOCK-DRIVEN: Apply delay to simulate real-time
                    self._apply_clock_driven_delay(speed_multiplier)
            
            # Periodic logging (every 100 iterations)
            if iteration % 100 == 0:
                current_time = self._time_manager.get_current_time()
                logger.info(
                    f"Streaming iteration {iteration}: {current_time.time()}"
                )
        
        # Final time check and metrics
        final_time = self._time_manager.get_current_time()
        logger.info(
            f"[SESSION_FLOW] PHASE_5.SUMMARY: {iteration} iterations, "
            f"{total_bars_processed} bars, final time = {final_time.time()}"
        )
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
    
    def _deactivate_session(self):
        """Phase 4: Deactivate session and record metrics (NO cleanup).
        
        MODIFIED (Phase 4): Renamed from _end_session, removed cleanup logic.
        - Clearing happens in Phase 1 (_teardown_and_cleanup)
        - Clock advancing happens in Phase 1 (_teardown_and_cleanup)
        
        Tasks:
        - Deactivate session
        - Record metrics
        - Leave data INTACT for analysis
        """
        # 1. Deactivate session
        self._session_active = False
        self.session_data.set_session_active(False)
        
        # Notify scanner manager that session has ended
        self._scanner_manager.on_session_end()
        logger.debug("Scanner manager notified of session end")
        
        logger.info("Session deactivated")
        
        # 2. Record session metrics
        if self._session_start_time is not None:
            self.metrics.record_session_duration(self._session_start_time)
            logger.debug("Session duration recorded")
        
        # 3. Increment trading days counter
        self.metrics.increment_trading_days()
        
        # 4. Get current session date for logging
        current_time = self._time_manager.get_current_time()
        current_date = current_time.date()
        
        logger.info(f"Session {current_date} ended - data preserved for analysis")
        
        # REMOVED: clear_session_bars() - moved to Phase 1
        # REMOVED: _advance_to_next_trading_day() - moved to Phase 1
    
    def _end_session(self):
        """DEPRECATED: Use _deactivate_session() instead.
        
        Kept for backwards compatibility during migration.
        """
        logger.warning("_end_session() is deprecated, use _deactivate_session()")
        self._deactivate_session()
    
    def _advance_to_next_trading_day(self, current_date: date):
        """Advance time to next trading day's market open.
        
        Args:
            current_date: Current session date
        """
        # Find next trading date
        with SessionLocal() as session:
            next_date = self._time_manager.get_next_trading_date(
                session,
                current_date,
                exchange=self.session_config.exchange_group
            )
        
        if next_date is None:
            # No more trading days - backtest complete
            logger.info("No more trading days, backtest complete")
            self._backtest_complete = True
            return
        
        # Check if we've exceeded backtest end date
        # Use TimeManager as single source of truth (not config)
        end_date = self._time_manager.backtest_end_date
        
        if next_date > end_date:
            logger.info(
                f"Next trading date {next_date} exceeds backtest end {end_date}, "
                "backtest complete"
            )
            self._backtest_complete = True
            return
        
        # Get next session's market open time
        with SessionLocal() as session:
            next_session = self._time_manager.get_trading_session(
                session,
                next_date,
                exchange=self.session_config.exchange_group
            )
        
        if not next_session or next_session.is_holiday:
            logger.warning(
                f"Next date {next_date} is not a trading day, searching further"
            )
            # Recursively find next valid trading day
            self._advance_to_next_trading_day(next_date)
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
            
            # Use TimeManager as single source of truth (not config)
            end_date = self._time_manager.backtest_end_date
            
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
    
    def _validate_stream_requirements(self) -> bool:
        """Validate stream configuration and data availability (ONCE only).
        
        Phase 2 - BEFORE LOOP: Validates but does NOT register symbols.
        
        Uses stream requirements coordinator to:
        1. Validate configuration format
        2. Analyze requirements to determine base interval
        3. Validate Parquet data availability (backtest mode)
        
        Stores validation results in instance variables for later use:
        - self._base_interval
        - self._derived_intervals_validated
        - self._streams_validated
        
        Returns:
            True if validation passed, False if failed
        """
        if self.mode != "backtest":
            # Live mode: no Parquet validation needed
            logger.info("Live mode: stream validation skipped (no Parquet check needed)")
            self._streams_validated = True
            # In live mode, we'll determine intervals during registration
            return True
        
        logger.info("=" * 70)
        logger.info("STREAM REQUIREMENTS VALIDATION (Backtest Mode)")
        logger.info("=" * 70)
        
        # Create coordinator
        coordinator = StreamRequirementsCoordinator(
            session_config=self.session_config,
            time_manager=self._time_manager
        )
        
        # Create data checker using DataManager API
        data_manager = self._system_manager.get_data_manager()
        data_checker = create_data_manager_checker(data_manager)
        
        # Validate requirements
        result = coordinator.validate_requirements(data_checker)
        
        if not result.valid:
            logger.error("=" * 70)
            logger.error("STREAM REQUIREMENTS VALIDATION FAILED")
            logger.error("=" * 70)
            logger.error(result.error_message)
            logger.error("=" * 70)
            logger.error("Cannot start session: validation failed")
            logger.error("Suggestions:")
            logger.error("  1. Check data availability: Is required data downloaded?")
            logger.error("  2. Check date range: Does backtest window have data?")
            logger.error("  3. Check config: Are stream intervals correct?")
            logger.error("=" * 70)
            return False
        
        logger.info("=" * 70)
        logger.info("✓ STREAM REQUIREMENTS VALIDATION PASSED")
        logger.info(f"  Stream base interval: {result.required_base_interval}")
        logger.info(f"  Generate derived: {result.derivable_intervals}")
        logger.info("=" * 70)
        
        # Store results for later use (during symbol registration)
        self._base_interval = result.required_base_interval
        self._derived_intervals_validated = result.derivable_intervals
        self._streams_validated = True
        
        logger.info("Validation results stored for symbol registration")
        
        return True
    
    # =========================================================================
    # Phase 5a: Unified Requirement Analysis (Three-Phase Pattern)
    # =========================================================================
    
    def _analyze_requirements(
        self,
        operation_type: str,
        symbol: str,
        source: str,
        **kwargs
    ) -> ProvisioningRequirements:
        """Phase 1: Unified requirement analysis for ANY addition operation.
        
        This is the DISPATCHER for the three-phase unified provisioning pattern.
        ALL additions (symbols, bars, indicators) from ALL sources (config, scanner,
        strategy) go through this method.
        
        Three-Phase Pattern:
            1. REQUIREMENT ANALYSIS (this method) → Determines what's needed
            2. VALIDATION (caller uses validation_result) → Checks if possible
            3. PROVISIONING (caller uses provisioning_steps) → Executes plan
        
        Args:
            operation_type: What to add ("symbol", "bar", "indicator")
            symbol: Symbol to operate on
            source: Who is adding ("config", "scanner", "strategy")
            **kwargs: Operation-specific arguments
                For "indicator": indicator_config (IndicatorConfig)
                For "bar": interval (str), days (int), historical_only (bool)
                For "symbol": None (infers from config)
        
        Returns:
            ProvisioningRequirements with complete analysis
        
        Code Reuse:
            - REUSES: analyze_indicator_requirements() for indicators
            - REUSES: parse_interval() + determine_required_base() for bars
            - REUSES: Session config for symbol requirements
            - REUSES: _validate_symbol_for_loading() for validation
        """
        logger.debug(f"[ANALYZE] {operation_type.upper()} for {symbol} (source={source})")
        
        # Create requirements object
        req = ProvisioningRequirements(
            operation_type=operation_type,
            source=source,
            symbol=symbol.upper(),
            added_by=source
        )
        
        # Phase 1: Check existing state (INFER from structure)
        existing = self.session_data.get_symbol_data(symbol)
        req.symbol_exists = existing is not None
        req.symbol_data = existing
        
        if existing:
            req.intervals_exist = {interval: True for interval in existing.bars.keys()}
            logger.debug(f"[ANALYZE] {symbol}: Symbol exists with intervals={list(existing.bars.keys())}")
        
        # Phase 2: Analyze by operation type
        if operation_type == "indicator":
            self._analyze_indicator_requirements(req, **kwargs)
        elif operation_type == "bar":
            self._analyze_bar_requirements(req, **kwargs)
        elif operation_type == "symbol":
            self._analyze_symbol_requirements(req)
        else:
            req.can_proceed = False
            req.validation_errors.append(f"Unknown operation_type: {operation_type}")
            return req
        
        # Phase 3: Validate (REUSE Step 0 validation for symbols/bars)
        if operation_type in ["symbol", "bar"]:
            validation_result = self._validate_symbol_for_loading(symbol)
            req.validation_result = validation_result
            req.can_proceed = validation_result.can_proceed
            
            if not validation_result.can_proceed:
                req.validation_errors.append(validation_result.reason)
        else:
            # Lightweight validation for indicators
            req.can_proceed = len(req.validation_errors) == 0
        
        # Phase 4: Determine provisioning steps
        self._determine_provisioning_steps(req)
        
        # Phase 5: Set metadata flags
        req.meets_session_config_requirements = (source == "config")
        req.auto_provisioned = (not req.symbol_exists and source != "config")
        
        logger.info(
            f"[ANALYZE] {symbol}: {operation_type} analysis complete - "
            f"can_proceed={req.can_proceed}, steps={len(req.provisioning_steps)}"
        )
        
        return req
    
    def _analyze_indicator_requirements(
        self,
        req: ProvisioningRequirements,
        indicator_config,
        **kwargs
    ):
        """Analyze indicator-specific requirements.
        
        REUSES: analyze_indicator_requirements() from requirement_analyzer
        """
        from app.threads.quality.requirement_analyzer import analyze_indicator_requirements
        
        # REUSE existing analyzer (uses TimeManager internally!)
        indicator_reqs = analyze_indicator_requirements(
            indicator_config=indicator_config,
            system_manager=self._system_manager,
            warmup_multiplier=2.0,
            from_date=None,  # Uses TimeManager.get_current_time()
            exchange="NYSE"
        )
        
        req.indicator_config = indicator_config
        req.indicator_requirements = indicator_reqs
        req.required_intervals = indicator_reqs.required_intervals
        req.historical_bars = indicator_reqs.historical_bars
        req.historical_days = indicator_reqs.historical_days
        req.needs_historical = indicator_reqs.historical_days > 0
        req.needs_session = True
        req.reason = indicator_reqs.reason
        
        if len(req.required_intervals) > 1:
            req.base_interval = req.required_intervals[0]
    
    def _analyze_bar_requirements(
        self,
        req: ProvisioningRequirements,
        interval: str,
        days: int = 0,
        historical_only: bool = False,
        **kwargs
    ):
        """Analyze bar-specific requirements.
        
        REUSES: parse_interval() + determine_required_base() from requirement_analyzer
        """
        from app.threads.quality.requirement_analyzer import parse_interval, determine_required_base
        
        try:
            interval_info = parse_interval(interval)
        except ValueError as e:
            req.can_proceed = False
            req.validation_errors.append(f"Invalid interval: {e}")
            return
        
        req.required_intervals = [interval]
        
        if not interval_info.is_base:
            base_interval = determine_required_base(interval)
            if base_interval:
                req.required_intervals.insert(0, base_interval)
                req.base_interval = base_interval
        
        req.historical_days = days
        req.needs_historical = days > 0
        req.needs_session = not historical_only
        req.reason = f"Bar {interval} requires intervals={req.required_intervals}, {days} days historical"
    
    def _analyze_symbol_requirements(self, req: ProvisioningRequirements):
        """Analyze symbol-specific requirements.
        
        INFERS requirements from session config (Single Source of Truth).
        """
        config = self.session_config.session_data_config
        
        # INFER intervals from config
        req.required_intervals = list(config.streams)
        
        if hasattr(config, 'derived_intervals') and config.derived_intervals:
            req.required_intervals.extend(config.derived_intervals)
        elif self._derived_intervals_validated:
            req.required_intervals.extend(self._derived_intervals_validated)
        
        req.base_interval = self._base_interval or "1m"
        
        # INFER historical from config
        if config.historical.enabled and config.historical.data:
            first_config = config.historical.data[0]
            req.historical_days = first_config.trailing_days
            req.needs_historical = True
        
        req.needs_session = True
        req.reason = f"Symbol requires intervals={req.required_intervals}, {req.historical_days} days historical"
    
    def _determine_provisioning_steps(self, req: ProvisioningRequirements):
        """Determine provisioning steps based on requirements and existing state.
        
        INFERS steps from structure analysis (what exists vs what's needed).
        """
        steps = []
        
        # Step 1: Symbol provisioning
        if not req.symbol_exists:
            steps.append("create_symbol")
        elif req.symbol_data and not req.symbol_data.meets_session_config_requirements:
            if req.source in ["config", "strategy"]:
                steps.append("upgrade_symbol")
        
        # Step 2: Interval provisioning
        for interval in req.required_intervals:
            if interval not in req.intervals_exist:
                steps.append(f"add_interval_{interval}")
        
        # Step 3: Historical provisioning
        if req.needs_historical:
            if req.source == "config" or req.historical_days > 0:
                steps.append("load_historical")
        
        # Step 4: Session provisioning
        if req.needs_session:
            steps.append("load_session")
        
        # Step 5: Indicator provisioning
        if req.indicator_config:
            steps.append("register_indicator")
        
        # Step 6: Quality calculation (only for full loading)
        if req.source == "config" and req.needs_historical:
            steps.append("calculate_quality")
        
        req.provisioning_steps = steps
    
    # =========================================================================
    # Phase 5b: Unified Provisioning Executor (Orchestrates Step 3 Loading)
    # =========================================================================
    
    def _execute_provisioning(self, req: ProvisioningRequirements) -> bool:
        """Phase 3: Execute provisioning plan from requirement analysis.
        
        This is the EXECUTOR for the three-phase unified provisioning pattern.
        It takes the provisioning plan from Phase 1 (requirement analysis) and
        Phase 2 (validation) and executes it by orchestrating existing Step 3
        loading methods.
        
        Three-Phase Pattern:
            1. REQUIREMENT ANALYSIS → Creates ProvisioningRequirements
            2. VALIDATION → Populates can_proceed
            3. PROVISIONING (this method) → Executes provisioning_steps
        
        Args:
            req: ProvisioningRequirements with complete analysis and plan
        
        Returns:
            True if provisioning succeeded, False otherwise
        
        Code Reuse:
            - REUSES: _register_single_symbol() from Phases 1-4
            - REUSES: _manage_historical_data() existing method
            - REUSES: _register_session_indicators() existing method
            - REUSES: _load_queues() existing method
            - REUSES: _calculate_historical_quality() existing method
        
        Provisioning Steps:
            - "create_symbol": Create new SymbolSessionData with metadata
            - "upgrade_symbol": Upgrade adhoc symbol to full
            - "add_interval_{interval}": Add interval bar structure
            - "load_historical": Load historical bars via DataManager
            - "load_session": Load session/streaming data
            - "register_indicator": Register indicator with IndicatorManager
            - "calculate_quality": Calculate quality scores
        
        Example:
            >>> req = coordinator._analyze_requirements("symbol", "AAPL", "config")
            >>> if req.can_proceed:
            ...     success = coordinator._execute_provisioning(req)
        """
        if not req.can_proceed:
            logger.error(
                f"[PROVISION] {req.symbol}: Cannot proceed - validation failed: "
                f"{req.validation_errors}"
            )
            return False
        
        logger.info(
            f"[PROVISION] {req.symbol}: Starting provisioning "
            f"({len(req.provisioning_steps)} steps) - "
            f"operation={req.operation_type}, source={req.source}"
        )
        
        try:
            # Execute each provisioning step in order
            for step in req.provisioning_steps:
                if not self._execute_provisioning_step(req, step):
                    logger.error(f"[PROVISION] {req.symbol}: Step '{step}' failed")
                    return False
            
            logger.info(
                f"[PROVISION] {req.symbol}: ✅ Complete "
                f"({len(req.provisioning_steps)} steps executed)"
            )
            return True
            
        except Exception as e:
            logger.error(f"[PROVISION] {req.symbol}: Exception during provisioning: {e}")
            logger.exception(e)
            return False
    
    def _execute_provisioning_step(
        self,
        req: ProvisioningRequirements,
        step: str
    ) -> bool:
        """Execute a single provisioning step.
        
        REUSES: All existing Step 3 loading methods!
        
        Args:
            req: ProvisioningRequirements with context
            step: Step to execute (e.g., "create_symbol", "load_historical")
        
        Returns:
            True if step succeeded, False otherwise
        """
        logger.debug(f"[PROVISION] {req.symbol}: Executing step '{step}'")
        
        try:
            if step == "create_symbol":
                return self._provision_create_symbol(req)
            
            elif step == "upgrade_symbol":
                return self._provision_upgrade_symbol(req)
            
            elif step.startswith("add_interval_"):
                interval = step.replace("add_interval_", "")
                return self._provision_add_interval(req, interval)
            
            elif step == "load_historical":
                return self._provision_load_historical(req)
            
            elif step == "load_session":
                return self._provision_load_session(req)
            
            elif step == "register_indicator":
                return self._provision_register_indicator(req)
            
            elif step == "calculate_quality":
                return self._provision_calculate_quality(req)
            
            else:
                logger.warning(f"[PROVISION] {req.symbol}: Unknown step '{step}'")
                return True  # Don't fail on unknown steps
        
        except Exception as e:
            logger.error(f"[PROVISION] {req.symbol}: Step '{step}' exception: {e}")
            return False
    
    def _provision_create_symbol(self, req: ProvisioningRequirements) -> bool:
        """Create new symbol with metadata.
        
        REUSES: _register_single_symbol() from Phases 1-4
        """
        logger.debug(
            f"[PROVISION] {req.symbol}: Creating symbol "
            f"(meets_config_req={req.meets_session_config_requirements})"
        )
        
        # REUSE existing method with metadata
        self._register_single_symbol(
            req.symbol,
            meets_session_config_requirements=req.meets_session_config_requirements,
            added_by=req.added_by,
            auto_provisioned=req.auto_provisioned
        )
        
        logger.debug(f"[PROVISION] {req.symbol}: Symbol created ✅")
        return True
    
    def _provision_upgrade_symbol(self, req: ProvisioningRequirements) -> bool:
        """Upgrade adhoc symbol to full.
        
        Updates metadata to indicate full loading.
        """
        if not req.symbol_data:
            logger.error(f"[PROVISION] {req.symbol}: No symbol_data for upgrade")
            return False
        
        logger.debug(f"[PROVISION] {req.symbol}: Upgrading adhoc → full")
        
        # Update metadata (INFER from structure - metadata is part of object)
        req.symbol_data.meets_session_config_requirements = True
        req.symbol_data.upgraded_from_adhoc = True
        req.symbol_data.added_by = req.added_by
        
        logger.debug(f"[PROVISION] {req.symbol}: Symbol upgraded ✅")
        return True
    
    def _provision_add_interval(
        self,
        req: ProvisioningRequirements,
        interval: str
    ) -> bool:
        """Add interval bar structure to symbol.
        
        Creates bar structure for base or derived interval.
        """
        from collections import deque
        from app.managers.data_manager.session_data import BarIntervalData
        
        symbol_data = self.session_data.get_symbol_data(req.symbol)
        if not symbol_data:
            logger.error(f"[PROVISION] {req.symbol}: No symbol_data for interval add")
            return False
        
        logger.debug(f"[PROVISION] {req.symbol}: Adding interval {interval}")
        
        # Determine if this is a derived interval
        is_derived = (interval != req.base_interval and req.base_interval is not None)
        
        # Create bar structure
        symbol_data.bars[interval] = BarIntervalData(
            derived=is_derived,
            base=req.base_interval if is_derived else None,
            data=deque() if not is_derived else [],
            quality=0.0,
            gaps=[],
            updated=False
        )
        
        logger.debug(
            f"[PROVISION] {req.symbol}: Interval {interval} added "
            f"(derived={is_derived}) ✅"
        )
        return True
    
    def _provision_load_historical(self, req: ProvisioningRequirements) -> bool:
        """Load historical data for symbol.
        
        REUSES: _manage_historical_data() existing method
        """
        logger.debug(
            f"[PROVISION] {req.symbol}: Loading {req.historical_days} days historical"
        )
        
        # REUSE existing historical loading method
        # Note: This method already uses DataManager.load_historical_bars()
        self._manage_historical_data(symbols=[req.symbol])
        
        logger.debug(f"[PROVISION] {req.symbol}: Historical loaded ✅")
        return True
    
    def _provision_load_session(self, req: ProvisioningRequirements) -> bool:
        """Load session/streaming data for symbol.
        
        REUSES: _load_queues() existing method
        """
        logger.debug(f"[PROVISION] {req.symbol}: Loading session data")
        
        # REUSE existing queue loading method
        self._load_queues(symbols=[req.symbol])
        
        logger.debug(f"[PROVISION] {req.symbol}: Session data loaded ✅")
        return True
    
    def _provision_register_indicator(self, req: ProvisioningRequirements) -> bool:
        """Register indicator for symbol.
        
        REUSES: _register_session_indicators() existing method
        """
        if not req.indicator_config:
            logger.error(f"[PROVISION] {req.symbol}: No indicator_config provided")
            return False
        
        logger.debug(
            f"[PROVISION] {req.symbol}: Registering indicator "
            f"{req.indicator_config.name}"
        )
        
        # Add indicator to symbol_data
        from app.indicators import IndicatorData
        
        symbol_data = self.session_data.get_symbol_data(req.symbol)
        if not symbol_data:
            logger.error(f"[PROVISION] {req.symbol}: No symbol_data for indicator")
            return False
        
        key = req.indicator_config.make_key()
        
        # Check if already exists
        if key in symbol_data.indicators:
            logger.debug(f"[PROVISION] {req.symbol}: Indicator {key} already exists")
            return True
        
        # Add indicator metadata (invalid until calculated)
        symbol_data.indicators[key] = IndicatorData(
            name=req.indicator_config.name,
            type=req.indicator_config.type.value,
            interval=req.indicator_config.interval,
            current_value=None,
            last_updated=None,
            valid=False
        )
        
        # Register with IndicatorManager (if available)
        if hasattr(self, '_indicator_manager') and self._indicator_manager:
            self._indicator_manager.register_symbol_indicators(
                symbol=req.symbol,
                indicators=[req.indicator_config],
                historical_bars=None  # Will calculate when bars available
            )
        
        logger.debug(f"[PROVISION] {req.symbol}: Indicator {key} registered ✅")
        return True
    
    def _provision_calculate_quality(self, req: ProvisioningRequirements) -> bool:
        """Calculate quality scores for symbol.
        
        REUSES: _calculate_historical_quality() existing method
        """
        logger.debug(f"[PROVISION] {req.symbol}: Calculating quality scores")
        
        # REUSE existing quality calculation method
        self._calculate_historical_quality(symbols=[req.symbol])
        
        logger.debug(f"[PROVISION] {req.symbol}: Quality calculated ✅")
        return True
    
    # =========================================================================
    # Phase 3: Per-Symbol Validation Helpers (Call existing APIs)
    # =========================================================================
    
    def _check_parquet_data(self, symbol: str, interval: str, check_date: date) -> bool:
        """Check if Parquet data exists for symbol/interval/date.
        
        REUSES: DataManager.load_historical_bars() API
        
        Args:
            symbol: Symbol to check
            interval: Interval to check (e.g., "1m", "5m")
            check_date: Date to check
        
        Returns:
            True if data exists, False otherwise
        """
        try:
            # Call DataManager API (which uses TimeManager internally)
            bars = self._data_manager.load_historical_bars(
                symbol=symbol,
                interval=interval,
                days=1  # Just check for this date
            )
            return len(bars) > 0
        except Exception as e:
            logger.debug(f"{symbol}: Error checking Parquet data: {e}")
            return False
    
    def _check_historical_data_availability(self, symbol: str) -> bool:
        """Check if historical data exists for symbol.
        
        REUSES: DataManager.load_historical_bars() API
        Infers: Required intervals from config
        
        Args:
            symbol: Symbol to check
        
        Returns:
            True if historical data available, False otherwise
        """
        historical_config = self.session_config.session_data_config.historical
        
        # No historical required?
        if not historical_config.data:
            return True  # Nothing to check
        
        # Check first configured interval
        first_config = historical_config.data[0]
        interval = first_config.intervals[0]  # Get first interval from list
        days = first_config.trailing_days
        
        try:
            # Call DataManager API (uses TimeManager internally)
            bars = self._data_manager.load_historical_bars(
                symbol=symbol,
                interval=interval,
                days=days
            )
            return len(bars) > 0
        except Exception as e:
            logger.error(f"{symbol}: Error checking historical data: {e}", exc_info=True)
            return False
    
    def _check_data_source_for_symbol(self, symbol: str) -> Optional[str]:
        """Check which data source has this symbol.
        
        For now, assumes Parquet is primary source.
        Future: Query Alpaca/Schwab APIs for availability.
        
        Args:
            symbol: Symbol to check
        
        Returns:
            Data source name or None
        """
        # For backtest mode, check Parquet
        if self.mode == "backtest":
            # Check if we have any historical data in Parquet
            if self._check_historical_data_availability(symbol):
                return "parquet"
        else:
            # Live mode: assume API availability
            # Future: Query Alpaca/Schwab for symbol info
            return "alpaca"  # Default for live mode
        
        return None
    
    def _validate_symbol_for_loading(self, symbol: str) -> SymbolValidationResult:
        """Step 0: Validate single symbol for full loading.
        
        Determines if symbol can proceed to Step 3 (data loading).
        Uses stored system-wide validation results and calls existing APIs.
        
        Args:
            symbol: Symbol to validate
        
        Returns:
            SymbolValidationResult with can_proceed flag
        """
        result = SymbolValidationResult(symbol=symbol)
        
        logger.debug(f"[STEP_0] Validating {symbol}")
        
        # Check 1: Already loaded?
        existing = self.session_data.get_symbol_data(symbol)
        if existing and existing.meets_session_config_requirements:
            result.can_proceed = False
            result.reason = "already_loaded"
            logger.debug(f"[STEP_0] {symbol}: Already fully loaded")
            return result
        
        # Check 2: Data source available?
        data_source = self._check_data_source_for_symbol(symbol)
        if not data_source:
            result.can_proceed = False
            result.reason = "no_data_source"
            result.data_source_available = False
            logger.warning(f"[STEP_0] {symbol}: No data source available")
            return result
        
        result.data_source = data_source
        result.data_source_available = True
        
        # Check 3: Intervals supported?
        # Use stored validation results (from system-wide validation)
        result.base_interval = self._base_interval or "1m"
        result.intervals_supported = [result.base_interval] + (self._derived_intervals_validated or [])
        
        # Check 4: Historical data available?
        has_historical = self._check_historical_data_availability(symbol)
        if not has_historical and self.session_config.session_data_config.historical.enabled:
            result.can_proceed = False
            result.reason = "no_historical_data"
            result.has_historical_data = False
            logger.warning(f"[STEP_0] {symbol}: No historical data available")
            return result
        
        result.has_historical_data = has_historical
        
        # Check 5: Meets all requirements?
        result.meets_config_requirements = True
        result.can_proceed = True
        result.reason = "validated"
        
        logger.debug(f"[STEP_0] {symbol}: Validation passed ✅")
        return result
    
    def _validate_symbols_for_loading(self, symbols: List[str]) -> List[str]:
        """Step 0: Validate all symbols, drop failures, proceed with successes.
        
        Graceful degradation: Failed symbols dropped, others proceed.
        Terminates ONLY if ALL symbols fail.
        
        Args:
            symbols: List of symbols to validate
        
        Returns:
            List of validated symbols that can proceed to Step 3
        
        Raises:
            RuntimeError: If NO symbols pass validation
        """
        logger.info(f"[STEP_0] Validating {len(symbols)} symbols")
        
        validated_symbols = []
        failed_symbols = []
        
        for symbol in symbols:
            result = self._validate_symbol_for_loading(symbol)
            
            if result.can_proceed:
                validated_symbols.append(symbol)
                logger.info(f"[STEP_0] {symbol}: ✅ Validated")
            else:
                failed_symbols.append((symbol, result.reason))
                logger.warning(
                    f"[STEP_0] {symbol}: ❌ Validation failed - {result.reason}"
                )
        
        # Report results
        if failed_symbols:
            logger.warning(
                f"[STEP_0] {len(failed_symbols)} symbols failed validation: "
                f"{[s for s, _ in failed_symbols]}"
            )
            for symbol, reason in failed_symbols:
                logger.warning(f"  - {symbol}: {reason}")
        
        # Check if ANY symbols passed
        if not validated_symbols:
            raise RuntimeError(
                "[STEP_0] NO SYMBOLS PASSED VALIDATION - Cannot proceed to session. "
                f"Failed symbols: {failed_symbols}"
            )
        
        logger.info(
            f"[STEP_0] {len(validated_symbols)} symbols validated, "
            f"proceeding to Step 3"
        )
        
        return validated_symbols
    
    # =========================================================================
    # Symbol Registration
    # =========================================================================
    
    def _register_single_symbol(
        self,
        symbol: str,
        meets_session_config_requirements: bool = True,
        added_by: str = "config",
        auto_provisioned: bool = False
    ):
        """Register a single symbol with bar structure and metadata (helper for bulk and mid-session).
        
        Phase 7: Extracted from _register_symbols for code reuse.
        Phase 8: Enhanced with metadata parameters.
        
        Used by:
        - _register_symbols() - bulk registration (all symbols)
        - _process_pending_symbols() - mid-session insertion (single symbol)
        - _auto_provision_symbol() - adhoc bar/indicator addition
        
        Uses stored validation results from _validate_stream_requirements().
        
        Args:
            symbol: Symbol to register
            meets_session_config_requirements: True for full loading, False for adhoc
            added_by: Source of addition ("config", "strategy", "scanner", "adhoc")
            auto_provisioned: True if auto-created for adhoc addition
        """
        base_interval = self._base_interval or "1m"  # Default to 1m if not set
        derived_intervals = self._derived_intervals_validated or []
        
        # Create bar structure with base interval (streamed) + derived intervals (generated)
        bars = {
            # Base interval (streamed from queue/API)
            base_interval: BarIntervalData(
                derived=False,  # Streamed, not generated
                base=None,      # Not derived from anything
                data=deque(),   # Empty deque for base interval
                quality=0.0,
                gaps=[],
                updated=False
            )
        }
        
        # Add derived intervals (generated by DataProcessor)
        for interval in derived_intervals:
            bars[interval] = BarIntervalData(
                derived=True,       # Generated, not streamed
                base=base_interval, # Derived from base
                data=[],            # Empty list for derived
                quality=0.0,
                gaps=[],
                updated=False
            )
        
        # Create SymbolSessionData with bar structure and metadata
        symbol_data = SymbolSessionData(
            symbol=symbol,
            base_interval=base_interval,
            bars=bars,
            meets_session_config_requirements=meets_session_config_requirements,
            added_by=added_by,
            auto_provisioned=auto_provisioned,
            added_at=self._time_manager.get_current_time() if self._session_active else None,
            upgraded_from_adhoc=False
        )
        
        # Register with SessionData
        self.session_data.register_symbol_data(symbol_data)
        
        logger.debug(
            f"{symbol}: Registered with base={base_interval}, "
            f"derived={derived_intervals}, "
            f"meets_config_req={meets_session_config_requirements}, "
            f"added_by={added_by}"
        )
    
    def _register_symbols(self):
        """Register all symbols in SessionData using stored validation results.
        
        Phase 2 - Step 3: Called every session after validation (first time) or directly (subsequent sessions).
        
        Uses stored validation results:
        - self._base_interval (from _validate_stream_requirements)
        - self._derived_intervals_validated (from _validate_stream_requirements)
        
        Creates SymbolSessionData with bar structure for each symbol.
        """
        logger.info("Registering symbols with bar structure")
        
        symbols_to_process = self.session_config.session_data_config.symbols
        
        # Register each symbol using helper
        for symbol in symbols_to_process:
            self._register_single_symbol(symbol)
        
        # Log results
        base_interval = self._base_interval or "1m"
        derived_intervals = self._derived_intervals_validated or []
        streamed_count = len(symbols_to_process)  # Each symbol has 1 base interval
        generated_count = len(symbols_to_process) * len(derived_intervals)
        
        logger.info(
            f"Registered {len(symbols_to_process)} symbols: "
            f"{streamed_count} STREAMED, {generated_count} GENERATED"
        )
        logger.debug(f"Base interval: {base_interval}, Derived: {derived_intervals}")
    
    def _validate_and_mark_streams(self, symbols: Optional[List[str]] = None) -> bool:
        """Validate stream requirements and mark streams/generations.
        
        DEPRECATED: This method combines validation + registration.
        Use _validate_stream_requirements() + _register_symbols() instead.
        
        Kept for backwards compatibility during migration.
        """
        logger.warning("_validate_and_mark_streams() is deprecated, use split methods")
        
        # Call new split methods
        if not self._streams_validated:
            if not self._validate_stream_requirements():
                return False
        
        self._register_symbols()
        return True
    
    def _mark_stream_generate(self, symbols: Optional[List[str]] = None):
        """Mark which data types are STREAMED vs GENERATED vs IGNORED.
        
        Called for live mode stream determination. Creates SymbolSessionData with bar structure.
        
        Live Mode:
        - Stream whatever API provides
        - Generate what's not available from API
        
        Note: Backtest mode uses _validate_and_mark_streams() instead.
        """
        symbols_to_process = symbols or self.session_config.session_data_config.symbols
        streams = self.session_config.session_data_config.streams
        
        logger.info(f"Marking stream/generate for {len(symbols_to_process)} symbols, {len(streams)} streams (live mode)")
        
        # In live mode, mark all streams as streamed (API will provide)
        # For now, use simple marking - can be enhanced based on API capabilities
        self._mark_live_streams(symbols_to_process, streams)
        
        logger.info(f"Registered {len(symbols_to_process)} symbols for live streaming")
    
    def _mark_live_streams(self, symbols: List[str], streams: List[str]):
        """Mark streams for live mode.
        
        Creates SymbolSessionData with bar structure for each symbol.
        In live mode, we assume API can provide all requested streams.
        
        Args:
            symbols: List of symbols
            streams: List of requested streams (e.g., ["1m", "quotes"])
        """
        # Separate bar intervals from other types
        bar_intervals = [s for s in streams if s not in ["quotes", "ticks"]]
        
        for symbol in symbols:
            # In live mode, assume smallest interval is streamed, rest are derived
            # Priority order: 1s > 1m > 5m > etc
            if not bar_intervals:
                logger.warning(f"{symbol}: No bar intervals in streams, skipping")
                continue
            
            # Use smallest interval as base
            base_interval = min(bar_intervals, key=lambda x: int(x[:-1]) if x[:-1].isdigit() else 999)
            derived_intervals = [i for i in bar_intervals if i != base_interval]
            
            # Create bar structure
            bars = {
                # Base interval (streamed from API)
                base_interval: BarIntervalData(
                    derived=False,
                    base=None,
                    data=deque(),
                    quality=0.0,
                    gaps=[],
                    updated=False
                )
            }
            
            # Add derived intervals
            for interval in derived_intervals:
                bars[interval] = BarIntervalData(
                    derived=True,
                    base=base_interval,
                    data=[],
                    quality=0.0,
                    gaps=[],
                    updated=False
                )
            
            # Create and register symbol
            symbol_data = SymbolSessionData(
                symbol=symbol,
                base_interval=base_interval,
                bars=bars
            )
            
            self.session_data.register_symbol_data(symbol_data)
            
            logger.debug(
                f"{symbol}: Registered for live mode - base: {base_interval}, derived: {derived_intervals}"
            )
    
    # NOTE: _mark_backtest_streams() removed - backtest mode now uses _validate_and_mark_streams()
    
    def _load_historical_data_config(
        self,
        hist_config,
        current_date: date,
        symbols_filter: Optional[List[str]] = None
    ):
        """Load historical data for one configuration.
        
        Args:
            hist_config: HistoricalDataConfig instance
            current_date: Current session date
            symbols_filter: Optional list of symbols to load. If provided, only load these symbols.
                           If None, uses symbols from hist_config.apply_to.
        """
        trailing_days = hist_config.trailing_days
        intervals = hist_config.intervals
        
        # Resolve symbols from config
        config_symbols = self._resolve_symbols(hist_config.apply_to)
        
        # Apply filter if provided (for mid-session adds)
        if symbols_filter:
            symbols = [s for s in config_symbols if s in symbols_filter]
        else:
            symbols = config_symbols
        
        logger.info(
            f"Loading {trailing_days} days of {intervals} for "
            f"{len(symbols)} symbols"
        )
        
        # Calculate date range
        # End date is yesterday (we don't include current day in historical)
        end_date = current_date - timedelta(days=1)
        
        # Start date: count back trailing_days of TRADING days
        start_date = self._get_start_date_for_trailing_days(
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
                bars = self._load_historical_bars(
                    symbol,
                    interval,
                    start_date,
                    end_date
                )
                
                if not bars:
                    logger.warning(
                        f"[SESSION_FLOW] PHASE_2.1: No {interval} bars found for {symbol} "
                        f"in range {start_date} to {end_date} - check if data exists in parquet storage"
                    )
                
                # Store in session_data
                for bar in bars:
                    self.session_data.append_bar(symbol, interval, bar)
                
                logger.info(
                    f"[SESSION_FLOW] PHASE_2.1: Stored {len(bars)} {interval} bars for {symbol} "
                    f"in historical storage ({start_date} to {end_date})"
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
    
    def _get_start_date_for_trailing_days(
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
        with SessionLocal() as session:
            start_date = self._time_manager.get_previous_trading_date(
                session,
                end_date,
                n=days_to_go_back,  # FIXED: was trailing_days, should be days_to_go_back
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
            f"{start_date} to {end_date} ({trailing_days} trading days)"
        )
        
        return start_date
    
    def _load_historical_bars(
        self,
        symbol: str,
        interval: str,
        start_date: date,
        end_date: date
    ) -> List['BarData']:
        """Load historical bars from DataManager.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval (e.g., "1m", "1d")
            start_date: Start date
            end_date: End date
            
        Returns:
            List of BarData objects
        """
        from datetime import datetime, time
        from app.models.database import SessionLocal
        
        try:
            logger.info(
                f"[SESSION_FLOW] PHASE_2.1: Loading {symbol} {interval} bars "
                f"from {start_date} to {end_date} (interval type: {type(interval).__name__})"
            )
            
            # Convert dates to datetimes (start of day to end of day)
            start_dt = datetime.combine(start_date, time(0, 0))
            end_dt = datetime.combine(end_date, time(23, 59, 59))
            
            logger.debug(
                f"[SESSION_FLOW] PHASE_2.1: Calling data_manager.get_bars with: "
                f"symbol={symbol}, interval={interval}, start={start_dt}, end={end_dt}"
            )
            
            # Query via DataManager using existing API
            with SessionLocal() as db_session:
                bars = self._data_manager.get_bars(
                    session=db_session,
                    symbol=symbol,
                    start=start_dt,
                    end=end_dt,
                    interval=interval
                )
            
            logger.info(
                f"[SESSION_FLOW] PHASE_2.1: Loaded {len(bars)} {interval} bars for {symbol}"
            )
            
            if bars and interval == "1d":
                logger.info(
                    f"[SESSION_FLOW] PHASE_2.1: First 1d bar: {bars[0].timestamp.date()} "
                    f"close=${bars[0].close}, vol={bars[0].volume}"
                )
                logger.info(
                    f"[SESSION_FLOW] PHASE_2.1: Last 1d bar: {bars[-1].timestamp.date()} "
                    f"close=${bars[-1].close}, vol={bars[-1].volume}"
                )
            
            return bars
            
        except Exception as e:
            logger.error(
                f"[SESSION_FLOW] PHASE_2.1.ERROR: Failed to load {symbol} {interval}: {e}"
            )
            logger.error(
                f"Error loading historical bars for {symbol} {interval}: {e}",
                exc_info=True
            )
            return []
    
    # =========================================================================
    # Historical Indicator Calculation
    # =========================================================================
    
    def _calculate_trailing_average(
        self,
        symbol: str,
        indicator_name: str,
        config: Dict[str, Any]
    ) -> float:
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
            # Single value: average over all N days for this symbol
            return self._calculate_daily_average(
                symbol,
                field,
                period_days,
                skip_early_close=False
            )
        elif granularity == 'minute':
            # Minute: average for each minute of trading day
            result = self._calculate_intraday_average(
                field, period_days
            )
        else:
            raise ValueError(f"Unknown granularity: {granularity}")
        
        return result
    
    def _calculate_trailing_max(
        self,
        symbol: str,
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
        max_value = self._calculate_field_max(field, period_days)
        
        return max_value
    
    def _calculate_trailing_min(
        self,
        symbol: str,
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
        min_value = self._calculate_field_min(field, period_days)
        
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
    
    def _calculate_daily_average(
        self,
        symbol: str,
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
        logger.debug(
            f"Calculating daily average for {symbol} {field} over {period_days} days "
            f"(skip_early_close={skip_early_close})"
        )
        
        # Collect field values from this symbol's 1d bars
        field_values = []
        
        # Use internal=True since session not active yet (Phase 2)
        symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
        if symbol_data is None:
            logger.warning(f"No symbol_data for {symbol}")
            return 0.0
        
        # Debug: Log all intervals in historical.bars
        logger.debug(
            f"Historical bars intervals for {symbol}: "
            f"{list(symbol_data.historical.bars.keys())}"
        )
        
        # Get 1d historical bars for this symbol
        historical_1d_data = symbol_data.historical.bars.get("1d")
        
        if not historical_1d_data or not historical_1d_data.data_by_date:
            logger.warning(
                f"No 1d historical bars for {symbol}. "
                f"Available intervals: {list(symbol_data.historical.bars.keys())}"
            )
            return 0.0
        
        # Get all dates, sorted
        dates = sorted(historical_1d_data.data_by_date.keys())
        logger.debug(f"Found {len(dates)} dates with 1d bars for {symbol}: {dates}")
        
        # Take last N days (should match period_days if data loaded correctly)
        dates_to_use = dates[-period_days:] if len(dates) > period_days else dates
        logger.debug(f"Using {len(dates_to_use)} dates for {period_days}-day period: {dates_to_use}")
        
        for date in dates_to_use:
            bars = historical_1d_data.data_by_date[date]
            logger.debug(f"Processing {len(bars)} bars for date {date}")
            for bar in bars:
                # Extract field value
                if field == 'volume':
                    value = bar.volume
                elif field == 'close':
                    value = bar.close
                elif field == 'open':
                    value = bar.open
                elif field == 'high':
                    value = bar.high
                elif field == 'low':
                    value = bar.low
                else:
                    logger.warning(f"Unknown field: {field}")
                    continue
                
                field_values.append(value)
        
        if not field_values:
            logger.warning(f"No data to calculate {field} average for {symbol}")
            return 0.0
        
        # Calculate average
        avg = sum(field_values) / len(field_values)
        
        logger.info(
            f"✓ Calculated daily {field} average for {symbol}: {avg:.2f} "
            f"(from {len(field_values)} values over {len(dates_to_use)} days, values={field_values})"
        )
        
        return avg
    
    def _calculate_intraday_average(
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
    
    def _calculate_field_max(
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
    
    def _calculate_field_min(
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
    # Queue Operations (Backtest Streaming)
    # =========================================================================
    
    def _get_streamed_intervals_for_symbol(self, symbol: str) -> List[str]:
        """Get list of STREAMED intervals for a symbol.
        
        Returns only intervals marked as STREAMED (not GENERATED).
        Now queries SessionData for base intervals (those with derived=False).
        
        Args:
            symbol: Symbol to query
        
        Returns:
            List of streamed intervals (e.g., ["1m"])
        """
        # Query SessionData for base (non-derived) intervals
        symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
        if not symbol_data:
            return []
        
        # Return intervals that are not derived (i.e., streamed)
        streamed = [interval for interval, data in symbol_data.bars.items() if not data.derived]
        return streamed
    
    def _get_date_plus_trading_days(
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
        with SessionLocal() as session:
            end_date = self._time_manager.get_next_trading_date(
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

    def _drop_pre_market_data(self, market_open: datetime) -> int:
        """Drop any queue data with timestamps before market open.
        
        Used in clock-driven mode to ensure we start at market open time
        and don't process any pre-market data.
        
        Args:
            market_open: Market opening datetime
            
        Returns:
            Number of bars dropped
        """
        total_dropped = 0
        
        for queue_key, queue in self._bar_queues.items():
            dropped_for_queue = 0
            
            # Pop items from front while timestamp < market_open
            while queue and queue[0].timestamp < market_open:
                dropped_bar = queue.popleft()
                dropped_for_queue += 1
                total_dropped += 1
            
            if dropped_for_queue > 0:
                logger.debug(
                    f"[SESSION_FLOW] PHASE_5.2: Dropped {dropped_for_queue} pre-market bars "
                    f"from {queue_key}, {len(queue)} remain"
                )
        
        return total_dropped
    
    def get_queue_stats(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Get queue statistics for display purposes.
        
        Returns dictionary of queue stats grouped by symbol and interval.
        Format: {symbol: {interval: {size: int, oldest: datetime, newest: datetime}}}
        
        Returns:
            Dictionary of queue statistics
        """
        from typing import Any
        
        stats = {}
        
        for queue_key, queue in self._bar_queues.items():
            symbol, interval = queue_key
            
            if symbol not in stats:
                stats[symbol] = {}
            
            queue_size = len(queue)
            oldest = queue[0].timestamp if queue_size > 0 else None
            newest = queue[-1].timestamp if queue_size > 0 else None
            
            stats[symbol][interval] = {
                "size": queue_size,
                "oldest": oldest,
                "newest": newest
            }
        
        return stats

    def _get_next_queue_timestamp(self) -> Optional[datetime]:
        """Get the next timestamp from queues.

        Queries all queues and returns the earliest timestamp.
        This determines when we advance time to next.

        Returns:
            Next timestamp or None if all queues empty
        """
        if not self._bar_queues:
            logger.debug("[SESSION_FLOW] PHASE_5.2: No queues initialized")
            return None

        # Find minimum timestamp across all queue fronts
        min_timestamp = None
        queue_count = 0
        empty_count = 0

        for queue_key, queue in self._bar_queues.items():
            queue_count += 1
            if queue:  # Queue not empty
                bar = queue[0]  # Peek at front (don't pop yet)
                if min_timestamp is None or bar.timestamp < min_timestamp:
                    min_timestamp = bar.timestamp
            else:
                empty_count += 1

        if min_timestamp:
            logger.debug(
                f"[SESSION_FLOW] PHASE_5.2: Next timestamp: {min_timestamp.time()} "
                f"({queue_count - empty_count}/{queue_count} queues active)"
            )
        else:
            logger.debug(
                f"[SESSION_FLOW] PHASE_5.2: All queues empty ({empty_count}/{queue_count})"
            )

        return min_timestamp

    def _process_queue_data_at_timestamp(self, timestamp: datetime) -> int:
        """Process all queue data up to and including the given timestamp.

        Consumes bars from queues with timestamp <= current time.
        This supports clock-driven mode where time advances by fixed intervals.

        Args:
            timestamp: Current time - process all bars up to this time

        Returns:
            Number of bars processed
        """
        bars_processed = 0
        bars_by_symbol = {}  # Track bars per symbol for logging

        logger.debug(f"[SESSION_FLOW] PHASE_5.3: Processing bars up to {timestamp.time()}")

        # Track dropped bars (outside regular hours)
        bars_dropped = 0
        bars_dropped_by_symbol = {}

        # Process all queues that have data at or before this timestamp
        for queue_key, queue in self._bar_queues.items():
            symbol, interval = queue_key

            # Consume all bars with timestamp <= current time
            # (Clock-driven: process multiple bars if time advanced past them)
            while queue and queue[0].timestamp <= timestamp:
                bar = queue.popleft()
                
                # ========== Per-Symbol Lag Detection ==========
                # Only check lag in clock-driven and live modes
                # In data-driven mode, we block anyway so lag is irrelevant
                if self._should_check_lag():
                    # Check lag BEFORE incrementing (so new symbols check immediately on first bar)
                    if self._symbol_check_counters[symbol] % self._catchup_check_interval == 0:
                        current_time = self._time_manager.get_current_time()
                        lag_seconds = (current_time - bar.timestamp).total_seconds()
                        
                        if lag_seconds > self._catchup_threshold:
                            if self.session_data._session_active:
                                logger.info(
                                    f"[STREAMING] Lag detected for {symbol} "
                                    f"({lag_seconds:.1f}s > {self._catchup_threshold}s) "
                                    f"- deactivating session"
                                )
                                self.session_data.deactivate_session()
                        else:
                            if not self.session_data._session_active:
                                logger.info(
                                    f"[STREAMING] Caught up on {symbol} "
                                    f"({lag_seconds:.1f}s ≤ {self._catchup_threshold}s) "
                                    f"- reactivating session"
                                )
                                self.session_data.activate_session()
                
                # Increment counter for this symbol AFTER check
                self._symbol_check_counters[symbol] += 1
                # ===============================================
                
                # DEBUG: Log each bar being processed from queue
                logger.debug(
                    f"[QUEUE_POP] {symbol} {interval}: Processing bar at {bar.timestamp} "
                    f"(queue remaining: {len(queue)})"
                )

                # Filter: Drop bars outside regular trading hours
                if hasattr(self, '_market_open') and hasattr(self, '_market_close'):
                    bar_time = bar.timestamp
                    if bar_time < self._market_open or bar_time > self._market_close:
                        # Bar is outside regular trading hours - DROP IT
                        logger.debug(
                            f"[SESSION_FLOW] PHASE_5.3: Dropping {symbol} {interval} bar at {bar_time.time()} "
                            f"(outside {self._market_open.time()}-{self._market_close.time()})"
                        )
                        if symbol not in bars_dropped_by_symbol:
                            bars_dropped_by_symbol[symbol] = 0
                        bars_dropped_by_symbol[symbol] += 1
                        bars_dropped += 1
                        continue  # Skip this bar, don't add to session_data

                # Get or register symbol data
                symbol_data = self.session_data.get_symbol_data(symbol)
                if symbol_data is None:
                    symbol_data = self.session_data.register_symbol(symbol)

                # Add to current session bars (not historical)
                # Get base interval data
                base_interval = symbol_data.base_interval
                if base_interval not in symbol_data.bars:
                    from app.managers.data_manager.session_data import BarIntervalData
                    symbol_data.bars[base_interval] = BarIntervalData(
                        derived=False,
                        base=None,
                        data=deque()
                    )
                
                base_bars = symbol_data.bars[base_interval].data
                bars_before = len(base_bars)
                
                # DEBUG: Log ALL bars being added (not just first 5)
                logger.debug(
                    f"[BAR_ADD] {symbol} bar at {bar.timestamp.time()} | "
                    f"Before: {bars_before} | Will be #{bars_before + 1}"
                )
                
                base_bars.append(bar)
                symbol_data.update_from_bar(bar)
                
                # Verify count after adding
                bars_after = len(base_bars)
                if bars_after != bars_before + 1:
                    logger.error(
                        f"[BAR_ADD] Count mismatch! Before: {bars_before}, "
                        f"After: {bars_after}, Expected: {bars_after + 1}"
                    )

                # Phase 6b: Update indicators for this base interval
                if hasattr(self, 'indicator_manager') and self.indicator_manager:
                    # Convert deque to list for indicator calculation
                    bars_list = list(base_bars)
                    self.indicator_manager.update_indicators(
                        symbol=symbol,
                        interval=base_interval,
                        bars=bars_list
                    )

                # Track for logging
                if symbol not in bars_by_symbol:
                    bars_by_symbol[symbol] = 0
                bars_by_symbol[symbol] += 1

                bars_processed += 1

                # Notify data processor for derived bar computation
                if hasattr(self, 'data_processor') and self.data_processor:
                    self.data_processor.notify_data_available(symbol, interval, bar.timestamp)
                
                # Notify quality manager for quality calculation
                if hasattr(self, 'quality_manager') and self.quality_manager:
                    # Notify with symbol's BASE interval, not queue interval
                    # (queues might have mixed intervals, but quality tracks base interval)
                    base_interval = symbol_data.base_interval
                    self.quality_manager.notify_data_available(symbol, base_interval, bar.timestamp)

        # Log summary
        if bars_processed > 0:
            symbols_str = ", ".join([f"{sym}: {cnt}" for sym, cnt in bars_by_symbol.items()])
            logger.debug(
                f"[SESSION_FLOW] PHASE_5.3: Processed {bars_processed} bars ({symbols_str})"
            )
        
        if bars_dropped > 0:
            dropped_str = ", ".join([f"{sym}: {cnt}" for sym, cnt in bars_dropped_by_symbol.items()])
            logger.info(
                f"[SESSION_FLOW] PHASE_5.3: Dropped {bars_dropped} bars outside trading hours ({dropped_str})"
            )

        return bars_processed

    def _should_check_lag(self) -> bool:
        """Determine if lag detection should run based on mode.
        
        Lag detection is only relevant when:
        - Live mode: Real-time data can lag
        - Clock-driven backtest: Processing can fall behind clock
        - NOT data-driven: We block until processor ready, so lag is controlled
        
        Returns:
            True if lag detection should run, False otherwise
        """
        if self.mode == "live":
            return True
        
        if self.mode == "backtest" and self.session_config.backtest_config:
            # Only check lag in clock-driven mode (speed > 0)
            return self.session_config.backtest_config.speed_multiplier > 0
        
        return False
    
    def _apply_clock_driven_delay(self, speed_multiplier: float):
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
            import time
            time.sleep(delay_seconds)
    
    def to_json(self, complete: bool = True) -> dict:
        """Export SessionCoordinator state to JSON format.
        
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
            "_running": self._running,
            "_session_active": self._session_active
        }
