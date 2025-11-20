"""
Weight Database Models
Stores optimized weights and their performance
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index, JSON
from app.models.database import Base


class WeightSet(Base):
    """
    A set of weights for trading analysis
    """
    __tablename__ = "weight_sets"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Weight identification
    name = Column(String(200), nullable=True)
    symbol = Column(String(20), nullable=False, index=True)
    
    # Weight values (stored as JSON for flexibility)
    weights = Column(JSON, nullable=False)
    # Example: {
    #   "rsi": 0.15,
    #   "macd": 0.20,
    #   "bollinger": 0.15,
    #   "volume": 0.10,
    #   "pattern": 0.25,
    #   "llm": 0.15
    # }
    
    # Performance metrics
    success_rate = Column(Float, nullable=True)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    avg_profit = Column(Float, nullable=True)
    avg_loss = Column(Float, nullable=True)
    sharpe_ratio = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    
    # Status
    is_active = Column(Integer, default=1)  # SQLite doesn't have Boolean
    
    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    __table_args__ = (
        Index('idx_weights_symbol_success', 'symbol', 'success_rate'),
    )
    
    def __repr__(self):
        return f"<WeightSet {self.id} {self.symbol} SR:{self.success_rate}>"


class WeightPerformance(Base):
    """
    Historical performance records for weight sets
    """
    __tablename__ = "weight_performance"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Reference to weight set
    weight_set_id = Column(Integer, ForeignKey("weight_sets.id"), nullable=False, index=True)
    
    # Performance details
    test_date = Column(DateTime, nullable=False, index=True)
    trades_count = Column(Integer, nullable=False)
    success_rate = Column(Float, nullable=False)
    total_pnl = Column(Float, nullable=False)
    max_drawdown = Column(Float, nullable=True)
    
    # Test parameters
    test_start_date = Column(DateTime, nullable=False)
    test_end_date = Column(DateTime, nullable=False)
    test_mode = Column(String(20), nullable=False)  # backtest, paper, live
    
    def __repr__(self):
        return f"<Performance WS:{self.weight_set_id} SR:{self.success_rate:.2%}>"
