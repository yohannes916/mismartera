"""DataManager Public API

Single source of truth for all datasets.
All CLI and API routes must use this interface.
"""
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from typing import List, Optional, AsyncIterator, Dict, Any
from types import SimpleNamespace
import asyncio
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import BarData, TickData
from app.models.trading_calendar import TradingHoliday, TradingHours
from app.repositories.market_data_repository import MarketDataRepository
from app.managers.data_manager.repositories.quote_repo import QuoteRepository
from app.managers.data_manager.repositories.holiday_repo import HolidayRepository
from app.managers.data_manager.config import DataManagerConfig
from app.managers.data_manager.integrations.holiday_import_service import (
    holiday_import_service,
)
from app.managers.data_manager.time_provider import get_time_provider
from app.managers.data_manager.backtest_stream_coordinator import (
    get_coordinator,
    StreamType,
)
from app.config import settings
from app.logger import logger


@dataclass
class DayTradingHours:
    """Concrete trading hours for a specific date."""

    open_time: time
    close_time: time


@dataclass
class CurrentDayMarketInfo:
    """Aggregate market information for the current date.

    This is a convenience DTO used by higher layers (CLI, API routes) so they
    don't need to call multiple DataManager methods to understand today's
    market status.
    """

    now: datetime
    date: date
    is_weekend: bool
    is_holiday: bool
    holiday_name: Optional[str]
    is_early_close: bool
    early_close_time: Optional[time]
    trading_hours: Optional[DayTradingHours]
    is_market_open: bool


