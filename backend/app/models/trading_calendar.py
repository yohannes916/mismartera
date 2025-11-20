"""
Trading Calendar Models
Track market holidays and early closes
"""
from sqlalchemy import Column, Integer, String, Date, Time, Boolean
from sqlalchemy.sql import func
from app.models.database import Base
from datetime import datetime


class TradingHoliday(Base):
    """
    Market holidays and early close days
    """
    __tablename__ = "trading_holidays"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    holiday_name = Column(String(200), nullable=False)
    notes = Column(String(500))
    is_closed = Column(Boolean, default=True)  # True = market closed, False = early close
    early_close_time = Column(Time)  # e.g., 13:00 for 1pm early close
    created_at = Column(Date, server_default=func.current_date())
    
    def __repr__(self):
        if self.is_closed:
            return f"<TradingHoliday {self.date}: {self.holiday_name} (CLOSED)>"
        else:
            return f"<TradingHoliday {self.date}: {self.holiday_name} (Early close: {self.early_close_time})>"


class TradingHours:
    """
    Standard market hours (configurable)
    """
    MARKET_OPEN = "09:30:00"
    MARKET_CLOSE = "16:00:00"
    MINUTES_PER_DAY = 390  # 6.5 hours * 60 minutes
    
    @staticmethod
    def is_weekend(date: datetime) -> bool:
        """Check if date is weekend (Saturday=5, Sunday=6)"""
        return date.weekday() >= 5
