"""
Top-Level Module APIs

This package contains the three core top-level modules:
- DataManager: Single source of truth for all data
- ExecutionManager: All order execution and account management
- AnalysisEngine: AI-powered trading analysis and decision making

All CLI and API interactions must go through these module APIs only.
"""

from app.managers.data_manager.api import DataManager
from app.managers.execution_manager.api import ExecutionManager
from app.managers.analysis_engine.api import AnalysisEngine

__all__ = [
    'DataManager',
    'ExecutionManager',
    'AnalysisEngine',
]
