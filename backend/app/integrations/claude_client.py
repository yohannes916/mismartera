"""
Anthropic Claude API Client Integration
"""
from typing import Optional, Dict, Any, List
from anthropic import Anthropic, AsyncAnthropic
from app.config import settings
from app.logger import logger


class ClaudeClient:
    """
    Client for interacting with Anthropic Claude API
    
    Uses Claude Opus 4.1 for advanced trading analysis
    """
    
    def __init__(self):
        self.api_key = settings.CLAUDE.api_key
        self.model = settings.CLAUDE.model
        
        if not self.api_key:
            logger.warning("Anthropic API key not configured")
            self.client = None
        else:
            self.client = AsyncAnthropic(api_key=self.api_key)
            logger.info(f"Claude client initialized with model: {self.model}")
    
    async def analyze_stock(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        analysis_type: str = "technical"
    ) -> Dict[str, Any]:
        """
        Analyze a stock using Claude AI
        
        Args:
            symbol: Stock symbol
            market_data: Price data, indicators, etc.
            analysis_type: technical, fundamental, sentiment, or comprehensive
            
        Returns:
            Analysis results with recommendation
        """
        if not self.client:
            raise ValueError("Claude API not configured. Set ANTHROPIC_API_KEY in .env")
        
        logger.info(f"Analyzing {symbol} with Claude ({analysis_type})")
        
        # Construct prompt based on analysis type
        prompt = self._build_analysis_prompt(symbol, market_data, analysis_type)
        
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=0.2,  # Lower for more consistent analysis
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            analysis_text = response.content[0].text
            
            logger.success(f"Claude analysis completed for {symbol}")
            
            return {
                "symbol": symbol,
                "analysis_type": analysis_type,
                "analysis": analysis_text,
                "model": self.model,
                "tokens_used": response.usage.input_tokens + response.usage.output_tokens
            }
            
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            raise
    
    def _build_analysis_prompt(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        analysis_type: str
    ) -> str:
        """
        Build analysis prompt based on type
        
        Args:
            symbol: Stock symbol
            market_data: Market data and indicators
            analysis_type: Type of analysis
            
        Returns:
            Formatted prompt
        """
        base_prompt = f"""You are an expert day trader and technical analyst. 
Analyze {symbol} and provide actionable trading insights.

Market Data:
{self._format_market_data(market_data)}

"""
        
        if analysis_type == "technical":
            prompt = base_prompt + """
Provide a technical analysis including:
1. Price action and trends
2. Key support and resistance levels
3. Technical indicators analysis
4. Volume analysis
5. Chart patterns
6. Trading recommendation (BUY/SELL/HOLD) with confidence level
7. Entry and exit points
8. Risk assessment and stop-loss recommendations

Be specific with price levels and timeframes.
"""
        
        elif analysis_type == "fundamental":
            prompt = base_prompt + """
Provide a fundamental analysis including:
1. Company overview and business model
2. Financial health assessment
3. Earnings and revenue trends
4. Competitive position
5. Industry trends
6. Valuation analysis
7. Investment recommendation with rationale
8. Risk factors

Focus on day trading relevance.
"""
        
        elif analysis_type == "sentiment":
            prompt = base_prompt + """
Provide a market sentiment analysis including:
1. Overall market sentiment
2. News and social media sentiment
3. Institutional vs retail sentiment
4. Fear & greed indicators
5. Market momentum
6. Short-term sentiment forecast
7. Trading implications

Focus on intraday trading opportunities.
"""
        
        else:  # comprehensive
            prompt = base_prompt + """
Provide a comprehensive analysis including:
1. Technical analysis (trends, patterns, indicators)
2. Fundamental factors affecting intraday movement
3. Market sentiment and momentum
4. Risk/reward assessment
5. Multiple timeframe analysis
6. Clear trading recommendation with entry/exit points
7. Risk management strategy

Prioritize actionable day trading insights.
"""
        
        return prompt
    
    def _format_market_data(self, market_data: Dict[str, Any]) -> str:
        """
        Format market data for prompt
        
        Args:
            market_data: Dictionary of market data
            
        Returns:
            Formatted string
        """
        formatted = []
        for key, value in market_data.items():
            if isinstance(value, (int, float)):
                formatted.append(f"{key}: {value:.2f}")
            else:
                formatted.append(f"{key}: {value}")
        
        return "\n".join(formatted)
    
    async def scan_multiple_stocks(
        self,
        symbols: List[str],
        market_data_dict: Dict[str, Dict[str, Any]],
        strategy: str = "momentum"
    ) -> List[Dict[str, Any]]:
        """
        Scan multiple stocks for trading opportunities
        
        Args:
            symbols: List of stock symbols
            market_data_dict: Dictionary of symbol -> market data
            strategy: Scanning strategy (momentum, breakout, reversal)
            
        Returns:
            List of ranked trading opportunities
        """
        if not self.client:
            raise ValueError("Claude API not configured")
        
        logger.info(f"Scanning {len(symbols)} stocks with {strategy} strategy")
        
        prompt = f"""You are an expert day trader. Scan these stocks and identify the best trading opportunities for a {strategy} strategy.

Stocks to scan:
"""
        for symbol in symbols:
            data = market_data_dict.get(symbol, {})
            prompt += f"\n{symbol}:\n{self._format_market_data(data)}\n"
        
        prompt += f"""
Using the {strategy} strategy, rank these stocks by trading potential.
For each stock provide:
1. Ranking (1-{len(symbols)})
2. Trading setup and rationale
3. Entry and exit points
4. Risk/reward ratio
5. Confidence level (1-10)

Format your response as a clear ranked list.
"""
        
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            scan_results = response.content[0].text
            
            logger.success(f"Market scan completed for {len(symbols)} symbols")
            
            return {
                "strategy": strategy,
                "symbols_scanned": symbols,
                "results": scan_results,
                "tokens_used": response.usage.input_tokens + response.usage.output_tokens
            }
            
        except Exception as e:
            logger.error(f"Market scan error: {e}")
            raise
    
    async def validate_strategy(
        self,
        strategy_description: str,
        backtest_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Validate and improve a trading strategy using Claude
        
        Args:
            strategy_description: Description of the trading strategy
            backtest_data: Optional backtest results
            
        Returns:
            Strategy analysis and recommendations
        """
        if not self.client:
            raise ValueError("Claude API not configured")
        
        logger.info("Validating trading strategy with Claude")
        
        prompt = f"""You are an expert trading strategist. Analyze this trading strategy:

Strategy Description:
{strategy_description}
"""
        
        if backtest_data:
            prompt += f"\n\nBacktest Results:\n{self._format_market_data(backtest_data)}\n"
        
        prompt += """
Provide:
1. Strategy strengths and weaknesses
2. Market conditions where it works best
3. Risk factors and mitigation strategies
4. Suggested improvements
5. Recommended position sizing
6. Expected win rate and risk/reward
7. Overall viability rating (1-10)

Be specific and actionable.
"""
        
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=3072,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            validation = response.content[0].text
            
            logger.success("Strategy validation completed")
            
            return {
                "validation": validation,
                "tokens_used": response.usage.input_tokens + response.usage.output_tokens
            }
            
        except Exception as e:
            logger.error(f"Strategy validation error: {e}")
            raise


# Global client instance
claude_client = ClaudeClient()
