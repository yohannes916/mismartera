"""
Claude Probability Analyzer
Uses Claude Opus 4.1 for deep pattern analysis and probability estimation
"""
from typing import Optional, List
import json
from datetime import datetime

from app.models.trading import (
    BarData,
    TechnicalIndicators,
    ClaudeAnalysis
)
from app.integrations.claude_client import claude_client
from app.logger import logger


class ClaudeProbabilityAnalyzer:
    """
    Use Claude AI for sophisticated pattern analysis and probability estimation
    """
    
    def __init__(self):
        self.model = claude_client.model
    
    async def analyze_probability(
        self,
        bar: BarData,
        indicators: TechnicalIndicators,
        recent_bars: Optional[List[BarData]] = None,
        profit_target_pct: float = 1.0,
        stop_loss_pct: float = 0.5
    ) -> ClaudeAnalysis:
        """
        Use Claude to analyze probability of trade success
        
        Args:
            bar: Current bar data
            indicators: Calculated technical indicators
            recent_bars: Recent historical bars for context
            profit_target_pct: Profit target percentage
            stop_loss_pct: Stop-loss percentage
            
        Returns:
            ClaudeAnalysis with probabilities and reasoning
        """
        if not claude_client.client:
            raise ValueError("Claude API not configured")
        
        # Build analysis prompt
        prompt = self._build_probability_prompt(
            bar,
            indicators,
            recent_bars,
            profit_target_pct,
            stop_loss_pct
        )
        
        try:
            # Call Claude API
            response = await claude_client.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0.3,  # Lower temperature for more consistent probabilities
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parse response
            answer = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens
            cost_usd = self._calculate_cost(response.usage.input_tokens, response.usage.output_tokens)
            
            # Extract structured data
            analysis = self._parse_analysis_response(answer, tokens_used, cost_usd)
            
            logger.info(f"Claude analysis completed: {tokens_used} tokens, ${cost_usd:.4f}")
            
            return analysis
            
        except Exception as e:
            logger.error(f"Claude probability analysis error: {e}")
            raise
    
    def _build_probability_prompt(
        self,
        bar: BarData,
        indicators: TechnicalIndicators,
        recent_bars: Optional[List[BarData]],
        profit_target_pct: float,
        stop_loss_pct: float
    ) -> str:
        """Build detailed prompt for Claude analysis"""
        
        # Format recent price action
        price_context = ""
        if recent_bars and len(recent_bars) >= 10:
            recent_10 = recent_bars[-10:]
            price_context = "Recent 10 bars:\n"
            for i, b in enumerate(recent_10):
                direction = "▲" if b.close > b.open else "▼"
                price_context += f"{i+1}. {direction} O:{b.open:.2f} H:{b.high:.2f} L:{b.low:.2f} C:{b.close:.2f} V:{b.volume:.0f}\n"
        
        prompt = f"""You are an expert quantitative trader analyzing 1-minute bar data for {bar.symbol}.

**Current Bar ({bar.timestamp.strftime('%Y-%m-%d %H:%M')}):**
- Open: ${bar.open:.2f}
- High: ${bar.high:.2f}
- Low: ${bar.low:.2f}
- Close: ${bar.close:.2f}
- Volume: {bar.volume:,.0f}

{price_context}

**Technical Indicators:**
- RSI(14): {indicators.rsi:.1f if indicators.rsi else 'N/A'}
- MACD: {indicators.macd:.3f if indicators.macd else 'N/A'} (Signal: {indicators.macd_signal:.3f if indicators.macd_signal else 'N/A'}, Histogram: {indicators.macd_histogram:.3f if indicators.macd_histogram else 'N/A'})
- Bollinger Bands: Upper=${indicators.bollinger_upper:.2f if indicators.bollinger_upper else 'N/A'}, Middle=${indicators.bollinger_middle:.2f if indicators.bollinger_middle else 'N/A'}, Lower=${indicators.bollinger_lower:.2f if indicators.bollinger_lower else 'N/A'}
- ATR(14): {indicators.atr:.2f if indicators.atr else 'N/A'}
- ADX(14): {indicators.adx:.1f if indicators.adx else 'N/A'}
- Volume Ratio: {indicators.volume_ratio:.2f if indicators.volume_ratio else 'N/A'}x average
- Support: ${indicators.support_level:.2f if indicators.support_level else 'N/A'} ({indicators.distance_to_support_pct:.1f if indicators.distance_to_support_pct else 'N/A'}% away)
- Resistance: ${indicators.resistance_level:.2f if indicators.resistance_level else 'N/A'} ({indicators.distance_to_resistance_pct:.1f if indicators.distance_to_resistance_pct else 'N/A'}% away)

**Trading Parameters:**
- Profit Target: {profit_target_pct}%
- Stop Loss: {stop_loss_pct}%

**Task:**
Analyze this data and provide probability estimates for:
1. **BUY trade**: Probability that price will rise {profit_target_pct}% before falling {stop_loss_pct}%
2. **SELL trade**: Probability that price will fall {profit_target_pct}% before rising {stop_loss_pct}%
3. **Stop-loss risk**: Probability of hitting the stop-loss

**Required Response Format (JSON):**
```json
{{
  "buy_probability": 0.0-1.0,
  "sell_probability": 0.0-1.0,
  "stop_loss_risk": 0.0-1.0,
  "confidence": 0.0-1.0,
  "detected_patterns": ["pattern1", "pattern2"],
  "key_indicators": ["indicator1", "indicator2"],
  "risk_factors": ["risk1", "risk2"],
  "reasoning": "Brief explanation of the analysis and why these probabilities were assigned"
}}
```

Be precise with probabilities. Consider:
- Pattern recognition (flags, triangles, head & shoulders, etc.)
- Indicator convergence/divergence
- Volume confirmation
- Support/resistance proximity
- Trend strength and momentum
- Market microstructure

Provide your analysis:"""
        
        return prompt
    
    def _parse_analysis_response(
        self,
        response: str,
        tokens_used: int,
        cost_usd: float
    ) -> ClaudeAnalysis:
        """Parse Claude's JSON response into ClaudeAnalysis"""
        
        try:
            # Extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")
            
            json_str = response[json_start:json_end]
            data = json.loads(json_str)
            
            return ClaudeAnalysis(
                buy_probability=float(data.get('buy_probability', 0.5)),
                sell_probability=float(data.get('sell_probability', 0.5)),
                stop_loss_risk=float(data.get('stop_loss_risk', 0.3)),
                confidence=float(data.get('confidence', 0.5)),
                reasoning=data.get('reasoning', 'No reasoning provided'),
                detected_patterns=data.get('detected_patterns', []),
                key_indicators=data.get('key_indicators', []),
                risk_factors=data.get('risk_factors', []),
                tokens_used=tokens_used,
                cost_usd=cost_usd,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error parsing Claude response: {e}")
            logger.debug(f"Response was: {response}")
            
            # Return fallback analysis
            return ClaudeAnalysis(
                buy_probability=0.5,
                sell_probability=0.5,
                stop_loss_risk=0.3,
                confidence=0.3,
                reasoning=f"Failed to parse Claude response: {str(e)}",
                detected_patterns=[],
                key_indicators=[],
                risk_factors=["Parsing error"],
                tokens_used=tokens_used,
                cost_usd=cost_usd,
                timestamp=datetime.now()
            )
    
    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate API cost in USD"""
        # Claude Opus 4 pricing (as of 2024)
        input_cost = (input_tokens / 1_000_000) * 15.0
        output_cost = (output_tokens / 1_000_000) * 75.0
        return input_cost + output_cost


# Global instance
claude_analyzer = ClaudeProbabilityAnalyzer()
