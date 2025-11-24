"""
Order Database Models
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.models.database import Base


class Order(Base):
    """
    Order tracking table
    Records all orders (live and backtest)
    """
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Order identification
    order_id = Column(String(100), unique=True, nullable=False, index=True)
    broker_order_id = Column(String(100), nullable=True)  # Broker's order ID
    account_id = Column(String(100), nullable=False, index=True)
    
    # Order details
    symbol = Column(String(20), nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    side = Column(String(10), nullable=False)  # BUY, SELL
    order_type = Column(String(20), nullable=False)  # MARKET, LIMIT, STOP, STOP_LIMIT
    price = Column(Float, nullable=True)  # Limit price
    stop_price = Column(Float, nullable=True)  # Stop price
    time_in_force = Column(String(10), nullable=False, default="DAY")  # DAY, GTC, IOC, FOK
    
    # Execution details
    status = Column(String(20), nullable=False, index=True)  # PENDING, WORKING, FILLED, PARTIAL_FILLED, CANCELLED, REJECTED
    filled_quantity = Column(Float, default=0.0)
    remaining_quantity = Column(Float, nullable=True)
    avg_fill_price = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    submitted_at = Column(DateTime, nullable=True)  # When submitted to broker
    filled_at = Column(DateTime, nullable=True)  # When fully filled
    cancelled_at = Column(DateTime, nullable=True)
    
    # Metadata
    mode = Column(String(20), nullable=False, default="live")  # live, backtest
    brokerage = Column(String(50), nullable=True)  # schwab, paper, etc.
    error_message = Column(String(500), nullable=True)
    
    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_orders_account_status', 'account_id', 'status'),
        Index('idx_orders_symbol_date', 'symbol', 'created_at'),
        Index('idx_orders_mode', 'mode'),
    )
    
    def __repr__(self):
        return f"<Order {self.order_id} {self.side} {self.quantity} {self.symbol} @ {self.status}>"


class OrderExecution(Base):
    """
    Individual execution/fill records for an order
    An order may have multiple partial fills
    """
    __tablename__ = "order_executions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Reference to parent order
    order_id = Column(String(100), ForeignKey("orders.order_id"), nullable=False, index=True)
    
    # Execution details
    execution_id = Column(String(100), unique=True, nullable=False)  # Broker's execution ID
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    commission = Column(Float, default=0.0)
    fees = Column(Float, default=0.0)
    
    # Timestamp
    executed_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Metadata
    venue = Column(String(50), nullable=True)  # Exchange/venue
    
    def __repr__(self):
        return f"<Execution {self.execution_id} {self.quantity}@{self.price}>"
