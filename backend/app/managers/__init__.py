"""
Top-Level Module APIs

This package contains the core management modules:
- SystemManager: Central coordinator for all managers (singleton registry)
- DataManager: Single source of truth for all data
- ExecutionManager: All order execution and account management

Architecture:
    SystemManager creates and coordinates all other managers, passing itself
    as a reference so managers can access each other. All managers are singletons
    that live for the application lifetime.
    
    AnalysisEngine is a thread (app/threads/analysis_engine.py) managed by
    SystemManager, not a manager module.

All CLI and API interactions should use SystemManager to access other managers.
"""

from app.managers.system_manager.api import (
    SystemManager,
    get_system_manager,
    reset_system_manager
)
from app.core.enums import SystemState, OperationMode
from app.managers.data_manager.api import DataManager
from app.managers.execution_manager.api import ExecutionManager

__all__ = [
    'SystemManager',
    'get_system_manager',
    'reset_system_manager',
    'SystemState',
    'OperationMode',
    'DataManager',
    'ExecutionManager',
]
