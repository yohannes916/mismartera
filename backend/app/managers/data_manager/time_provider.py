"""
Time Provider
Provides current time for real and backtest modes
"""
from datetime import datetime
from typing import Optional
from app.logger import logger


class TimeProvider:
    """
    Provides time in both real and backtest modes.
    In backtest mode, time comes from the data being processed.
    """
    
    def __init__(self, mode: str = "real"):
        """
        Initialize TimeProvider
        
        Args:
            mode: "real" or "backtest"
        """
        self.mode = mode
        self._backtest_time: Optional[datetime] = None
        logger.debug(f"TimeProvider initialized in {mode} mode")
    
    def get_current_time(self) -> datetime:
        """
        Get current time based on mode.
        
        Returns:
            Current datetime
        """
        if self.mode == "real":
            return datetime.now()
        elif self.mode == "backtest":
            if self._backtest_time is None:
                raise ValueError("Backtest time not set. Call set_backtest_time() first.")
            return self._backtest_time
        else:
            raise ValueError(f"Invalid mode: {self.mode}")
    
    def set_backtest_time(self, timestamp: datetime):
        """
        Set the current time for backtest mode.
        This should be called for each bar being processed.
        
        Args:
            timestamp: Timestamp from current bar
        """
        if self.mode != "backtest":
            logger.warning("set_backtest_time called but not in backtest mode")
            return
        
        self._backtest_time = timestamp
        logger.debug(f"Backtest time set to: {timestamp}")
    
    def set_mode(self, mode: str):
        """
        Change the operating mode.
        
        Args:
            mode: "real" or "backtest"
        """
        if mode not in ["real", "backtest"]:
            raise ValueError(f"Invalid mode: {mode}")
        
        self.mode = mode
        logger.info(f"TimeProvider mode changed to: {mode}")
        
        if mode == "real":
            self._backtest_time = None
