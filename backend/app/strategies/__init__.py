"""
Trading Strategies Module

This module contains example trading strategies that can be loaded
by the Analysis Engine.
"""

from app.strategies.sma_crossover import SMAcrossoverStrategy
from app.strategies.rsi_strategy import RSIStrategy

__all__ = [
    'SMAcrossoverStrategy',
    'RSIStrategy',
]
