"""
Loguru logger configuration with runtime level control and deduplication
"""
from loguru import logger
import sys
import time
import threading
from pathlib import Path
from collections import deque
from typing import Dict, Any
from app.config import settings


class LogDeduplicationFilter:
    """Filter to suppress duplicate log messages from the same location.
    
    Tracks recent logs and suppresses duplicates based on:
    1. Same file path
    2. Same line number
    3. Within time threshold (default 1 second)
    
    This prevents log spam from loops or frequently-called functions.
    
    Example:
        2025-11-29 20:39:58.268 | DEBUG | app.foo:bar:24 - Registered AAPL
        2025-11-29 20:39:58.268 | DEBUG | app.foo:bar:24 - Registered MSFT  <- Suppressed
        2025-11-29 20:39:58.268 | DEBUG | app.foo:bar:24 - Registered TSLA  <- Suppressed
        ... (1.5 seconds later)
        2025-11-29 20:40:00.000 | DEBUG | app.foo:bar:24 - Registered NVDA  <- Allowed
    """
    
    def __init__(self, max_history: int = 5, time_threshold_seconds: float = 1.0):
        """Initialize deduplication filter.
        
        Args:
            max_history: Number of recent logs to track (default 5)
            time_threshold_seconds: Suppress duplicates within this time window (default 1.0s)
        """
        self.max_history = max_history
        self.time_threshold = time_threshold_seconds
        # Use deque for efficient O(1) append/pop operations
        # Each entry: {"file": str, "line": int, "timestamp": float}
        self.recent_logs = deque(maxlen=max_history)
        # Thread safety lock for accessing recent_logs
        self._lock = threading.Lock()
    
    def __call__(self, record: Dict[str, Any]) -> bool:
        """Filter function called for each log record.
        
        Args:
            record: Loguru log record dict with 'file', 'line', 'time' keys
            
        Returns:
            True to allow log, False to suppress
        """
        current_file = record["file"].path
        current_line = record["line"]
        current_time = time.time()
        
        # Thread-safe access to recent_logs
        with self._lock:
            # Check if this log matches any recent log
            for recent in self.recent_logs:
                # Match criteria: same file AND same line
                if recent["line"] == current_line and recent["file"] == current_file:
                    # Check time threshold
                    time_diff = current_time - recent["timestamp"]
                    if time_diff < self.time_threshold:
                        # Duplicate detected - suppress this log
                        return False
            
            # Not a duplicate - allow this log and track it
            self.recent_logs.append({
                "file": current_file,
                "line": current_line,
                "timestamp": current_time
            })
            return True


class LoggerManager:
    """Manages application logging with runtime level control"""
    
    def __init__(self):
        # Use nested LOGGER config
        self.current_level = settings.LOGGER.default_level
        self.log_file_path = Path(settings.LOGGER.file_path)
        self.log_rotation = settings.LOGGER.rotation
        self.log_retention = settings.LOGGER.retention
        
        # Initialize deduplication filter if enabled
        self.dedup_filter = None
        if settings.LOGGER.filter_enabled:
            self.dedup_filter = LogDeduplicationFilter(
                max_history=settings.LOGGER.filter_max_history,
                time_threshold_seconds=settings.LOGGER.filter_time_threshold_seconds
            )
        
        self.setup_logger()
    
    def setup_logger(self):
        """Configure logger with console and file handlers"""
        # Ensure log directory exists
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Remove default handler
        logger.remove()
        
        # Console handler with rich formatting and colors
        # Only show ERROR and above in the console to keep CLI output clean
        logger.add(
            sys.stdout,
            level="ERROR",
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                "<level>{message}</level>"
            ),
            colorize=True,
            backtrace=True,
            diagnose=True,
            filter=self.dedup_filter  # Apply deduplication filter
        )
        
        # File handler with rotation and retention
        logger.add(
            str(self.log_file_path),
            level="DEBUG",  # Always log DEBUG and above to file
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                "{level: <8} | "
                "{name}:{function}:{line} - "
                "{message}"
            ),
            rotation=self.log_rotation,
            retention=self.log_retention,
            compression="zip",
            backtrace=True,
            diagnose=True,
            enqueue=True,  # Thread-safe logging
            filter=self.dedup_filter  # Apply deduplication filter
        )
        
        logger.info(f"Logger initialized with level: {self.current_level}")
        if self.dedup_filter:
            logger.info(
                f"Log deduplication enabled: tracking last {self.dedup_filter.max_history} logs, "
                f"threshold {self.dedup_filter.time_threshold}s"
            )
    
    def set_level(self, level: str) -> str:
        """
        Change log level at runtime
        
        Args:
            level: New log level (TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL)
            
        Returns:
            The new log level
            
        Raises:
            ValueError: If level is invalid
        """
        valid_levels = ["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]
        level_upper = level.upper()
        
        if level_upper not in valid_levels:
            raise ValueError(f"Invalid level '{level}'. Choose from: {', '.join(valid_levels)}")
        
        old_level = self.current_level
        self.current_level = level_upper
        
        # Re-setup logger with new level
        logger.remove()
        self.setup_logger()
        
        logger.success(f"Log level changed from {old_level} to {level_upper}")
        return self.current_level
    
    def get_level(self) -> str:
        """Get current log level"""
        return self.current_level
    
    def get_available_levels(self) -> list[str]:
        """Get list of available log levels"""
        return ["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]


# Global logger manager instance
logger_manager = LoggerManager()

# Export logger for use throughout the application
__all__ = ["logger", "logger_manager"]
