"""
📊 DataManager Module

Single source of truth for all datasets.
Provides data to all other modules.

Responsibilities:
- Current date/time (real or backtest mode)
- Trading hours and status
- 1-minute bar data stream
- Tick data stream
- Holiday and early closing information
- Data import from various sources

Supports both Real and Backtest modes.
"""

from app.managers.data_manager.api import DataManager

__all__ = ['DataManager']
