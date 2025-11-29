"""
SQLAlchemy database models
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.models.database import Base
import datetime

# Note: User model moved to app/models/user.py


class AccountInfo(Base):
    """User account information from Schwab"""
    __tablename__ = "account_info"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    schwab_account_id = Column(String(100), unique=True, index=True)
    account_type = Column(String(50))  # CASH, MARGIN, etc.
    cash_balance = Column(Float, default=0.0)
    buying_power = Column(Float, default=0.0)
    total_value = Column(Float, default=0.0)
    equity = Column(Float, default=0.0)
    last_synced = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="account_info")


class MarketData(Base):
    """OHLCV market data for backtesting and analysis"""
    __tablename__ = "market_data"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(10), index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    interval = Column(String(10), default='1m', nullable=False)  # 1m, 5m, 15m, 1h, 1d
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        # Composite unique constraint for symbol + timestamp + interval
        # Prevents duplicate bars
        Index('ix_market_data_symbol_timestamp_interval', 'symbol', 'timestamp', 'interval', unique=True),
        {"sqlite_autoincrement": True},
    )


class QuoteData(Base):
    """Bid/ask quote ticks for backtesting and analysis."""

    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(10), index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    bid_price = Column(Float, nullable=True)
    bid_size = Column(Float, nullable=True)
    ask_price = Column(Float, nullable=True)
    ask_size = Column(Float, nullable=True)
    exchange = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_quotes_symbol_timestamp", "symbol", "timestamp", unique=True),
        {"sqlite_autoincrement": True},
    )


class Analysis(Base):
    """AI analysis results from Claude"""
    __tablename__ = "analysis"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    symbol = Column(String(10), index=True, nullable=False)
    analysis_type = Column(String(50))  # TECHNICAL, FUNDAMENTAL, SENTIMENT, STRATEGY
    prompt = Column(Text)
    response = Column(Text)
    confidence_score = Column(Float)
    recommendation = Column(String(20))  # BUY, SELL, HOLD
    extra_data = Column(Text)  # JSON string for additional data (renamed from metadata to avoid SQLAlchemy conflict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User")
