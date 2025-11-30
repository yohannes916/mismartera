"""
Technical Indicators Calculator
Calculates all technical indicators for probability analysis
"""
import pandas as pd
import numpy as np
from typing import List, Optional
from app.models.trading import BarData, TechnicalIndicators
from app.logger import logger


class TechnicalIndicatorCalculator:
    """
    Calculate technical indicators from OHLCV data
    """
    
    def __init__(self):
        self.min_periods = 50  # Minimum bars needed for reliable calculations
    
    def calculate_all(
        self,
        bars: List[BarData],
        current_index: int
    ) -> TechnicalIndicators:
        """
        Calculate all indicators for a specific bar
        
        Args:
            bars: List of historical bars
            current_index: Index of the bar to calculate indicators for
            
        Returns:
            TechnicalIndicators with all calculated values
        """
        if current_index < self.min_periods:
            logger.warning(f"Insufficient data for reliable indicators: {current_index}/{self.min_periods}")
        
        # Convert to DataFrame
        df = self._bars_to_dataframe(bars[:current_index + 1])
        
        # Calculate indicators
        indicators = TechnicalIndicators()
        
        # Moving averages
        indicators.sma_20 = self._calculate_sma(df['close'], 20)
        indicators.sma_50 = self._calculate_sma(df['close'], 50)
        indicators.ema_12 = self._calculate_ema(df['close'], 12)
        indicators.ema_26 = self._calculate_ema(df['close'], 26)
        
        # VWAP
        indicators.vwap = self._calculate_vwap(df)
        
        # RSI
        indicators.rsi = self._calculate_rsi(df['close'], 14)
        
        # MACD
        macd_result = self._calculate_macd(df['close'])
        if macd_result:
            indicators.macd = macd_result['macd']
            indicators.macd_signal = macd_result['signal']
            indicators.macd_histogram = macd_result['histogram']
        
        # Bollinger Bands
        bb_result = self._calculate_bollinger_bands(df['close'], 20, 2)
        if bb_result:
            indicators.bollinger_upper = bb_result['upper']
            indicators.bollinger_middle = bb_result['middle']
            indicators.bollinger_lower = bb_result['lower']
            indicators.bollinger_width = bb_result['width']
        
        # ATR
        indicators.atr = self._calculate_atr(df, 14)
        
        # ADX
        indicators.adx = self._calculate_adx(df, 14)
        
        # Volume analysis
        indicators.volume_sma = self._calculate_sma(df['volume'], 20)
        if indicators.volume_sma:
            current_volume = df['volume'].iloc[-1]
            indicators.volume_ratio = current_volume / indicators.volume_sma
        
        # Support/Resistance
        sr_result = self._calculate_support_resistance(df, 20)
        if sr_result:
            indicators.support_level = sr_result['support']
            indicators.resistance_level = sr_result['resistance']
            current_price = df['close'].iloc[-1]
            if indicators.support_level:
                indicators.distance_to_support_pct = (
                    (current_price - indicators.support_level) / current_price * 100
                )
            if indicators.resistance_level:
                indicators.distance_to_resistance_pct = (
                    (indicators.resistance_level - current_price) / current_price * 100
                )
        
        # Pattern complexity (0-1 score)
        indicators.pattern_complexity = self._calculate_pattern_complexity(df, indicators)
        
        # Trend strength (0-1 score)
        indicators.trend_strength = self._calculate_trend_strength(indicators)
        
        # Composite scores
        indicators.bullish_score = self._calculate_bullish_score(indicators)
        indicators.bearish_score = self._calculate_bearish_score(indicators)
        
        return indicators
    
    def _bars_to_dataframe(self, bars: List[BarData]) -> pd.DataFrame:
        """Convert list of BarData to pandas DataFrame"""
        data = {
            'timestamp': [b.timestamp for b in bars],
            'open': [b.open for b in bars],
            'high': [b.high for b in bars],
            'low': [b.low for b in bars],
            'close': [b.close for b in bars],
            'volume': [b.volume for b in bars]
        }
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        return df
    
    def _calculate_sma(self, series: pd.Series, period: int) -> Optional[float]:
        """Simple Moving Average"""
        if len(series) < period:
            return None
        return float(series.rolling(window=period).mean().iloc[-1])
    
    def _calculate_ema(self, series: pd.Series, period: int) -> Optional[float]:
        """Exponential Moving Average"""
        if len(series) < period:
            return None
        return float(series.ewm(span=period, adjust=False).mean().iloc[-1])
    
    def _calculate_vwap(self, df: pd.DataFrame) -> Optional[float]:
        """Volume Weighted Average Price"""
        if len(df) < 1:
            return None
        
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        vwap = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
        return float(vwap.iloc[-1])
    
    def _calculate_rsi(self, series: pd.Series, period: int = 14) -> Optional[float]:
        """Relative Strength Index"""
        if len(series) < period + 1:
            return None
        
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi.iloc[-1])
    
    def _calculate_macd(self, series: pd.Series) -> Optional[dict]:
        """MACD (Moving Average Convergence Divergence)"""
        if len(series) < 26:
            return None
        
        ema_12 = series.ewm(span=12, adjust=False).mean()
        ema_26 = series.ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal
        
        return {
            'macd': float(macd.iloc[-1]),
            'signal': float(signal.iloc[-1]),
            'histogram': float(histogram.iloc[-1])
        }
    
    def _calculate_bollinger_bands(
        self,
        series: pd.Series,
        period: int = 20,
        std_dev: float = 2
    ) -> Optional[dict]:
        """Bollinger Bands"""
        if len(series) < period:
            return None
        
        middle = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        width = (upper - lower) / middle
        
        return {
            'upper': float(upper.iloc[-1]),
            'middle': float(middle.iloc[-1]),
            'lower': float(lower.iloc[-1]),
            'width': float(width.iloc[-1])
        }
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Average True Range"""
        if len(df) < period + 1:
            return None
        
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()
        
        return float(atr.iloc[-1])
    
    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Average Directional Index (simplified)"""
        if len(df) < period + 1:
            return None
        
        # Simplified ADX calculation
        high_diff = df['high'].diff()
        low_diff = -df['low'].diff()
        
        pos_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
        neg_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)
        
        atr = self._calculate_atr(df, period)
        if not atr:
            return None
        
        pos_di = 100 * pos_dm.rolling(window=period).mean() / atr
        neg_di = 100 * neg_dm.rolling(window=period).mean() / atr
        
        dx = 100 * np.abs(pos_di - neg_di) / (pos_di + neg_di)
        adx = dx.rolling(window=period).mean()
        
        return float(adx.iloc[-1])
    
    def _calculate_support_resistance(
        self,
        df: pd.DataFrame,
        lookback: int = 20
    ) -> Optional[dict]:
        """Calculate support and resistance levels"""
        if len(df) < lookback:
            return None
        
        recent_df = df.tail(lookback)
        
        support = recent_df['low'].min()
        resistance = recent_df['high'].max()
        
        return {
            'support': float(support),
            'resistance': float(resistance)
        }
    
    def _calculate_pattern_complexity(
        self,
        df: pd.DataFrame,
        indicators: TechnicalIndicators
    ) -> float:
        """
        Calculate pattern complexity score (0-1)
        Higher = more complex/uncertain pattern
        """
        complexity_score = 0.0
        factors = 0
        
        # Check for conflicting signals
        if indicators.rsi and indicators.macd:
            # RSI overbought but MACD bullish (conflict)
            if (indicators.rsi > 70 and indicators.macd_histogram and indicators.macd_histogram > 0):
                complexity_score += 0.3
                factors += 1
            # RSI oversold but MACD bearish (conflict)
            elif (indicators.rsi < 30 and indicators.macd_histogram and indicators.macd_histogram < 0):
                complexity_score += 0.3
                factors += 1
        
        # Check volatility
        if indicators.atr and indicators.bollinger_width:
            if indicators.bollinger_width > 0.1:  # High volatility
                complexity_score += 0.2
                factors += 1
        
        # Check proximity to support/resistance
        if indicators.distance_to_support_pct and indicators.distance_to_resistance_pct:
            if abs(indicators.distance_to_support_pct) < 1 or abs(indicators.distance_to_resistance_pct) < 1:
                complexity_score += 0.2
                factors += 1
        
        # Average the factors
        if factors > 0:
            return min(complexity_score / factors, 1.0)
        
        return 0.5  # Default moderate complexity
    
    def _calculate_trend_strength(self, indicators: TechnicalIndicators) -> float:
        """Calculate trend strength (0-1)"""
        if not indicators.adx:
            return 0.5
        
        # ADX > 25 = strong trend
        # ADX < 20 = weak trend
        return min(indicators.adx / 50.0, 1.0)
    
    def _calculate_bullish_score(self, indicators: TechnicalIndicators) -> float:
        """Calculate bullish composite score (0-1)"""
        score = 0.5  # Start neutral
        factors = 0
        
        # RSI
        if indicators.rsi:
            if indicators.rsi < 30:
                score += 0.2  # Oversold = bullish
            elif indicators.rsi > 70:
                score -= 0.2  # Overbought = bearish
            factors += 1
        
        # MACD
        if indicators.macd_histogram:
            if indicators.macd_histogram > 0:
                score += 0.15
            else:
                score -= 0.15
            factors += 1
        
        # Price vs Bollinger
        if indicators.bollinger_lower and indicators.bollinger_middle:
            # Placeholder for current price comparison
            pass
        
        return max(0.0, min(score, 1.0))
    
    def _calculate_bearish_score(self, indicators: TechnicalIndicators) -> float:
        """Calculate bearish composite score (0-1)"""
        return 1.0 - self._calculate_bullish_score(indicators)


# Global instance
indicator_calculator = TechnicalIndicatorCalculator()
