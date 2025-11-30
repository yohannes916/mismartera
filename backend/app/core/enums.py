"""
Core enumerations used throughout the system.

These fundamental enums are used by multiple components and should be
imported from here (single source of truth).
"""

from enum import Enum


class SystemState(Enum):
    """
    System state enumeration.
    
    Values:
        STOPPED: System is not running
        RUNNING: System is actively running
        PAUSED: System is paused (future use)
    """
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"  # Future use


class OperationMode(Enum):
    """
    Operation mode enumeration.
    
    Values:
        LIVE: Live trading mode (real-time data)
        BACKTEST: Backtest mode (simulated time)
    """
    LIVE = "live"
    BACKTEST = "backtest"
