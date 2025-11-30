"""
Hybrid Probability Engine
Combines traditional and Claude-based analysis with configurable usage
"""
from typing import List, Optional
from datetime import datetime

from app.models.trading import (
    BarData,
    TechnicalIndicators,
    ProbabilityResult,
    ClaudeAnalysis,
    TradeDecision,
    TradeSignal
)
from app.config.trading_config import TradingConfig
from app.services.indicators.technical_indicators import indicator_calculator
from app.services.analysis.traditional_probability import get_traditional_model
from app.services.analysis.claude_probability import claude_analyzer
from app.logger import logger


class HybridProbabilityEngine:
    """
    Main engine that combines traditional and Claude analysis
    with configurable usage based on TradingConfig
    """
    
    def __init__(self, config: TradingConfig):
        self.config = config
        self.traditional_model = get_traditional_model(config)
        self.daily_claude_cost = 0.0
        self.cost_reset_date = datetime.now().date()
    
    async def analyze_bar(
        self,
        bar: BarData,
        historical_bars: List[BarData],
        current_index: int,
        position_size: Optional[float] = None
    ) -> TradeDecision:
        """
        Analyze a single bar and produce trading decision
        
        Args:
            bar: Current bar to analyze
            historical_bars: All historical bars up to current
            current_index: Index of current bar in historical_bars
            position_size: Optional position size for high-stakes detection
            
        Returns:
            TradeDecision with signal, probabilities, and reasoning
        """
        # Reset daily cost counter if new day
        self._check_reset_daily_cost()
        
        # Calculate technical indicators
        indicators = indicator_calculator.calculate_all(historical_bars, current_index)
        
        # Get traditional probability
        traditional_result = self.traditional_model.calculate_probability(bar, indicators)
        
        # Decide if Claude should be used
        should_use_claude = self._should_use_claude(
            traditional_result,
            indicators,
            position_size
        )
        
        claude_result = None
        
        if should_use_claude:
            # Use Claude for deep analysis
            try:
                recent_bars = historical_bars[max(0, current_index-20):current_index+1]
                
                claude_result = await claude_analyzer.analyze_probability(
                    bar=bar,
                    indicators=indicators,
                    recent_bars=recent_bars,
                    profit_target_pct=self.config.profit_target_pct,
                    stop_loss_pct=self.config.stop_loss_pct
                )
                
                # Track cost
                self.daily_claude_cost += claude_result.cost_usd
                
                logger.info(
                    f"Claude analysis used - Cost: ${claude_result.cost_usd:.4f}, "
                    f"Daily total: ${self.daily_claude_cost:.2f}"
                )
                
            except Exception as e:
                logger.error(f"Claude analysis failed, falling back to traditional: {e}")
                should_use_claude = False
        
        # Combine results
        if should_use_claude and claude_result:
            final_decision = self._combine_results(
                traditional_result,
                claude_result,
                bar,
                indicators
            )
        else:
            final_decision = self._traditional_only_decision(
                traditional_result,
                bar,
                indicators
            )
        
        return final_decision
    
    def _should_use_claude(
        self,
        traditional_result: ProbabilityResult,
        indicators: TechnicalIndicators,
        position_size: Optional[float]
    ) -> bool:
        """Determine if Claude should be used for this bar"""
        
        return self.config.claude.should_use_claude(
            traditional_confidence=traditional_result.confidence,
            uncertainty=traditional_result.uncertainty,
            pattern_complexity=indicators.pattern_complexity,
            position_size=position_size,
            current_daily_cost=self.daily_claude_cost
        )
    
    def _combine_results(
        self,
        traditional: ProbabilityResult,
        claude: ClaudeAnalysis,
        bar: BarData,
        indicators: TechnicalIndicators
    ) -> TradeDecision:
        """Combine traditional and Claude results using configured weight"""
        
        # Weighted average of probabilities
        claude_weight = self.config.claude.claude_weight
        trad_weight = 1.0 - claude_weight
        
        final_buy_prob = (
            trad_weight * traditional.buy_probability +
            claude_weight * claude.buy_probability
        )
        
        final_sell_prob = (
            trad_weight * traditional.sell_probability +
            claude_weight * claude.sell_probability
        )
        
        # Use Claude's stop-loss risk if confidence is high
        if claude.confidence > 0.7:
            stop_loss_prob = claude.stop_loss_risk
        else:
            stop_loss_prob = traditional.stop_loss_probability
        
        # Determine signal
        signal = self._determine_final_signal(
            final_buy_prob,
            final_sell_prob,
            stop_loss_prob
        )
        
        # Calculate confidence (higher of the two, since Claude is expensive)
        confidence = max(traditional.confidence, claude.confidence)
        
        # Position sizing based on confidence
        position_size = self._calculate_position_size(confidence)
        
        # Calculate stop-loss and profit target prices
        stop_loss_price, profit_target_price = self._calculate_prices(
            bar.close,
            signal
        )
        
        # Combined reasoning
        reasoning = self._generate_hybrid_reasoning(
            traditional,
            claude,
            final_buy_prob,
            final_sell_prob
        )
        
        return TradeDecision(
            signal=signal,
            buy_probability=final_buy_prob,
            sell_probability=final_sell_prob,
            confidence=confidence,
            recommended_position_size=position_size,
            stop_loss_price=stop_loss_price,
            profit_target_price=profit_target_price,
            used_claude=True,
            traditional_result=traditional,
            claude_result=claude,
            reasoning=reasoning,
            timestamp=datetime.now()
        )
    
    def _traditional_only_decision(
        self,
        traditional: ProbabilityResult,
        bar: BarData,
        indicators: TechnicalIndicators
    ) -> TradeDecision:
        """Create decision using only traditional analysis"""
        
        signal = traditional.signal
        position_size = self._calculate_position_size(traditional.confidence)
        stop_loss_price, profit_target_price = self._calculate_prices(bar.close, signal)
        
        return TradeDecision(
            signal=signal,
            buy_probability=traditional.buy_probability,
            sell_probability=traditional.sell_probability,
            confidence=traditional.confidence,
            recommended_position_size=position_size,
            stop_loss_price=stop_loss_price,
            profit_target_price=profit_target_price,
            used_claude=False,
            traditional_result=traditional,
            claude_result=None,
            reasoning=traditional.reasoning,
            timestamp=datetime.now()
        )
    
    def _determine_final_signal(
        self,
        buy_prob: float,
        sell_prob: float,
        stop_loss_prob: float
    ) -> TradeSignal:
        """Determine final trade signal"""
        
        # Check risk limit
        risk_limit = self.config.risk_limit_pct / 100.0
        if stop_loss_prob > risk_limit:
            return TradeSignal.EXIT
        
        # Minimum probability threshold
        min_prob = 0.65
        
        if buy_prob > min_prob and buy_prob > sell_prob:
            return TradeSignal.BUY
        
        if sell_prob > min_prob and sell_prob > buy_prob:
            return TradeSignal.SELL
        
        return TradeSignal.HOLD
    
    def _calculate_position_size(self, confidence: float) -> float:
        """Calculate recommended position size based on confidence"""
        max_size = self.config.max_position_size
        
        # Scale position size by confidence
        # Confidence 0.5 = 30% of max
        # Confidence 1.0 = 100% of max
        if confidence < 0.5:
            return max_size * 0.3
        
        return max_size * (0.3 + (confidence - 0.5) * 1.4)
    
    def _calculate_prices(
        self,
        current_price: float,
        signal: TradeSignal
    ) -> tuple[Optional[float], Optional[float]]:
        """Calculate stop-loss and profit target prices"""
        
        if signal == TradeSignal.HOLD or signal == TradeSignal.EXIT:
            return None, None
        
        if signal == TradeSignal.BUY:
            stop_loss = current_price * (1 - self.config.stop_loss_pct / 100)
            profit_target = current_price * (1 + self.config.profit_target_pct / 100)
        else:  # SELL
            stop_loss = current_price * (1 + self.config.stop_loss_pct / 100)
            profit_target = current_price * (1 - self.config.profit_target_pct / 100)
        
        return stop_loss, profit_target
    
    def _generate_hybrid_reasoning(
        self,
        traditional: ProbabilityResult,
        claude: ClaudeAnalysis,
        final_buy_prob: float,
        final_sell_prob: float
    ) -> str:
        """Generate combined reasoning"""
        
        reasoning_parts = []
        
        # Traditional insights
        reasoning_parts.append(f"Traditional: {traditional.reasoning}")
        
        # Claude insights
        if claude.detected_patterns:
            patterns = ", ".join(claude.detected_patterns)
            reasoning_parts.append(f"Patterns: {patterns}")
        
        if claude.key_indicators:
            indicators = ", ".join(claude.key_indicators[:3])  # Top 3
            reasoning_parts.append(f"Key: {indicators}")
        
        # Claude reasoning
        reasoning_parts.append(f"Claude: {claude.reasoning[:100]}...")
        
        # Risk factors
        if claude.risk_factors:
            risks = ", ".join(claude.risk_factors[:2])
            reasoning_parts.append(f"Risks: {risks}")
        
        return " | ".join(reasoning_parts)
    
    def _check_reset_daily_cost(self):
        """Reset daily cost counter if new day"""
        today = datetime.now().date()
        if today != self.cost_reset_date:
            logger.info(
                f"Daily Claude cost reset - Previous day: ${self.daily_claude_cost:.2f}"
            )
            self.daily_claude_cost = 0.0
            self.cost_reset_date = today
    
    def get_daily_cost(self) -> float:
        """Get current daily Claude API cost"""
        return self.daily_claude_cost
