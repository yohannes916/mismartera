"""
Time Manager Data Models
Core data structures for trading sessions and market hours configuration
"""
from dataclasses import dataclass, field
from datetime import date, time, datetime
from typing import Optional, List
from zoneinfo import ZoneInfo


@dataclass
class TradingSession:
    """Complete information about a trading session for a specific date
    
    Represents all market information for a given exchange and asset class
    on a specific date, including regular hours, extended hours, and special
    conditions (holidays, early closes).
    """
    date: date
    exchange: str           # PRIMARY: "NYSE", "NASDAQ", "CME"
    asset_class: str        # PRIMARY: "EQUITY", "OPTION", "FUTURES"
    timezone: str           # IANA timezone (e.g., "America/New_York")
    
    # Optional metadata
    country: Optional[str] = None  # For display/grouping
    exchange_name: Optional[str] = None  # "New York Stock Exchange"
    
    # Regular hours (in local market time)
    regular_open: Optional[time] = None
    regular_close: Optional[time] = None
    
    # Extended hours (optional)
    pre_market_open: Optional[time] = None
    pre_market_close: Optional[time] = None
    post_market_open: Optional[time] = None
    post_market_close: Optional[time] = None
    
    # Special flags
    is_trading_day: bool = True
    is_holiday: bool = False
    is_early_close: bool = False
    holiday_name: Optional[str] = None
    
    def get_regular_open_datetime(self) -> Optional[datetime]:
        """Get regular open as timezone-aware datetime
        
        Returns:
            Timezone-aware datetime or None if market closed
        """
        if self.regular_open is None:
            return None
        dt = datetime.combine(self.date, self.regular_open)
        return dt.replace(tzinfo=ZoneInfo(self.timezone))
    
    def get_regular_close_datetime(self) -> Optional[datetime]:
        """Get regular close as timezone-aware datetime
        
        Returns:
            Timezone-aware datetime or None if market closed
        """
        if self.regular_close is None:
            return None
        dt = datetime.combine(self.date, self.regular_close)
        return dt.replace(tzinfo=ZoneInfo(self.timezone))
    
    def get_regular_open_utc(self) -> Optional[datetime]:
        """Get regular open in UTC
        
        Returns:
            UTC datetime or None if market closed
        """
        open_dt = self.get_regular_open_datetime()
        if open_dt is None:
            return None
        return open_dt.astimezone(ZoneInfo("UTC"))
    
    def get_regular_close_utc(self) -> Optional[datetime]:
        """Get regular close in UTC
        
        Returns:
            UTC datetime or None if market closed
        """
        from app.util.logging_config import get_logger
        logger = get_logger(__name__)
        
        close_dt = self.get_regular_close_datetime()
        if close_dt is None:
            return None
        
        utc_dt = close_dt.astimezone(ZoneInfo("UTC"))
        logger.debug(
            f"get_regular_close_utc: date={self.date}, "
            f"regular_close={self.regular_close}, "
            f"timezone={self.timezone}, "
            f"close_dt={close_dt}, "
            f"utc_dt={utc_dt}"
        )
        return utc_dt


@dataclass
class MarketHoursConfig:
    """Market hours configuration for a specific exchange + asset class
    
    Defines the trading schedule for a particular market, including regular
    and extended hours, timezone, and trading days.
    """
    exchange: str           # PRIMARY: "NYSE", "NASDAQ", "CME"
    asset_class: str        # PRIMARY: "EQUITY", "OPTION", "FUTURES"
    timezone: str           # IANA timezone (e.g., "America/New_York")
    
    # Regular hours (in local market time)
    regular_open: time
    regular_close: time
    
    # Optional metadata
    country: Optional[str] = None      # For display/grouping ("USA", "UK", "JP")
    exchange_name: Optional[str] = None  # "New York Stock Exchange"
    
    # Extended hours (optional)
    pre_market_open: Optional[time] = None
    pre_market_close: Optional[time] = None
    post_market_open: Optional[time] = None
    post_market_close: Optional[time] = None
    
    # Trading days (0=Monday, 6=Sunday)
    trading_days: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    
    def is_trading_day_of_week(self, weekday: int) -> bool:
        """Check if a weekday is a trading day
        
        Args:
            weekday: Day of week (0=Monday, 6=Sunday)
            
        Returns:
            True if trading day
        """
        return weekday in self.trading_days
