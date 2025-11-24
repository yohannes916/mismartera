"""Session Detector for Prefetch Mechanism

Detects next trading sessions and determines when to trigger prefetch operations.

Used by PrefetchManager to anticipate and prepare for upcoming sessions.
"""
from datetime import date, datetime, time, timedelta
from typing import Optional
from app.managers.data_manager.trading_calendar import get_trading_calendar, TradingCalendar
from app.config import settings
from app.logger import logger


class SessionDetector:
    """Detect and analyze trading sessions.
    
    Responsibilities:
    - Determine next trading session
    - Calculate prefetch timing
    - Validate session boundaries
    """
    
    # US Market hours (Eastern Time)
    MARKET_OPEN = time(9, 30)   # 9:30 AM ET
    MARKET_CLOSE = time(16, 0)  # 4:00 PM ET
    
    def __init__(self, trading_calendar: Optional[TradingCalendar] = None):
        """Initialize session detector.
        
        Args:
            trading_calendar: Trading calendar to use (default: singleton)
        """
        self._calendar = trading_calendar or get_trading_calendar()
        logger.debug("SessionDetector initialized")
    
    def get_next_session(
        self,
        from_date: date,
        skip_today: bool = False
    ) -> Optional[date]:
        """Get the next trading session after a given date.
        
        Args:
            from_date: Reference date
            skip_today: If True, skip today even if it's a trading day
            
        Returns:
            Next trading session date, or None if not found
        """
        # If not skipping today and today is a trading day, return it
        if not skip_today and self._calendar.is_trading_day(from_date):
            return from_date
        
        # Get next trading day
        next_day = self._calendar.get_next_trading_day(from_date, days_ahead=1)
        
        if next_day:
            logger.debug(f"Next session after {from_date}: {next_day}")
        else:
            logger.warning(f"No next session found after {from_date}")
        
        return next_day
    
    def should_prefetch(
        self,
        current_time: datetime,
        next_session: date,
        prefetch_window_minutes: Optional[int] = None
    ) -> bool:
        """Determine if prefetch should start now.
        
        Prefetch window: configurable minutes before session start
        (default: from settings.PREFETCH_WINDOW_MINUTES)
        
        Args:
            current_time: Current datetime
            next_session: Next session date
            prefetch_window_minutes: Minutes before session to start prefetch
            
        Returns:
            True if prefetch should start
        """
        if prefetch_window_minutes is None:
            prefetch_window_minutes = settings.PREFETCH_WINDOW_MINUTES
        
        # Calculate session start time
        session_start = datetime.combine(next_session, self.MARKET_OPEN)
        
        # Calculate time until session
        time_until_session = (session_start - current_time).total_seconds()
        
        # Convert window to seconds
        window_seconds = prefetch_window_minutes * 60
        
        # Should prefetch if within window but not past session start
        should_start = 0 < time_until_session <= window_seconds
        
        if should_start:
            logger.info(
                f"Prefetch window active: {time_until_session/60:.1f} minutes "
                f"until session {next_session}"
            )
        
        return should_start
    
    def is_during_market_hours(self, check_time: datetime) -> bool:
        """Check if time is during market hours.
        
        Args:
            check_time: Datetime to check
            
        Returns:
            True if during market hours (9:30 AM - 4:00 PM ET)
        """
        # Check if trading day
        if not self._calendar.is_trading_day(check_time.date()):
            return False
        
        # Check if within market hours
        current_time = check_time.time()
        return self.MARKET_OPEN <= current_time <= self.MARKET_CLOSE
    
    def get_session_boundary_status(
        self,
        current_time: datetime,
        current_session: Optional[date]
    ) -> str:
        """Determine if at session boundary.
        
        Args:
            current_time: Current datetime
            current_session: Currently active session date
            
        Returns:
            "pre_market" - Before market open
            "market_hours" - During market hours
            "post_market" - After market close
            "session_end" - Session ended, new session starting
            "no_session" - No active session
        """
        current_date = current_time.date()
        current_time_only = current_time.time()
        
        # No active session?
        if current_session is None:
            if self._calendar.is_trading_day(current_date):
                if current_time_only < self.MARKET_OPEN:
                    return "pre_market"
                elif current_time_only <= self.MARKET_CLOSE:
                    return "market_hours"
                else:
                    return "post_market"
            return "no_session"
        
        # Have active session - check if it's still valid
        if current_date == current_session:
            # Same day as session
            if current_time_only < self.MARKET_OPEN:
                return "pre_market"
            elif current_time_only <= self.MARKET_CLOSE:
                return "market_hours"
            else:
                return "post_market"
        
        elif current_date > current_session:
            # Session is in the past - need new session
            return "session_end"
        
        else:
            # current_date < current_session (shouldn't happen normally)
            logger.warning(
                f"Current date {current_date} is before session {current_session}"
            )
            return "no_session"
    
    def calculate_prefetch_start_time(
        self,
        session_date: date,
        prefetch_window_minutes: Optional[int] = None
    ) -> datetime:
        """Calculate when prefetch should start for a session.
        
        Args:
            session_date: Session date
            prefetch_window_minutes: Minutes before session to prefetch
            
        Returns:
            Datetime when prefetch should start
        """
        if prefetch_window_minutes is None:
            prefetch_window_minutes = settings.PREFETCH_WINDOW_MINUTES
        
        # Session starts at market open
        session_start = datetime.combine(session_date, self.MARKET_OPEN)
        
        # Prefetch starts N minutes before
        prefetch_start = session_start - timedelta(minutes=prefetch_window_minutes)
        
        return prefetch_start
    
    def get_time_until_next_session(
        self,
        current_time: datetime,
        from_date: Optional[date] = None
    ) -> Optional[timedelta]:
        """Calculate time remaining until next session starts.
        
        Args:
            current_time: Current datetime
            from_date: Reference date (default: current_time.date())
            
        Returns:
            Timedelta until next session, or None if no session found
        """
        if from_date is None:
            from_date = current_time.date()
        
        next_session = self.get_next_session(from_date, skip_today=False)
        if next_session is None:
            return None
        
        session_start = datetime.combine(next_session, self.MARKET_OPEN)
        time_remaining = session_start - current_time
        
        return time_remaining if time_remaining.total_seconds() > 0 else timedelta(0)
    
    def should_roll_session(
        self,
        current_time: datetime,
        current_session: Optional[date]
    ) -> bool:
        """Determine if session should be rolled to new day.
        
        Args:
            current_time: Current datetime
            current_session: Currently active session
            
        Returns:
            True if session should be rolled
        """
        if current_session is None:
            return False
        
        status = self.get_session_boundary_status(current_time, current_session)
        
        # Roll if session has ended
        return status == "session_end"


# Example usage
if __name__ == "__main__":
    detector = SessionDetector()
    
    # Test next session
    today = date.today()
    next_session = detector.get_next_session(today)
    print(f"Next session after {today}: {next_session}")
    
    # Test prefetch timing
    now = datetime.now()
    if next_session:
        should_prefetch = detector.should_prefetch(now, next_session)
        print(f"Should prefetch now: {should_prefetch}")
        
        prefetch_time = detector.calculate_prefetch_start_time(next_session)
        print(f"Prefetch should start at: {prefetch_time}")
    
    # Test market hours
    is_market = detector.is_during_market_hours(now)
    print(f"Currently during market hours: {is_market}")
    
    # Test time until next
    time_until = detector.get_time_until_next_session(now)
    if time_until:
        print(f"Time until next session: {time_until}")
