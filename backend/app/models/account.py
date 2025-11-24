"""
Account Database Models
Tracks account balance, transactions, and P&L
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index, Text
from app.models.database import Base


class Account(Base):
    """
    Trading account information
    """
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Account identification
    account_id = Column(String(100), unique=True, nullable=False, index=True)
    account_name = Column(String(200), nullable=True)
    brokerage = Column(String(50), nullable=False)  # schwab, paper, etc.
    
    # Account status
    is_active = Column(Integer, default=1)  # SQLite doesn't have Boolean
    mode = Column(String(20), nullable=False, default="live")  # live, backtest
    
    # Current balances (updated periodically)
    cash_balance = Column(Float, default=0.0)
    buying_power = Column(Float, default=0.0)
    total_value = Column(Float, default=0.0)  # Cash + positions
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    def __repr__(self):
        return f"<Account {self.account_id} ({self.brokerage})>"


class AccountTransaction(Base):
    """
    Account transaction history
    Records all debits, credits, fees, etc.
    """
    __tablename__ = "account_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Account reference
    account_id = Column(String(100), ForeignKey("accounts.account_id"), nullable=False, index=True)
    
    # Transaction details
    transaction_type = Column(String(50), nullable=False)  # DEPOSIT, WITHDRAWAL, TRADE, FEE, DIVIDEND, INTEREST
    amount = Column(Float, nullable=False)  # Positive for credit, negative for debit
    description = Column(Text, nullable=True)
    
    # Related order (if applicable)
    order_id = Column(String(100), ForeignKey("orders.order_id"), nullable=True)
    
    # Balance after transaction
    balance_after = Column(Float, nullable=False)
    
    # Timestamp
    transaction_date = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Metadata
    reference_id = Column(String(100), nullable=True)  # External reference
    
    __table_args__ = (
        Index('idx_transactions_account_date', 'account_id', 'transaction_date'),
        Index('idx_transactions_type', 'transaction_type'),
    )
    
    def __repr__(self):
        return f"<Transaction {self.transaction_type} ${self.amount:.2f}>"


class Position(Base):
    """
    Current positions snapshot
    """
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Account reference
    account_id = Column(String(100), ForeignKey("accounts.account_id"), nullable=False, index=True)
    
    # Position details
    symbol = Column(String(20), nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    avg_entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    market_value = Column(Float, nullable=True)
    
    # P&L
    unrealized_pnl = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    
    # Timestamps
    opened_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_positions_account_symbol', 'account_id', 'symbol'),
    )
    
    def __repr__(self):
        return f"<Position {self.symbol} {self.quantity}@{self.avg_entry_price:.2f}>"
