"""Simple moving average crossover strategy.

This is an example strategy demonstrating the new strategy framework.
"""
from typing import List, Tuple
from collections import deque

from app.strategies.base import BaseStrategy, StrategyContext, Signal, SignalAction


class SimpleMaCrossStrategy(BaseStrategy):
    """Moving average crossover strategy.
    
    Generates BUY signal when fast MA crosses above slow MA.
    Generates SELL signal when fast MA crosses below slow MA.
    
    Config Parameters:
        symbols (List[str]): Symbols to trade
        interval (str): Bar interval (e.g., "5m")
        fast_period (int): Fast MA period (default: 10)
        slow_period (int): Slow MA period (default: 20)
        min_quality (float): Minimum data quality % (default: 95.0)
    
    Example Config:
        {
            "symbols": ["AAPL", "GOOGL"],
            "interval": "5m",
            "fast_period": 10,
            "slow_period": 20,
            "min_quality": 95.0
        }
    """
    
    def setup(self, context: StrategyContext) -> bool:
        """Initialize strategy parameters."""
        # Call parent setup
        if not super().setup(context):
            return False
        
        # Extract config parameters
        self.symbols = self.config.get('symbols', [])
        self.interval = self.config.get('interval', '5m')
        self.fast_period = self.config.get('fast_period', 10)
        self.slow_period = self.config.get('slow_period', 20)
        self.min_quality = self.config.get('min_quality', 95.0)
        
        # Validate parameters
        if not self.symbols:
            self._logger.error("No symbols configured")
            return False
        
        if self.fast_period >= self.slow_period:
            self._logger.error("fast_period must be < slow_period")
            return False
        
        if self.fast_period <= 0 or self.slow_period <= 0:
            self._logger.error("Periods must be positive")
            return False
        
        self._logger.info(
            f"Initialized with {len(self.symbols)} symbols, "
            f"interval={self.interval}, fast={self.fast_period}, slow={self.slow_period}"
        )
        
        # Initialize state tracking
        self._last_signal = {}  # Track last signal per symbol
        
        return True
    
    def get_subscriptions(self) -> List[Tuple[str, str]]:
        """Subscribe to configured symbols and interval.
        
        Note: This is called before setup(), so read from config directly.
        """
        symbols = self.config.get('symbols', [])
        interval = self.config.get('interval', '5m')
        return [(symbol, interval) for symbol in symbols]
    
    def on_bars(self, symbol: str, interval: str) -> List[Signal]:
        """Generate signals based on MA crossover."""
        # Get config (in case setup() hasn't been called yet)
        symbols = getattr(self, 'symbols', self.config.get('symbols', []))
        strategy_interval = getattr(self, 'interval', self.config.get('interval', '5m'))
        
        # Only process subscribed data
        if symbol not in symbols or interval != strategy_interval:
            return []
        
        # Get config values (with defaults if setup() not called)
        min_quality = getattr(self, 'min_quality', self.config.get('min_quality', 95.0))
        fast_period = getattr(self, 'fast_period', self.config.get('fast_period', 10))
        slow_period = getattr(self, 'slow_period', self.config.get('slow_period', 20))
        
        # Check data quality
        quality = self.context.get_bar_quality(symbol, interval)
        if quality < min_quality:
            self._logger.warning(
                f"Skipping {symbol} - quality {quality:.1f}% < {min_quality}%"
            )
            return []
        
        # Get bars (zero-copy reference)
        bars = self.context.get_bars(symbol, interval)
        
        # Need enough bars for slow MA
        if len(bars) < slow_period:
            return []
        
        # Calculate MAs
        fast_ma = self._calculate_ma(bars, fast_period)
        slow_ma = self._calculate_ma(bars, slow_period)
        
        if fast_ma is None or slow_ma is None:
            return []
        
        # Get previous MAs (for crossover detection)
        prev_fast_ma = self._calculate_ma(bars, fast_period, offset=1)
        prev_slow_ma = self._calculate_ma(bars, slow_period, offset=1)
        
        if prev_fast_ma is None or prev_slow_ma is None:
            return []
        
        # Detect crossover
        signals = []
        
        # Get or initialize last signal dict
        if not hasattr(self, '_last_signal'):
            self._last_signal = {}
        
        # Bullish crossover (fast crosses above slow)
        if prev_fast_ma <= prev_slow_ma and fast_ma > slow_ma:
            if self._last_signal.get(symbol) != 'BUY':
                signal = Signal(
                    symbol=symbol,
                    action=SignalAction.BUY,
                    reason=f"Fast MA ({fast_ma:.2f}) crossed above slow MA ({slow_ma:.2f})",
                    metadata={
                        'fast_ma': fast_ma,
                        'slow_ma': slow_ma,
                        'interval': interval
                    }
                )
                signals.append(signal)
                self.log_signal(signal)
                self._last_signal[symbol] = 'BUY'
        
        # Bearish crossover (fast crosses below slow)
        elif prev_fast_ma >= prev_slow_ma and fast_ma < slow_ma:
            if self._last_signal.get(symbol) != 'SELL':
                signal = Signal(
                    symbol=symbol,
                    action=SignalAction.SELL,
                    reason=f"Fast MA ({fast_ma:.2f}) crossed below slow MA ({slow_ma:.2f})",
                    metadata={
                        'fast_ma': fast_ma,
                        'slow_ma': slow_ma,
                        'interval': interval
                    }
                )
                signals.append(signal)
                self.log_signal(signal)
                self._last_signal[symbol] = 'SELL'
        
        return signals
    
    def _calculate_ma(self, bars: deque, period: int, offset: int = 0) -> float:
        """Calculate simple moving average.
        
        Args:
            bars: Bar data
            period: MA period
            offset: Offset from end (0=latest, 1=previous, etc.)
            
        Returns:
            MA value or None if insufficient data
        """
        if len(bars) < period + offset:
            return None
        
        # Get slice of bars
        end_idx = len(bars) - offset
        start_idx = end_idx - period
        
        if start_idx < 0:
            return None
        
        # Calculate average of close prices
        bars_list = list(bars)
        total = sum(bar.close for bar in bars_list[start_idx:end_idx])
        return total / period


# Required: Export strategy class
__all__ = ['SimpleMaCrossStrategy']