class DataManager:
    """
    📊 DataManager - Single source of truth for all data
    
    Provides:
    - Current time (live or backtest)
    - Trading hours and market status
    - 1-minute bar data
    - Tick data
    - Holiday information
    - Data import capabilities
    
    Supports both Real and Backtest modes.
    """
    
    def __init__(
        self,
        mode: Optional[str] = None,
        config: Optional[DataManagerConfig] = None,
        system_manager: Optional[object] = None,
    ):
        """Initialize DataManager.

        Args:
            mode: Optional override for operating mode ("live" or "backtest").
            config: Optional DataManagerConfig. If not provided, defaults are
                loaded from global settings.
            system_manager: Optional reference to SystemManager for inter-manager
                communication. If provided, enables access to other managers.
        """
        # Reference to SystemManager for accessing other managers
        self.system_manager = system_manager
        
        self.config = config or DataManagerConfig()

        # Selected data API provider name (e.g., "alpaca", "schwab")
        self.data_api: str = self.config.data_api

        # Connection status flag for the active data provider
        self._data_provider_connected: bool = False

        # Backtest configuration (expressed in trading days)
        self.backtest_days: int = self.config.backtest_days
        self.backtest_start_date: Optional[date] = None
        self.backtest_end_date: Optional[date] = None

        # Default market hours (PST). These may be refined per-day using
        # the trading calendar/holiday repository when needed.
        self.opening_time: time = time(6, 30)   # 6:30am PST
        self.closing_time: time = time(13, 0)   # 1:00pm PST

        # TimeProvider for live vs backtest clock. Uses singleton instance
        # shared across all components (DataManager, BacktestStreamCoordinator, etc.)
        # Pass system_manager so TimeProvider can query mode from single source of truth
        self.time_provider = get_time_provider(system_manager=self.system_manager)

        # In-memory registries for live/backtest data streams
        self._bar_stream_cancel_tokens: Dict[str, asyncio.Event] = {}
        self._tick_stream_cancel_tokens: Dict[str, asyncio.Event] = {}
        self._quote_stream_cancel_tokens: Dict[str, asyncio.Event] = {}
        
        # Holiday cache for synchronous market status checks
        # Key: date, Value: (is_closed, early_close_time)
        self._holiday_cache: Dict[date, tuple[bool, Optional[time]]] = {}

        logger.info(
            f"DataManager initialized using data_api={self.data_api}"
        )

    # ==================== CONFIGURATION & PROVIDERS ====================

    async def select_data_api(self, api: str) -> bool:
        """Select the active data API provider and auto-connect if needed.

        Args:
            api: Provider name (e.g., "alpaca", "schwab").

        Returns:
            True if provider is connected successfully, False otherwise.
        """
        provider = api.lower()

        if provider == self.data_api and self._data_provider_connected:
            logger.info(f"Data provider {provider} already selected and connected")
            return True

        self.data_api = provider
        self._data_provider_connected = False

        # Support both Alpaca and Schwab as live providers
        if provider == "alpaca":
            from app.integrations.alpaca_client import alpaca_client
            logger.info("Selecting Alpaca as data provider and validating connection")
            ok = await alpaca_client.validate_connection()
            self._data_provider_connected = ok
            return ok
        elif provider == "schwab":
            from app.integrations.schwab_client import schwab_client
            logger.info("Selecting Schwab as data provider and validating connection")
            ok = await schwab_client.validate_connection()
            self._data_provider_connected = ok
            return ok

        logger.warning(f"Data provider '{provider}' is not yet implemented")
        return False
    
    # ==================== TIME & STATUS ====================
    
    def check_market_open(self, timestamp: Optional[datetime] = None) -> bool:
        """Check if market is currently open (synchronous with holiday caching).
        
        This performs a complete market status check including:
        - Trading hours (9:30 AM - 4:00 PM ET)
        - Weekends
        - Holidays (cached from database)
        - Early close times (cached from database)
        
        Holiday lookups are cached by date. The cache is populated on first
        access and reused for subsequent checks on the same date. This provides
        database accuracy with synchronous performance.
        
        The first call for a new date will query the database (fast, holiday table
        is small). Subsequent calls for the same date use the cache.
        
        Args:
            timestamp: Time to check (defaults to current time from TimeProvider)
            
        Returns:
            True if market is open, False otherwise
        """
        import asyncio
        from app.models.trading_calendar import TradingHours
        from app.repositories.trading_calendar_repository import TradingCalendarRepository
        from app.models.database import AsyncSessionLocal
        
        check_time = timestamp or self.get_current_time()
        check_date = check_time.date()
        
        # Closed on weekends
        if TradingHours.is_weekend(check_time):
            return False
        
        # Check holiday cache, fetch from DB if not cached
        if check_date not in self._holiday_cache:
            # Synchronous wrapper around async DB query using thread pool
            import concurrent.futures
            
            async def fetch_holiday():
                async with AsyncSessionLocal() as session:
                    return await TradingCalendarRepository.get_holiday(session, check_date)
            
            def run_async_in_thread():
                """Run async code in a new thread with its own event loop."""
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(fetch_holiday())
                finally:
                    loop.close()
            
            # Execute in thread pool to avoid "event loop already running" error
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async_in_thread)
                holiday = future.result(timeout=5.0)  # 5 second timeout
            
            if holiday:
                # Cache: (is_closed, early_close_time)
                self._holiday_cache[check_date] = (holiday.is_closed, holiday.early_close_time)
            else:
                # No holiday for this date
                self._holiday_cache[check_date] = (False, None)
        
        # Use cached holiday data
        is_closed, early_close_time = self._holiday_cache[check_date]
        
        # Full-day holiday
        if is_closed:
            return False
        
        # Determine open/close times for the day
        open_time = time.fromisoformat(TradingHours.MARKET_OPEN)
        close_time = early_close_time if early_close_time else time.fromisoformat(TradingHours.MARKET_CLOSE)
        
        # Check if current time is within trading hours
        current_time_of_day = check_time.time()
        return open_time <= current_time_of_day <= close_time
    
    def clear_holiday_cache(self) -> None:
        """Clear the holiday cache.
        
        This forces the next call to check_market_open() to re-fetch
        holiday data from the database. Useful after holidays are updated
        or for testing purposes.
        """
        self._holiday_cache.clear()
        logger.info("Holiday cache cleared")
    
    async def stop_all_streams(self) -> None:
        """Stop all active data streams and the coordinator worker.
        
        This method stops:
        - All bar streams
        - All tick streams  
        - All quote streams
        - The BacktestStreamCoordinator worker
        - Clears all session data (symbols, bars, metrics)
        
        This is useful when you need to:
        - Stop all streaming before exiting
        - Clean up streams before starting new ones
        - Manually stop streams before resetting backtest time
        
        The method is automatically called by time modification functions like
        reset_backtest_clock() and init_backtest(), but can also be called
        directly by users when needed.
        """
        import traceback
        logger.warning(f"⚠ stop_all_streams() called from:")
        logger.warning("".join(traceback.format_stack()[-4:-1]))
        
        # Stop all bar streams
        await self.stop_bars_stream()
        
        # Stop all tick streams
        await self.stop_ticks_stream()
        
        # Stop all quote streams
        await self.stop_quotes_stream()
        
        # Stop the BacktestStreamCoordinator worker
        coordinator = get_coordinator(self.system_manager)
        coordinator.stop_worker()
        
        logger.info("All active streams stopped")
        
        # Clear session data
        from app.managers.data_manager.session_data import get_session_data
        session_data = get_session_data()
        await session_data.clear()
        
        logger.success("✓ All streams stopped and session data cleared")
    
    def get_current_time(self) -> datetime:
        """Get current date/time.

        In backtest mode, this returns the simulated clock maintained
        by :class:`TimeProvider`. In live mode, it returns system time.
        """
        return self.time_provider.get_current_time()
    
    def get_execution_manager(self) -> object:
        """Get ExecutionManager via SystemManager.
        
        Returns:
            ExecutionManager instance if SystemManager is available, None otherwise
        """
        if self.system_manager is None:
            logger.warning("SystemManager not available, cannot access ExecutionManager")
            return None
        return self.system_manager.get_execution_manager()
    
    def get_analysis_engine(self) -> object:
        """Get AnalysisEngine via SystemManager.
        
        Returns:
            AnalysisEngine instance if SystemManager is available, None otherwise
        """
        if self.system_manager is None:
            logger.warning("SystemManager not available, cannot access AnalysisEngine")
            return None
        return self.system_manager.get_analysis_engine()
    
    @property
    def session_data(self):
        """Get the global session_data singleton.
        
        Returns:
            SessionData instance
        """
        from app.managers.data_manager.session_data import get_session_data
        return get_session_data()
    
    async def get_session_metrics(self, symbol: str) -> Dict[str, any]:
        """Get current session metrics for a symbol.
        
        Convenience method that delegates to session_data.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with session metrics
        """
        return await self.session_data.get_session_metrics(symbol)
    
    def is_regular_trading_hours(self, dt: datetime) -> bool:
        """Check if a datetime is within regular trading hours.
        
        Regular trading hours are 9:30 AM - 4:00 PM ET (market time).
        Excludes pre-market and after-hours sessions.
        
        Args:
            dt: Datetime to check (should be in ET/market timezone)
            
        Returns:
            True if within regular trading hours, False otherwise
        """
        # Extract time component
        t = dt.time()
        
        # Regular market hours: 09:30:00 to 16:00:00 (ET)
        market_open = time(9, 30, 0)
        market_close = time(16, 0, 0)
        
        return market_open <= t < market_close

    async def init_backtest_window(self, session: AsyncSession) -> None:
        """Compute and cache the backtest window based on backtest_days.

        The window is defined in trading days (excluding weekends/holidays),
        counting backwards from the most recent trading day.
        
        NOTE: This stops all active streams before modifying the backtest window.
        """
        # Stop all streams before modifying backtest window
        await self.stop_all_streams()
        
        # Determine the most recent trading day (walking backwards from today).
        current = datetime.utcnow().date()
        trading_days: list[date] = []

        while len(trading_days) < self.backtest_days:
            current_dt = datetime.combine(current, time(0, 0))
            if await HolidayRepository.is_trading_day(session, current_dt):
                trading_days.append(current)
            current -= timedelta(days=1)

        trading_days.sort()
        self.backtest_start_date = trading_days[0]
        self.backtest_end_date = trading_days[-1]

        logger.info(
            "Backtest window initialized: %s trading days from %s to %s",
            self.backtest_days,
            self.backtest_start_date,
            self.backtest_end_date,
        )

    async def init_backtest(self, session: AsyncSession) -> None:
        """Initialize backtest window and reset the simulated clock.

        Helper for backtest runners that want a single call to configure the
        backtest date range and starting time.
        
        NOTE: Both init_backtest_window() and reset_backtest_clock() 
        automatically stop all active streams before making changes.
        """
        await self.init_backtest_window(session)
        await self.reset_backtest_clock()

    async def reset_backtest_clock(self) -> None:
        """Reset simulated time to the start of the backtest window.

        Sets the TimeProvider's backtest clock to ``backtest_start_date`` at
        the regular market open time in the canonical trading timezone (ET).
        The resulting naive datetime is interpreted as Eastern Time by
        DataManager and is converted to the local display timezone (e.g. PST)
        by callers such as the CLI.
        
        NOTE: This method only RESETS time to the start. Time advancement 
        forward during streaming is handled exclusively by 
        BacktestStreamCoordinator as data flows through it.
        
        IMPORTANT: This stops all active streams before resetting time to
        prevent inconsistencies.
        """
        if not self.backtest_start_date:
            raise ValueError("backtest_start_date is not set. Call init_backtest_window() first.")

        # Stop all streams before resetting time
        await self.stop_all_streams()

        # Use TradingHours.MARKET_OPEN (ET) as the canonical open time
        open_et = time.fromisoformat(TradingHours.MARKET_OPEN)
        start_dt = datetime.combine(self.backtest_start_date, open_et)
        self.time_provider.set_backtest_time(start_dt)
        
        logger.info(f"Backtest clock reset to: {start_dt}")
    
    async def set_backtest_window(
        self,
        session: AsyncSession,
        start_date: date,
        end_date: Optional[date] = None,
    ) -> None:
        """Override the backtest window start/end dates and reset the clock.

        If ``end_date`` is not provided, the existing ``backtest_end_date`` is
        preserved. If that existing end date is ``None`` or is less than or
        equal to ``start_date``, the end date defaults to the last trading day
        based on real-+world time (UTC today), using the trading calendar.
        """
        # Determine effective end date
        if end_date is not None:
            effective_end = end_date
        else:
            # Compute the last completed trading session based on current
            # US/Eastern time, ignoring any previously stored
            # ``backtest_end_date``. This ensures the implicit end-date always
            # reflects "as of now".
            now_et = datetime.now(ZoneInfo("America/New_York"))
            today_et = now_et.date()
            # The last fully completed session is conservatively assumed to be
            # the previous calendar day in Eastern time.
            last_session_candidate = today_et - timedelta(days=1)

            # Walk backwards from the last-session candidate to find the most
            # recent trading day in the calendar.
            current = last_session_candidate
            while True:
                current_dt = datetime.combine(current, time(0, 0))
                if await HolidayRepository.is_trading_day(session, current_dt):
                    effective_end = current
                    break
                current -= timedelta(days=1)

        if start_date > effective_end:
            raise ValueError("backtest start_date cannot be after end_date")

        self.backtest_start_date = start_date
        self.backtest_end_date = effective_end

        # Move the simulated clock to the new start of window
        # (reset_backtest_clock will stop all streams)
        await self.reset_backtest_clock()

    async def set_backtest_speed(self, speed: float) -> None:
        """Set the global backtest speed multiplier.

        This updates the single source of truth on the Settings object. Valid
        values are:

        - 0.0: run backtests as fast as possible (no pacing)
        - 1.0: realtime speed (pace according to actual timestamps)
        - 2.0: 2x speed (twice as fast as realtime)
        - 0.5: half speed (slower than realtime)
        
        Args:
            speed: Speed multiplier (0 = max, 1.0 = realtime, >1 = faster, <1 = slower)
        """
        if speed < 0:
            raise ValueError("DATA_MANAGER_BACKTEST_SPEED must be >= 0")

        settings.DATA_MANAGER_BACKTEST_SPEED = speed
    
    async def get_trading_hours(
        self,
        session: AsyncSession,
        day: date,
    ) -> Optional[DayTradingHours]:
        """Get concrete trading hours for a specific date.

        Returns None if the market is fully closed that day.
        """
        # Weekend or full-day holiday -> closed
        dt = datetime.combine(day, time(0, 0))
        if TradingHours.is_weekend(dt):
            return None

        holiday = await HolidayRepository.get_holiday(session, day)
        if holiday and holiday.is_closed:
            return None

        # Default ET trading hours, override close with any ET early-close
        # time configured for this specific date.
        open_time = time.fromisoformat(TradingHours.MARKET_OPEN)

        if holiday and holiday.early_close_time:
            close_time = holiday.early_close_time
        else:
            close_time = time.fromisoformat(TradingHours.MARKET_CLOSE)

        return DayTradingHours(open_time=open_time, close_time=close_time)

    async def is_holiday(
        self,
        session: AsyncSession,
        day: date,
    ) -> tuple[bool, Optional[str]]:
        """Return whether the given day is a holiday and its name if present.

        A day is considered a holiday if there is any entry in the trading
        calendar for that date, regardless of whether it is a full-day
        closure or an early-close day.
        """
        holiday = await HolidayRepository.get_holiday(session, day)
        if not holiday:
            return False, None

        return True, holiday.holiday_name

    async def is_early_day(
        self,
        session: AsyncSession,
        day: date,
    ) -> tuple[bool, Optional[time]]:
        """Return whether the given day is an early-close trading day.

        An early-close day is one where there is a holiday entry for the date
        that is not marked as fully closed and has an early_close_time.
        """
        holiday = await HolidayRepository.get_holiday(session, day)
        if not holiday or holiday.is_closed or not holiday.early_close_time:
            return False, None

        # Return the ET early-close time directly; callers treat all times as
        # Eastern and are responsible for any display conversions.
        return True, holiday.early_close_time

    async def get_holidays(
        self,
        session: AsyncSession,
        start_date: date,
        end_date: date,
    ) -> List[TradingHoliday]:
        """Get holidays in a date range from the trading calendar."""
        return await HolidayRepository.get_holidays_in_range(
            session,
            start_date,
            end_date,
        )

    async def get_current_day_market_info(
        self,
        session: AsyncSession,
    ) -> CurrentDayMarketInfo:
        """Return aggregate market info for the current date.

        This wires together current time, trading hours, holiday meta, and the
        market-open flag for the date corresponding to the DataManager's
        current clock (live or backtest).
        """
        now = self.get_current_time()
        today = now.date()

        dt_midnight = datetime.combine(today, time(0, 0))
        is_weekend = TradingHours.is_weekend(dt_midnight)

        holiday = await HolidayRepository.get_holiday(session, today)
        is_holiday_flag = holiday is not None
        holiday_name = holiday.holiday_name if holiday else None

        is_early_close = False
        early_close_time: Optional[time] = None
        if holiday and not holiday.is_closed and holiday.early_close_time:
            is_early_close = True
            early_close_time = holiday.early_close_time

        trading_hours = await self.get_trading_hours(session, today)
        is_open = self.check_market_open(now)

        return CurrentDayMarketInfo(
            now=now,
            date=today,
            is_weekend=is_weekend,
            is_holiday=is_holiday_flag,
            holiday_name=holiday_name,
            is_early_close=is_early_close,
            early_close_time=early_close_time,
            trading_hours=trading_hours,
            is_market_open=is_open,
        )
    
    async def import_holidays_from_file(
        self,
        session: AsyncSession,
        file_path: str,
    ) -> Dict[str, Any]:
        """Import holiday schedule from CSV file via HolidayImportService.

        Args:
            session: Database session
            file_path: Path to holiday CSV file

        Returns:
            Import result dictionary
        """
        return await holiday_import_service.import_holidays_to_database(
            session=session,
            file_path=file_path,
        )
    
    async def delete_holidays_for_year(
        self,
        session: AsyncSession,
        year: int,
    ) -> int:
        """Delete all holidays for a specific year.
        
        Args:
            session: Database session
            year: Year to delete holidays for (e.g., 2025)
            
        Returns:
            Number of holidays deleted
        """
        logger.warning(f"Deleting holidays for year {year}")
        return await HolidayRepository.delete_holidays_for_year(session, year)
    
    # ==================== MARKET DATA (BARS) ====================
    
    async def get_bars(
        self,
        session: AsyncSession,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1m"
    ) -> List[BarData]:
        """
        Get historical bar data.
        
        Args:
            session: Database session
            symbol: Stock symbol
            start: Start datetime
            end: End datetime
            interval: Time interval (default: 1m)
            
        Returns:
            List of BarData objects
        """
        bars = await MarketDataRepository.get_bars_by_symbol(
            session,
            symbol=symbol,
            start_date=start,
            end_date=end,
            interval=interval
        )
        
        # Convert to BarData objects
        bar_data_list = [
            BarData(
                symbol=bar.symbol,
                timestamp=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume
            )
            for bar in bars
        ]
        
        return bar_data_list
    
    async def get_latest_bar(
        self,
        session: AsyncSession,
        symbol: str,
        interval: str = "1m"
    ) -> Optional[BarData]:
        """
        Get the most recent bar for a symbol.
        
        Args:
            session: Database session
            symbol: Stock symbol
            interval: Time interval (default: 1m)
            
        Returns:
            BarData object or None
        """
        now = self.get_current_time()
        today = now.date()
        day_start = datetime.combine(today, time(0, 0))

        mode = self.system_manager.mode.value

        # In live mode, fetch directly from the live data API (no DB).
        if mode == "live":
            if interval != "1m":
                raise NotImplementedError("Real-time latest_bar currently supports only 1m interval")

            from app.managers.data_manager.integrations.alpaca_data import fetch_1m_bars

            bars = await fetch_1m_bars(symbol=symbol, start=day_start, end=now)
            if not bars:
                return None

            last = bars[-1]
            return BarData(
                symbol=last["symbol"],
                timestamp=last["timestamp"],
                open=last["open"],
                high=last["high"],
                low=last["low"],
                close=last["close"],
                volume=last["volume"],
            )

        # Backtest mode: read from local DB up to current simulated time.
        bars = await MarketDataRepository.get_bars_by_symbol(
            session,
            symbol=symbol,
            start_date=day_start,
            end_date=now,
            interval=interval,
        )

        if not bars:
            return None

        bar = bars[-1]
        return BarData(
            symbol=bar.symbol,
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
    
    async def start_bar_streams(
        self,
        session: AsyncSession,
        symbols: List[str],
        interval: str = "1m",
    ) -> int:
        """Start bar streams without consuming them (for system startup).
        
        This method blocks while fetching current day data, registers symbols,
        and starts streaming. Returns immediately after setup - streams run in
        coordinator worker thread.
        
        Args:
            session: Database session
            symbols: List of symbols to stream
            interval: Time interval (default: 1m)
            
        Returns:
            Number of streams successfully started
        """
        from app.managers.data_manager.session_data import get_session_data
        from app.managers.data_manager.backtest_stream_coordinator import get_coordinator, StreamType
        from app.repositories.market_data_repository import MarketDataRepository
        from app.models.trading_calendar import TradingHours
        
        if not symbols:
            return 0
        
        session_data = get_session_data()
        symbols = [s.upper() for s in symbols]
        
        mode = self.system_manager.mode.value
        if mode != "backtest":
            logger.warning("start_bar_streams() only works in backtest mode")
            return 0
        
        coordinator = get_coordinator(self.system_manager)
        coordinator.start_worker()
        
        # VALIDATION: Only 1m bars can be streamed
        # Derived intervals (5m, 15m, etc.) are computed by the upkeep thread
        if interval != "1m":
            raise ValueError(
                f"Stream coordinator only supports 1m bars (requested: {interval}). "
                f"Derived intervals (5m, 15m, etc.) are automatically computed by the data upkeep thread. "
                f"Check your session configuration."
            )
        
        now = self.get_current_time()
        current_date = now.date()
        
        # Determine end time: CURRENT DAY ONLY at market close
        open_et = time.fromisoformat(TradingHours.MARKET_OPEN)
        close_et = time.fromisoformat(TradingHours.MARKET_CLOSE)
        start_time = datetime.combine(current_date, open_et)
        end_time = datetime.combine(current_date, close_et)
        
        streams_started = 0
        
        for symbol in symbols:
            # Check for duplicates
            if session_data.is_stream_active(symbol, "bars"):
                logger.warning(f"Bar stream for {symbol} already active")
                continue
            
            if coordinator.is_stream_active(symbol, StreamType.BAR):
                logger.warning(f"Bar stream for {symbol} already active in coordinator")
                continue
            
            # Register with session_data
            await session_data.register_symbol(symbol)
            await session_data.mark_stream_active(symbol, "bars")
            
            # Register with coordinator
            success, input_queue = coordinator.register_stream(symbol, StreamType.BAR)
            if not success:
                logger.error(f"Failed to register bar stream for {symbol}")
                await session_data.mark_stream_inactive(symbol, "bars")
                continue
            
            # BLOCK and fetch current day
            logger.info(f"Fetching bars for {symbol} on {current_date}...")
            bars = await MarketDataRepository.get_bars_by_symbol(
                session,
                symbol=symbol,
                start_date=start_time,
                end_date=end_time,
                interval=interval,
            )
            
            if not bars:
                logger.warning(f"No bars found for {symbol} on {current_date}")
                await session_data.mark_stream_inactive(symbol, "bars")
                continue
            
            logger.info(f"Fetched {len(bars)} bars for {symbol} on {current_date}")
            
            # Add bars to session_data
            logger.info(f"Adding {len(bars)} bars to session_data for {symbol}...")
            for idx, bar in enumerate(bars):
                await session_data.add_bar(symbol, BarData(
                    symbol=bar.symbol,
                    timestamp=bar.timestamp,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                ))
            
            # Verify bars were added
            symbol_data = await session_data.get_symbol_data(symbol)
            if symbol_data:
                bar_count = len(symbol_data.bars_1m)
                logger.info(f"✓ Added {bar_count} bars to session_data for {symbol}")
            else:
                logger.error(f"✗ Symbol data not found for {symbol} after adding bars!")
            
            # Feed to coordinator
            async def bar_iterator():
                for bar in bars:
                    yield BarData(
                        symbol=bar.symbol,
                        timestamp=bar.timestamp,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                    )
            
            await coordinator.feed_stream(symbol, StreamType.BAR, bar_iterator())
            logger.success(f"✓ Started bar stream for {symbol} ({len(bars)} bars)")
            streams_started += 1
        
        return streams_started
    
    async def stream_bars(
        self,
        session: AsyncSession,
        symbols: List[str],
        interval: str = "1m",
        stream_id: Optional[str] = None,
    ) -> AsyncIterator[BarData]:
        """Stream real-time or backtest bar data for one or more symbols.

        In backtest mode, this fetches ONLY the current market day from database,
        then yields bars chronologically. The upkeep thread handles prefetching
        future dates.

        In live mode, this connects to the configured live data provider.

        Args:
            session: Database session
            symbols: List of symbols to stream
            interval: Time interval (default: 1m)
            stream_id: Optional external stream identifier

        Yields:
            BarData objects.
        """
        if not symbols:
            return

        # Get session_data for stream tracking
        from app.managers.data_manager.session_data import get_session_data
        session_data = get_session_data()

        # Normalize to upper-case symbols
        symbols = [s.upper() for s in symbols]

        # Allocate or reuse a cancel token for this stream
        if stream_id is None:
            stream_id = uuid4().hex

        cancel_event = self._bar_stream_cancel_tokens.get(stream_id)
        if cancel_event is None:
            cancel_event = asyncio.Event()
            self._bar_stream_cancel_tokens[stream_id] = cancel_event

        mode = self.system_manager.mode.value

        if mode == "backtest":
            # Backtest mode: fetch current market day only, upkeep thread handles future
            coordinator = get_coordinator(self.system_manager)
            
            # Start worker thread if not already running
            coordinator.start_worker()
            
            now = self.get_current_time()
            current_date = now.date()
            
            # Determine end time: CURRENT DAY ONLY at market close
            open_et = time.fromisoformat(TradingHours.MARKET_OPEN)
            close_et = time.fromisoformat(TradingHours.MARKET_CLOSE)
            start_time = datetime.combine(current_date, open_et)
            end_time = datetime.combine(current_date, close_et)
            
            # Register and feed each symbol's stream (BLOCKS while fetching)
            for symbol in symbols:
                # 1. Check session_data first for duplicate stream
                if session_data.is_stream_active(symbol, "bars"):
                    logger.warning(f"Bar stream for {symbol} already active in session_data")
                    continue
                
                # 2. Check coordinator for duplicate stream
                if coordinator.is_stream_active(symbol, StreamType.BAR):
                    logger.warning(f"Bar stream for {symbol} already active in coordinator")
                    continue
                
                # 3. Register symbol with session_data
                await session_data.register_symbol(symbol)
                await session_data.mark_stream_active(symbol, "bars")
                
                # 4. Register stream with coordinator
                success, input_queue = coordinator.register_stream(symbol, StreamType.BAR)
                if not success:
                    logger.error(f"Failed to register bar stream for {symbol}")
                    await session_data.mark_stream_inactive(symbol, "bars")
                    continue
                
                # 5. BLOCK and fetch current day only
                logger.info(f"Fetching bars for {symbol} on {current_date}...")
                bars = await MarketDataRepository.get_bars_by_symbol(
                    session,
                    symbol=symbol,
                    start_date=start_time,
                    end_date=end_time,
                    interval=interval,
                )
                
                if not bars:
                    logger.warning(f"No bars found for {symbol} on {current_date}")
                    await session_data.mark_stream_inactive(symbol, "bars")
                    continue
                
                logger.info(f"Fetched {len(bars)} bars for {symbol} on {current_date}")
                
                # 6. Add initial bars to session_data
                for bar in bars:
                    await session_data.add_bar(symbol, BarData(
                        symbol=bar.symbol,
                        timestamp=bar.timestamp,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                    ))
                
                # 7. Feed data to coordinator
                async def bar_iterator():
                    for bar in bars:
                        if cancel_event.is_set():
                            break
                        yield BarData(
                            symbol=bar.symbol,
                            timestamp=bar.timestamp,
                            open=bar.open,
                            high=bar.high,
                            low=bar.low,
                            close=bar.close,
                            volume=bar.volume,
                        )
                
                await coordinator.feed_stream(symbol, StreamType.BAR, bar_iterator())
                logger.success(f"✓ Started bar stream for {symbol} ({len(bars)} bars)")
            
            # All symbols started, now yield from merged stream if consumer wants to iterate
            # NOTE: For system startup, we don't consume - streams run in coordinator worker thread
            async for data in coordinator.get_merged_stream():
                if cancel_event.is_set():
                    break
                
                # Update session_data with streamed bar (not initial load)
                # This catches bars added by upkeep thread
                await session_data.add_bar(data.symbol, data)
                
                yield data
            
            # Cleanup when stream ends
            for symbol in symbols:
                await session_data.mark_stream_inactive(symbol, "bars")
            self._bar_stream_cancel_tokens.pop(stream_id, None)
            return

        # Live mode: delegate to provider-specific streaming implementation.
        # To keep DataManager focused, we import the provider lazily.
        provider = self.data_api.lower()
        if provider == "alpaca":
            from app.managers.data_manager.integrations import alpaca_streams

            async for bar in alpaca_streams.stream_bars(
                symbols=symbols,
                interval=interval,
                cancel_event=cancel_event,
            ):
                yield BarData(
                    symbol=bar.symbol,
                    timestamp=bar.timestamp,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                )

            self._bar_stream_cancel_tokens.pop(stream_id, None)
            return

        raise NotImplementedError(f"Bar streaming not implemented for provider={provider}")

    async def stop_bars_stream(self, stream_id: Optional[str] = None) -> None:
        """Signal active bar stream(s) to stop via cancel tokens.

        If ``stream_id`` is provided, only that stream is cancelled.
        Otherwise, all active bar streams are signalled to stop.
        """
        if stream_id is not None:
            token = self._bar_stream_cancel_tokens.get(stream_id)
            if token is not None and not token.is_set():
                token.set()
            return

        # Cancel all active bar streams
        for token in self._bar_stream_cancel_tokens.values():
            if not token.is_set():
                token.set()

        return
    
    # ==================== TICK DATA ====================
    
    async def get_ticks(
        self,
        session: AsyncSession,
        symbol: str,
        start: datetime,
        end: datetime
    ) -> List[TickData]:
        """
        Get tick-level data.
        If not available, generates from 1-minute bars.
        
        Args:
            session: Database session
            symbol: Stock symbol
            start: Start datetime
            end: End datetime
            
        Returns:
            List of TickData objects
        """
        # For now, tick data is stored in MarketData with interval='tick'.
        bars = await MarketDataRepository.get_bars_by_symbol(
            session,
            symbol=symbol,
            start_date=start,
            end_date=end,
            interval="tick",
        )

        ticks: List[TickData] = [
            TickData(
                symbol=b.symbol,
                timestamp=b.timestamp,
                price=b.close,
                size=b.volume,
            )
            for b in bars
        ]
        return ticks

    async def get_latest_tick(
        self,
        session: AsyncSession,
        symbol: str,
    ) -> Optional[TickData]:
        """Get the most recent tick for a symbol.

        Tick data is stored as MarketData rows with interval="tick".
        """
        now = self.get_current_time()
        today = now.date()
        day_start = datetime.combine(today, time(0, 0))

        mode = self.system_manager.mode.value

        if mode == "live":
            from app.managers.data_manager.integrations.alpaca_data import fetch_ticks

            ticks = await fetch_ticks(symbol=symbol, start=day_start, end=now)
            if not ticks:
                return None

            last = ticks[-1]
            return TickData(
                symbol=last["symbol"],
                timestamp=last["timestamp"],
                price=last["close"],
                size=last["volume"],
            )

        # Backtest mode: read from DB
        bars = await MarketDataRepository.get_bars_by_symbol(
            session,
            symbol=symbol,
            start_date=day_start,
            end_date=now,
            interval="tick",
        )

        if not bars:
            return None

        b = bars[-1]
        return TickData(
            symbol=b.symbol,
            timestamp=b.timestamp,
            price=b.close,
            size=b.volume,
        )

    # ==================== QUOTE DATA ====================

    async def get_quotes(
        self,
        session: AsyncSession,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> List[Any]:
        """Get historical bid/ask quotes for a symbol."""
        return await QuoteRepository.get_quotes_by_symbol(
            session,
            symbol,
            start_date=start,
            end_date=end,
        )
    
    async def get_latest_quote(
        self,
        session: AsyncSession,
        symbol: str,
    ) -> Optional[Any]:
        """Get the most recent bid/ask quote for a symbol.

        Only considers quotes from the current DataManager date.
        """
        now = self.get_current_time()
        today = now.date()
        day_start = datetime.combine(today, time(0, 0))

        mode = self.system_manager.mode.value

        if mode == "live":
            from app.managers.data_manager.integrations.alpaca_data import fetch_quotes

            quotes = await fetch_quotes(symbol=symbol, start=day_start, end=now)
            if not quotes:
                return None

            last = quotes[-1]
            # Return a simple object with attribute access compatible with CLI usage
            return SimpleNamespace(
                symbol=last["symbol"],
                timestamp=last["timestamp"],
                bid_price=last.get("bid_price"),
                bid_size=last.get("bid_size"),
                ask_price=last.get("ask_price"),
                ask_size=last.get("ask_size"),
                exchange=last.get("exchange"),
            )

        # Backtest mode: read from DB
        quotes = await QuoteRepository.get_quotes_by_symbol(
            session,
            symbol,
            start_date=day_start,
            end_date=now,
        )

        if not quotes:
            return None

        return quotes[-1]

    async def stream_quotes(
        self,
        session: AsyncSession,
        symbols: List[str],
        stream_id: Optional[str] = None,
    ) -> AsyncIterator[Any]:
        """Stream real-time or backtest quote data.

        Backtest mode yields quotes from the database in chronological
        order for the current date. Live mode is wired to the active data
        provider (e.g., Alpaca websocket) and continues until cancelled
        via :meth:`stop_quotes_stream`.
        """
        if not symbols:
            return

        symbols = [s.upper() for s in symbols]

        if stream_id is None:
            stream_id = uuid4().hex

        cancel_event = self._quote_stream_cancel_tokens.get(stream_id)
        if cancel_event is None:
            cancel_event = asyncio.Event()
            self._quote_stream_cancel_tokens[stream_id] = cancel_event

        mode = self.system_manager.mode.value

        if mode == "backtest":
            # Backtest mode: use central coordinator to merge streams chronologically
            # Both DataManager and coordinator use the same TimeProvider singleton
            coordinator = get_coordinator(self.system_manager)
            
            # Start worker thread if not already running
            coordinator.start_worker()
            
            now = self.get_current_time()
            
            # Determine end time (end of backtest window at market close)
            if self.backtest_end_date is None:
                logger.warning("backtest_end_date not set, using current date")
                end_date = now
            else:
                # End at market close on backtest_end_date
                close_et = time.fromisoformat(TradingHours.MARKET_CLOSE)
                end_date = datetime.combine(self.backtest_end_date, close_et)
            
            # Register and feed each symbol's stream
            for symbol in symbols:
                # Check if stream already active
                if coordinator.is_stream_active(symbol, StreamType.QUOTE):
                    logger.warning(
                        f"Quote stream for {symbol} already active, skipping registration"
                    )
                    continue
                
                # Register stream
                success, input_queue = coordinator.register_stream(symbol, StreamType.QUOTE)
                if not success:
                    logger.error(f"Failed to register quote stream for {symbol}")
                    continue
                
                # Feed data in background task
                async def feed_quotes(sym: str):
                    """Background task to feed quotes from DB to coordinator."""
                    quotes = await QuoteRepository.get_quotes_by_symbol(
                        session,
                        sym,
                        start_date=now,
                        end_date=end_date,
                    )
                    
                    async def quote_iterator():
                        for q in quotes:
                            if cancel_event.is_set():
                                break
                            yield q
                    
                    await coordinator.feed_stream(sym, StreamType.QUOTE, quote_iterator())
                
                # Spawn background task
                asyncio.create_task(feed_quotes(symbol))
            
            # Yield from merged stream (quotes don't update session tracker volume/high/low)
            async for data in coordinator.get_merged_stream():
                if cancel_event.is_set():
                    break
                yield data
            
            # Cleanup
            self._quote_stream_cancel_tokens.pop(stream_id, None)
            return

        provider = self.data_api.lower()
        if provider == "alpaca":
            from app.managers.data_manager.integrations import alpaca_streams

            async for q in alpaca_streams.stream_quotes(
                symbols=symbols,
                cancel_event=cancel_event,
            ):
                yield q

            self._quote_stream_cancel_tokens.pop(stream_id, None)
            return

        raise NotImplementedError(f"Quote streaming not implemented for provider={provider}")

    async def stop_quotes_stream(self, stream_id: Optional[str] = None) -> None:
        """Signal active quote stream(s) to stop via cancel tokens."""
        if stream_id is not None:
            token = self._quote_stream_cancel_tokens.get(stream_id)
            if token is not None and not token.is_set():
                token.set()
            return

        for token in self._quote_stream_cancel_tokens.values():
            if not token.is_set():
                token.set()

        return
    
    async def stream_ticks(
        self,
        session: AsyncSession,
        symbols: List[str],
        stream_id: Optional[str] = None,
    ) -> AsyncIterator[TickData]:
        """Stream real-time or backtest tick data.

        Backtest mode yields ticks from the database in chronological
        order. Live mode is wired to the active data provider (e.g.,
        Alpaca websocket) and continues until cancelled via
        :meth:`stop_ticks_stream`.
        """
        if not symbols:
            return

        symbols = [s.upper() for s in symbols]

        if stream_id is None:
            stream_id = uuid4().hex

        cancel_event = self._tick_stream_cancel_tokens.get(stream_id)
        if cancel_event is None:
            cancel_event = asyncio.Event()
            self._tick_stream_cancel_tokens[stream_id] = cancel_event

        mode = self.system_manager.mode.value

        if mode == "backtest":
            # Backtest mode: use central coordinator to merge streams chronologically
            # Both DataManager and coordinator use the same TimeProvider singleton
            coordinator = get_coordinator(self.system_manager)
            
            # Start worker thread if not already running
            coordinator.start_worker()
            
            now = self.get_current_time()
            
            # Determine end time (end of backtest window at market close)
            if self.backtest_end_date is None:
                logger.warning("backtest_end_date not set, using current date")
                end_date = now
            else:
                # End at market close on backtest_end_date
                close_et = time.fromisoformat(TradingHours.MARKET_CLOSE)
                end_date = datetime.combine(self.backtest_end_date, close_et)
            
            # Register and feed each symbol's stream
            for symbol in symbols:
                # Check if stream already active
                if coordinator.is_stream_active(symbol, StreamType.TICK):
                    logger.warning(
                        f"Tick stream for {symbol} already active, skipping registration"
                    )
                    continue
                
                # Register stream
                success, input_queue = coordinator.register_stream(symbol, StreamType.TICK)
                if not success:
                    logger.error(f"Failed to register tick stream for {symbol}")
                    continue
                
                # Feed data in background task
                async def feed_ticks(sym: str):
                    """Background task to feed ticks from DB to coordinator."""
                    bars = await MarketDataRepository.get_bars_by_symbol(
                        session,
                        symbol=sym,
                        start_date=now,
                        end_date=end_date,
                        interval="tick",
                    )
                    
                    async def tick_iterator():
                        for bar in bars:
                            if cancel_event.is_set():
                                break
                            yield TickData(
                                symbol=bar.symbol,
                                timestamp=bar.timestamp,
                                price=bar.close,
                                size=bar.volume,
                            )
                    
                    await coordinator.feed_stream(sym, StreamType.TICK, tick_iterator())
                
                # Spawn background task
                asyncio.create_task(feed_ticks(symbol))
            
            # Yield from merged stream (ticks stored as bars, can update session tracker)
            from app.managers.data_manager.session_tracker import get_session_tracker
            tracker = get_session_tracker()
            
            async for data in coordinator.get_merged_stream():
                if cancel_event.is_set():
                    break
                
                # Update session tracker with tick/bar data
                if hasattr(data, 'high') and hasattr(data, 'low') and hasattr(data, 'volume'):
                    session_date = data.timestamp.date()
                    await tracker.update_session(
                        symbol=data.symbol,
                        session_date=session_date,
                        bar_high=data.high,
                        bar_low=data.low,
                        bar_volume=data.volume,
                        timestamp=data.timestamp
                    )
                
                yield data
            
            # Cleanup
            self._tick_stream_cancel_tokens.pop(stream_id, None)
            return

        provider = self.data_api.lower()
        if provider == "alpaca":
            from app.managers.data_manager.integrations import alpaca_streams

            async for tick in alpaca_streams.stream_ticks(
                symbols=symbols,
                cancel_event=cancel_event,
            ):
                yield TickData(
                    symbol=tick.symbol,
                    timestamp=tick.timestamp,
                    price=tick.price,
                    size=tick.size,
                )

            self._tick_stream_cancel_tokens.pop(stream_id, None)
            return

        raise NotImplementedError(f"Tick streaming not implemented for provider={provider}")

    async def stop_ticks_stream(self, stream_id: Optional[str] = None) -> None:
        """Signal active tick stream(s) to stop via cancel tokens."""
        if stream_id is not None:
            token = self._tick_stream_cancel_tokens.get(stream_id)
            if token is not None and not token.is_set():
                token.set()
            return

        for token in self._tick_stream_cancel_tokens.values():
            if not token.is_set():
                token.set()

        return
    
    # ==================== DATA IMPORT ====================
    
    async def import_csv(
        self,
        session: AsyncSession,
        file_path: str,
        symbol: str,
        **options
    ) -> Dict[str, Any]:
        """
        Import market data from CSV file.
        
        Args:
            session: Database session
            file_path: Path to CSV file
            symbol: Stock symbol
            **options: Additional import options
            
        Returns:
            Import result dictionary
        """
        from app.managers.data_manager.integrations.csv_import import CSVImportService
        
        result = await CSVImportService.import_csv_to_database(
            session=session,
            file_path=file_path,
            symbol=symbol,
            **options
        )
        
        logger.info(f"CSV import complete: {result.get('imported', 0)} bars")
        return result
    
    async def import_from_api(
        self,
        session: AsyncSession,
        data_type: str,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        **options
    ) -> Dict[str, Any]:
        """Import market data from the currently selected external API.

        Currently supports Alpaca and Schwab for 1-minute bars, daily bars, trade ticks, and quotes.

        Args:
            session: Database session
            data_type: Type of data to import (e.g., "1-minute", "1m", "tick").
            symbol: Stock symbol
            start_date: Start date
            end_date: End date
            **options: Additional import options

        Returns:
            Import result dictionary
        """
        provider = self.data_api.lower()
        normalized_type = data_type.lower().replace("minute", "min").replace(" ", "")

        if provider not in {"alpaca", "schwab"}:
            logger.warning(
                "API import not implemented for provider=%s, data_type=%s",
                provider,
                data_type,
            )
            raise NotImplementedError(
                f"API import from {provider} not yet implemented for data_type={data_type}"
            )

        # Tick data import (trades)
        if normalized_type in {"tick", "ticks"}:
            if provider == "alpaca":
                from app.managers.data_manager.integrations.alpaca_data import fetch_ticks
            else:  # schwab
                from app.managers.data_manager.integrations.schwab_data import fetch_ticks

            logger.info(
                f"Importing ticks from {provider.title()}: symbol={symbol.upper()} start={start_date} end={end_date}"
            )

            ticks = await fetch_ticks(symbol=symbol, start=start_date, end=end_date)

            if not ticks:
                logger.warning(f"No ticks returned from {provider.title()} for {symbol.upper()}")
                return {
                    "success": False,
                    "message": f"No ticks returned from {provider.title()}",
                    "total_rows": 0,
                    "imported": 0,
                    "symbol": symbol.upper(),
                }

            imported = 0
            try:
                imported, _ = await MarketDataRepository.bulk_create_bars(session, ticks)
            except Exception as exc:  # noqa: BLE001
                logger.error("Error importing %s ticks into database: %s", provider.title(), exc)
                raise

            # Compute simple date range from tick timestamps
            timestamps = [t["timestamp"] for t in ticks]
            timestamps.sort()
            date_range = {
                "start": timestamps[0].isoformat(),
                "end": timestamps[-1].isoformat(),
            }

            result_ticks: Dict[str, Any] = {
                "success": True,
                "message": f"Successfully imported {imported} ticks for {symbol.upper()} from {provider.title()}",
                "total_rows": len(ticks),
                "imported": imported,
                "symbol": symbol.upper(),
                "date_range": date_range,
            }

            logger.success(
                "%s tick import complete for %s: %s/%s ticks upserted",
                provider.title(),
                symbol.upper(),
                imported,
                len(ticks),
            )

            return result_ticks

        # Quote data import (bid/ask)
        if normalized_type in {"quote", "quotes"}:
            if provider == "alpaca":
                from app.managers.data_manager.integrations.alpaca_data import fetch_quotes
            else:  # schwab
                from app.managers.data_manager.integrations.schwab_data import fetch_quotes

            logger.info(
                f"Importing quotes from {provider.title()}: symbol={symbol.upper()} start={start_date} end={end_date}"
            )

            quotes = await fetch_quotes(symbol=symbol, start=start_date, end=end_date)

            if not quotes:
                logger.warning(f"No quotes returned from {provider.title()} for {symbol.upper()}")
                return {
                    "success": False,
                    "message": f"No quotes returned from {provider.title()}",
                    "total_rows": 0,
                    "imported": 0,
                    "symbol": symbol.upper(),
                }

            imported = 0
            try:
                imported, _ = await QuoteRepository.bulk_create_quotes(session, quotes)
            except Exception as exc:  # noqa: BLE001
                logger.error("Error importing %s quotes into database: %s", provider.title(), exc)
                raise

            timestamps = [q["timestamp"] for q in quotes]
            timestamps.sort()
            date_range = {
                "start": timestamps[0].isoformat(),
                "end": timestamps[-1].isoformat(),
            }

            result_quotes: Dict[str, Any] = {
                "success": True,
                "message": f"Successfully imported {imported} quotes for {symbol.upper()} from {provider.title()}",
                "total_rows": len(quotes),
                "imported": imported,
                "symbol": symbol.upper(),
                "date_range": date_range,
            }

            logger.success(
                "%s quote import complete for %s: %s/%s quotes upserted",
                provider.title(),
                symbol.upper(),
                imported,
                len(quotes),
            )

            return result_quotes

        # 1-minute bars
        if normalized_type in {"1m", "1min", "1-min"}:
            if provider == "alpaca":
                from app.managers.data_manager.integrations.alpaca_data import fetch_1m_bars
            else:  # schwab
                from app.managers.data_manager.integrations.schwab_data import fetch_1m_bars

            logger.info(
                f"Importing 1m bars from {provider.title()}: symbol={symbol.upper()} start={start_date} end={end_date}"
            )

            bars = await fetch_1m_bars(symbol=symbol, start=start_date, end=end_date)

            if not bars:
                logger.warning(f"No bars returned from {provider.title()} for {symbol.upper()}")
                return {
                    "success": False,
                    "message": f"No bars returned from {provider.title()}",
                    "total_rows": 0,
                    "imported": 0,
                    "symbol": symbol.upper(),
                }

            # Filter to only include regular trading hours (9:30 AM - 4:00 PM ET)
            # This excludes pre-market and after-hours data
            total_bars = len(bars)
            bars = [bar for bar in bars if self.is_regular_trading_hours(bar["timestamp"])]
            filtered_count = total_bars - len(bars)
            
            if filtered_count > 0:
                logger.info(
                    f"Filtered out {filtered_count} bars outside regular trading hours "
                    f"(keeping {len(bars)}/{total_bars})"
                )

            # Persist via repository
            imported = 0
            try:
                imported, _ = await MarketDataRepository.bulk_create_bars(session, bars)
            except Exception as exc:  # noqa: BLE001
                logger.error("Error importing %s bars into database: %s", provider.title(), exc)
                raise

            # Get quality metrics after import
            quality = await MarketDataRepository.check_data_quality(session, symbol.upper())

            result: Dict[str, Any] = {
                "success": True,
                "message": f"Successfully imported {imported} bars for {symbol.upper()} from {provider.title()}",
                "total_rows": len(bars),
                "imported": imported,
                "symbol": symbol.upper(),
                "date_range": quality.get("date_range"),
                "quality_score": quality.get("quality_score"),
                "missing_bars": quality.get("missing_bars", 0),
            }

            logger.success(
                "%s import complete for %s: %s/%s bars upserted (quality: %.1f%%)",
                provider.title(),
                symbol.upper(),
                imported,
                len(bars),
                (quality.get("quality_score", 0) or 0) * 100.0,
            )

            return result

        # Handle daily bars (1d)
        if normalized_type in {"1d", "1day", "1-day", "day", "daily"}:
            if provider == "alpaca":
                from app.managers.data_manager.integrations.alpaca_data import fetch_1d_bars
            elif provider == "schwab":
                from app.managers.data_manager.integrations.schwab_data import fetch_1d_bars
            else:
                raise ValueError(f"Unknown provider: {provider}")

            logger.info(
                f"Importing 1d bars from {provider.title()}: symbol={symbol.upper()} start={start_date} end={end_date}"
            )

            bars = await fetch_1d_bars(symbol=symbol, start=start_date, end=end_date)

            if not bars:
                logger.warning(f"No daily bars returned from {provider.title()} for {symbol.upper()}")
                return {
                    "success": False,
                    "message": f"No daily bars returned from {provider.title()}",
                    "total_rows": 0,
                    "imported": 0,
                    "symbol": symbol.upper(),
                }

            # Daily bars don't need regular hours filtering (they represent full trading days)

            # Persist via repository
            imported = 0
            try:
                imported, _ = await MarketDataRepository.bulk_create_bars(session, bars)
            except Exception as exc:  # noqa: BLE001
                logger.error("Error importing %s daily bars into database: %s", provider.title(), exc)
                raise

            # Get quality metrics after import
            quality = await MarketDataRepository.check_data_quality(session, symbol.upper())

            result: Dict[str, Any] = {
                "success": True,
                "message": f"Successfully imported {imported} daily bars for {symbol.upper()} from {provider.title()}",
                "total_rows": len(bars),
                "imported": imported,
                "symbol": symbol.upper(),
                "date_range": quality.get("date_range"),
                "quality_score": quality.get("quality_score"),
                "missing_bars": quality.get("missing_bars", 0),
            }

            logger.success(
                "%s import complete for %s: %s/%s daily bars upserted (quality: %.1f%%)",
                provider.title(),
                symbol.upper(),
                imported,
                len(bars),
                (quality.get("quality_score", 0) or 0) * 100.0,
            )

            return result

        logger.warning("%s import_from_api does not support data_type=%s", provider.title(), data_type)
        raise NotImplementedError(
            f"{provider.title()} import_from_api currently supports 1-minute bars, daily bars, ticks, or quotes (got {data_type})"
        )
    
    # ==================== DATA QUALITY ====================
    
    async def check_data_quality(
        self,
        session: AsyncSession,
        symbol: str,
        interval: str = "1m"
    ) -> Dict[str, Any]:
        """
        Check data quality for a symbol.
        
        Args:
            session: Database session
            symbol: Stock symbol
            interval: Time interval
            
        Returns:
            Quality metrics dictionary
        """
        return await MarketDataRepository.check_data_quality(
            session,
            symbol,
            interval,
            use_cache=True
        )
    
    async def get_symbols(
        self,
        session: AsyncSession,
        interval: str = "1m"
    ) -> List[str]:
        """
        Get list of all available symbols.
        
        Args:
            session: Database session
            interval: Time interval filter
            
        Returns:
            List of symbol strings
        """
        return await MarketDataRepository.get_symbols(session, interval)

    async def get_bar_count(
        self,
        session: AsyncSession,
        symbol: Optional[str] = None,
        interval: str = "1m",
    ) -> int:
        """Return the number of records for a symbol/interval.

        Used by CLI commands to summarize both bar and tick data without
        reaching directly into the repository layer.
        """
        return await MarketDataRepository.get_bar_count(session, symbol, interval)
    
    async def get_date_range(
        self,
        session: AsyncSession,
        symbol: str,
        interval: str = "1m"
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        """
        Get date range for a symbol's data.
        
        Args:
            session: Database session
            symbol: Stock symbol
            interval: Time interval
            
        Returns:
            Tuple of (start_date, end_date)
        """
        return await MarketDataRepository.get_date_range(session, symbol, interval)
    
    # ==================== SNAPSHOT & LIVE DATA ====================
    
    async def get_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest snapshot from data provider (live mode only).
        
        Snapshot includes:
        - Latest trade (price, size, timestamp)
        - Latest quote (bid/ask prices and sizes)
        - Latest minute bar (OHLCV)
        - Latest daily bar (OHLCV)
        - Previous daily bar (OHLCV)
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dict with snapshot data or None if unavailable/failed
        """
        mode = self.system_manager.mode.value
        if mode != "live":
            logger.warning("Snapshots only available in live mode")
            return None
        
        provider = self.data_api.lower()
        if provider == "alpaca":
            from app.managers.data_manager.integrations.alpaca_data import fetch_snapshot
            return await fetch_snapshot(symbol)
        
        logger.warning(f"Snapshot not implemented for provider: {provider}")
        return None
    
    # ==================== VOLUME & PRICE ANALYTICS ====================
    
    async def get_average_volume(
        self,
        session: AsyncSession,
        symbol: str,
        days: int,
        interval: str = "1m"
    ) -> float:
        """Get average daily volume over specified trading days.
        
        Uses caching to improve performance for repeated calls.
        
        Args:
            session: Database session
            symbol: Stock symbol
            days: Number of trading days to average
            interval: Time interval (default: 1m)
            
        Returns:
            Average daily volume
        """
        from app.managers.data_manager.session_tracker import get_session_tracker
        
        tracker = get_session_tracker()
        
        # Check cache first
        cached = tracker.get_cached_avg_volume(symbol, days)
        if cached is not None:
            logger.debug(f"Using cached average volume for {symbol} ({days} days): {cached}")
            return cached
        
        # Calculate from database
        end_date = self.get_current_time().date()
        avg_volume = await MarketDataRepository.calculate_average_volume(
            session, symbol, days, end_date, interval
        )
        
        # Cache the result
        tracker.cache_avg_volume(symbol, days, avg_volume)
        
        return avg_volume
    
    async def get_time_specific_average_volume(
        self,
        session: AsyncSession,
        symbol: str,
        target_time: time,
        days: int,
        interval: str = "1m"
    ) -> float:
        """Get average volume up to a specific time of day.
        
        For example, average volume by 10:30 AM over the last 20 days.
        Uses caching for performance.
        
        Args:
            session: Database session
            symbol: Stock symbol
            target_time: Time of day (e.g., time(10, 30))
            days: Number of trading days to average
            interval: Time interval (default: 1m)
            
        Returns:
            Average volume up to that time
        """
        from app.managers.data_manager.session_tracker import get_session_tracker
        
        tracker = get_session_tracker()
        
        # Check cache
        cached = tracker.get_cached_time_specific_volume(symbol, target_time, days)
        if cached is not None:
            logger.debug(f"Using cached time-specific volume for {symbol}")
            return cached
        
        # Calculate from database
        end_date = self.get_current_time().date()
        avg_volume = await MarketDataRepository.calculate_time_specific_average_volume(
            session, symbol, target_time, days, end_date, interval
        )
        
        # Cache the result
        tracker.cache_time_specific_volume(symbol, target_time, days, avg_volume)
        
        return avg_volume
    
    async def get_current_session_volume(
        self,
        session: AsyncSession,
        symbol: str,
        interval: str = "1m",
        use_api: bool = True
    ) -> int:
        """Get cumulative volume for the current trading session.
        
        In backtest mode, this returns the volume up to the current simulated time.
        In live mode, can fetch from Alpaca API (if use_api=True) or database.
        
        Uses session tracker for real-time updates during streaming.
        
        Args:
            session: Database session
            symbol: Stock symbol
            interval: Time interval (default: 1m)
            use_api: If True and in live mode, fetch from Alpaca API
            
        Returns:
            Cumulative session volume
        """
        from app.managers.data_manager.session_tracker import get_session_tracker
        
        current_time = self.get_current_time()
        session_date = current_time.date()
        
        tracker = get_session_tracker()
        
        # Get session metrics from tracker (may have real-time updates)
        metrics = await tracker.get_session_metrics(symbol, session_date)
        
        # If tracker has recent data, use it
        if metrics.last_update and metrics.session_volume > 0:
            return metrics.session_volume
        
        # In live mode, try to fetch from Alpaca API
        mode = self.system_manager.mode.value
        if mode == "live" and use_api and self.data_api.lower() == "alpaca":
            from app.managers.data_manager.integrations.alpaca_data import fetch_session_data
            
            session_data = await fetch_session_data(symbol, session_date)
            if session_data:
                # Update tracker with API data
                await tracker.update_session(
                    symbol=symbol,
                    session_date=session_date,
                    bar_high=session_data["high"],
                    bar_low=session_data["low"],
                    bar_volume=session_data["volume"],
                    timestamp=current_time
                )
                return session_data["volume"]
        
        # Fallback to database query
        volume = await MarketDataRepository.get_session_volume(
            session, symbol, session_date, interval
        )
        
        return volume
    
    async def get_historical_high_low(
        self,
        session: AsyncSession,
        symbol: str,
        days: int,
        interval: str = "1m"
    ) -> tuple[Optional[float], Optional[float]]:
        """Get highest and lowest prices over specified period.
        
        Uses caching for performance.
        
        Args:
            session: Database session
            symbol: Stock symbol
            days: Number of trading days to look back
            interval: Time interval (default: 1m)
            
        Returns:
            Tuple of (highest_price, lowest_price)
        """
        from app.managers.data_manager.session_tracker import get_session_tracker
        
        tracker = get_session_tracker()
        
        # Check cache
        cached = tracker.get_cached_historical_hl(symbol, days)
        if cached is not None:
            logger.debug(f"Using cached historical high/low for {symbol} ({days} days)")
            return cached
        
        # Calculate from database
        end_date = self.get_current_time().date()
        high, low = await MarketDataRepository.get_historical_high_low(
            session, symbol, days, end_date, interval
        )
        
        # Cache if we have valid data
        if high is not None and low is not None:
            tracker.cache_historical_hl(symbol, days, high, low)
        
        return (high, low)
    
    async def get_current_session_high_low(
        self,
        session: AsyncSession,
        symbol: str,
        interval: str = "1m",
        use_api: bool = True
    ) -> tuple[Optional[float], Optional[float]]:
        """Get session high and low prices for current trading session.
        
        In backtest mode, returns high/low up to current simulated time.
        In live mode, can fetch from Alpaca API (if use_api=True) or database.
        
        Uses session tracker for real-time updates during streaming.
        
        Args:
            session: Database session
            symbol: Stock symbol
            interval: Time interval (default: 1m)
            use_api: If True and in live mode, fetch from Alpaca API
            
        Returns:
            Tuple of (session_high, session_low)
        """
        from app.managers.data_manager.session_tracker import get_session_tracker
        
        current_time = self.get_current_time()
        session_date = current_time.date()
        
        tracker = get_session_tracker()
        
        # Get session metrics from tracker (may have real-time updates)
        metrics = await tracker.get_session_metrics(symbol, session_date)
        
        # If tracker has recent data, use it
        if metrics.last_update and metrics.session_high is not None:
            return (metrics.session_high, metrics.session_low)
        
        # In live mode, try to fetch from Alpaca API
        mode = self.system_manager.mode.value
        if mode == "live" and use_api and self.data_api.lower() == "alpaca":
            from app.managers.data_manager.integrations.alpaca_data import fetch_session_data
            
            session_data = await fetch_session_data(symbol, session_date)
            if session_data:
                # Update tracker with API data
                await tracker.update_session(
                    symbol=symbol,
                    session_date=session_date,
                    bar_high=session_data["high"],
                    bar_low=session_data["low"],
                    bar_volume=session_data["volume"],
                    timestamp=current_time
                )
                return (session_data["high"], session_data["low"])
        
        # Fallback to database query
        high, low = await MarketDataRepository.get_session_high_low(
            session, symbol, session_date, interval
        )
        
        return (high, low)
    
    # ==================== DATA DELETION ====================
    
    async def delete_symbol_data(
        self,
        session: AsyncSession,
        symbol: str,
        interval: str = "1m"
    ) -> int:
        """
        Delete all data for a symbol.
        
        Args:
            session: Database session
            symbol: Stock symbol
            interval: Time interval
            
        Returns:
            Number of bars deleted
        """
        logger.warning(f"Deleting all data for {symbol}")
        return await MarketDataRepository.delete_bars_by_symbol(
            session,
            symbol,
            interval
        )

    async def delete_all_data(
        self,
        session: AsyncSession,
    ) -> int:
        """Delete ALL market data from the database.

        Args:
            session: Database session

        Returns:
            Total number of bars deleted
        """
        logger.warning("Deleting ALL market data from database")
        return await MarketDataRepository.delete_all_bars(session)
