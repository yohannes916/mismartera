"""
📈 ExecutionManager Module

Handles all order execution and account management.

Responsibilities:
- Order placement (buy/sell, limit/market)
- Order management (cancel, modify)
- Open orders information
- Order history
- Account balance and trading power
- Profit & Loss reporting

Supports both Real and Backtest modes.
"""

from app.managers.execution_manager.api import ExecutionManager

__all__ = ['ExecutionManager']
