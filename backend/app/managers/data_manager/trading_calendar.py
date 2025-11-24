"""Trading Calendar for US Stock Markets

Provides functionality to determine trading days, holidays, and market hours
for the US stock market.

Used by prefetch mechanism and session management.
"""
from datetime import date, timedelta
from typing import Set, Optional
from app.logger import logger


class TradingCalendar:
    """US stock market trading calendar.
    
    Handles:
    - US market holidays
    - Weekend detection
    - Next trading day calculation
    - Trading day validation
    """
    
    def __init__(self):
        """Initialize trading calendar with US market holidays."""
        self._holidays = self._load_us_market_holidays()
        logger.debug(f"Trading calendar initialized with {len(self._holidays)} holidays")
    
    def _load_us_market_holidays(self) -> Set[date]:
        """Load US stock market holidays for 2025-2026.
        
        Returns:
            Set of holiday dates when market is closed
        """
        holidays = {
            # 2025 US Market Holidays
            date(2025, 1, 1),   # New Year's Day
            date(2025, 1, 20),  # Martin Luther King Jr. Day
            date(2025, 2, 17),  # Presidents' Day
            date(2025, 4, 18),  # Good Friday
            date(2025, 5, 26),  # Memorial Day
            date(2025, 6, 19),  # Juneteenth National Independence Day
            date(2025, 7, 4),   # Independence Day
            date(2025, 9, 1),   # Labor Day
            date(2025, 11, 27), # Thanksgiving Day
            date(2025, 12, 25), # Christmas Day
            
            # 2026 US Market Holidays (for continuity)
            date(2026, 1, 1),   # New Year's Day
            date(2026, 1, 19),  # Martin Luther King Jr. Day
            date(2026, 2, 16),  # Presidents' Day
            date(2026, 4, 3),   # Good Friday
            date(2026, 5, 25),  # Memorial Day
            date(2026, 6, 19),  # Juneteenth National Independence Day
            date(2026, 7, 3),   # Independence Day (observed)
            date(2026, 9, 7),   # Labor Day
            date(2026, 11, 26), # Thanksgiving Day
            date(2026, 12, 25), # Christmas Day
        }
        return holidays
    
    def is_trading_day(self, check_date: date) -> bool:
        """Check if a date is a valid trading day.
        
        Args:
            check_date: Date to check
            
        Returns:
            True if market is open on this date
        """
        # Check if weekend (Saturday=5, Sunday=6)
        if check_date.weekday() >= 5:
            return False
        
        # Check if holiday
        if check_date in self._holidays:
            return False
        
        return True
    
    def is_holiday(self, check_date: date) -> bool:
        """Check if a date is a market holiday.
        
        Args:
            check_date: Date to check
            
        Returns:
            True if date is a recognized market holiday
        """
        return check_date in self._holidays
    
    def get_next_trading_day(
        self,
        from_date: date,
        days_ahead: int = 1
    ) -> Optional[date]:
        """Get the Nth trading day after a given date.
        
        Args:
            from_date: Starting date (not included in count)
            days_ahead: Number of trading days ahead (default: 1 = next day)
            
        Returns:
            Date of the Nth trading day, or None if not found within 60 days
        """
        if days_ahead < 1:
            raise ValueError("days_ahead must be at least 1")
        
        current = from_date
        found = 0
        max_attempts = 60  # Safety limit
        attempts = 0
        
        while found < days_ahead and attempts < max_attempts:
            current += timedelta(days=1)
            attempts += 1
            
            if self.is_trading_day(current):
                found += 1
        
        if found < days_ahead:
            logger.warning(
                f"Could not find {days_ahead} trading days after {from_date} "
                f"within {max_attempts} days"
            )
            return None
        
        return current
    
    def get_previous_trading_day(
        self,
        from_date: date,
        days_back: int = 1
    ) -> Optional[date]:
        """Get the Nth trading day before a given date.
        
        Args:
            from_date: Starting date (not included in count)
            days_back: Number of trading days back (default: 1 = previous day)
            
        Returns:
            Date of the Nth previous trading day, or None if not found
        """
        if days_back < 1:
            raise ValueError("days_back must be at least 1")
        
        current = from_date
        found = 0
        max_attempts = 60  # Safety limit
        attempts = 0
        
        while found < days_back and attempts < max_attempts:
            current -= timedelta(days=1)
            attempts += 1
            
            if self.is_trading_day(current):
                found += 1
        
        if found < days_back:
            logger.warning(
                f"Could not find {days_back} trading days before {from_date} "
                f"within {max_attempts} days"
            )
            return None
        
        return current
    
    def count_trading_days(
        self,
        start_date: date,
        end_date: date
    ) -> int:
        """Count number of trading days in a date range (inclusive).
        
        Args:
            start_date: Start of range (inclusive)
            end_date: End of range (inclusive)
            
        Returns:
            Number of trading days in range
        """
        if start_date > end_date:
            return 0
        
        count = 0
        current = start_date
        
        while current <= end_date:
            if self.is_trading_day(current):
                count += 1
            current += timedelta(days=1)
        
        return count
    
    def get_trading_days_in_range(
        self,
        start_date: date,
        end_date: date
    ) -> list[date]:
        """Get list of all trading days in a date range.
        
        Args:
            start_date: Start of range (inclusive)
            end_date: End of range (inclusive)
            
        Returns:
            List of trading day dates
        """
        if start_date > end_date:
            return []
        
        trading_days = []
        current = start_date
        
        while current <= end_date:
            if self.is_trading_day(current):
                trading_days.append(current)
            current += timedelta(days=1)
        
        return trading_days
    
    def add_holiday(self, holiday_date: date) -> None:
        """Add a holiday to the calendar.
        
        Useful for adding special closures not in the standard calendar.
        
        Args:
            holiday_date: Date to add as holiday
        """
        self._holidays.add(holiday_date)
        logger.info(f"Added holiday to calendar: {holiday_date}")
    
    def remove_holiday(self, holiday_date: date) -> None:
        """Remove a holiday from the calendar.
        
        Args:
            holiday_date: Date to remove from holidays
        """
        if holiday_date in self._holidays:
            self._holidays.remove(holiday_date)
            logger.info(f"Removed holiday from calendar: {holiday_date}")


# Singleton instance
_calendar_instance: Optional[TradingCalendar] = None


def get_trading_calendar() -> TradingCalendar:
    """Get the singleton trading calendar instance.
    
    Returns:
        TradingCalendar instance
    """
    global _calendar_instance
    if _calendar_instance is None:
        _calendar_instance = TradingCalendar()
    return _calendar_instance


# Example usage
if __name__ == "__main__":
    cal = TradingCalendar()
    
    # Test basic checks
    print(f"2025-01-01 is trading day: {cal.is_trading_day(date(2025, 1, 1))}")  # False (holiday)
    print(f"2025-01-02 is trading day: {cal.is_trading_day(date(2025, 1, 2))}")  # True
    print(f"2025-01-04 is trading day: {cal.is_trading_day(date(2025, 1, 4))}")  # False (Saturday)
    
    # Test next trading day
    next_day = cal.get_next_trading_day(date(2025, 1, 1))
    print(f"Next trading day after 2025-01-01: {next_day}")  # Should skip to Jan 2
    
    # Test counting
    count = cal.count_trading_days(date(2025, 1, 1), date(2025, 1, 31))
    print(f"Trading days in January 2025: {count}")
