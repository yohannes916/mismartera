"""
Analysis Log Database Models
Logs all analysis decisions and LLM interactions
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index, Text, JSON
from app.models.database import Base


class AnalysisLog(Base):
    """
    Comprehensive analysis and decision logging with LLM details
    """
    __tablename__ = "analysis_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Analysis identification
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    mode = Column(String(20), nullable=False, default="live")  # live, backtest
    
    # Bar data at time of analysis
    bar_timestamp = Column(DateTime, nullable=False, index=True)
    bar_open = Column(Float, nullable=False)
    bar_high = Column(Float, nullable=False)
    bar_low = Column(Float, nullable=False)
    bar_close = Column(Float, nullable=False)
    bar_volume = Column(Float, nullable=False)
    
    # Decision made
    decision = Column(String(10), nullable=True)  # BUY, SELL, EXIT, HOLD
    decision_price = Column(Float, nullable=True)
    decision_quantity = Column(Float, nullable=True)
    decision_rationale = Column(Text, nullable=True)
    
    # Success Score (updated later after outcome is known)
    success_score = Column(Float, nullable=True)  # 0.0-1.0
    success_updated_at = Column(DateTime, nullable=True)
    actual_outcome = Column(String(50), nullable=True)  # WIN, LOSS, BREAK_EVEN
    actual_pnl = Column(Float, nullable=True)
    
    # LLM Interaction Details
    llm_provider = Column(String(50), nullable=True)  # 'claude', 'gpt4', 'gemini', etc.
    llm_model = Column(String(100), nullable=True)    # 'claude-opus-4', 'gpt-4-turbo', etc.
    llm_prompt = Column(Text, nullable=True)          # Full prompt sent
    llm_response = Column(Text, nullable=True)        # Full response received
    llm_latency_ms = Column(Integer, nullable=True)   # Response time in milliseconds
    llm_cost_usd = Column(Float, nullable=True)       # Cost of this call in USD
    llm_input_tokens = Column(Integer, nullable=True)
    llm_output_tokens = Column(Integer, nullable=True)
    llm_total_tokens = Column(Integer, nullable=True)
    
    # Probabilities from LLM
    buy_probability = Column(Float, nullable=True)
    sell_probability = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    
    # Technical indicators used (stored as JSON)
    indicators_json = Column(JSON, nullable=True)
    # Example: {
    #   "rsi": 65.5,
    #   "macd": 0.123,
    #   "bollinger_upper": 180.5,
    #   "volume_ratio": 1.8,
    #   ...
    # }
    
    # Pattern detection
    detected_patterns = Column(JSON, nullable=True)  # List of pattern names
    key_indicators = Column(JSON, nullable=True)     # List of key indicator names
    risk_factors = Column(JSON, nullable=True)       # List of risk factors
    
    # Weight set used
    weight_set_id = Column(Integer, ForeignKey("weight_sets.id"), nullable=True)
    
    # Related order (if placed)
    order_id = Column(String(100), ForeignKey("orders.order_id"), nullable=True)
    
    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    account_id = Column(String(100), ForeignKey("accounts.account_id"), nullable=True)
    
    __table_args__ = (
        Index('idx_analysis_symbol_time', 'symbol', 'bar_timestamp'),
        Index('idx_analysis_decision', 'decision'),
        Index('idx_analysis_mode', 'mode'),
        Index('idx_analysis_llm_provider', 'llm_provider'),
    )
    
    def __repr__(self):
        return f"<AnalysisLog {self.symbol} {self.decision} @ {self.bar_timestamp}>"


class AnalysisMetrics(Base):
    """
    Aggregated analysis metrics per symbol
    """
    __tablename__ = "analysis_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Metrics identification
    symbol = Column(String(20), nullable=False, unique=True, index=True)
    
    # Performance metrics
    total_analyses = Column(Integer, default=0)
    total_decisions = Column(Integer, default=0)
    buy_decisions = Column(Integer, default=0)
    sell_decisions = Column(Integer, default=0)
    hold_decisions = Column(Integer, default=0)
    
    # Success rates
    avg_success_score = Column(Float, nullable=True)
    win_rate = Column(Float, nullable=True)
    
    # LLM usage
    total_llm_calls = Column(Integer, default=0)
    total_llm_cost = Column(Float, default=0.0)
    avg_llm_latency_ms = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Metrics {self.symbol} WR:{self.win_rate:.1%}>"
