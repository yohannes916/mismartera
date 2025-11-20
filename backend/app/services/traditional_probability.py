"""
Traditional Probability Model
Fast rule-based probability calculation using technical indicators
"""
from typing import Optional
from app.models.trading import (
    BarData,
    TechnicalIndicators,
    ProbabilityResult,
    TradeSignal
)
from app.config.trading_config import TradingConfig
from app.logger import logger


class TraditionalProbabilityModel:
    """
    Rule-based probability model using technical indicators
    Fast, deterministic, no API costs
    """
    
    def __init__(self, config: TradingConfig):
        self.config = config
        self.profit_target_pct = config.profit_target_pct
        self.stop_loss_pct = config.stop_loss_pct
        self.risk_limit_pct = config.risk_limit_pct
    
    def calculate_probability(
        self,
        bar: BarData,
        indicators: TechnicalIndicators
    ) -> ProbabilityResult:
        """
        Calculate buy/sell probabilities using traditional indicators
        
        Args:
            bar: Current bar data
            indicators: Calculated technical indicators
            
        Returns:
            ProbabilityResult with buy/sell probabilities and signal
        """
        # Calculate individual probabilities
        buy_prob = self._calculate_buy_probability(bar, indicators)
        sell_prob = self._calculate_sell_probability(bar, indicators)
        stop_loss_prob = self._calculate_stop_loss_probability(bar, indicators)
        
        # Calculate confidence and uncertainty
        confidence = self._calculate_confidence(buy_prob, sell_prob, indicators)
        uncertainty = 1.0 - confidence
        
        # Determine signal
        signal = self._determine_signal(
            buy_prob,
            sell_prob,
            stop_loss_prob,
            confidence
        )
        
        return ProbabilityResult(
            buy_probability=buy_prob,
            sell_probability=sell_prob,
            stop_loss_probability=stop_loss_prob,
            confidence=confidence,
            uncertainty=uncertainty,
            signal=signal,
            source="traditional",
            reasoning=self._generate_reasoning(bar, indicators, buy_prob, sell_prob)
        )
    
    def _calculate_buy_probability(
        self,
        bar: BarData,
        indicators: TechnicalIndicators
    ) -> float:
        """Calculate probability of successful buy trade"""
        score = 0.5  # Start neutral
        weight_sum = 0.0
        
        # RSI - Oversold is bullish
        if indicators.rsi is not None:
            weight = 0.15
            if indicators.rsi < 30:
                score += 0.3 * weight
            elif indicators.rsi < 40:
                score += 0.15 * weight
            elif indicators.rsi > 70:
                score -= 0.2 * weight
            weight_sum += weight
        
        # MACD - Positive histogram is bullish
        if indicators.macd_histogram is not None:
            weight = 0.12
            if indicators.macd_histogram > 0:
                score += 0.2 * weight
            else:
                score -= 0.1 * weight
            weight_sum += weight
        
        # Bollinger Bands - Price near lower band is bullish
        if indicators.bollinger_lower and indicators.bollinger_middle:
            weight = 0.10
            price_position = (bar.close - indicators.bollinger_lower) / \
                           (indicators.bollinger_middle - indicators.bollinger_lower)
            if price_position < 0.3:  # Near lower band
                score += 0.25 * weight
            elif price_position > 0.7:  # Near upper band
                score -= 0.15 * weight
            weight_sum += weight
        
        # Volume - High volume confirmation
        if indicators.volume_ratio:
            weight = 0.08
            if indicators.volume_ratio > 1.5:  # High volume
                score += 0.15 * weight
            weight_sum += weight
        
        # Support/Resistance - Near support is bullish
        if indicators.distance_to_support_pct is not None:
            weight = 0.10
            if indicators.distance_to_support_pct < 1.0:  # Within 1% of support
                score += 0.2 * weight
            weight_sum += weight
        
        # Trend - Strong uptrend is bullish
        if indicators.trend_strength is not None:
            weight = 0.10
            if indicators.trend_strength > 0.6:
                # Use bullish score to determine direction
                if indicators.bullish_score > 0.6:
                    score += 0.15 * weight
            weight_sum += weight
        
        # Price action - Higher close vs open
        if bar.close > bar.open:
            score += 0.05
        
        # Normalize and bound
        if weight_sum > 0:
            score = score / weight_sum
        
        return max(0.0, min(score, 1.0))
    
    def _calculate_sell_probability(
        self,
        bar: BarData,
        indicators: TechnicalIndicators
    ) -> float:
        """Calculate probability of successful sell trade"""
        score = 0.5  # Start neutral
        weight_sum = 0.0
        
        # RSI - Overbought is bearish
        if indicators.rsi is not None:
            weight = 0.15
            if indicators.rsi > 70:
                score += 0.3 * weight
            elif indicators.rsi > 60:
                score += 0.15 * weight
            elif indicators.rsi < 30:
                score -= 0.2 * weight
            weight_sum += weight
        
        # MACD - Negative histogram is bearish
        if indicators.macd_histogram is not None:
            weight = 0.12
            if indicators.macd_histogram < 0:
                score += 0.2 * weight
            else:
                score -= 0.1 * weight
            weight_sum += weight
        
        # Bollinger Bands - Price near upper band is bearish
        if indicators.bollinger_upper and indicators.bollinger_middle:
            weight = 0.10
            price_position = (bar.close - indicators.bollinger_middle) / \
                           (indicators.bollinger_upper - indicators.bollinger_middle)
            if price_position > 0.7:  # Near upper band
                score += 0.25 * weight
            elif price_position < 0.3:  # Near lower band
                score -= 0.15 * weight
            weight_sum += weight
        
        # Volume confirmation
        if indicators.volume_ratio:
            weight = 0.08
            if indicators.volume_ratio > 1.5:
                score += 0.15 * weight
            weight_sum += weight
        
        # Resistance - Near resistance is bearish
        if indicators.distance_to_resistance_pct is not None:
            weight = 0.10
            if indicators.distance_to_resistance_pct < 1.0:
                score += 0.2 * weight
            weight_sum += weight
        
        # Trend - Strong downtrend is bearish
        if indicators.trend_strength is not None:
            weight = 0.10
            if indicators.trend_strength > 0.6:
                if indicators.bearish_score > 0.6:
                    score += 0.15 * weight
            weight_sum += weight
        
        # Price action - Lower close vs open
        if bar.close < bar.open:
            score += 0.05
        
        # Normalize and bound
        if weight_sum > 0:
            score = score / weight_sum
        
        return max(0.0, min(score, 1.0))
    
    def _calculate_stop_loss_probability(
        self,
        bar: BarData,
        indicators: TechnicalIndicators
    ) -> float:
        """Estimate probability of hitting stop-loss"""
        # Base on volatility and trend strength
        base_prob = 0.3  # Default 30% chance
        
        # High volatility increases stop-loss probability
        if indicators.atr and bar.close > 0:
            atr_pct = (indicators.atr / bar.close) * 100
            if atr_pct > self.stop_loss_pct * 1.5:
                base_prob += 0.2
        
        # Weak trend increases stop-loss probability
        if indicators.trend_strength is not None:
            if indicators.trend_strength < 0.3:
                base_prob += 0.15
        
        # High pattern complexity increases risk
        if indicators.pattern_complexity > 0.7:
            base_prob += 0.1
        
        return min(base_prob, 0.95)
    
    def _calculate_confidence(
        self,
        buy_prob: float,
        sell_prob: float,
        indicators: TechnicalIndicators
    ) -> float:
        """Calculate confidence in the probability estimates"""
        # High confidence when probabilities are clear (not close)
        prob_separation = abs(buy_prob - sell_prob)
        confidence = prob_separation
        
        # Reduce confidence for complex patterns
        if indicators.pattern_complexity > 0.7:
            confidence *= 0.7
        
        # Reduce confidence for weak trends
        if indicators.trend_strength is not None and indicators.trend_strength < 0.3:
            confidence *= 0.8
        
        return max(0.0, min(confidence, 1.0))
    
    def _determine_signal(
        self,
        buy_prob: float,
        sell_prob: float,
        stop_loss_prob: float,
        confidence: float
    ) -> TradeSignal:
        """Determine trade signal from probabilities"""
        
        # Check risk limit - force exit
        if stop_loss_prob > (self.risk_limit_pct / 100.0):
            return TradeSignal.EXIT
        
        # Require minimum confidence for signals
        min_confidence = 0.6
        min_probability = 0.65
        
        if confidence < min_confidence:
            return TradeSignal.HOLD
        
        # Check buy signal
        if buy_prob > min_probability and buy_prob > sell_prob:
            return TradeSignal.BUY
        
        # Check sell signal
        if sell_prob > min_probability and sell_prob > buy_prob:
            return TradeSignal.SELL
        
        return TradeSignal.HOLD
    
    def _generate_reasoning(
        self,
        bar: BarData,
        indicators: TechnicalIndicators,
        buy_prob: float,
        sell_prob: float
    ) -> str:
        """Generate human-readable reasoning"""
        reasons = []
        
        # RSI
        if indicators.rsi:
            if indicators.rsi < 30:
                reasons.append(f"RSI oversold ({indicators.rsi:.1f})")
            elif indicators.rsi > 70:
                reasons.append(f"RSI overbought ({indicators.rsi:.1f})")
        
        # MACD
        if indicators.macd_histogram:
            if indicators.macd_histogram > 0:
                reasons.append("MACD bullish")
            else:
                reasons.append("MACD bearish")
        
        # Volume
        if indicators.volume_ratio and indicators.volume_ratio > 1.5:
            reasons.append(f"High volume ({indicators.volume_ratio:.1f}x)")
        
        # Trend
        if indicators.trend_strength and indicators.trend_strength > 0.6:
            direction = "bullish" if indicators.bullish_score > 0.5 else "bearish"
            reasons.append(f"Strong {direction} trend")
        
        if not reasons:
            reasons.append("Neutral indicators")
        
        return "; ".join(reasons)


# Global instance
traditional_model: Optional[TraditionalProbabilityModel] = None

def get_traditional_model(config: TradingConfig) -> TraditionalProbabilityModel:
    """Get or create traditional probability model"""
    global traditional_model
    if traditional_model is None or traditional_model.config != config:
        traditional_model = TraditionalProbabilityModel(config)
    return traditional_model
