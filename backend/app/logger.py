"""
Loguru logger configuration with runtime level control
"""
from loguru import logger
import sys
from pathlib import Path
from app.config import settings


class LoggerManager:
    """Manages application logging with runtime level control"""
    
    def __init__(self):
        self.current_level = settings.LOG_LEVEL
        self.log_file_path = Path(settings.LOG_FILE_PATH)
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
            diagnose=True
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
            rotation=settings.LOG_ROTATION,
            retention=settings.LOG_RETENTION,
            compression="zip",
            backtrace=True,
            diagnose=True,
            enqueue=True  # Thread-safe logging
        )
        
        logger.info(f"Logger initialized with level: {self.current_level}")
    
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
