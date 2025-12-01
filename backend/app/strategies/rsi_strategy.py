"""
RSI (Relative Strength Index) Strategy

Mean-reversion strategy using RSI indicator:
- RSI < 30: Oversold → BUY signal
- RSI > 70: Overbought → SELL signal
- 30 <= RSI <= 70: No signal (HOLD)
"""

from typing import List, Any
from datetime import datetime

# Logging
from app.logger import logger

from app.threads.analysis_engine import BaseStrategy, Signal, SignalAction


class RSIStrategy(BaseStrategy):
    """RSI Mean-Reversion Strategy.
    
    Configuration:
        period: RSI period (default: 14)
        oversold_threshold: Buy when RSI below this (default: 30)
        overbought_threshold: Sell when RSI above this (default: 70)
        quantity: Position size (default: 10)
        intervals: List of intervals to trade (default: ["5m"])
    """
    
    def __init__(self, name: str, session_data, config: dict):
        """Initialize RSI Strategy.
        
        Args:
            name: Strategy name
            session_data: SessionData reference
            config: Strategy configuration
        """
        super().__init__(name, session_data, config)
        
        # Configuration
        self.period = config.get('period', 14)
        self.oversold_threshold = config.get('oversold_threshold', 30.0)
        self.overbought_threshold = config.get('overbought_threshold', 70.0)
        self.quantity = config.get('quantity', 10)
        self.intervals = config.get('intervals', ["5m"])
        
        # State tracking
        self._last_signal = {}  # {symbol: SignalAction}
        
        logger.info(
            f"RSIStrategy initialized: period={self.period}, "
            f"oversold={self.oversold_threshold}, overbought={self.overbought_threshold}, "
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
        """Generate signals based on RSI.
        
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
        
        # Need enough bars for RSI (period + 1 for smoothing)
        min_bars = self.period + 10  # Extra bars for better RSI calculation
        if len(bars) < min_bars:
            logger.debug(
                f"Not enough bars for {symbol} {interval}: "
                f"{len(bars)} < {min_bars}"
            )
            return []
        
        # Calculate RSI
        rsi = self._calculate_rsi(bars, self.period)
        
        if rsi is None:
            logger.debug(f"Could not calculate RSI for {symbol} {interval}")
            return []
        
        # Determine signal action
        signal_action = None
        
        # Oversold → BUY
        if rsi < self.oversold_threshold:
            signal_action = SignalAction.BUY
            logger.info(
                f"RSI BUY signal for {symbol} {interval}: "
                f"RSI={rsi:.2f} < {self.oversold_threshold}"
            )
        
        # Overbought → SELL
        elif rsi > self.overbought_threshold:
            signal_action = SignalAction.SELL
            logger.info(
                f"RSI SELL signal for {symbol} {interval}: "
                f"RSI={rsi:.2f} > {self.overbought_threshold}"
            )
        
        # No signal
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
        
        # Calculate confidence based on RSI extreme
        if signal_action == SignalAction.BUY:
            # More oversold = higher confidence
            confidence = min(1.0, (self.oversold_threshold - rsi) / self.oversold_threshold + 0.5)
        else:  # SELL
            # More overbought = higher confidence
            confidence = min(1.0, (rsi - self.overbought_threshold) / (100 - self.overbought_threshold) + 0.5)
        
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
                'rsi': rsi,
                'oversold_threshold': self.oversold_threshold,
                'overbought_threshold': self.overbought_threshold
            }
        )
        
        return [signal]
    
    def _calculate_rsi(self, bars: List[Any], period: int) -> float:
        """Calculate Relative Strength Index.
        
        Args:
            bars: List of bars
            period: RSI period
        
        Returns:
            RSI value (0-100) or None if not enough data
        """
        if len(bars) < period + 1:
            return None
        
        # Calculate price changes
        closes = [bar.close for bar in bars]
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        
        # Separate gains and losses
        gains = [max(0, change) for change in changes]
        losses = [abs(min(0, change)) for change in changes]
        
        # Use only last period changes for initial average
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        # Calculate RS and RSI
        if avg_loss == 0:
            return 100.0  # No losses = maximum RSI
        
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        
        return rsi
