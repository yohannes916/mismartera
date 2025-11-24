"""System Manager - Central coordinator for all application managers.

This is the top-level singleton that:
1. Creates and manages all other manager singletons (DataManager, ExecutionManager, etc.)
2. Provides references between managers so they can access each other
3. Lives for the entire application lifetime
4. Ensures consistent state across all subsystems
5. Controls application run state (running, paused, stopped)
6. Manages operation mode (live vs backtest)

Architecture:
    SystemManager (singleton)
        ├── DataManager (singleton)
        ├── ExecutionManager (singleton)
        └── AnalysisEngine (singleton)

Each manager receives a reference to SystemManager, allowing them to access
other managers via system_manager.get_xxx_manager().
"""
from typing import Optional, TYPE_CHECKING
from enum import Enum
import json
from pathlib import Path
from datetime import datetime

from app.logger import logger
from app.models.session_config import SessionConfig

# Avoid circular imports
if TYPE_CHECKING:
    from app.managers.data_manager.api import DataManager


class SystemState(Enum):
    """System run states."""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class OperationMode(Enum):
    """System operation modes."""
    LIVE = "live"
    BACKTEST = "backtest"


# Global singleton instance
_system_manager_instance: Optional['SystemManager'] = None


class SystemManager:
    """Central manager that coordinates all application subsystems.
    
    This is a singleton that lives for the entire application lifetime.
    All other managers are created by and registered with the SystemManager.
    
    Benefits:
    - Single source of truth for manager instances
    - Enables inter-manager communication
    - Centralized lifecycle management
    - Consistent state across the application
    
    Usage:
        system_mgr = get_system_manager()
        data_mgr = system_mgr.get_data_manager()
        exec_mgr = system_mgr.get_execution_manager()
    """
    
    def __init__(self):
        """Initialize SystemManager.
        
        WARNING: Do not call directly. Use get_system_manager() instead.
        """
        # Manager instances (lazy-loaded)
        self._data_manager: Optional['DataManager'] = None
        self._execution_manager: Optional[object] = None  # TODO: Type when implemented
        self._analysis_engine: Optional[object] = None  # TODO: Type when implemented
        
        # System-wide state
        self._initialized = False
        self._state = SystemState.STOPPED
        
        # Session configuration (loaded on start)
        self._session_config: Optional[SessionConfig] = None
        
        # Operation mode (live or backtest)
        from app.config import settings
        mode_str = settings.SYSTEM_OPERATING_MODE.lower()
        self._mode = OperationMode.LIVE if mode_str == "live" else OperationMode.BACKTEST
        
        logger.info(f"SystemManager initialized in {self._mode.value} mode")
    
    def get_data_manager(self) -> 'DataManager':
        """Get or create the DataManager singleton.
        
        Returns:
            DataManager instance with reference to this SystemManager
        """
        if self._data_manager is None:
            from app.managers.data_manager.api import DataManager
            self._data_manager = DataManager(system_manager=self)
            logger.info("DataManager created by SystemManager")
        return self._data_manager
    
    def get_execution_manager(self) -> object:
        """Get or create the ExecutionManager singleton.
        
        Returns:
            ExecutionManager instance (placeholder for now)
        """
        if self._execution_manager is None:
            # TODO: Implement ExecutionManager
            logger.warning("ExecutionManager not yet implemented, returning placeholder")
            self._execution_manager = object()  # Placeholder
        return self._execution_manager
    
    def get_analysis_engine(self) -> object:
        """Get or create the AnalysisEngine singleton.
        
        Returns:
            AnalysisEngine instance (placeholder for now)
        """
        if self._analysis_engine is None:
            # TODO: Implement AnalysisEngine
            logger.warning("AnalysisEngine not yet implemented, returning placeholder")
            self._analysis_engine = object()  # Placeholder
        return self._analysis_engine
    
    def initialize(self):
        """Initialize all managers in correct order.
        
        Call this at application startup to ensure all managers are ready.
        """
        if self._initialized:
            logger.warning("SystemManager already initialized")
            return
        
        logger.info("Initializing SystemManager and all subsystems...")
        
        # Create all managers in dependency order
        self.get_data_manager()
        # self.get_execution_manager()  # TODO: Uncomment when implemented
        # self.get_analysis_engine()     # TODO: Uncomment when implemented
        
        self._initialized = True
        logger.info("SystemManager initialization complete")
    
    def shutdown(self):
        """Shutdown all managers gracefully.
        
        Call this at application shutdown to cleanup resources.
        """
        logger.info("Shutting down SystemManager and all subsystems...")
        
        # Shutdown in reverse dependency order
        # TODO: Add shutdown methods to managers as needed
        
        self._initialized = False
        logger.info("SystemManager shutdown complete")
    
    @property
    def is_initialized(self) -> bool:
        """Check if SystemManager has been initialized."""
        return self._initialized
    
    @property
    def state(self) -> SystemState:
        """Get current system state."""
        return self._state
    
    @property
    def mode(self) -> OperationMode:
        """Get current operation mode."""
        return self._mode
    
    def set_mode(self, mode: str) -> bool:
        """Set operation mode.
        
        Args:
            mode: "live" or "backtest"
            
        Returns:
            True if mode changed successfully, False otherwise
        """
        mode_lower = mode.lower()
        if mode_lower not in ["live", "backtest"]:
            logger.error(f"Invalid mode: {mode}. Must be 'live' or 'backtest'")
            return False
        
        new_mode = OperationMode.LIVE if mode_lower == "live" else OperationMode.BACKTEST
        
        if new_mode == self._mode:
            logger.info(f"Already in {mode_lower} mode")
            return True
        
        # Can only change mode when stopped
        if self._state != SystemState.STOPPED:
            logger.warning(f"Cannot change mode while system is {self._state.value}. Stop the system first.")
            return False
        
        old_mode = self._mode.value
        self._mode = new_mode
        logger.success(f"Operation mode changed: {old_mode} → {new_mode.value}")
        return True
    
    def is_live_mode(self) -> bool:
        """Check if system is in live mode."""
        return self._mode == OperationMode.LIVE
    
    def is_backtest_mode(self) -> bool:
        """Check if system is in backtest mode."""
        return self._mode == OperationMode.BACKTEST
    
    async def start(self, config_file_path: str) -> bool:
        """Start the system run with a mandatory configuration file.
        
        STRICT REQUIREMENTS:
        1. config_file_path is mandatory - no defaults or fallbacks
        2. File must exist and be valid JSON
        3. Configuration must pass validation
        4. Data streams are started before transitioning to RUNNING
        5. System state changes only after successful initialization
        
        Args:
            config_file_path: Absolute or relative path to session config JSON file
            
        Returns:
            True if started successfully
            
        Raises:
            ValueError: If config_file_path is None, empty, or invalid
            FileNotFoundError: If config file does not exist
            json.JSONDecodeError: If config file is not valid JSON
            Exception: If configuration validation or stream startup fails
        """
        # STRICT VALIDATION: No null, empty, or missing paths
        if not config_file_path:
            raise ValueError(
                "Configuration file path is mandatory. "
                "You must provide a valid path to a session configuration file."
            )
        
        if not isinstance(config_file_path, str) or not config_file_path.strip():
            raise ValueError(
                f"Invalid configuration file path: {config_file_path}. "
                "Path must be a non-empty string."
            )
        
        # Stop system first to ensure clean state
        # This handles RUNNING, PAUSED, or already STOPPED states
        if self._state != SystemState.STOPPED:
            logger.info(f"System in {self._state.value} state, stopping first...")
            await self.stop()
        
        logger.info(f"Starting system with configuration: {config_file_path}")
        
        try:
            # STRICT FILE VALIDATION: File must exist
            config_path = Path(config_file_path)
            if not config_path.exists():
                raise FileNotFoundError(
                    f"Configuration file not found: {config_file_path}\n"
                    f"Absolute path: {config_path.absolute()}\n"
                    "Please provide a valid path to a session configuration file."
                )
            
            if not config_path.is_file():
                raise ValueError(
                    f"Configuration path is not a file: {config_file_path}\n"
                    f"Please provide a path to a JSON configuration file."
                )
            
            # Load and parse JSON configuration
            logger.info(f"Loading configuration from: {config_path.absolute()}")
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            # Parse and validate configuration
            logger.info("Parsing and validating session configuration...")
            self._session_config = SessionConfig.from_dict(config_data)
            logger.success(f"Configuration loaded: {self._session_config.session_name}")
            
            # Apply operation mode from configuration
            if self._session_config.mode != self._mode.value:
                logger.info(f"Setting operation mode to: {self._session_config.mode}")
                if not self.set_mode(self._session_config.mode):
                    raise ValueError(f"Failed to set operation mode to: {self._session_config.mode}")
            
            # Initialize managers if needed
            if not self._initialized:
                self.initialize()
            
            # Apply session_data configuration BEFORE starting streams
            # This configures historical bars, data upkeep, prefetch, etc.
            from app.managers.data_manager.session_data import get_session_data
            session_data = get_session_data()
            if self._session_config.session_data_config:
                session_data.apply_config(self._session_config.session_data_config)
            
            # Apply backtest configuration if in backtest mode
            # DataManager is responsible for backtest window and speed configuration
            # TimeProvider will use these values as the single source of truth
            data_manager = self.get_data_manager()
            if self._session_config.mode == "backtest" and self._session_config.backtest_config:
                from app.models.database import AsyncSessionLocal
                from datetime import datetime
                
                logger.info(
                    f"Configuring backtest window: {self._session_config.backtest_config.start_date} to "
                    f"{self._session_config.backtest_config.end_date}"
                )
                
                # Parse dates
                start_date = datetime.strptime(self._session_config.backtest_config.start_date, "%Y-%m-%d").date()
                end_date = datetime.strptime(self._session_config.backtest_config.end_date, "%Y-%m-%d").date()
                
                # Set backtest window via DataManager (this also resets TimeProvider clock)
                async with AsyncSessionLocal() as db_session:
                    await data_manager.set_backtest_window(db_session, start_date, end_date)
                
                # Set backtest speed via DataManager (updates settings as single source of truth)
                await data_manager.set_backtest_speed(self._session_config.backtest_config.speed_multiplier)
                logger.info(f"Backtest speed multiplier: {self._session_config.backtest_config.speed_multiplier}")
            
            # Apply API configuration
            logger.info(f"Configuring data API: {self._session_config.api_config.data_api}")
            # TODO: Apply API config to data_manager when API selection is implemented
            
            # START CONFIGURED STREAMS
            logger.info(f"Starting {len(self._session_config.data_streams)} configured stream(s)...")
            
            from app.models.database import AsyncSessionLocal
            
            # Initialize backtest if needed
            if self._session_config.mode == "backtest" and data_manager.backtest_start_date is None:
                async with AsyncSessionLocal() as init_session:
                    await data_manager.init_backtest(init_session)
            
            # Verify TimeProvider is available
            current_time = data_manager.get_current_time()
            session_date = current_time.date()
            logger.info(f"Session date from TimeProvider: {session_date}")
            
            # Track stream startup results
            streams_started = 0
            streams_skipped = 0
            
            # Group streams by type for batch processing
            bars_symbols = []
            ticks_symbols = []
            quotes_symbols = []
            
            for idx, stream_config in enumerate(self._session_config.data_streams, 1):
                # Validate stream configuration
                if not stream_config.symbol:
                    raise ValueError(f"Stream {idx} missing symbol")
                
                if stream_config.type == "bars":
                    if not stream_config.interval:
                        raise ValueError(f"Bar stream for {stream_config.symbol} requires an interval")
                    
                    # ENFORCE: Only 1m bars can be streamed
                    # Derived intervals (5m, 15m, etc.) are computed by the upkeep thread
                    if stream_config.interval != "1m":
                        raise ValueError(
                            f"Stream coordinator only supports 1m bars. "
                            f"Symbol {stream_config.symbol} has interval '{stream_config.interval}'. "
                            f"Derived intervals (5m, 15m, etc.) are automatically computed by the data upkeep thread."
                        )
                    
                    bars_symbols.append((stream_config.symbol, stream_config.interval))
                elif stream_config.type == "ticks":
                    ticks_symbols.append(stream_config.symbol)
                elif stream_config.type == "quotes":
                    quotes_symbols.append(stream_config.symbol)
                else:
                    raise ValueError(f"Invalid stream type: {stream_config.type}")
            
            # Start bar streams using start_bar_streams() API
            if bars_symbols:
                # Group by interval
                from collections import defaultdict
                by_interval = defaultdict(list)
                for symbol, interval in bars_symbols:
                    by_interval[interval].append(symbol)
                
                for interval, symbols in by_interval.items():
                    logger.info(f"Starting bar streams ({interval}) for {len(symbols)} symbol(s): {', '.join(symbols)}")
                    
                    try:
                        async with AsyncSessionLocal() as stream_session:
                            # Call start_bar_streams() - blocks during fetch, then returns
                            # Streams continue running in coordinator worker thread
                            count = await data_manager.start_bar_streams(
                                stream_session,
                                symbols=symbols,
                                interval=interval
                            )
                            
                            streams_started += count
                            streams_skipped += len(symbols) - count
                            
                    except Exception as e:
                        logger.error(f"Failed to start bar streams: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        streams_skipped += len(symbols)
            
            # Ticks and quotes not yet implemented
            if ticks_symbols:
                logger.warning(f"⚠ Tick streams not yet implemented, skipping {len(ticks_symbols)} symbol(s)")
                streams_skipped += len(ticks_symbols)
            
            if quotes_symbols:
                logger.warning(f"⚠ Quote streams not yet implemented, skipping {len(quotes_symbols)} symbol(s)")
                streams_skipped += len(quotes_symbols)
            
            # Log summary
            if streams_started > 0:
                logger.success(f"✓ Started {streams_started} stream(s)")
            if streams_skipped > 0:
                logger.warning(f"⚠ Skipped {streams_skipped} stream(s) (unsupported or no data)")
            
            if streams_started == 0:
                logger.warning("No streams were started. System is running but inactive.")
            
            # CRITICAL: Only transition to RUNNING after streams are started
            self._state = SystemState.RUNNING
            
            # Build success message
            success_msg = (
                f"System started successfully!\n"
                f"  Session: {self._session_config.session_name}\n"
                f"  Mode: {self._session_config.mode.upper()}\n"
            )
            
            if self._session_config.mode == "backtest" and self._session_config.backtest_config:
                success_msg += (
                    f"  Backtest Window: {self._session_config.backtest_config.start_date} to "
                    f"{self._session_config.backtest_config.end_date}\n"
                    f"  Speed: {self._session_config.backtest_config.speed_multiplier}x (0=max)\n"
                )
            
            success_msg += (
                f"  Configured Streams: {len(self._session_config.data_streams)}\n"
                f"  Active Streams: {streams_started}\n"
            )
            
            if streams_skipped > 0:
                success_msg += f"  Skipped Streams: {streams_skipped}\n"
            
            success_msg += (
                f"  Max Buying Power: ${self._session_config.trading_config.max_buying_power:,.2f}\n"
                f"  Max Per Trade: ${self._session_config.trading_config.max_per_trade:,.2f}\n"
                f"  Paper Trading: {self._session_config.trading_config.paper_trading}\n"
            )
            
            if streams_started > 0:
                success_msg += "\nStreams are now active. Data is being streamed from the coordinator."
            else:
                success_msg += "\n⚠ No streams active. Import data and configure bar streams in your session config."
            
            logger.success(success_msg)
            return True
            
        except FileNotFoundError:
            # Re-raise file not found errors as-is
            raise
        except json.JSONDecodeError as e:
            # Invalid JSON format
            raise json.JSONDecodeError(
                f"Configuration file contains invalid JSON: {config_file_path}\n"
                f"Error: {e.msg}",
                e.doc,
                e.pos
            )
        except ValueError as e:
            # Configuration validation failed
            raise ValueError(
                f"Configuration validation failed: {config_file_path}\n"
                f"Error: {str(e)}"
            )
        except Exception as e:
            # Any other error during startup
            logger.error(f"System startup failed: {e}", exc_info=True)
            # Ensure system remains in STOPPED state on failure
            self._state = SystemState.STOPPED
            raise Exception(f"System startup failed: {str(e)}") from e
    
    def pause(self) -> bool:
        """Pause the system run.
        
        Transitions from RUNNING to PAUSED.
        Managers should suspend operations but maintain state.
        
        Returns:
            True if paused successfully, False if not running
        """
        if self._state != SystemState.RUNNING:
            logger.warning(f"Cannot pause system in state: {self._state.value}")
            return False
        
        logger.info("Pausing system...")
        
        # Pause all managers
        # TODO: Add manager-specific pause logic as needed
        
        self._state = SystemState.PAUSED
        logger.success("System paused")
        return True
    
    def resume(self) -> bool:
        """Resume the system from paused state.
        
        Transitions from PAUSED to RUNNING.
        
        Returns:
            True if resumed successfully, False if not paused
        """
        if self._state != SystemState.PAUSED:
            logger.warning(f"Cannot resume system in state: {self._state.value}")
            return False
        
        logger.info("Resuming system...")
        
        # Resume all managers
        # TODO: Add manager-specific resume logic as needed
        
        self._state = SystemState.RUNNING
        logger.success("System resumed")
        return True
    
    async def stop(self) -> bool:
        """Stop the system run.
        
        Transitions from any state to STOPPED.
        Stops all active data streams and cleans up resources.
        
        Returns:
            True if stopped successfully, False if already stopped
        """
        if self._state == SystemState.STOPPED:
            logger.debug("System already stopped")
            return True  # Already in desired state, not an error
        
        logger.info(f"Stopping system from state: {self._state.value}...")
        
        # Stop all data streams if data manager exists
        if self._data_manager is not None:
            logger.info("Stopping all active data streams...")
            await self._data_manager.stop_all_streams()
            logger.success("All data streams stopped")
        
        # Clear session configuration
        self._session_config = None
        
        # Transition to STOPPED state
        self._state = SystemState.STOPPED
        logger.success("System stopped")
        return True
    
    def is_running(self) -> bool:
        """Check if system is in RUNNING state."""
        return self._state == SystemState.RUNNING
    
    def is_paused(self) -> bool:
        """Check if system is in PAUSED state."""
        return self._state == SystemState.PAUSED
    
    def is_stopped(self) -> bool:
        """Check if system is in STOPPED state."""
        return self._state == SystemState.STOPPED
    
    @property
    def session_data(self):
        """Get the global session_data singleton.
        
        Returns:
            SessionData instance
        """
        from app.managers.data_manager.session_data import get_session_data
        return get_session_data()
    
    @property
    def session_config(self) -> Optional[SessionConfig]:
        """Get the current session configuration.
        
        Returns:
            SessionConfig if a session is active, None otherwise
        """
        return self._session_config


def get_system_manager() -> SystemManager:
    """Get or create the global SystemManager singleton instance.
    
    This is the main entry point for accessing the SystemManager.
    
    Returns:
        The singleton SystemManager instance
    """
    global _system_manager_instance
    if _system_manager_instance is None:
        _system_manager_instance = SystemManager()
        logger.info("SystemManager singleton instance created")
    return _system_manager_instance


def reset_system_manager() -> None:
    """Reset the global SystemManager singleton (useful for testing).
    
    WARNING: This will destroy all manager instances. Use with caution.
    """
    global _system_manager_instance
    if _system_manager_instance is not None:
        _system_manager_instance.shutdown()
    _system_manager_instance = None
    logger.info("SystemManager singleton instance reset")
