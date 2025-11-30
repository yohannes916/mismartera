"""
Fundamental data structures for the trading system.

These are the core primitives used throughout the application:
- Bar: OHLCV candlestick data
- Quote: Bid/ask quotes
- Tick: Individual trade ticks

Note: Currently imports from app.models for compatibility.
      Will be refactored to live here directly in future.
"""

# Import from models for now (for compatibility)
try:
    from app.models.trading import Bar, Quote, Tick
except ImportError:
    # Placeholders if models don't exist yet
    Bar = None
    Quote = None
    Tick = None

__all__ = ['Bar', 'Quote', 'Tick']
