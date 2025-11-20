"""
AnalysisEngine Public API

AI-powered trading analysis and decision making.
All CLI and API routes must use this interface.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import BarData, TechnicalIndicators
from app.managers.data_manager.api import DataManager
from app.managers.execution_manager.api import ExecutionManager
from app.logger import logger


class AnalysisEngine:
    """
    🧠 AnalysisEngine - AI-powered trading analysis and decision making
    
    Provides:
    - Calculate evaluation metrics
    - Consult with LLMs (Claude, GPT-4, etc.)
    - Generate success probability
    - Make buy/sell/exit decisions
    - Optimize weights
    - Log all analysis with LLM interaction details
    
    Supports both Real and Backtest modes.
    """
    
    def __init__(
        self,
        data_manager: DataManager,
        execution_manager: ExecutionManager,
        mode: str = "real",
        llm_provider: str = "claude"
    ):
        """
        Initialize AnalysisEngine
        
        Args:
            data_manager: DataManager instance
            execution_manager: ExecutionManager instance
            mode: Operating mode - "real" or "backtest"
            llm_provider: LLM provider - "claude", "gpt4", etc.
        """
        self.data_manager = data_manager
        self.execution_manager = execution_manager
        self.mode = mode
        self.llm_provider_name = llm_provider
        self.llm = None  # Will be initialized on first use
        logger.info(f"AnalysisEngine initialized in {mode} mode with {llm_provider}")
    
    # ==================== ANALYSIS ====================
    
    async def analyze_bar(
        self,
        session: AsyncSession,
        symbol: str,
        bar: BarData,
        recent_bars: Optional[List[BarData]] = None
    ) -> Dict[str, Any]:
        """
        Analyze a single bar and generate trading signals.
        
        Args:
            session: Database session
            symbol: Stock symbol
            bar: Current bar data
            recent_bars: Recent historical bars for context
            
        Returns:
            Analysis result dictionary with indicators, probabilities, and decision
        """
        from app.managers.analysis_engine.technical_indicators import TechnicalIndicatorService
        
        # Calculate technical indicators
        indicators = await TechnicalIndicatorService.calculate_indicators(
            session,
            symbol,
            current_bar=bar,
            lookback_bars=recent_bars or []
        )
        
        # Get LLM analysis if configured
        llm_analysis = None
        if self.llm_provider_name:
            try:
                llm_analysis = await self._consult_llm(
                    bar=bar,
                    indicators=indicators,
                    recent_bars=recent_bars
                )
            except Exception as e:
                logger.error(f"LLM analysis failed: {e}")
        
        # Make decision
        decision = await self._make_decision(
            bar=bar,
            indicators=indicators,
            llm_analysis=llm_analysis
        )
        
        # Log analysis
        await self._log_analysis(
            session=session,
            symbol=symbol,
            bar=bar,
            indicators=indicators,
            llm_analysis=llm_analysis,
            decision=decision
        )
        
        return {
            "symbol": symbol,
            "timestamp": bar.timestamp.isoformat(),
            "indicators": indicators.__dict__ if indicators else {},
            "decision": decision,
            "llm_analysis": llm_analysis
        }
    
    async def _consult_llm(
        self,
        bar: BarData,
        indicators: TechnicalIndicators,
        recent_bars: Optional[List[BarData]] = None
    ) -> Dict[str, Any]:
        """
        Consult LLM for analysis.
        
        Args:
            bar: Current bar data
            indicators: Technical indicators
            recent_bars: Recent historical bars
            
        Returns:
            LLM analysis dictionary
        """
        # TODO: Load appropriate LLM integration based on provider
        if self.llm_provider_name == "claude":
            from app.managers.analysis_engine.integrations.claude_analyzer import ClaudeProbabilityAnalyzer
            
            analyzer = ClaudeProbabilityAnalyzer()
            result = await analyzer.analyze_probability(
                bar=bar,
                indicators=indicators,
                recent_bars=recent_bars
            )
            
            return {
                "provider": "claude",
                "buy_probability": result.buy_probability,
                "sell_probability": result.sell_probability,
                "confidence": result.confidence,
                "reasoning": result.reasoning,
                "patterns": result.detected_patterns,
                "key_indicators": result.key_indicators,
                "risk_factors": result.risk_factors,
                "tokens_used": result.tokens_used,
                "cost_usd": result.cost_usd,
                "latency_ms": 0  # TODO: Track latency
            }
        
        return None
    
    async def _make_decision(
        self,
        bar: BarData,
        indicators: TechnicalIndicators,
        llm_analysis: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make trading decision based on analysis.
        
        Args:
            bar: Current bar data
            indicators: Technical indicators
            llm_analysis: LLM analysis results
            
        Returns:
            Decision dictionary
        """
        # Simple decision logic for now
        # TODO: Implement sophisticated decision making with weights
        
        decision = "HOLD"
        confidence = 0.5
        rationale = "Neutral signals"
        
        if llm_analysis:
            buy_prob = llm_analysis.get("buy_probability", 0.5)
            sell_prob = llm_analysis.get("sell_probability", 0.5)
            
            if buy_prob > 0.65:
                decision = "BUY"
                confidence = buy_prob
                rationale = f"Strong buy signal (prob: {buy_prob:.2%})"
            elif sell_prob > 0.65:
                decision = "SELL"
                confidence = sell_prob
                rationale = f"Strong sell signal (prob: {sell_prob:.2%})"
        
        return {
            "action": decision,
            "confidence": confidence,
            "rationale": rationale,
            "price": bar.close,
            "quantity": 0  # TODO: Calculate position size
        }
    
    async def _log_analysis(
        self,
        session: AsyncSession,
        symbol: str,
        bar: BarData,
        indicators: TechnicalIndicators,
        llm_analysis: Optional[Dict[str, Any]],
        decision: Dict[str, Any]
    ):
        """
        Log analysis to database.
        
        Args:
            session: Database session
            symbol: Stock symbol
            bar: Bar data
            indicators: Technical indicators
            llm_analysis: LLM analysis results
            decision: Decision made
        """
        from app.models.analysis_log import AnalysisLog
        
        log = AnalysisLog(
            timestamp=datetime.utcnow(),
            symbol=symbol,
            mode=self.mode,
            bar_timestamp=bar.timestamp,
            bar_open=bar.open,
            bar_high=bar.high,
            bar_low=bar.low,
            bar_close=bar.close,
            bar_volume=bar.volume,
            decision=decision["action"],
            decision_price=decision["price"],
            decision_quantity=decision["quantity"],
            decision_rationale=decision["rationale"],
            indicators_json=indicators.__dict__ if indicators else {}
        )
        
        # Add LLM details if available
        if llm_analysis:
            log.llm_provider = llm_analysis.get("provider")
            log.llm_model = "claude-opus-4"  # TODO: Get from config
            log.llm_response = llm_analysis.get("reasoning")
            log.llm_latency_ms = llm_analysis.get("latency_ms")
            log.llm_cost_usd = llm_analysis.get("cost_usd")
            log.llm_total_tokens = llm_analysis.get("tokens_used")
            log.buy_probability = llm_analysis.get("buy_probability")
            log.sell_probability = llm_analysis.get("sell_probability")
            log.confidence = llm_analysis.get("confidence")
            log.detected_patterns = llm_analysis.get("patterns")
            log.key_indicators = llm_analysis.get("key_indicators")
            log.risk_factors = llm_analysis.get("risk_factors")
        
        session.add(log)
        await session.commit()
        
        logger.debug(f"Analysis logged for {symbol} @ {bar.timestamp}")
    
    # ==================== METRICS ====================
    
    async def evaluate_metrics(
        self,
        session: AsyncSession,
        symbol: str
    ) -> Dict[str, Any]:
        """
        Evaluate performance metrics for a symbol.
        
        Args:
            session: Database session
            symbol: Stock symbol
            
        Returns:
            Metrics dictionary
        """
        from app.models.analysis_log import AnalysisMetrics
        from sqlalchemy import select
        
        result = await session.execute(
            select(AnalysisMetrics).where(AnalysisMetrics.symbol == symbol)
        )
        metrics = result.scalar_one_or_none()
        
        if not metrics:
            return {
                "symbol": symbol,
                "total_analyses": 0,
                "win_rate": 0.0,
                "avg_success_score": 0.0
            }
        
        return {
            "symbol": metrics.symbol,
            "total_analyses": metrics.total_analyses,
            "total_decisions": metrics.total_decisions,
            "win_rate": metrics.win_rate or 0.0,
            "avg_success_score": metrics.avg_success_score or 0.0,
            "total_llm_cost": metrics.total_llm_cost,
            "avg_llm_latency_ms": metrics.avg_llm_latency_ms
        }
    
    # ==================== OPTIMIZATION ====================
    
    async def optimize_weights(
        self,
        session: AsyncSession,
        symbol: str,
        historical_data: List[BarData]
    ) -> Dict[str, Any]:
        """
        Optimize weights for trading indicators.
        
        Args:
            session: Database session
            symbol: Stock symbol
            historical_data: Historical bar data for optimization
            
        Returns:
            Optimized weight set dictionary
        """
        # TODO: Implement weight optimization
        logger.warning("Weight optimization not yet implemented")
        
        return {
            "symbol": symbol,
            "weights": {
                "rsi": 0.15,
                "macd": 0.20,
                "bollinger": 0.15,
                "volume": 0.10,
                "pattern": 0.25,
                "llm": 0.15
            },
            "success_rate": 0.0,
            "total_trades": 0
        }
    
    # ==================== PROBABILITY ====================
    
    async def calculate_probability(
        self,
        session: AsyncSession,
        symbol: str,
        direction: str,
        bar: Optional[BarData] = None
    ) -> float:
        """
        Calculate success probability for a trade direction.
        
        Args:
            session: Database session
            symbol: Stock symbol
            direction: "BUY" or "SELL"
            bar: Current bar (optional, will fetch latest if not provided)
            
        Returns:
            Probability (0.0 to 1.0)
        """
        if bar is None:
            bar = await self.data_manager.get_latest_bar(session, symbol)
            if not bar:
                return 0.5  # Neutral if no data
        
        # Get recent bars for context
        from datetime import timedelta
        end_time = bar.timestamp
        start_time = end_time - timedelta(minutes=50)
        
        recent_bars = await self.data_manager.get_bars(
            session, symbol, start_time, end_time
        )
        
        # Analyze
        analysis = await self.analyze_bar(session, symbol, bar, recent_bars)
        
        # Return appropriate probability
        if direction.upper() == "BUY":
            return analysis.get("llm_analysis", {}).get("buy_probability", 0.5)
        elif direction.upper() == "SELL":
            return analysis.get("llm_analysis", {}).get("sell_probability", 0.5)
        
        return 0.5
