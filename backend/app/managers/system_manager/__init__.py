"""
SystemManager - Central orchestrator and service locator

This package provides the SystemManager class which:
- Creates and manages all managers (TimeManager, DataManager, etc.)
- Creates and wires the 4-thread pool
- Provides singleton access via get_system_manager()
- Tracks system state (STOPPED, RUNNING)

Usage:
    from app.managers.system_manager import get_system_manager
    
    system_mgr = get_system_manager()
    system_mgr.start("session_configs/example_session.json")
    time_mgr = system_mgr.get_time_manager()
"""

from app.managers.system_manager.api import (
    SystemManager,
    get_system_manager,
    reset_system_manager
)
from app.core.enums import SystemState, OperationMode

__all__ = [
    'SystemManager',
    'get_system_manager',
    'reset_system_manager',
    'SystemState',
    'OperationMode',
]
