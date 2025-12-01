"""
Trading Calendar Models
Track market holidays, early closes, and market hours
"""
from sqlalchemy import Column, Integer, String, Date, Time, Boolean, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.models.database import Base
from datetime import datetime, date, time as time_obj
from typing import Optional, List
from zoneinfo import ZoneInfo


class TradingHoliday(Base):
    """
    Market holidays and early close days at exchange group level.
    
    Holidays apply to entire exchange groups (US_EQUITY, LSE, etc.), not individual exchanges.
    This avoids duplication since NYSE and NASDAQ have identical holiday schedules.
    
    Examples:
        US_EQUITY: Applies to NYSE, NASDAQ, AMEX, ARCA
        LSE: Applies to London Stock Exchange
        TSE: Applies to Tokyo Stock Exchange
    """
    __tablename__ = "trading_holidays"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    exchange_group = Column(String(50), nullable=False, default="US_EQUITY", index=True)
    holiday_name = Column(String(200), nullable=False)
    notes = Column(String(500))
    is_closed = Column(Boolean, default=True)  # True = market closed, False = early close
    early_close_time = Column(Time)  # e.g., 13:00 for 1pm early close
    created_at = Column(Date, server_default=func.current_date())
    
    # Unique constraint: one holiday per date per exchange group
    __table_args__ = (
        UniqueConstraint('date', 'exchange_group', name='uix_date_exchange_group'),
        {"sqlite_autoincrement": True},
    )
    
    def __repr__(self):
        if self.is_closed:
            return f"<TradingHoliday {self.exchange_group} {self.date}: {self.holiday_name} (CLOSED)>"
        else:
            return f"<TradingHoliday {self.exchange_group} {self.date}: {self.holiday_name} (Early close: {self.early_close_time})>"


class MarketHours(Base):
    """
    Market hours configuration per exchange group and asset class.
    
    Exchange group can be:
      - A single exchange: "LSE", "TSE", "HKEX"
      - A group of exchanges: "US_EQUITY" (NYSE + NASDAQ + AMEX + ARCA)
    
    CRITICAL TIMEZONE HANDLING:
      - The 'timezone' column specifies the timezone for ALL time fields in this row
      - regular_open, regular_close, pre_market_open, etc. are Time objects WITHOUT timezone
      - When reading these times, they MUST be combined with the 'timezone' column
      - Example: regular_open = 09:30:00, timezone = "America/New_York"
                 → Means 9:30am Eastern Time
      - When system_manager.timezone is different, conversion must happen using this timezone
    
    NEVER interpret Time columns without checking the timezone column!
    """
    __tablename__ = "market_hours"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Primary identifiers
    exchange_group = Column(String(50), nullable=False, index=True)
    asset_class = Column(String(50), nullable=False, index=True)
    
    # Individual exchanges in this group (comma-separated)
    exchanges = Column(String(200))
    
    # TIMEZONE - CRITICAL: This applies to ALL time fields in this row
    timezone = Column(String(100), nullable=False)
    
    country = Column(String(50))
    exchange_name = Column(String(200))
    
    # Regular hours (Time objects - interpret using 'timezone' column!)
    regular_open = Column(Time, nullable=False)
    regular_close = Column(Time, nullable=False)
    
    # Extended hours (optional)
    pre_market_open = Column(Time)
    pre_market_close = Column(Time)
    post_market_open = Column(Time)
    post_market_close = Column(Time)
    
    # Trading days (comma-separated weekday numbers: 0=Mon, 6=Sun)
    trading_days = Column(String(50), nullable=False, default="0,1,2,3,4")
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Unique constraint: one config per exchange_group + asset_class
    __table_args__ = (
        UniqueConstraint('exchange_group', 'asset_class', name='uix_exchange_group_asset'),
        {"sqlite_autoincrement": True},
    )
    
    def get_trading_days_list(self) -> List[int]:
        """Parse trading_days string to list of integers"""
        if not self.trading_days:
            return [0, 1, 2, 3, 4]
        return [int(d.strip()) for d in self.trading_days.split(',')]
    
    def get_exchanges_list(self) -> List[str]:
        """Parse exchanges string to list"""
        if not self.exchanges:
            return []
        return [e.strip() for e in self.exchanges.split(',')]
    
    def is_trading_day_of_week(self, weekday: int) -> bool:
        """Check if a weekday is a trading day"""
        return weekday in self.get_trading_days_list()
    
    def includes_exchange(self, exchange: str) -> bool:
        """Check if this group includes a specific exchange"""
        return exchange.upper() in [e.upper() for e in self.get_exchanges_list()]
    
    def get_regular_open_datetime(
        self,
        trade_date: date,
        target_timezone: Optional[str] = None
    ) -> datetime:
        """
        Convert regular_open Time to timezone-aware datetime.
        
        CRITICAL: This method ensures timezone is always considered!
        
        Args:
            trade_date: The date to combine with the time
            target_timezone: Target timezone (uses market timezone if None)
        
        Returns:
            Timezone-aware datetime in target timezone
        """
        # Step 1: Combine Time with date in MARKET timezone (from database)
        market_tz = ZoneInfo(self.timezone)
        local_dt = datetime.combine(trade_date, self.regular_open)
        local_aware = local_dt.replace(tzinfo=market_tz)
        
        # Step 2: Convert to target timezone if different
        if target_timezone is None or target_timezone == self.timezone:
            return local_aware
        else:
            target_tz = ZoneInfo(target_timezone)
            return local_aware.astimezone(target_tz)
    
    def get_regular_close_datetime(
        self,
        trade_date: date,
        target_timezone: Optional[str] = None
    ) -> datetime:
        """Convert regular_close Time to timezone-aware datetime"""
        market_tz = ZoneInfo(self.timezone)
        local_dt = datetime.combine(trade_date, self.regular_close)
        local_aware = local_dt.replace(tzinfo=market_tz)
        
        if target_timezone is None or target_timezone == self.timezone:
            return local_aware
        else:
            target_tz = ZoneInfo(target_timezone)
            return local_aware.astimezone(target_tz)
    
    def get_pre_market_open_datetime(
        self,
        trade_date: date,
        target_timezone: Optional[str] = None
    ) -> Optional[datetime]:
        """Convert pre_market_open Time to timezone-aware datetime"""
        if self.pre_market_open is None:
            return None
        
        market_tz = ZoneInfo(self.timezone)
        local_dt = datetime.combine(trade_date, self.pre_market_open)
        local_aware = local_dt.replace(tzinfo=market_tz)
        
        if target_timezone is None or target_timezone == self.timezone:
            return local_aware
        else:
            target_tz = ZoneInfo(target_timezone)
            return local_aware.astimezone(target_tz)
    
    def get_post_market_close_datetime(
        self,
        trade_date: date,
        target_timezone: Optional[str] = None
    ) -> Optional[datetime]:
        """Convert post_market_close Time to timezone-aware datetime"""
        if self.post_market_close is None:
            return None
        
        market_tz = ZoneInfo(self.timezone)
        local_dt = datetime.combine(trade_date, self.post_market_close)
        local_aware = local_dt.replace(tzinfo=market_tz)
        
        if target_timezone is None or target_timezone == self.timezone:
            return local_aware
        else:
            target_tz = ZoneInfo(target_timezone)
            return local_aware.astimezone(target_tz)
    
    def __repr__(self):
        return (
            f"<MarketHours {self.exchange_group} {self.asset_class}: "
            f"{self.regular_open}-{self.regular_close} {self.timezone}>"
        )
