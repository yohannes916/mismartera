"""
Time Manager API
Single source of truth for all date/time and market calendar operations

Phase 2.2: Added caching layer for improved performance
- Last-query cache for repeated queries
- LRU cache for trading sessions (~100 entries)
- get_first_trading_date() for inclusive date finding
- Cache invalidation support
"""
from datetime import date, time, datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from functools import lru_cache

from app.config import settings
from app.logger import logger
from app.managers.time_manager.models import TradingSession, MarketHoursConfig
from app.managers.time_manager.repositories import TradingCalendarRepository


# Global singleton instance
_time_manager_instance: Optional['TimeManager'] = None


class TimeManager:
    """Single source of truth for all time and calendar operations
    
    Responsibilities:
    - Current time (live/backtest modes)
    - Market hours (regular + extended)
    - Trading calendar (holidays, early closes)
    - Trading date navigation
    - Timezone conversion
    
    This class is a SINGLETON - use get_time_manager() to obtain the instance.
    """
    
    def __init__(self, system_manager=None):
        """Initialize TimeManager with SystemManager reference
        
        Args:
            system_manager: Reference to SystemManager (REQUIRED for production use)
            
        IMPORTANT: Do not call directly. Use get_time_manager() instead.
        """
        self._system_manager = system_manager
        self._backtest_time: Optional[datetime] = None
        
        # Backtest window (loaded from session config)
        self.backtest_start_date: Optional[date] = None
        self.backtest_end_date: Optional[date] = None
        
        # Market hours configuration (loaded from database)
        self._market_configs: Dict[Tuple[str, str], MarketHoursConfig] = {}
        self._load_market_hours_from_database()
        
        # Caching infrastructure (Phase 2.2)
        # Last-query cache: Stores the most recent query and result
        # This is highly effective for repeated identical queries
        self._last_query_cache: Dict[str, Any] = {
            'key': None,
            'result': None
        }
        
        # LRU cache statistics (for monitoring)
        self._cache_hits = 0
        self._cache_misses = 0
        
        if system_manager is None:
            logger.warning("TimeManager initialized without SystemManager - mode checks will fail!")
        else:
            logger.debug("TimeManager initialized with SystemManager reference")
    
    @property
    def default_timezone(self) -> str:
        """Get default timezone from system manager"""
        if self._system_manager is None:
            return "America/New_York"  # Fallback
        return self._system_manager.timezone
    
    @property
    def default_exchange_group(self) -> str:
        """Get default exchange group from system manager"""
        if self._system_manager is None:
            return "US_EQUITY"  # Fallback
        return self._system_manager.exchange_group
    
    @property
    def default_asset_class(self) -> str:
        """Get default asset class from system manager"""
        if self._system_manager is None:
            return "EQUITY"  # Fallback
        return self._system_manager.asset_class
    
    def _load_market_hours_from_database(self):
        """
        Load market hours from database into in-memory cache.
        
        If database is empty or error occurs, falls back to hardcoded defaults.
        """
        from app.models.database import SessionLocal
        from app.models.trading_calendar import MarketHours as MarketHoursDB
        
        try:
            with SessionLocal() as session:
                market_hours_list = session.query(MarketHoursDB).filter(
                    MarketHoursDB.is_active == True
                ).all()
                
                if market_hours_list:
                    for mh in market_hours_list:
                        # Convert database model to dataclass
                        config = MarketHoursConfig(
                            exchange=mh.exchange_group,  # Use exchange_group as exchange
                            asset_class=mh.asset_class,
                            timezone=mh.timezone,
                            country=mh.country,
                            exchange_name=mh.exchange_name,
                            regular_open=mh.regular_open,
                            regular_close=mh.regular_close,
                            pre_market_open=mh.pre_market_open,
                            pre_market_close=mh.pre_market_close,
                            post_market_open=mh.post_market_open,
                            post_market_close=mh.post_market_close,
                            trading_days=mh.get_trading_days_list()
                        )
                        # Key by (exchange_group, asset_class)
                        key = (mh.exchange_group, mh.asset_class)
                        self._market_configs[key] = config
                    
                    logger.info(f"Loaded {len(market_hours_list)} market hours from database")
                else:
                    logger.warning("No market hours in database, using hardcoded defaults")
                    self._initialize_default_markets()
        except Exception as e:
            logger.error(f"Error loading market hours from database: {e}")
            logger.warning("Falling back to hardcoded market hours")
            self._initialize_default_markets()
    
    def _initialize_default_markets(self):
        """Initialize default market configurations (NYSE, NASDAQ equities)"""
        # NYSE Equities
        self._market_configs[("NYSE", "EQUITY")] = MarketHoursConfig(
            exchange="NYSE",
            asset_class="EQUITY",
            timezone="America/New_York",
            country="USA",
            exchange_name="New York Stock Exchange",
            regular_open=time(9, 30),
            regular_close=time(16, 0),
            pre_market_open=time(4, 0),
            pre_market_close=time(9, 30),
            post_market_open=time(16, 0),
            post_market_close=time(20, 0),
            trading_days=[0, 1, 2, 3, 4]  # Mon-Fri
        )
        
        # NASDAQ Equities (same hours as NYSE)
        self._market_configs[("NASDAQ", "EQUITY")] = MarketHoursConfig(
            exchange="NASDAQ",
            asset_class="EQUITY",
            timezone="America/New_York",
            country="USA",
            exchange_name="NASDAQ Stock Market",
            regular_open=time(9, 30),
            regular_close=time(16, 0),
            pre_market_open=time(4, 0),
            pre_market_close=time(9, 30),
            post_market_open=time(16, 0),
            post_market_close=time(20, 0),
            trading_days=[0, 1, 2, 3, 4]
        )
        
        logger.info("Initialized default market configurations (NYSE, NASDAQ)")
    
    def _auto_initialize_backtest(self) -> None:
        """Auto-initialize backtest window and time.
        
        This is a fallback for cases where init_backtest() wasn't called.
        Requires SystemManager with session config to be available.
        
        IMPORTANT: _backtest_time is stored as UTC naive internally.
        Timezone information is added on output via get_current_time().
        """
        if self._system_manager is None:
            raise RuntimeError(
                "Cannot auto-initialize backtest: SystemManager not available. "
                "Call init_backtest() explicitly."
            )
        
        session_config = self._system_manager.session_config
        if session_config is None or session_config.backtest_config is None:
            raise RuntimeError(
                "Cannot auto-initialize backtest: No backtest config available. "
                "Ensure session config is loaded before accessing backtest time."
            )
        
        # Initialize from config
        with SessionLocal() as session:
            self.init_backtest(session)
        
        logger.info(
            "Backtest auto-initialized from config: %s - %s",
            self.backtest_start_date,
            self.backtest_end_date
        )
    
    # ==================== Current Time ====================
    
    def get_current_time(self, timezone: Optional[str] = None) -> datetime:
        """Get current time based on operation mode
        
        AUTO-INITIALIZATION: If in backtest mode and time is not set,
        automatically initializes backtest window and time on first access.
        
        TIMEZONE HANDLING:
        - Internal: _backtest_time stored as UTC naive
        - Output: Always timezone-aware, converted to requested timezone
        - Default: Uses system manager's timezone (from exchange_group config)
        
        Args:
            timezone: Target timezone (IANA format, e.g., 'America/New_York')
                     If None, uses system manager's default timezone
        
        Returns:
            Timezone-aware datetime
            
        Raises:
            ValueError: If SystemManager not available or initialization fails
        """
        if self._system_manager is None:
            raise ValueError(
                "SystemManager not available in TimeManager. "
                "TimeManager must be initialized with SystemManager reference."
            )
        
        mode = self._system_manager.mode.value
        
        # Use system default timezone if not specified
        if timezone is None:
            timezone = self.default_timezone
        
        if mode == "live":
            # Real-time clock in requested timezone
            tz = ZoneInfo(timezone)
            return datetime.now(tz)
        
        elif mode == "backtest":
            # Auto-initialize on first access
            if self._backtest_time is None:
                logger.info("Backtest time not set - auto-initializing from settings")
                self._auto_initialize_backtest()
            
            # _backtest_time is stored as UTC naive - add UTC timezone then convert
            utc_time = self._backtest_time.replace(tzinfo=ZoneInfo("UTC"))
            
            # Convert to target timezone
            target_tz = ZoneInfo(timezone)
            return utc_time.astimezone(target_tz)
        
        else:
            raise ValueError(f"Invalid operation mode: {mode}")
    
    def set_backtest_time(self, timestamp: datetime) -> None:
        """Set simulated time for backtest mode (called by stream coordinator)
        
        TIMEZONE HANDLING:
        - Accepts timezone-aware or naive datetime
        - Stores internally as UTC naive
        
        Args:
            timestamp: Backtest time to set
                      If naive, assumes exchange's timezone
                      If timezone-aware, converts to UTC
        """
        if self._system_manager is None:
            logger.warning("SystemManager not available - cannot verify mode for set_backtest_time")
            # Store as-is if naive, or convert to UTC naive if aware
            if timestamp.tzinfo is None:
                self._backtest_time = timestamp
            else:
                self._backtest_time = timestamp.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            return
        
        mode = self._system_manager.mode.value
        if mode != "backtest":
            logger.warning(
                "set_backtest_time called while mode=%s (ignored)",
                mode,
            )
            return
        
        # Store as UTC naive internally
        if timestamp.tzinfo is None:
            # Assume exchange's timezone if naive (for backward compatibility with ET)
            exchange_tz = ZoneInfo(self.get_market_timezone(self.default_exchange_group))
            aware_time = timestamp.replace(tzinfo=exchange_tz)
            # Convert to UTC and strip timezone
            self._backtest_time = aware_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        else:
            # Convert to UTC and strip timezone
            self._backtest_time = timestamp.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        
        logger.debug(f"Backtest time set to: {self._backtest_time} (UTC naive)")
    
    def get_current_mode(self) -> str:
        """Get current operation mode
        
        Returns:
            "live" or "backtest"
        """
        if self._system_manager is None:
            raise ValueError("SystemManager not available")
        return self._system_manager.mode.value
    
    # ==================== Market Sessions ====================
    
    def get_trading_session(
        self,
        session: Session,
        date: date,
        exchange: Optional[str] = None,
        asset_class: Optional[str] = None
    ) -> Optional[TradingSession]:
        """Get complete trading session information for a date
        
        CACHING: Uses last-query cache for repeated identical queries.
        LRU cache not used here due to database session parameter.
        
        Uses system manager defaults if not specified.
        
        Args:
            session: Database session
            date: Date to query
            exchange: Exchange group identifier (uses system default if None)
            asset_class: Asset class (uses system default if None)
            
        Returns:
            TradingSession or None if not found
        """
        # Use system defaults
        if exchange is None:
            exchange = self.default_exchange_group
        if asset_class is None:
            asset_class = self.default_asset_class
        
        # Check last-query cache (most common pattern: same query repeatedly)
        cache_key = f"trading_session:{date}:{exchange}:{asset_class}"
        if self._last_query_cache['key'] == cache_key:
            self._cache_hits += 1
            logger.debug(f"Cache hit for {cache_key}")
            return self._last_query_cache['result']
        
        self._cache_misses += 1
        
        # Get market configuration
        config = self.get_market_config(exchange, asset_class)
        if config is None:
            logger.warning(f"No configuration found for {exchange} {asset_class}")
            result = None
            # Cache the result
            self._last_query_cache['key'] = cache_key
            self._last_query_cache['result'] = result
            return result
        
        # Check if weekend
        if not config.is_trading_day_of_week(date.weekday()):
            result = TradingSession(
                date=date,
                exchange=exchange,
                asset_class=asset_class,
                timezone=config.timezone,
                country=config.country,
                exchange_name=config.exchange_name,
                is_trading_day=False,
                is_holiday=False
            )
            # Cache the result
            self._last_query_cache['key'] = cache_key
            self._last_query_cache['result'] = result
            return result
        
        # Check if holiday
        holiday = TradingCalendarRepository.get_holiday(session, date, exchange)
        
        if holiday and holiday.is_closed:
            # Full closure
            result = TradingSession(
                date=date,
                exchange=exchange,
                asset_class=asset_class,
                timezone=config.timezone,
                country=config.country,
                exchange_name=config.exchange_name,
                is_trading_day=False,
                is_holiday=True,
                holiday_name=holiday.holiday_name
            )
            # Cache the result
            self._last_query_cache['key'] = cache_key
            self._last_query_cache['result'] = result
            return result
        
        # Regular trading day or early close
        is_early_close = holiday is not None and holiday.early_close_time is not None
        close_time = holiday.early_close_time if is_early_close else config.regular_close
        
        result = TradingSession(
            date=date,
            exchange=exchange,
            asset_class=asset_class,
            timezone=config.timezone,
            country=config.country,
            exchange_name=config.exchange_name,
            regular_open=config.regular_open,
            regular_close=close_time,
            pre_market_open=config.pre_market_open,
            pre_market_close=config.pre_market_close,
            post_market_open=config.post_market_open if not is_early_close else close_time,
            post_market_close=config.post_market_close,
            is_trading_day=True,
            is_holiday=False,  # Trading days (including early closes) are NOT holidays
            is_early_close=is_early_close,
            holiday_name=holiday.holiday_name if holiday else None
        )
        # Cache the result
        self._last_query_cache['key'] = cache_key
        self._last_query_cache['result'] = result
        return result
    
    def get_market_hours(
        self,
        date: date,
        exchange: Optional[str] = None,
        asset_class: Optional[str] = None,
        include_extended: bool = False
    ) -> Optional[Dict[str, time]]:
        """Get market hours for a specific date
        
        Uses system defaults if not specified.
        
        Args:
            date: Date to query
            exchange: Exchange group identifier (uses system default if None)
            asset_class: Asset class (uses system default if None)
            include_extended: If True, include pre/post market hours
            
        Returns:
            Dict with 'open' and 'close' times (regular or extended)
        """
        # Use system defaults
        if exchange is None:
            exchange = self.default_exchange_group
        if asset_class is None:
            asset_class = self.default_asset_class
        
        from app.models.database import SessionLocal
        
        with SessionLocal() as session:
            trading_session = self.get_trading_session(
                session, date, exchange, asset_class
            )
            
            if trading_session is None or not trading_session.is_trading_day:
                return None
            
            hours = {
                'open': trading_session.regular_open,
                'close': trading_session.regular_close
            }
            
            if include_extended:
                if trading_session.pre_market_open:
                    hours['pre_open'] = trading_session.pre_market_open
                    hours['pre_close'] = trading_session.pre_market_close
                if trading_session.post_market_open:
                    hours['post_open'] = trading_session.post_market_open
                    hours['post_close'] = trading_session.post_market_close
            
            return hours
    
    # ==================== Market Status ====================
    
    def is_market_open(
        self,
        session: Session,
        timestamp: datetime,
        exchange: Optional[str] = None,
        asset_class: Optional[str] = None,
        include_extended: bool = False
    ) -> bool:
        """Check if market is currently open at given timestamp
        
        Uses system defaults if not specified.
        
        Args:
            session: Database session
            timestamp: Time to check
            exchange: Exchange group identifier (uses system default if None)
            asset_class: Asset class (uses system default if None)
            include_extended: If True, include pre/post market hours
            
        Returns:
            True if market is open
        """
        # Use system defaults
        if exchange is None:
            exchange = self.default_exchange_group
        if asset_class is None:
            asset_class = self.default_asset_class
        
        # Ensure timestamp is timezone-aware
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=ZoneInfo("UTC"))
        
        # Get market config to determine timezone
        config = self.get_market_config(exchange, asset_class)
        if config is None:
            return False
        
        # Convert timestamp to market timezone
        market_tz = ZoneInfo(config.timezone)
        local_time = timestamp.astimezone(market_tz)
        local_date = local_time.date()
        time_of_day = local_time.time()
        
        # Get trading session
        trading_session = self.get_trading_session(
            session, local_date, exchange, asset_class
        )
        
        if trading_session is None or not trading_session.is_trading_day:
            return False
        
        # Check regular hours
        if trading_session.regular_open <= time_of_day < trading_session.regular_close:
            return True
        
        # Check extended hours if requested
        if include_extended:
            # Pre-market
            if (trading_session.pre_market_open and
                trading_session.pre_market_open <= time_of_day < trading_session.pre_market_close):
                return True
            # Post-market
            if (trading_session.post_market_open and
                trading_session.post_market_open <= time_of_day < trading_session.post_market_close):
                return True
        
        return False
    
    def get_market_hours_datetime(
        self,
        session: Session,
        date: date,
        exchange: Optional[str] = None,
        asset_class: Optional[str] = None
    ) -> Optional[Tuple[datetime, datetime]]:
        """Get market open and close as timezone-aware datetime objects.
        
        This is the CORRECT way to get market hours for time comparisons.
        Returns complete datetime objects with proper timezone set.
        
        Args:
            session: Database session
            date: Trading date
            exchange: Exchange identifier (uses default if None)
            asset_class: Asset class (uses default if None)
            
        Returns:
            Tuple of (market_open_datetime, market_close_datetime) with timezone,
            or None if not a trading day
            
        Example:
            market_open, market_close = time_mgr.get_market_hours_datetime(session, date)
            current = time_mgr.get_current_time()
            if current >= market_close:
                # Market is closed
        """
        # Use system defaults
        if exchange is None:
            exchange = self.default_exchange_group
        if asset_class is None:
            asset_class = self.default_asset_class
        
        # Get trading session
        trading_session = self.get_trading_session(session, date, exchange, asset_class)
        
        if not trading_session or not trading_session.is_trading_day:
            return None
        
        # Get timezone
        tz = ZoneInfo(trading_session.timezone)
        
        # Create timezone-aware datetime objects
        market_open = datetime.combine(date, trading_session.regular_open, tzinfo=tz)
        market_close = datetime.combine(date, trading_session.regular_close, tzinfo=tz)
        
        return (market_open, market_close)
    
    def is_trading_day(
        self,
        session: Session,
        date: date,
        exchange: Optional[str] = None
    ) -> bool:
        """Check if date is a trading day (not weekend/holiday)
        
        Uses system default if not specified.
        
        Args:
            session: Database session
            date: Date to check
            exchange: Exchange group identifier (uses system default if None)
            
        Returns:
            True if trading day
        """
        # Use system default
        if exchange is None:
            exchange = self.default_exchange_group
        
        trading_session = self.get_trading_session(session, date, exchange, "EQUITY"  # Use EQUITY as default
        )
        return trading_session is not None and trading_session.is_trading_day
    
    def is_holiday(
        self,
        session: Session,
        date: date,
        exchange: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Check if date is a holiday (full market closure)
        
        Returns True ONLY for full market closures (is_closed=True).
        Early close days (is_closed=False) are NOT considered holidays.
        
        Uses system default if not specified.
        
        Args:
            session: Database session
            date: Date to check
            exchange: Exchange group identifier (uses system default if None)
            
        Returns:
            (is_holiday, holiday_name) - True only for full closures
        """
        # Use system default
        if exchange is None:
            exchange = self.default_exchange_group
        
        holiday = TradingCalendarRepository.get_holiday(session, date, exchange)
        if not holiday:
            return False, None
        # Only return True for full market closures
        if holiday.is_closed:
            return True, holiday.holiday_name
        # Early close days are NOT holidays
        return False, None
    
    def is_early_close(
        self,
        session: Session,
        date: date,
        exchange: Optional[str] = None
    ) -> Tuple[bool, Optional[time]]:
        """Check if date has early close
        
        Uses system default if not specified.
        
        Args:
            session: Database session
            date: Date to check
            exchange: Exchange group identifier (uses system default if None)
            
        Returns:
            (is_early_close, early_close_time)
        """
        # Use system default
        if exchange is None:
            exchange = self.default_exchange_group
        
        holiday = TradingCalendarRepository.get_holiday(session, date, exchange)
        if not holiday or holiday.is_closed or not holiday.early_close_time:
            return False, None
        return True, holiday.early_close_time
    
    # ==================== Trading Date Navigation ====================
    
    def get_next_trading_date(
        self,
        session: Session,
        from_date: date,
        n: int = 1,
        exchange: str = "NYSE"
    ) -> Optional[date]:
        """Get the Nth next trading date from a given date
        
        Args:
            session: Database session
            from_date: Starting date (exclusive)
            n: Number of trading days forward (default: 1)
            exchange: Exchange identifier
            
        Returns:
            Next trading date or None if not found within reasonable range
        """
        if n < 1:
            raise ValueError("n must be >= 1")
        
        current_date = from_date + timedelta(days=1)
        count = 0
        max_iterations = 365  # Safety limit
        
        for _ in range(max_iterations):
            if self.is_trading_day(session, current_date, exchange):
                count += 1
                if count == n:
                    return current_date
            current_date += timedelta(days=1)
        
        logger.warning(f"Could not find {n}th trading date after {from_date}")
        return None
    
    def get_previous_trading_date(
        self,
        session: Session,
        from_date: date,
        n: int = 1,
        exchange: str = "NYSE"
    ) -> Optional[date]:
        """Get the Nth previous trading date from a given date
        
        Args:
            session: Database session
            from_date: Starting date (exclusive)
            n: Number of trading days backward (default: 1)
            exchange: Exchange identifier
            
        Returns:
            Previous trading date or None if not found
        """
        if n < 1:
            raise ValueError("n must be >= 1")
        
        current_date = from_date - timedelta(days=1)
        count = 0
        max_iterations = 365  # Safety limit
        
        for _ in range(max_iterations):
            if self.is_trading_day(session, current_date, exchange):
                count += 1
                if count == n:
                    return current_date
            current_date -= timedelta(days=1)
        
        logger.warning(f"Could not find {n}th trading date before {from_date}")
        return None
    
    def count_trading_days(
        self,
        session: Session,
        start_date: date,
        end_date: date,
        exchange: str = "NYSE"
    ) -> int:
        """Count trading days between two dates (inclusive)
        
        Args:
            session: Database session
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            exchange: Exchange identifier
            
        Returns:
            Number of trading days
        """
        count = 0
        current = start_date
        
        while current <= end_date:
            if self.is_trading_day(session, current, exchange):
                count += 1
            current += timedelta(days=1)
        
        return count
    
    def get_first_trading_date(
        self,
        session: Session,
        from_date: date,
        exchange: str = "NYSE"
    ) -> Optional[date]:
        """Get first trading date starting from given date (INCLUSIVE)
        
        NEW in Phase 2.2: This method finds the first trading date from a given
        date, INCLUDING that date if it's a trading day. This is different from
        get_next_trading_date which is EXCLUSIVE.
        
        Use cases:
        - Finding session start date from config date (which may not be a trading day)
        - Determining first valid date in a backtest window
        
        Args:
            session: Database session
            from_date: Starting date (INCLUSIVE - checked first)
            exchange: Exchange identifier
            
        Returns:
            First trading date from from_date (inclusive), or None if not found
            
        Examples:
            - from_date is Monday (trading day) → returns Monday
            - from_date is Saturday → returns next Monday
            - from_date is holiday → returns next trading day
        """
        # Check if from_date itself is a trading day
        if self.is_trading_day(session, from_date, exchange):
            return from_date
        
        # Otherwise, find next trading date (exclusive from from_date)
        return self.get_next_trading_date(session, from_date, n=1, exchange=exchange)
    
    def get_trading_dates_in_range(
        self,
        session: Session,
        start_date: date,
        end_date: date,
        exchange: str = "NYSE"
    ) -> List[date]:
        """Get list of all trading dates in a range
        
        Args:
            session: Database session
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            exchange: Exchange identifier
            
        Returns:
            List of trading dates
        """
        dates = []
        current = start_date
        
        while current <= end_date:
            if self.is_trading_day(session, current, exchange):
                dates.append(current)
            current += timedelta(days=1)
        
        return dates
    
    # ==================== Extended Hours ====================
    
    def get_session_type(
        self,
        session: Session,
        timestamp: datetime,
        exchange: str = "NYSE",
        asset_class: str = "EQUITY"
    ) -> str:
        """Get current market session type
        
        Args:
            session: Database session
            timestamp: Time to check
            exchange: Exchange identifier
            asset_class: Asset class
            
        Returns:
            "pre_market", "regular", "post_market", or "closed"
        """
        # Ensure timestamp is timezone-aware
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=ZoneInfo("UTC"))
        
        # Get market config
        config = self.get_market_config(exchange, asset_class)
        if config is None:
            return "closed"
        
        # Convert to market timezone
        market_tz = ZoneInfo(config.timezone)
        local_time = timestamp.astimezone(market_tz)
        local_date = local_time.date()
        time_of_day = local_time.time()
        
        # Get trading session
        trading_session = self.get_trading_session(
            session, local_date, exchange, asset_class
        )
        
        if trading_session is None or not trading_session.is_trading_day:
            return "closed"
        
        # Check session type
        if trading_session.regular_open <= time_of_day < trading_session.regular_close:
            return "regular"
        
        if trading_session.pre_market_open and trading_session.pre_market_open <= time_of_day < trading_session.pre_market_close:
            return "pre_market"
        
        if trading_session.post_market_open and trading_session.post_market_open <= time_of_day < trading_session.post_market_close:
            return "post_market"
        
        return "closed"
    
    # ==================== Timezone Conversion ====================
    
    def convert_timezone(
        self,
        dt: datetime,
        to_timezone: str
    ) -> datetime:
        """Convert datetime to specified timezone
        
        Args:
            dt: Datetime (naive=UTC, or timezone-aware)
            to_timezone: Target timezone (IANA format)
            
        Returns:
            Timezone-aware datetime in target timezone
        """
        # Ensure dt is timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        
        return dt.astimezone(ZoneInfo(to_timezone))
    
    def to_utc(self, dt: datetime) -> datetime:
        """Convert datetime to UTC
        
        Args:
            dt: Datetime (naive=UTC, or timezone-aware)
            
        Returns:
            Timezone-aware datetime in UTC
        """
        return self.convert_timezone(dt, "UTC")
    
    def to_market_timezone(
        self,
        dt: datetime,
        exchange: str = "NYSE"
    ) -> datetime:
        """Convert datetime to market's local timezone
        
        Args:
            dt: Datetime to convert
            exchange: Exchange identifier
            
        Returns:
            Datetime in market's timezone
        """
        tz = self.get_market_timezone(exchange)
        return self.convert_timezone(dt, tz)
    
    def get_market_timezone(
        self,
        exchange: str = "NYSE"
    ) -> str:
        """Get the timezone for a specific market
        
        Args:
            exchange: Exchange identifier
            
        Returns:
            IANA timezone string (e.g., "America/New_York")
        """
        # Look up in market configs
        for (exch, _), config in self._market_configs.items():
            if exch == exchange:
                return config.timezone
        
        # Default to NY timezone
        logger.warning(f"Unknown exchange {exchange}, defaulting to America/New_York")
        return "America/New_York"
    
    # ==================== Configuration Management ====================
    
    def register_market_hours(
        self,
        config: MarketHoursConfig
    ) -> None:
        """Register market hours configuration for an exchange
        
        Args:
            config: Market hours configuration
        """
        key = (config.exchange, config.asset_class)
        self._market_configs[key] = config
        logger.info(f"Registered market hours: {config.exchange} {config.asset_class}")
    
    def get_market_config(
        self,
        exchange: Optional[str] = None,
        asset_class: Optional[str] = None
    ) -> Optional[MarketHoursConfig]:
        """Get market hours configuration
        
        Uses system manager defaults if parameters not specified.
        
        Args:
            exchange: Exchange group identifier (uses system default if None)
            asset_class: Asset class (uses system default if None)
            
        Returns:
            MarketHoursConfig or None if not configured
        """
        if exchange is None:
            exchange = self.default_exchange_group
        if asset_class is None:
            asset_class = self.default_asset_class
        
        key = (exchange, asset_class)
        return self._market_configs.get(key)
    
    # ==================== Holiday Management ====================
    
    def add_holiday(
        self,
        session: Session,
        date: date,
        holiday_name: str,
        exchange: str = "NYSE",
        country: Optional[str] = None,
        notes: Optional[str] = None,
        early_close_time: Optional[time] = None
    ) -> None:
        """Add a holiday or early close day
        
        Args:
            session: Database session
            date: Holiday date
            holiday_name: Name of holiday
            exchange: Exchange identifier
            country: Country code
            notes: Optional notes
            early_close_time: If set, market closes early (not full closure)
        """
        TradingCalendarRepository.create_holiday(
            session, date, holiday_name, exchange, country, notes, early_close_time
        )
    
    def bulk_import_holidays(
        self,
        session: Session,
        holidays: List[Dict],
        exchange: str = "NYSE"
    ) -> int:
        """Bulk import holidays for a market
        
        Args:
            session: Database session
            holidays: List of holiday dicts
            exchange: Exchange identifier
            
        Returns:
            Number of holidays imported
        """
        return TradingCalendarRepository.bulk_create_holidays(
            session, holidays, exchange
        )
    
    def get_holidays_in_range(
        self,
        session: Session,
        start_date: date,
        end_date: date,
        exchange: str = "NYSE"
    ) -> List[Dict]:
        """Get all holidays in date range
        
        Args:
            session: Database session
            start_date: Start date
            end_date: End date
            exchange: Exchange identifier
            
        Returns:
            List of holiday information
        """
        holidays = TradingCalendarRepository.get_holidays_in_range(
            session, start_date, end_date, exchange
        )
        return [
            {
                'date': h.date,
                'holiday_name': h.holiday_name,
                'is_closed': h.is_closed,
                'early_close_time': h.early_close_time,
                'notes': h.notes
            }
            for h in holidays
        ]
    
    # ==================== Backtest Window Management ====================
    
    def init_backtest_window(
        self,
        session: Session,
        exchange: Optional[str] = None
    ) -> None:
        """Initialize backtest window from session config dates.
        
        Uses start_date and end_date from BacktestConfig.
        
        Args:
            session: Database session
            exchange: Exchange group identifier (uses system default if None)
        """
        # Get backtest config from SystemManager
        if self._system_manager is None:
            raise ValueError("SystemManager not available")
        
        session_config = self._system_manager.session_config
        if session_config is None or session_config.backtest_config is None:
            raise ValueError("Backtest config not available")
        
        backtest_config = session_config.backtest_config
        
        # Parse dates from config
        self.backtest_start_date = datetime.strptime(
            backtest_config.start_date, "%Y-%m-%d"
        ).date()
        self.backtest_end_date = datetime.strptime(
            backtest_config.end_date, "%Y-%m-%d"
        ).date()
        
        logger.info(
            "Backtest window initialized from config: %s to %s",
            self.backtest_start_date,
            self.backtest_end_date,
        )
    
    def init_backtest(self, session: Session) -> None:
        """Initialize backtest window and reset the simulated clock
        
        Helper for backtest runners that want a single call to configure the
        backtest date range and starting time.
        
        Args:
            session: Database session
        """
        self.init_backtest_window(session)
        self.reset_backtest_clock(session)
    
    def reset_backtest_clock(self, session: Session) -> None:
        """Reset simulated time to the start of the backtest window
        
        Sets the backtest clock to backtest_start_date at regular market
        open time in the canonical trading timezone (ET).
        
        Args:
            session: Database session
            
        Raises:
            ValueError: If backtest_start_date not set
        """
        if not self.backtest_start_date:
            raise ValueError(
                "backtest_start_date is not set. Call init_backtest_window() first."
            )
        
        # Get market open time and timezone
        market_config = self._market_configs.get(("NYSE", "EQUITY"))
        if market_config:
            open_time = market_config.regular_open
            market_tz = ZoneInfo(market_config.timezone)
        else:
            open_time = time(9, 30)  # Default NYSE open
            market_tz = ZoneInfo("America/New_York")
        
        # Create datetime in market timezone, then convert to UTC naive for storage
        start_dt_local = datetime.combine(self.backtest_start_date, open_time)
        start_dt_aware = start_dt_local.replace(tzinfo=market_tz)
        self._backtest_time = start_dt_aware.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        
        logger.info(f"Backtest clock reset to: {start_dt_local} {market_tz} (stored as UTC naive)")
    
    
    def get_exchange_group(self, exchange: Optional[str] = None) -> str:
        """Get the exchange group for an exchange
        
        Maps individual exchange codes to their exchange groups for holiday imports.
        
        Args:
            exchange: Exchange code (uses system default if None)
            
        Returns:
            Exchange group name (e.g., "US_EQUITY" for NYSE/NASDAQ)
            
        Examples:
            >>> time_mgr.get_exchange_group("NYSE")
            'US_EQUITY'
            >>> time_mgr.get_exchange_group("LSE")
            'LSE'
        """
        from app.managers.time_manager.exchange_groups import get_group_for_exchange
        
        if exchange is None:
            exchange = self.default_exchange_group
        
        return get_group_for_exchange(exchange)
    
    def get_current_exchange_group(self) -> str:
        """Get the exchange group for the current session
        
        Returns the exchange group from system manager configuration.
        Used for data storage, symbol mapping, and holiday management.
        
        Returns:
            Exchange group name (e.g., "US_EQUITY", "LSE", "TSE")
            
        Examples:
            >>> time_mgr.get_current_exchange_group()
            'US_EQUITY'  # From system manager config
        """
        return self.default_exchange_group
    
    def get_session_exchanges(self) -> List[str]:
        """Get all exchanges in the current exchange group
        
        Returns all individual exchanges that are part of the current
        exchange group (from MarketHours database).
        
        Returns:
            List of exchange codes (e.g., ['NYSE', 'NASDAQ', 'AMEX', 'ARCA'])
            
        Examples:
            >>> time_mgr.get_session_exchanges()
            ['NYSE', 'NASDAQ', 'AMEX', 'ARCA']  # For US_EQUITY group
        """
        config = self.get_market_config()
        if config and hasattr(config, 'exchanges'):
            # MarketHoursConfig from DB might have exchanges list
            from app.models.database import SessionLocal
            from app.models.trading_calendar import MarketHours as MarketHoursDB
            
            with SessionLocal() as session:
                market_hours = session.query(MarketHoursDB).filter(
                    MarketHoursDB.exchange_group == self.default_exchange_group,
                    MarketHoursDB.asset_class == self.default_asset_class
                ).first()
                
                if market_hours:
                    return market_hours.get_exchanges_list()
        
        # Fallback to exchange_group name itself
        return [self.default_exchange_group]
    
    def set_backtest_window(
        self,
        session: Session,
        start_date: date,
        end_date: Optional[date] = None,
        exchange: str = "NYSE"
    ) -> None:
        """Override the backtest window start/end dates and reset the clock
        
        Args:
            session: Database session
            start_date: Backtest start date
            end_date: Backtest end date (if None, uses existing or calculates)
            exchange: Exchange identifier
            
        Raises:
            ValueError: If start_date > end_date
        """
        # Determine effective end date
        if end_date:
            effective_end = end_date
        elif self.backtest_end_date and self.backtest_end_date > start_date:
            effective_end = self.backtest_end_date
        else:
            # Default to yesterday
            effective_end = date.today() - timedelta(days=1)
        
        if start_date > effective_end:
            raise ValueError("backtest start_date cannot be after end_date")
        
        self.backtest_start_date = start_date
        self.backtest_end_date = effective_end
        
        # Reset clock to new start
        self.reset_backtest_clock(session)
        
        logger.info(
            "Backtest window set: %s to %s",
            self.backtest_start_date,
            self.backtest_end_date
        )
    
    def advance_to_market_open(
        self,
        session: Session,
        exchange: Optional[str] = None,
        asset_class: Optional[str] = None,
        include_extended: bool = False
    ) -> datetime:
        """Advance backtest time to next market opening time
        
        Advances to the next trading day at market open (regular or extended).
        Skips weekends and holidays automatically.
        
        Uses system defaults if not specified.
        
        Args:
            session: Database session
            exchange: Exchange group identifier (uses system default if None)
            asset_class: Asset class (uses system default if None)
            include_extended: If True, advance to pre-market open; if False, regular open
            
        Returns:
            New backtest time
            
        Raises:
            ValueError: If not in backtest mode or window not initialized
        """
        # Use system defaults if not specified
        if exchange is None:
            exchange = self.default_exchange_group
        if asset_class is None:
            asset_class = self.default_asset_class
        if self._system_manager is None:
            raise ValueError("SystemManager not available")
        
        if self._system_manager.mode.value != "backtest":
            raise ValueError("advance_to_market_open only works in backtest mode")
        
        if self._backtest_time is None:
            raise ValueError("Backtest time not initialized. Call init_backtest() first.")
        
        # Get market configuration
        market_config = self._market_configs.get((exchange, asset_class))
        if not market_config:
            raise ValueError(f"No market configuration for {exchange} {asset_class}")
        
        # Determine target open time
        if include_extended and market_config.pre_market_open:
            open_time = market_config.pre_market_open
        else:
            open_time = market_config.regular_open
        
        # Convert current backtest time (UTC naive) to market timezone to get correct date
        current_time_utc = self._backtest_time.replace(tzinfo=ZoneInfo("UTC"))
        current_time_local = current_time_utc.astimezone(ZoneInfo(market_config.timezone))
        current_date = current_time_local.date()
        current_time_only = current_time_local.time()
        
        # If current time is before market open today, use today
        if current_time_only < open_time:
            candidate_date = current_date
        else:
            # Otherwise, start from next day
            candidate_date = current_date + timedelta(days=1)
        
        # Find next trading day
        max_attempts = 100  # Prevent infinite loop (allow checking ~3 months)
        for attempt in range(max_attempts):
            # Check if it's a weekend
            if candidate_date.weekday() >= 5:  # Saturday=5, Sunday=6
                candidate_date += timedelta(days=1)
                continue
            
            # Check if it's a holiday (if database has holiday data)
            try:
                is_holiday_result, holiday_name = self.is_holiday(session, candidate_date, exchange)
                if is_holiday_result:
                    logger.debug(f"Skipping holiday {candidate_date}: {holiday_name}")
                    candidate_date += timedelta(days=1)
                    continue
            except Exception as e:
                # If holiday check fails (e.g., no holiday data), assume not a holiday
                logger.debug(f"Holiday check failed for {candidate_date}: {e}")
            
            # Found a trading day!
            break
        else:
            # Loop completed without finding a trading day
            raise ValueError(f"Could not find next trading day within {max_attempts} days")
        
        # Set backtest time to market open on this date
        # Create in exchange timezone, then convert to UTC naive for storage
        new_time_local = datetime.combine(candidate_date, open_time)
        new_time_aware = new_time_local.replace(tzinfo=ZoneInfo(market_config.timezone))
        self._backtest_time = new_time_aware.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        
        logger.info(
            "Advanced backtest time to %s market open: %s %s (stored as UTC naive)",
            "extended" if include_extended else "regular",
            new_time_local,
            market_config.timezone
        )
        
        # Return timezone-aware datetime (for consistency with get_current_time)
        return new_time_aware
    
    def reset_to_backtest_start(
        self,
        session: Session,
        include_extended: bool = False
    ) -> datetime:
        """Reset backtest time to the start of the backtest window
        
        Args:
            session: Database session
            include_extended: If True, set to pre-market open; if False, regular open
            
        Returns:
            New backtest time
            
        Raises:
            ValueError: If backtest window not initialized
        """
        if not self.backtest_start_date:
            raise ValueError(
                "Backtest window not initialized. Call init_backtest_window() first."
            )
        
        # Get market open time
        market_config = self._market_configs.get(("NYSE", "EQUITY"))
        if market_config:
            if include_extended and market_config.pre_market_open:
                open_time = market_config.pre_market_open
            else:
                open_time = market_config.regular_open
        else:
            open_time = time(9, 30)  # Default NYSE open
        
        # Set backtest time to start date at market open
        # Create in exchange timezone, then convert to UTC naive for storage
        start_dt_local = datetime.combine(self.backtest_start_date, open_time)
        start_dt_aware = start_dt_local.replace(tzinfo=ZoneInfo(market_config.timezone))
        self._backtest_time = start_dt_aware.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        
        logger.info(f"Reset backtest time to window start: {start_dt_local} {market_config.timezone} (stored as UTC naive)")
        
        # Return timezone-aware datetime (for consistency with get_current_time)
        return start_dt_aware
    
    # ==================== Cache Management (Phase 2.2) ====================
    
    def invalidate_cache(self) -> None:
        """Invalidate all caches (call when holiday data is updated)
        
        NEW in Phase 2.2: Clear all caching data structures.
        
        Use cases:
        - After importing new holiday data
        - After system configuration changes
        - When switching trading sessions/modes
        
        Note: Market config cache is NOT cleared (loaded from database at init)
        """
        # Clear last-query cache
        self._last_query_cache = {
            'key': None,
            'result': None
        }
        
        # Reset statistics
        self._cache_hits = 0
        self._cache_misses = 0
        
        logger.info("TimeManager cache invalidated")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics
        
        NEW in Phase 2.2: Returns cache hit/miss statistics for monitoring.
        
        Returns:
            Dictionary with cache statistics:
            - cache_hits: Number of cache hits
            - cache_misses: Number of cache misses
            - hit_rate: Cache hit rate (0.0 to 1.0)
            - total_queries: Total queries made
        """
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0.0
        
        return {
            'cache_hits': self._cache_hits,
            'cache_misses': self._cache_misses,
            'hit_rate': hit_rate,
            'total_queries': total
        }


def get_time_manager(system_manager=None) -> TimeManager:
    """Get or create the global TimeManager singleton instance
    
    Args:
        system_manager: Reference to SystemManager (required for production use)
    
    Returns:
        The singleton TimeManager instance
    """
    global _time_manager_instance
    if _time_manager_instance is None:
        _time_manager_instance = TimeManager(system_manager=system_manager)
        logger.info("TimeManager singleton instance created")
    return _time_manager_instance


def reset_time_manager():
    """Reset the singleton instance (for testing only)"""
    global _time_manager_instance
    _time_manager_instance = None
