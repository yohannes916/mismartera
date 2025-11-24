"""Time Provider

Provides current time for live and backtest modes.

ARCHITECTURE (2025-11):
- **SystemManager** is the ONLY source of truth for operation mode
- **TimeProvider** receives SystemManager reference and queries SystemManager.mode
- **NO FALLBACKS** to settings - SystemManager must be provided
- All components must use SystemManager for mode checks

This ensures a single source of truth and prevents mode inconsistencies.

IMPORTANT: TimeProvider is a SINGLETON - all components (DataManager, 
BacktestStreamCoordinator, etc.) share the same instance to ensure 
consistent time across the application.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from app.config import settings
from app.logger import logger


# Global singleton instance
_time_provider_instance: Optional['TimeProvider'] = None


class TimeProvider:
    """Provides time in both live and backtest modes.

    In backtest mode, time comes from the data being processed and is stored
    in an internal _backtest_time value.
    
    MODE MANAGEMENT:
    - SystemManager is the ONLY source of truth for operation mode
    - TimeProvider requires SystemManager reference
    
    TIME ADVANCEMENT:
    - Live mode: Returns current system time (no state)
    - Backtest mode: Returns _backtest_time (advanced by BacktestStreamCoordinator)
    
    This class is a SINGLETON - use get_time_provider() to obtain the instance.
    """

    def __init__(self, system_manager=None) -> None:
        """Initialize TimeProvider with SystemManager reference.
        
        Args:
            system_manager: Reference to SystemManager (REQUIRED for production use)
        
        IMPORTANT: Do not call directly. Use get_time_provider() instead.
        """
        self._system_manager = system_manager
        self._backtest_time: Optional[datetime] = None
        
        if system_manager is None:
            logger.warning("TimeProvider initialized without SystemManager - mode checks will fail!")
        else:
            logger.debug("TimeProvider initialized with SystemManager reference")

    def get_current_time(self) -> datetime:
        """Get current time based on SystemManager.mode.
        
        SystemManager is the ONLY source of truth for operation mode.
        
        AUTO-INITIALIZATION: If in backtest mode and time is not set,
        automatically initializes backtest window and time on first access.

        Returns:
            Current datetime (naive, interpreted as ET)
            
        Raises:
            ValueError: If invalid mode or SystemManager not available
        """
        if self._system_manager is None:
            raise ValueError(
                "SystemManager not available in TimeProvider. "
                "TimeProvider must be initialized with SystemManager reference."
            )
        
        mode = self._system_manager.mode.value

        if mode == "live":
            # Real-time clock in canonical trading timezone (ET). We return a
            # naive datetime that should be interpreted as Eastern Time by all
            # DataManager APIs.
            tz = ZoneInfo(settings.TRADING_TIMEZONE)
            return datetime.now(tz).replace(tzinfo=None)
        if mode == "backtest":
            # Auto-initialize on first access
            if self._backtest_time is None:
                logger.info("Backtest time not set - auto-initializing from settings")
                self._auto_initialize_backtest()
            return self._backtest_time

        raise ValueError(f"Invalid operation mode: {mode}")
    
    def _auto_initialize_backtest(self) -> None:
        """Auto-initialize backtest window and time on first access.
        
        This is called automatically by get_current_time() when in backtest mode
        and time hasn't been set yet. Uses settings values to configure backtest.
        """
        try:
            # Get DataManager from SystemManager
            data_mgr = self._system_manager.get_data_manager()
            if data_mgr is None:
                raise ValueError("DataManager not available for auto-initialization")
            
            # Run async initialization
            import asyncio
            from app.models.database import AsyncSessionLocal
            
            async def _init():
                async with AsyncSessionLocal() as session:
                    await data_mgr.init_backtest(session)
            
            # Check if we're already in an async context
            try:
                asyncio.get_running_loop()
                # We're in an async context - we can't block it, so raise an error
                # The caller should use async initialization instead
                raise ValueError(
                    "Cannot auto-initialize backtest from within async context. "
                    "Call 'await data_mgr.init_backtest(session)' directly."
                )
            except RuntimeError:
                # No running loop - safe to create one and run
                asyncio.run(_init())
            
            logger.info(
                f"Auto-initialized backtest: {data_mgr.backtest_start_date} to "
                f"{data_mgr.backtest_end_date} ({data_mgr.backtest_days} trading days)"
            )
        except Exception as e:
            logger.error(f"Failed to auto-initialize backtest: {e}", exc_info=True)
            raise ValueError(
                f"Backtest time not set and auto-initialization failed: {e}. "
                "Call DataManager.init_backtest() manually or use 'data init' command."
            )

    def set_backtest_time(self, timestamp: datetime) -> None:
        """Set the current time for backtest mode.

        IMPORTANT: In normal operation, this is called ONLY by the 
        BacktestStreamCoordinator as it yields data chronologically.
        Manual calls should be limited to initialization (reset to start)
        or special testing scenarios.
        
        SYSTEM STATE: BacktestStreamCoordinator checks SystemManager.is_running()
        before calling this method to ensure state-aware time advancement.

        Args:
            timestamp: Timestamp to set as current backtest time
        """
        if self._system_manager is None:
            logger.warning("SystemManager not available - cannot verify mode for set_backtest_time")
            self._backtest_time = timestamp
            return
        
        mode = self._system_manager.mode.value
        if mode != "backtest":
            logger.warning(
                "set_backtest_time called while mode=%s (ignored)",
                mode,
            )
            return

        self._backtest_time = timestamp
        logger.debug("Backtest time set to: %s", timestamp)


def get_time_provider(system_manager=None) -> TimeProvider:
    """Get or create the global TimeProvider singleton instance.
    
    Args:
        system_manager: Reference to SystemManager (required for production use)
    
    Returns:
        The singleton TimeProvider instance
    """
    global _time_provider_instance
    if _time_provider_instance is None:
        _time_provider_instance = TimeProvider(system_manager=system_manager)
        logger.info("TimeProvider singleton instance created")
    return _time_provider_instance


def reset_time_provider() -> None:
    """Reset the global TimeProvider singleton (useful for testing).
    
    This will create a new instance the next time get_time_provider() is called.
    """
    global _time_provider_instance
    _time_provider_instance = None
    logger.info("TimeProvider singleton instance reset")
