"""
Core primitives and fundamental data structures.

This package contains:
- session_data.py: SessionData (unified data store)
- enums.py: SystemState, OperationMode
- exceptions.py: Custom exceptions
- data_structures/: Bar, Quote, Tick classes
"""

from app.core.enums import SystemState, OperationMode
from app.core.exceptions import (
    TradingSystemError,
    SystemNotRunningError,
    SystemAlreadyRunningError,
    ConfigurationError,
    TimeManagerError,
    DataManagerError,
    ExecutionManagerError,
    SessionDataError,
    RepositoryError,
    IntegrationError,
    ThreadError
)
from app.core.session_data import SessionData
from app.core.data_structures import Bar, Quote, Tick

__all__ = [
    # Enums
    'SystemState',
    'OperationMode',
    
    # Exceptions
    'TradingSystemError',
    'SystemNotRunningError',
    'SystemAlreadyRunningError',
    'ConfigurationError',
    'TimeManagerError',
    'DataManagerError',
    'ExecutionManagerError',
    'SessionDataError',
    'RepositoryError',
    'IntegrationError',
    'ThreadError',
    
    # Core data
    'SessionData',
    
    # Data structures
    'Bar',
    'Quote',
    'Tick',
]
