"""
Trading data models for probability engine
"""
from datetime import datetime
from typing import Dict, Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class TradeSignal(str, Enum):
    """Trade signal types"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    EXIT = "exit"


class BarData(BaseModel):
    """OHLCV bar with flexible interval support (1s, 1m, 5m, etc.)"""
    timestamp: datetime
    symbol: str
    interval: str = "1m"  # Bar interval: 1s, 1m, 5m, 15m, etc.
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class TickData(BaseModel):
    """Single tick quote or trade.

    Minimal model to support DataManager tick APIs; can be extended later.
    """

    timestamp: datetime
    symbol: str
    price: float = Field(gt=0)
    size: float = Field(ge=0)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class TechnicalIndicators(BaseModel):
    """Calculated technical indicators for a bar"""
    
    # Moving averages
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None
    
    # VWAP
    vwap: Optional[float] = None
    
    # Momentum
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    
    # Volatility
    atr: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_middle: Optional[float] = None
    bollinger_lower: Optional[float] = None
    bollinger_width: Optional[float] = None
    
    # Trend
    adx: Optional[float] = None
    
    # Volume
    volume_sma: Optional[float] = None
    volume_ratio: Optional[float] = None  # current/average
    
    # Support/Resistance
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None
    distance_to_support_pct: Optional[float] = None
    distance_to_resistance_pct: Optional[float] = None
    
    # Pattern detection
    pattern_complexity: float = Field(default=0.0, ge=0.0, le=1.0)
    trend_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    
    # Composite scores
    bullish_score: float = Field(default=0.5, ge=0.0, le=1.0)
    bearish_score: float = Field(default=0.5, ge=0.0, le=1.0)


class ProbabilityResult(BaseModel):
    """Probability calculation result"""
    
    # Core probabilities
    buy_probability: float = Field(ge=0.0, le=1.0)
    sell_probability: float = Field(ge=0.0, le=1.0)
    stop_loss_probability: float = Field(ge=0.0, le=1.0)
    
    # Confidence and uncertainty
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0, le=1.0)
    
    # Signal
    signal: TradeSignal
    
    # Metadata
    source: str = Field(description="traditional, claude, or hybrid")
    reasoning: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ClaudeAnalysis(BaseModel):
    """Claude AI analysis result"""
    
    buy_probability: float = Field(ge=0.0, le=1.0)
    sell_probability: float = Field(ge=0.0, le=1.0)
    stop_loss_risk: float = Field(ge=0.0, le=1.0)
    
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    
    # Pattern insights
    detected_patterns: List[str] = Field(default_factory=list)
    key_indicators: List[str] = Field(default_factory=list)
    risk_factors: List[str] = Field(default_factory=list)
    
    # Token usage
    tokens_used: int
    cost_usd: float
    
    timestamp: datetime = Field(default_factory=datetime.now)


class TradeDecision(BaseModel):
    """Final trading decision"""
    
    signal: TradeSignal
    
    # Probabilities
    buy_probability: float = Field(ge=0.0, le=1.0)
    sell_probability: float = Field(ge=0.0, le=1.0)
    
    # Confidence
    confidence: float = Field(ge=0.0, le=1.0)
    
    # Position sizing
    recommended_position_size: Optional[float] = None
    
    # Risk management
    stop_loss_price: Optional[float] = None
    profit_target_price: Optional[float] = None
    
    # Metadata
    used_claude: bool
    traditional_result: ProbabilityResult
    claude_result: Optional[ClaudeAnalysis] = None
    
    # Reasoning
    reasoning: str
    
    timestamp: datetime = Field(default_factory=datetime.now)


class BacktestTrade(BaseModel):
    """Single backtest trade record"""
    
    entry_time: datetime
    entry_price: float
    signal: TradeSignal  # BUY or SELL
    
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # "profit_target", "stop_loss", "risk_limit"
    
    # P&L
    profit_loss: Optional[float] = None
    profit_loss_pct: Optional[float] = None
    
    # Probabilities at entry
    entry_buy_probability: float
    entry_sell_probability: float
    
    # Was Claude used?
    used_claude: bool
    
    # Outcome
    hit_profit_target: Optional[bool] = None
    hit_stop_loss: Optional[bool] = None


class BacktestResults(BaseModel):
    """Complete backtest results"""
    
    # Configuration
    symbol: str
    start_date: datetime
    end_date: datetime
    
    profit_target_pct: float
    stop_loss_pct: float
    risk_limit_pct: float
    
    # Overall metrics
    total_trades: int
    winning_trades: int
    losing_trades: int
    
    win_rate: float = Field(ge=0.0, le=1.0)
    
    # Financial metrics
    total_profit_loss: float
    gross_profit: float
    gross_loss: float
    profit_factor: float  # gross_profit / abs(gross_loss)
    
    average_win: float
    average_loss: float
    
    largest_win: float
    largest_loss: float
    
    # Risk metrics
    max_drawdown: float
    max_drawdown_pct: float
    
    # Claude usage
    claude_calls: int
    claude_cost_usd: float
    
    # Trade breakdown
    buy_trades: int
    sell_trades: int
    
    # All trades
    trades: List[BacktestTrade]
    
    # Timestamp
    completed_at: datetime = Field(default_factory=datetime.now)
