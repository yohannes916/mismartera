"""
Custom exceptions for the trading system.

All custom exceptions should be defined here for easy discovery
and consistent error handling throughout the application.
"""


class TradingSystemError(Exception):
    """Base exception for all trading system errors."""
    pass


class SystemNotRunningError(TradingSystemError):
    """Raised when an operation requires the system to be running."""
    pass


class SystemAlreadyRunningError(TradingSystemError):
    """Raised when trying to start a system that's already running."""
    pass


class ConfigurationError(TradingSystemError):
    """Raised when there's an error in configuration."""
    pass


class TimeManagerError(TradingSystemError):
    """Raised when there's an error in time management operations."""
    pass


class DataManagerError(TradingSystemError):
    """Raised when there's an error in data management operations."""
    pass


class ExecutionManagerError(TradingSystemError):
    """Raised when there's an error in execution operations."""
    pass


class SessionDataError(TradingSystemError):
    """Raised when there's an error with session data operations."""
    pass


class RepositoryError(TradingSystemError):
    """Raised when there's an error in database repository operations."""
    pass


class IntegrationError(TradingSystemError):
    """Raised when there's an error with external integrations."""
    pass


class ThreadError(TradingSystemError):
    """Raised when there's an error with thread operations."""
    pass
