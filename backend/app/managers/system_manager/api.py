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

import logging
from pathlib import Path
from typing import Optional

from app.logger import logger

# Core primitives
from app.core.session_data import SessionData
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
        
        # Thread pool (created on start)
        self._coordinator: Optional['SessionCoordinator'] = None
        self._data_processor: Optional['DataProcessor'] = None
        self._quality_manager: Optional['DataQualityManager'] = None
        self._analysis_engine: Optional['AnalysisEngine'] = None
        
        # Performance metrics
        self._performance_metrics = PerformanceMetrics()
        
        # System state
        self._state = SystemState.STOPPED
        self._session_config: Optional[SessionConfig] = None
        
        # Exchange configuration (derived from session config)
        self.exchange_group: str = "US_EQUITY"  # Default
        self.asset_class: str = "EQUITY"  # Default
        
        # Timezone (derived from exchange_group + asset_class via MarketHours database)
        # CRITICAL: This is the market timezone used by TimeManager and DataManager
        # All timestamps returned by managers are in this timezone
        self.timezone: Optional[str] = None  # Derived from exchange+asset
        
        logger.info("SystemManager initialized")
    
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
            self._data_manager = DataManager(self)
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
            logger.info(f"Loading configuration: {config_file}")
            self._session_config = self.load_session_config(config_file)
            
            # 2. Initialize managers
            logger.info("Initializing managers...")
            time_manager = self.get_time_manager()
            data_manager = self.get_data_manager()
            
            # 3. Apply backtest configuration (if needed)
            if self._session_config.mode == "backtest" and self._session_config.backtest_config:
                logger.info("Applying backtest configuration...")
                with SessionLocal() as db:
                    # Initialize backtest window
                    time_manager.init_backtest(db)
                    logger.info(
                        f"Backtest window: {time_manager.backtest_start_date} to "
                        f"{time_manager.backtest_end_date}"
                    )
            
            # 4. Create SessionData (unified store)
            logger.info("Creating SessionData...")
            session_data = SessionData()
            
            # 5. Create thread pool
            logger.info("Creating thread pool...")
            self._create_thread_pool(session_data, time_manager, data_manager)
            
            # 6. Wire threads together
            logger.info("Wiring thread pool...")
            self._wire_threads()
            
            # 7. Start coordinator (orchestrates everything)
            logger.info("Starting session coordinator...")
            self._coordinator.start()
            
            # 8. Update state
            self._state = SystemState.RUNNING
            
            # 9. Success message
            self._log_startup_success()
            
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
            data_manager=data_manager,
            session_config=self._session_config,
            mode=self._session_config.mode
        )
        
        # 2. Create DataProcessor (derived bars + indicators)
        logger.debug("Creating DataProcessor...")
        self._data_processor = DataProcessor(
            session_data=session_data,
            system_manager=self,
            session_config=self._session_config,
            metrics=self._performance_metrics
        )
        
        # 3. Create DataQualityManager (quality + gap filling)
        logger.debug("Creating DataQualityManager...")
        self._quality_manager = DataQualityManager(
            session_data=session_data,
            system_manager=self,
            session_config=self._session_config,
            metrics=self._performance_metrics,
            data_manager=data_manager
        )
        
        # 4. Create AnalysisEngine (strategy execution)
        logger.debug("Creating AnalysisEngine...")
        self._analysis_engine = AnalysisEngine(
            session_data=session_data,
            system_manager=self,
            session_config=self._session_config,
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
        
        # 3. Wire coordinator → processor
        self._coordinator.set_data_processor(
            self._data_processor,
            processor_subscription
        )
        
        # 4. Wire coordinator → quality manager
        self._coordinator.set_quality_manager(self._quality_manager)
        
        # 5. Wire processor → analysis
        self._data_processor.set_analysis_engine_queue(analysis_queue)
        self._analysis_engine.set_notification_queue(analysis_queue)
        
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
                logger.info(f"Prefetch:       {config.backtest_config.prefetch_days} days")
        
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
    
    # =========================================================================
    # State Queries
    # =========================================================================
    
    def is_running(self) -> bool:
        """Check if system is running."""
        return self._state == SystemState.RUNNING
    
    def is_stopped(self) -> bool:
        """Check if system is stopped."""
        return self._state == SystemState.STOPPED
    
    def get_state(self) -> SystemState:
        """Get current system state."""
        return self._state
    
    @property
    def session_config(self) -> Optional[SessionConfig]:
        """Get current session configuration."""
        return self._session_config
    
    @property
    def state(self) -> SystemState:
        """Get current system state."""
        return self._state
    
    @property
    def mode(self) -> OperationMode:
        """Get current operation mode from session config."""
        if self._session_config is None:
            raise RuntimeError("Session config not loaded")
        return OperationMode(self._session_config.mode)
    
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
