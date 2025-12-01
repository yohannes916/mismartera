"""
Simple Moving Average Crossover Strategy

Classic trend-following strategy using two moving averages:
- Fast SMA (e.g., 5 periods)
- Slow SMA (e.g., 20 periods)

Buy Signal: Fast SMA crosses above Slow SMA
Sell Signal: Fast SMA crosses below Slow SMA
"""

from typing import List, Any
from datetime import datetime

# Logging
from app.logger import logger

from app.threads.analysis_engine import BaseStrategy, Signal, SignalAction


class SMAcrossoverStrategy(BaseStrategy):
    """Simple Moving Average Crossover Strategy.
    
    Configuration:
        fast_period: Fast SMA period (default: 5)
        slow_period: Slow SMA period (default: 20)
        quantity: Position size (default: 10)
        intervals: List of intervals to trade (default: ["5m"])
    """
    
    def __init__(self, name: str, session_data, config: dict):
        """Initialize SMA Crossover Strategy.
        
        Args:
            name: Strategy name
            session_data: SessionData reference
            config: Strategy configuration
        """
        super().__init__(name, session_data, config)
        
        # Configuration
        self.fast_period = config.get('fast_period', 5)
        self.slow_period = config.get('slow_period', 20)
        self.quantity = config.get('quantity', 10)
        self.intervals = config.get('intervals', ["5m"])
        
        # State tracking
        self._last_signal = {}  # {symbol: SignalAction}
        
        logger.info(
            f"SMAcrossoverStrategy initialized: "
            f"fast={self.fast_period}, slow={self.slow_period}, "
            f"quantity={self.quantity}, intervals={self.intervals}"
        )
    
    def on_bar(self, symbol: str, interval: str, bar: Any) -> List[Signal]:
        """Called when new bar arrives.
        
        Args:
            symbol: Symbol
            interval: Interval
            bar: Bar data
        
        Returns:
            List of signals
        """
        # Use on_bars instead
        return []
    
    def on_bars(self, symbol: str, interval: str) -> List[Signal]:
        """Generate signals based on SMA crossover.
        
        Args:
            symbol: Symbol
            interval: Interval
        
        Returns:
            List of signals (0 or 1)
        """
        # Only trade configured intervals
        if interval not in self.intervals:
            return []
        
        # Get bars from SessionData (zero-copy)
        bars = list(self.session_data.get_bars(symbol, interval))
        
        # Need enough bars for slow SMA
        if len(bars) < self.slow_period + 1:
            logger.debug(
                f"Not enough bars for {symbol} {interval}: "
                f"{len(bars)} < {self.slow_period + 1}"
            )
            return []
        
        # Calculate SMAs
        fast_sma_current = self._calculate_sma(bars, self.fast_period)
        fast_sma_previous = self._calculate_sma(bars[:-1], self.fast_period)
        
        slow_sma_current = self._calculate_sma(bars, self.slow_period)
        slow_sma_previous = self._calculate_sma(bars[:-1], self.slow_period)
        
        if fast_sma_current is None or slow_sma_current is None:
            return []
        
        if fast_sma_previous is None or slow_sma_previous is None:
            return []
        
        # Detect crossover
        signal_action = None
        
        # Fast crosses above slow = BUY
        if fast_sma_previous <= slow_sma_previous and fast_sma_current > slow_sma_current:
            signal_action = SignalAction.BUY
            logger.info(
                f"SMA Crossover BUY signal for {symbol} {interval}: "
                f"fast={fast_sma_current:.2f}, slow={slow_sma_current:.2f}"
            )
        
        # Fast crosses below slow = SELL
        elif fast_sma_previous >= slow_sma_previous and fast_sma_current < slow_sma_current:
            signal_action = SignalAction.SELL
            logger.info(
                f"SMA Crossover SELL signal for {symbol} {interval}: "
                f"fast={fast_sma_current:.2f}, slow={slow_sma_current:.2f}"
            )
        
        # No crossover
        if signal_action is None:
            return []
        
        # Avoid duplicate signals
        last_signal = self._last_signal.get(symbol)
        if last_signal == signal_action:
            logger.debug(f"Duplicate {signal_action.value} signal for {symbol}, skipping")
            return []
        
        # Update state
        self._last_signal[symbol] = signal_action
        
        # Get current price (last bar close)
        current_price = bars[-1].close
        
        # Calculate confidence based on separation
        separation = abs(fast_sma_current - slow_sma_current) / slow_sma_current
        confidence = min(0.5 + separation * 10, 1.0)  # Scale to 0.5-1.0
        
        # Create signal
        signal = Signal(
            symbol=symbol,
            action=signal_action,
            quantity=self.quantity,
            price=current_price,
            timestamp=bars[-1].timestamp,
            strategy_name=self.name,
            confidence=confidence,
            interval=interval,
            metadata={
                'fast_sma': fast_sma_current,
                'slow_sma': slow_sma_current,
                'separation': separation
            }
        )
        
        return [signal]
    
    def _calculate_sma(self, bars: List[Any], period: int) -> float:
        """Calculate Simple Moving Average.
        
        Args:
            bars: List of bars
            period: SMA period
        
        Returns:
            SMA value or None if not enough bars
        """
        if len(bars) < period:
            return None
        
        # Use last N bars
        recent_bars = bars[-period:]
        closes = [bar.close for bar in recent_bars]
        
        return sum(closes) / period
