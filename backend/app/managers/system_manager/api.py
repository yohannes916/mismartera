"""
SystemManager - Central orchestrator and service locator

Clean implementation aligned with new architecture (Nov 2025).
See ARCHITECTURE.md for complete documentation.

Key Responsibilities:
1. Create and manage all managers (TimeManager, DataManager, etc.)
2. Load and validate session configuration
3. Create and wire 4-thread pool
4. Provide singleton access to managers
5. Track system state (STOPPED, RUNNING)
6. Handle start() and stop() lifecycle
"""

from pathlib import Path
from typing import Optional
from datetime import date

# Logging
from app.logger import logger

# Core primitives
from app.managers.data_manager.session_data import SessionData, get_session_data
from app.core.enums import SystemState, OperationMode

# Models
from app.models.session_config import SessionConfig
from app.models.database import SessionLocal

# Monitoring
from app.monitoring.performance_metrics import PerformanceMetrics


class SystemManager:
    """
    Central orchestrator and service locator.
    
    Architecture:
    - Creates managers (TimeManager, DataManager, ExecutionManager)
    - Creates 4-thread pool (SessionCoordinator, DataProcessor, DataQualityManager, AnalysisEngine)
    - Wires threads together via queues and subscriptions
    - Provides singleton access via get_system_manager()
    
    Thread Pool:
    1. SessionCoordinator - Orchestrates session lifecycle
    2. DataProcessor - Generates derived bars + indicators
    3. DataQualityManager - Measures quality + fills gaps (live only)
    4. AnalysisEngine - Runs strategies + generates signals
    
    Timezone Handling:
    - system_manager.timezone is derived from exchange_group + asset_class
    - This becomes the DEFAULT timezone for all time operations
    - TimeManager and DataManager convert to/from UTC at boundaries
    - Application code works in market timezone (never converts manually)
    
    Usage:
        system_mgr = get_system_manager()
        system_mgr.start("session_configs/example_session.json")
        time_mgr = system_mgr.get_time_manager()
        # ... use managers ...
        system_mgr.stop()
    """
    
    def __init__(self):
        """
        Initialize SystemManager.
        
        WARNING: Do not call directly. Use get_system_manager() instead.
        """
        # Managers (lazy-loaded singletons)
        self._time_manager: Optional['TimeManager'] = None
        self._data_manager: Optional['DataManager'] = None
        self._execution_manager: Optional[object] = None  # TODO: Type when implemented
        self._scanner_manager: Optional['ScannerManager'] = None
        self._strategy_manager: Optional['StrategyManager'] = None
        
        # Thread pool (created on start)
        self._coordinator: Optional['SessionCoordinator'] = None
        self._data_processor: Optional['DataProcessor'] = None
        self._quality_manager: Optional['DataQualityManager'] = None
        self._analysis_engine: Optional['AnalysisEngine'] = None
        
        # Performance metrics
        self._performance_metrics = PerformanceMetrics()
        
        # System state
        self._state = SystemState.STOPPED
        self._mode: OperationMode = OperationMode.BACKTEST  # Default, set from config
        self._session_config: Optional[SessionConfig] = None
        
        # Exchange configuration (derived from session config)
        self.exchange_group: str = "US_EQUITY"  # Default
        self.asset_class: str = "EQUITY"  # Default
        
        # Timezone (derived from exchange_group + asset_class via MarketHours database)
        # CRITICAL: This is the market timezone used by TimeManager and DataManager
        # All timestamps returned by managers are in this timezone
        self.timezone: Optional[str] = None  # Derived from exchange+asset
        
        # Initialize timezone based on default exchange/asset
        self._update_timezone()
        
        logger.info("SystemManager initialized")
    
    # =========================================================================
    # Session Configuration Properties (Single Source of Truth)
    # =========================================================================
    
    @property
    def backtest_start_date(self) -> Optional['date']:
        """Get backtest start date from session config (single source of truth).
        
        This is a reference to session_config.backtest_config.start_date.
        Reading or writing this property reads/writes the session config value.
        
        Returns:
            Start date as date object, or None if not configured
        """
        from datetime import datetime
        
        if not self._session_config or not self._session_config.backtest_config:
            return None
        
        try:
            return datetime.strptime(
                self._session_config.backtest_config.start_date,
                "%Y-%m-%d"
            ).date()
        except (ValueError, AttributeError):
            return None
    
    @backtest_start_date.setter
    def backtest_start_date(self, value: 'date') -> None:
        """Set backtest start date in session config.
        
        Args:
            value: Date to set as backtest start
        """
        if not self._session_config or not self._session_config.backtest_config:
            raise RuntimeError("Session config not loaded")
        
        self._session_config.backtest_config.start_date = value.strftime("%Y-%m-%d")
        logger.info(f"Backtest start date set to: {value}")
    
    @property
    def backtest_end_date(self) -> Optional['date']:
        """Get backtest end date from session config (single source of truth).
        
        This is a reference to session_config.backtest_config.end_date.
        Reading or writing this property reads/writes the session config value.
        
        Returns:
            End date as date object, or None if not configured
        """
        from datetime import datetime
        
        if not self._session_config or not self._session_config.backtest_config:
            return None
        
        try:
            return datetime.strptime(
                self._session_config.backtest_config.end_date,
                "%Y-%m-%d"
            ).date()
        except (ValueError, AttributeError):
            return None
    
    @backtest_end_date.setter
    def backtest_end_date(self, value: 'date') -> None:
        """Set backtest end date in session config.
        
        Args:
            value: Date to set as backtest end
        """
        if not self._session_config or not self._session_config.backtest_config:
            raise RuntimeError("Session config not loaded")
        
        self._session_config.backtest_config.end_date = value.strftime("%Y-%m-%d")
        logger.info(f"Backtest end date set to: {value}")
    
    @property
    def session_config(self) -> Optional[SessionConfig]:
        """Get current session configuration.
        
        Returns:
            SessionConfig instance or None if not loaded
        """
        return self._session_config
    
    @property
    def mode(self) -> OperationMode:
        """Get current operation mode (fast direct access).
        
        This is the SINGLE SOURCE OF TRUTH for system mode.
        Stored as attribute for O(1) access (not computed).
        Synchronized with session_config.mode during load.
        
        Returns:
            OperationMode enum (BACKTEST or LIVE)
        """
        return self._mode
    
    # =========================================================================
    # Manager Access (Singleton Pattern)
    # =========================================================================
    
    def get_time_manager(self) -> 'TimeManager':
        """
        Get TimeManager singleton.
        
        Returns:
            TimeManager instance
            
        Raises:
            RuntimeError: If managers not initialized
        """
        if self._time_manager is None:
            from app.managers.time_manager.api import TimeManager
            self._time_manager = TimeManager(self)
            logger.debug("TimeManager created")
        return self._time_manager
    
    def get_data_manager(self) -> 'DataManager':
        """
        Get DataManager singleton.
        
        Returns:
            DataManager instance
            
        Raises:
            RuntimeError: If managers not initialized
        """
        if self._data_manager is None:
            from app.managers.data_manager.api import DataManager
            self._data_manager = DataManager(system_manager=self)
            logger.debug("DataManager created")
        return self._data_manager
    
    def get_execution_manager(self) -> object:
        """
        Get ExecutionManager singleton.
        
        Returns:
            ExecutionManager instance
            
        Note:
            Not yet implemented
        """
        if self._execution_manager is None:
            # TODO: Implement ExecutionManager
            raise NotImplementedError("ExecutionManager not yet implemented")
        return self._execution_manager
    
    def get_scanner_manager(self) -> 'ScannerManager':
        """
        Get ScannerManager singleton.
        
        Returns:
            ScannerManager instance
            
        Raises:
            RuntimeError: If managers not initialized
        """
        if self._scanner_manager is None:
            from app.threads.scanner_manager import ScannerManager
            self._scanner_manager = ScannerManager(self)
            logger.debug("ScannerManager created")
        return self._scanner_manager
    
    def get_strategy_manager(self) -> 'StrategyManager':
        """
        Get StrategyManager singleton.
        
        Returns:
            StrategyManager instance
            
        Raises:
            RuntimeError: If managers not initialized
        """
        if self._strategy_manager is None:
            from app.strategies.manager import StrategyManager
            self._strategy_manager = StrategyManager(self)
            logger.debug("StrategyManager created")
        return self._strategy_manager
    
    # =========================================================================
    # Configuration Management
    # =========================================================================
    
    def load_session_config(self, config_file: str) -> SessionConfig:
        """
        Load and validate session configuration.
        
        Args:
            config_file: Path to session config JSON file
            
        Returns:
            Loaded SessionConfig
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config validation fails
        """
        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(f"Session config not found: {config_file}")
        
        logger.info(f"Loading session config: {config_file}")
        
        # Load config
        config = SessionConfig.from_file(str(config_path))
        
        # Validate
        config.validate()
        
        # Update exchange configuration
        self.exchange_group = config.exchange_group
        self.asset_class = config.asset_class
        self._update_timezone()
        
        # Synchronize mode (CRITICAL: Keep SystemManager._mode in sync with config)
        self._mode = OperationMode(config.mode)
        logger.debug(f"Mode synchronized: {self._mode.value}")
        
        logger.success(
            f"Session config loaded: {config.session_name} "
            f"({config.mode} mode, {config.exchange_group}/{config.asset_class})"
        )
        
        return config
    
    def _update_timezone(self):
        """
        Derive timezone from exchange_group + asset_class.
        
        CRITICAL TIMEZONE PRINCIPLE:
        - This timezone (system_manager.timezone) becomes the DEFAULT timezone
        - TimeManager and DataManager store times in UTC internally
        - TimeManager and DataManager RETURN times in this timezone
        - Application code should NEVER specify timezone explicitly
        - All timestamp conversions happen at TimeManager/DataManager boundaries
        
        Query: SELECT timezone FROM market_hours 
               WHERE exchange_group = ? AND asset_class = ?
        
        Example:
            exchange_group = "US_EQUITY"
            asset_class = "EQUITY"
            → timezone = "America/New_York"
        """
        try:
            with SessionLocal() as session:
                # Query MarketHours for timezone
                from app.models.trading_calendar import MarketHours
                market_hours = session.query(MarketHours).filter_by(
                    exchange_group=self.exchange_group,
                    asset_class=self.asset_class
                ).first()
                
                if market_hours:
                    self.timezone = market_hours.timezone
                    logger.debug(f"Timezone set to: {self.timezone}")
                else:
                    # Fallback to US Eastern
                    self.timezone = "America/New_York"
                    logger.warning(
                        f"No timezone found for {self.exchange_group}/{self.asset_class}, "
                        f"defaulting to {self.timezone}"
                    )
        except Exception as e:
            # Fallback on error
            self.timezone = "America/New_York"
            logger.warning(f"Error looking up timezone: {e}, defaulting to {self.timezone}")
    
    # =========================================================================
    # System Lifecycle
    # =========================================================================
    
    def start(self, config_file: Optional[str] = None) -> bool:
        """
        Start the trading system.
        
        Workflow:
        1. Load session configuration
        2. Initialize managers (TimeManager, DataManager)
        3. Apply backtest configuration (if backtest mode)
        4. Create SessionData (unified store)
        5. Create 4-thread pool
        6. Wire threads together
        7. Start SessionCoordinator (orchestrates everything)
        
        Args:
            config_file: Path to session config (default: session_configs/example_session.json)
            
        Returns:
            True if started successfully
            
        Raises:
            RuntimeError: If system already running or startup fails
        """
        if self._state == SystemState.RUNNING:
            raise RuntimeError("System already running")
        
        # Default config
        if config_file is None:
            config_file = "session_configs/example_session.json"
        
        logger.info("=" * 70)
        logger.info("STARTING TRADING SYSTEM")
        logger.info("=" * 70)
        
        try:
            # 1. Load configuration
            logger.info("[SESSION_FLOW] 2.a: SystemManager - Loading configuration")
            logger.info(f"Loading configuration: {config_file}")
            self._session_config = self.load_session_config(config_file)
            logger.info(f"[SESSION_FLOW] 2.a: Complete - Config loaded: {self._session_config.session_name}")
            
            # 2. Initialize managers
            logger.info("[SESSION_FLOW] 2.b: SystemManager - Initializing managers")
            logger.info("Initializing managers...")
            time_manager = self.get_time_manager()
            logger.info("[SESSION_FLOW] 2.b.1: TimeManager created")
            data_manager = self.get_data_manager()
            logger.info("[SESSION_FLOW] 2.b.2: DataManager created")
            scanner_manager = self.get_scanner_manager()
            logger.info("[SESSION_FLOW] 2.b.3: ScannerManager created")
            
            # Initialize scanner manager (load scanners from config)
            success = scanner_manager.initialize()
            if not success:
                raise RuntimeError("Scanner manager initialization failed")
            logger.info("[SESSION_FLOW] 2.b.4: ScannerManager initialized")
            
            # Get strategy manager
            strategy_manager = self.get_strategy_manager()
            logger.info("[SESSION_FLOW] 2.b.5: StrategyManager created")
            
            # Initialize strategy manager (load strategies from config)
            success = strategy_manager.initialize()
            if not success:
                raise RuntimeError("Strategy manager initialization failed")
            logger.info("[SESSION_FLOW] 2.b.6: StrategyManager initialized")
            
            # Start strategies (before threads start)
            success = strategy_manager.start_strategies()
            if not success:
                raise RuntimeError("Failed to start strategies")
            logger.info("[SESSION_FLOW] 2.b.7: Strategies started")
            
            logger.info("[SESSION_FLOW] 2.b: Complete - Managers initialized")
            
            # 3. Apply backtest configuration (if needed)
            if self._session_config.mode == "backtest" and self._session_config.backtest_config:
                logger.info("[SESSION_FLOW] 2.c: SystemManager - Applying backtest configuration")
                logger.info("Applying backtest configuration...")
                with SessionLocal() as db:
                    # Initialize backtest window
                    time_manager.init_backtest(db)
                    logger.info(
                        f"Backtest window: {time_manager.backtest_start_date} to "
                        f"{time_manager.backtest_end_date}"
                    )
                    logger.info(
                        f"[SESSION_FLOW] 2.c: Complete - Backtest window set: "
                        f"{time_manager.backtest_start_date} to {time_manager.backtest_end_date}"
                    )
            
            # 4. Create SessionData (unified store) - use singleton
            logger.info("[SESSION_FLOW] 2.d: SystemManager - Getting SessionData singleton")
            logger.info("Getting SessionData singleton...")
            session_data = get_session_data()  # Use singleton
            logger.info("[SESSION_FLOW] 2.d: Complete - SessionData singleton obtained")
            
            # 5. Create thread pool
            logger.info("[SESSION_FLOW] 2.e: SystemManager - Creating 4-thread pool")
            logger.info("Creating thread pool...")
            self._create_thread_pool(session_data, time_manager, data_manager)
            logger.info("[SESSION_FLOW] 2.e: Complete - Thread pool created")
            
            # 6. Wire threads together
            logger.info("[SESSION_FLOW] 2.f: SystemManager - Wiring threads together")
            logger.info("Wiring thread pool...")
            self._wire_threads()
            logger.info("[SESSION_FLOW] 2.f: Complete - Threads wired")
            
            # 7. Start all threads in correct order
            logger.info("[SESSION_FLOW] 2.g: SystemManager - Starting thread pool")
            
            # Start Data Processor (generates derived bars + indicators)
            logger.info("Starting DataProcessor thread...")
            self._data_processor.start()
            logger.info("[SESSION_FLOW] 2.g.1: DataProcessor thread started")
            
            # Start Data Quality Manager (measures quality, fills gaps)
            logger.info("Starting DataQualityManager thread...")
            self._quality_manager.start()
            logger.info("[SESSION_FLOW] 2.g.2: DataQualityManager thread started")
            
            # Start Analysis Engine (trading signals)
            logger.info("Starting AnalysisEngine thread...")
            self._analysis_engine.start()
            logger.info("[SESSION_FLOW] 2.g.3: AnalysisEngine thread started")
            
            # Start SessionCoordinator last (orchestrates everything)
            logger.info("Starting SessionCoordinator thread...")
            self._coordinator.start()
            logger.info("[SESSION_FLOW] 2.g.4: SessionCoordinator thread started")
            
            logger.info("[SESSION_FLOW] 2.g: Complete - All threads started")
            
            # 8. Update state
            self._state = SystemState.RUNNING
            logger.info("[SESSION_FLOW] 2.h: SystemManager - State set to RUNNING")
            
            # 9. Success message
            self._log_startup_success()
            logger.info("[SESSION_FLOW] 2: Complete - SystemManager.start() finished")
            
            return True
            
        except Exception as e:
            logger.error(f"System startup failed: {e}", exc_info=True)
            self._state = SystemState.STOPPED
            raise RuntimeError(f"System startup failed: {e}") from e
    
    def _create_thread_pool(
        self,
        session_data: SessionData,
        time_manager: 'TimeManager',
        data_manager: 'DataManager'
    ):
        """
        Create 4-thread pool.
        
        Threads:
        1. SessionCoordinator - Session orchestrator
        2. DataProcessor - Derived bars + indicators
        3. DataQualityManager - Quality + gap filling
        4. AnalysisEngine - Strategy execution
        
        Args:
            session_data: Unified data store
            time_manager: TimeManager instance
            data_manager: DataManager instance
        """
        # Import thread classes
        from app.threads.session_coordinator import SessionCoordinator
        from app.threads.data_processor import DataProcessor
        from app.threads.data_quality_manager import DataQualityManager
        from app.threads.analysis_engine import AnalysisEngine
        
        # 1. Create SessionCoordinator (main orchestrator)
        logger.debug("Creating SessionCoordinator...")
        self._coordinator = SessionCoordinator(
            system_manager=self,
            data_manager=data_manager
        )
        
        # 2. Create DataProcessor (derived bars + indicators)
        logger.debug("Creating DataProcessor...")
        self._data_processor = DataProcessor(
            session_data=session_data,
            system_manager=self,
            metrics=self._performance_metrics,
            strategy_manager=self._strategy_manager
        )
        
        # 3. Create DataQualityManager (quality + gap filling)
        logger.debug("Creating DataQualityManager...")
        self._quality_manager = DataQualityManager(
            session_data=session_data,
            system_manager=self,
            metrics=self._performance_metrics,
            data_manager=data_manager
        )
        
        # 4. Create AnalysisEngine (strategy execution)
        logger.debug("Creating AnalysisEngine...")
        self._analysis_engine = AnalysisEngine(
            session_data=session_data,
            system_manager=self,
            metrics=self._performance_metrics
        )
        
        logger.success("Thread pool created (4 threads)")
    
    def _wire_threads(self):
        """
        Wire threads together via queues and subscriptions.
        
        Communication:
        - Coordinator → DataProcessor (via subscription)
        - Coordinator → DataQualityManager (via subscription)
        - DataProcessor → AnalysisEngine (via queue)
        """
        from app.threads.sync.stream_subscription import StreamSubscription
        import queue
        
        # Determine subscription mode based on session config
        if self._session_config.mode == "live":
            subscription_mode = "live"
        elif self._session_config.backtest_config and self._session_config.backtest_config.speed_multiplier == 0:
            subscription_mode = "data-driven"
        else:
            subscription_mode = "clock-driven"
        
        logger.debug(f"Using subscription mode: {subscription_mode}")
        
        # 1. Create processor subscription (coordinator → processor)
        logger.debug("Creating processor subscription...")
        processor_subscription = StreamSubscription(
            mode=subscription_mode,
            stream_id="coordinator->data_processor"
        )
        
        # 2. Create analysis queue (processor → analysis)
        logger.debug("Creating analysis queue...")
        analysis_queue = queue.Queue()
        
        # 2.5. Create analysis subscription (analysis → processor, for data-driven sync)
        logger.debug("Creating analysis subscription...")
        analysis_subscription = StreamSubscription(
            mode=subscription_mode,
            stream_id="analysis_engine->data_processor"
        )
        
        # 3. Wire coordinator → processor
        self._coordinator.set_data_processor(
            self._data_processor,
            processor_subscription
        )
        
        # 4. Wire coordinator → quality manager
        self._coordinator.set_quality_manager(self._quality_manager)
        
        # 4.5. Wire indicator_manager to data_processor (Phase 6b)
        if hasattr(self._coordinator, 'indicator_manager'):
            self._data_processor.indicator_manager = self._coordinator.indicator_manager
            logger.debug("Wired indicator_manager to data_processor")
        
        # 5. Wire processor → analysis (queue and subscription)
        self._data_processor.set_analysis_engine_queue(analysis_queue)
        self._data_processor.set_analysis_subscription(analysis_subscription)
        self._analysis_engine.set_notification_queue(analysis_queue)
        self._analysis_engine.set_processor_subscription(analysis_subscription)
        
        logger.success("Thread pool wired")
    
    def _log_startup_success(self):
        """Log startup success message with configuration details."""
        config = self._session_config
        
        logger.info("=" * 70)
        logger.success("SYSTEM STARTED SUCCESSFULLY")
        logger.info("=" * 70)
        logger.info("")
        logger.info(f"Session:        {config.session_name}")
        logger.info(f"Mode:           {config.mode}")
        logger.info(f"Exchange:       {config.exchange_group}")
        logger.info(f"Asset Class:    {config.asset_class}")
        logger.info(f"Timezone:       {self.timezone}")
        logger.info("")
        
        # Session data config
        sdc = config.session_data_config
        logger.info(f"Symbols:        {', '.join(sdc.symbols)}")
        logger.info(f"Streams:        {', '.join(sdc.streams)}")
        
        # Historical config
        if sdc.historical and sdc.historical.data:
            logger.info(f"Historical:     {len(sdc.historical.data)} config(s)")
            for hist in sdc.historical.data:
                logger.info(
                    f"  - {hist.trailing_days} days x "
                    f"{len(hist.intervals)} intervals"
                )
        
        # Backtest config (query TimeManager for dates - single source of truth)
        if config.mode == "backtest":
            time_mgr = self.get_time_manager()
            logger.info("")
            logger.info(f"Start Date:     {time_mgr.backtest_start_date}")
            logger.info(f"End Date:       {time_mgr.backtest_end_date}")
            if config.backtest_config:
                logger.info(f"Speed:          {config.backtest_config.speed_multiplier}x")
        
        logger.info("")
        logger.info("Thread Pool:    4 threads")
        logger.info("  1. SessionCoordinator")
        logger.info("  2. DataProcessor")
        logger.info("  3. DataQualityManager")
        logger.info("  4. AnalysisEngine")
        logger.info("")
        logger.info("=" * 70)
    
    def stop(self) -> bool:
        """
        Stop the trading system.
        
        Stops threads in reverse order:
        1. AnalysisEngine
        2. DataProcessor
        3. DataQualityManager
        4. SessionCoordinator
        
        Returns:
            True if stopped successfully
        """
        if self._state == SystemState.STOPPED:
            logger.debug("System already stopped")
            return True
        
        logger.info("=" * 70)
        logger.info("STOPPING TRADING SYSTEM")
        logger.info("=" * 70)
        
        # Stop strategies first (before threads)
        if self._strategy_manager is not None:
            logger.info("Stopping strategies...")
            self._strategy_manager.stop_strategies()
            logger.success("Strategies stopped")
        
        # Stop threads in reverse order
        if self._analysis_engine is not None:
            logger.info("Stopping AnalysisEngine...")
            self._analysis_engine.stop()
            self._analysis_engine.join(timeout=5.0)
            self._analysis_engine = None
            logger.success("AnalysisEngine stopped")
        
        if self._data_processor is not None:
            logger.info("Stopping DataProcessor...")
            self._data_processor.stop()
            self._data_processor.join(timeout=5.0)
            self._data_processor = None
            logger.success("DataProcessor stopped")
        
        if self._quality_manager is not None:
            logger.info("Stopping DataQualityManager...")
            self._quality_manager.stop()
            self._quality_manager.join(timeout=5.0)
            self._quality_manager = None
            logger.success("DataQualityManager stopped")
        
        if self._coordinator is not None:
            logger.info("Stopping SessionCoordinator...")
            self._coordinator.stop()
            self._coordinator.join(timeout=5.0)
            self._coordinator = None
            logger.success("SessionCoordinator stopped")
        
        # Clear config
        self._session_config = None
        
        # Update state
        self._state = SystemState.STOPPED
        
        logger.info("=" * 70)
        logger.success("SYSTEM STOPPED")
        logger.info("=" * 70)
        
        return True
    
    def pause(self) -> bool:
        """
        Pause the backtest.
        
        Only applies to backtest mode - ignored in live mode.
        
        In backtest mode, pauses:
        - Time advancement (data-driven and clock-driven)
        - Bar processing
        - All downstream processing (processor, analysis)
        
        System state changes to PAUSED.
        Threads remain alive but idle (blocked on pause event).
        
        Returns:
            True if paused successfully, False if not applicable
        
        Raises:
            RuntimeError: If system not running
        """
        if self._state != SystemState.RUNNING:
            raise RuntimeError(f"Cannot pause - system is {self._state.value}")
        
        if self._mode != OperationMode.BACKTEST:
            logger.warning("[PAUSE] Ignored - only applies to backtest mode")
            return False
        
        logger.info("=" * 70)
        logger.info("PAUSING BACKTEST")
        logger.info("=" * 70)
        
        # Pause coordinator streaming
        if self._coordinator is not None:
            self._coordinator.pause_backtest()
        
        # Update state
        self._state = SystemState.PAUSED
        
        logger.success("BACKTEST PAUSED")
        logger.info("=" * 70)
        
        return True
    
    def resume(self) -> bool:
        """
        Resume the backtest.
        
        Only applies to backtest mode - ignored in live mode.
        Resumes time advancement and processing.
        
        System state changes back to RUNNING.
        
        Returns:
            True if resumed successfully, False if not applicable
        
        Raises:
            RuntimeError: If system not paused
        """
        if self._state != SystemState.PAUSED:
            raise RuntimeError(f"Cannot resume - system is {self._state.value}")
        
        if self._mode != OperationMode.BACKTEST:
            logger.warning("[RESUME] Ignored - only applies to backtest mode")
            return False
        
        logger.info("=" * 70)
        logger.info("RESUMING BACKTEST")
        logger.info("=" * 70)
        
        # Resume coordinator streaming
        if self._coordinator is not None:
            self._coordinator.resume_backtest()
        
        # Update state
        self._state = SystemState.RUNNING
        
        logger.success("BACKTEST RESUMED")
        logger.info("=" * 70)
        
        return True
    
    # =========================================================================
    # State Queries
    # =========================================================================
    
    def is_running(self) -> bool:
        """Check if system is running (not stopped, not paused)."""
        return self._state == SystemState.RUNNING
    
    def is_stopped(self) -> bool:
        """Check if system is stopped."""
        return self._state == SystemState.STOPPED
    
    def is_paused(self) -> bool:
        """Check if system is paused."""
        return self._state == SystemState.PAUSED
    
    def get_state(self) -> SystemState:
        """Get current system state."""
        return self._state
    
    # =========================================================================
    # Backtest Window Management (modifies SessionConfig)
    # =========================================================================
    
    def set_backtest_window(
        self,
        start_date: date,
        end_date: date
    ) -> None:
        """Update backtest window in SessionConfig (single source of truth).
        
        This modifies the SessionConfig's BacktestConfig, which TimeManager
        reads via properties. The config becomes the live configuration.
        
        Args:
            start_date: New backtest start date
            end_date: New backtest end date
            
        Raises:
            RuntimeError: If system not initialized or not in backtest mode
            ValueError: If dates are invalid
        """
        if self._session_config is None:
            raise RuntimeError("System not initialized")
        
        if self._session_config.mode != "backtest":
            raise RuntimeError("System must be in backtest mode to set backtest window")
        
        if self._session_config.backtest_config is None:
            raise ValueError("Backtest config not available")
        
        if start_date > end_date:
            raise ValueError(f"start_date ({start_date}) cannot be after end_date ({end_date})")
        
        # Modify SessionConfig (single source of truth)
        self._session_config.backtest_config.start_date = start_date.strftime("%Y-%m-%d")
        self._session_config.backtest_config.end_date = end_date.strftime("%Y-%m-%d")
        
        logger.info(
            "Backtest window updated in SessionConfig: %s to %s",
            start_date,
            end_date
        )
        
        # Reset TimeManager clock if time manager exists
        if self._time_manager is not None:
            from app.models.database import SessionLocal
            with SessionLocal() as db_session:
                self._time_manager.reset_backtest_clock(db_session)
    
    # =========================================================================
    # System Information Export
    # =========================================================================
    
    def system_info(self, complete: bool = True) -> dict:
        """Export system state to JSON format.
        
        Args:
            complete: If True, return full data including historical.
                     If False, return delta (only new session data, excludes historical).
        
        Returns:
            Dictionary matching SYSTEM_JSON_EXAMPLE.json format
            
        Delta Mode Strategy:
            - **Always sent**: System metadata, threads, performance metrics (small, frequently changing)
            - **Filtered**: Session data (bars, ticks, quotes) - only new data since last export
            - **Excluded**: Historical data (massive, never changes after load)
            
        Metadata:
            - delta: true/false flag indicating if this is a delta export
            - last_update: ISO timestamp of previous export (delta mode only)
            
        Performance:
            - Complete mode: ~17K lines (includes all historical data)
            - Delta mode: ~10-50 lines (only new session data since last export)
        """
        from datetime import datetime
        from app.managers.data_manager.session_data import get_session_data
        
        # Get current time from TimeManager (if available)
        if self._time_manager:
            current_time = self._time_manager.get_current_time()
        else:
            # Fallback to system time if TimeManager not initialized
            current_time = datetime.now()
        
        # Build backtest_window if TimeManager is available
        backtest_window = None
        if self._time_manager and hasattr(self._time_manager, 'backtest_start_date'):
            backtest_window = {
                "start_date": self._time_manager.backtest_start_date.isoformat() if self._time_manager.backtest_start_date else None,
                "end_date": self._time_manager.backtest_end_date.isoformat() if self._time_manager.backtest_end_date else None
            }
        
        result = {
            "system_manager": {
                "_state": self._state.value if self._state else "STOPPED",
                "_mode": self._mode.value if self._mode else "BACKTEST",
                "_start_time": self._start_time.isoformat() if hasattr(self, '_start_time') and self._start_time else None,
                "timezone": self.timezone,
                "exchange_group": self.exchange_group,
                "asset_class": self.asset_class,
                "backtest_window": backtest_window
            },
            "performance_metrics": self._performance_metrics.get_backtest_summary() if self._performance_metrics else {},
            "time_manager": self._time_manager.to_json() if self._time_manager else {},
            "threads": {},
            "session_data": {},  # Will populate below
            "_metadata": {
                "generated_at": current_time.isoformat(),
                "version": "2.0",
                "mode": "complete" if complete else "delta",  # Explicit mode indicator
                "delta": not complete,  # True if delta mode, False if complete
                "complete": complete,
                "diff_mode": not complete,
                "last_update": None,  # Will be populated for delta mode
                "changed_paths": []  # Delta tracking not yet implemented
            }
        }
        
        # Get session_data from singleton (not a SystemManager attribute)
        last_update_time = None
        try:
            session_data = get_session_data()
            session_data_dict, last_export_time = session_data.to_json(complete=complete)
            result["session_data"] = session_data_dict
            last_update_time = last_export_time
        except Exception as e:
            logger.warning(f"Could not export session_data: {e}")
            result["session_data"] = {}
        
        # Add session_config (only in complete mode)
        if complete and self._session_config:
            try:
                result["session_config"] = self._session_config.to_dict()
            except Exception as e:
                logger.warning(f"Could not export session_config: {e}")
                result["session_config"] = None
        
        # Add thread information
        if hasattr(self, '_session_coordinator') and self._session_coordinator:
            result["threads"]["session_coordinator"] = self._session_coordinator.to_json(complete=complete)
        
        if hasattr(self, '_data_processor') and self._data_processor:
            result["threads"]["data_processor"] = self._data_processor.to_json(complete=complete)
        
        if hasattr(self, '_quality_manager') and self._quality_manager:
            result["threads"]["data_quality_manager"] = self._quality_manager.to_json(complete=complete)
        
        if hasattr(self, '_analysis_engine') and self._analysis_engine:
            result["threads"]["analysis_engine"] = self._analysis_engine.to_json(complete=complete)
        
        # Update metadata with last_update time (for delta mode)
        if last_update_time:
            result["_metadata"]["last_update"] = last_update_time.isoformat()
        
        return result
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def session_config(self) -> Optional[SessionConfig]:
        """Get current session configuration."""
        return self._session_config
    
    @property
    def state(self) -> SystemState:
        """Get current system state."""
        return self._state
    
    @property
    def performance_metrics(self) -> PerformanceMetrics:
        """Get performance metrics."""
        return self._performance_metrics


# =============================================================================
# Singleton Pattern
# =============================================================================

_system_manager_instance: Optional[SystemManager] = None


def get_system_manager() -> SystemManager:
    """
    Get SystemManager singleton.
    
    Returns:
        SystemManager instance (creates if doesn't exist)
        
    Usage:
        system_mgr = get_system_manager()
        system_mgr.start("session_configs/example_session.json")
    """
    global _system_manager_instance
    if _system_manager_instance is None:
        _system_manager_instance = SystemManager()
    return _system_manager_instance


def reset_system_manager():
    """
    Reset SystemManager singleton (for testing).
    
    WARNING: Only use in tests.
    """
    global _system_manager_instance
    if _system_manager_instance is not None and _system_manager_instance.is_running():
        _system_manager_instance.stop()
    _system_manager_instance = None
