"""DataManager Public API

Single source of truth for all datasets.
All CLI and API routes must use this interface.
"""
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import List, Optional, Iterator, Dict, Any
from types import SimpleNamespace
import asyncio
from uuid import uuid4
from sqlalchemy.orm import Session

from app.models.trading import BarData, TickData
from app.managers.data_manager.parquet_storage import parquet_storage
from app.managers.data_manager.config import DataManagerConfig
# Holiday import and time functionality moved to time_manager
# Old backtest_stream_coordinator removed - SessionCoordinator is used now
from app.config import settings
from app.logger import logger


class DataManager:
    """
    📊 DataManager - Single source of truth for market data
    
    Provides:
    - Bar data (1-minute bars, historical queries)
    - Tick data
    - Quote data
    - Data streaming (live and backtest)
    - Parquet import/export
    - Stream coordination
    - Session data management
    
    NOTE: Time/calendar operations have been moved to TimeManager.
    Use time_manager for: current time, trading hours, holidays, market open status.
    
    Supports both Live and Backtest modes.
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

        # In-memory registries for live/backtest data streams
        self._bar_stream_cancel_tokens: Dict[str, asyncio.Event] = {}
        self._tick_stream_cancel_tokens: Dict[str, asyncio.Event] = {}
        self._quote_stream_cancel_tokens: Dict[str, asyncio.Event] = {}

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
            ok = alpaca_client.validate_connection()
            self._data_provider_connected = ok
            return ok
        elif provider == "schwab":
            from app.integrations.schwab_client import schwab_client
            logger.info("Selecting Schwab as data provider and validating connection")
            ok = schwab_client.validate_connection()
            self._data_provider_connected = ok
            return ok

        logger.warning(f"Data provider '{provider}' is not yet implemented")
        return False
    
    # ==================== STREAM MANAGEMENT ====================
    # Time/calendar operations moved to TimeManager
    
    def stop_all_streams(self) -> None:
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
        self.stop_bars_stream()
        
        # Stop all tick streams
        self.stop_ticks_stream()
        
        # Stop all quote streams
        self.stop_quotes_stream()
        
        # OLD ARCHITECTURE REMOVED:
        # BacktestStreamCoordinator is no longer used
        # SessionCoordinator handles all streaming now
        
        logger.info("All active streams stopped")
        
        # Clear session data
        from app.managers.data_manager.session_data import get_session_data
        session_data = get_session_data()
        session_data.clear()
        
        logger.success("✓ All streams stopped and session data cleared")
    
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
    
    def get_current_time(self) -> datetime:
        """Get current time from TimeManager.
        
        Delegates to TimeManager via SystemManager.
        Handles both live mode (real-time) and backtest mode (simulated time).
        
        Returns:
            Current datetime
        """
        if self.system_manager is None:
            logger.error("SystemManager not available, cannot get current time")
            raise RuntimeError("DataManager requires SystemManager to access TimeManager")
        
        time_mgr = self.system_manager.get_time_manager()
        return time_mgr.get_current_time()
    
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
        return self.session_data.get_session_metrics(symbol)
    
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

    def set_backtest_speed(self, speed: float) -> None:
        """Set the backtest speed multiplier in session config.

        Valid values:
        - 0: Maximum speed (no pacing)
        - 1.0: Realtime speed
        - 2.0: 2x speed
        - 0.5: Half speed

        Args:
            speed: Speed multiplier (0 = max, 1.0 = realtime, >1 = faster, <1 = slower)
        """
        if speed < 0:
            raise ValueError("speed_multiplier must be >= 0")
        
        if self.system_manager and self.system_manager.session_config and self.system_manager.session_config.backtest_config:
            self.system_manager.session_config.backtest_config.speed_multiplier = speed
        else:
            raise RuntimeError("Session config not loaded")
    
    # ==================== MARKET DATA (BARS) ====================
    
    def get_bars(
        self,
        session: Session,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1m",
        regular_hours_only: bool = False
    ) -> List[BarData]:
        """
        Get historical bar data.
        
        Args:
            session: Database session
            symbol: Stock symbol
            start: Start datetime
            end: End datetime
            interval: Time interval (default: 1m)
            regular_hours_only: If True, filter to regular trading hours only (default: False)
            
        Returns:
            List of BarData objects
        """
        # Read bars from Parquet storage (no database)
        df = parquet_storage.read_bars(
            interval,
            symbol,
            start_date=start,
            end_date=end,
            regular_hours_only=regular_hours_only
        )
        
        if df.empty:
            return []
        
        # Convert DataFrame to BarData objects
        bar_data_list = [
            BarData(
                symbol=row['symbol'],
                timestamp=row['timestamp'],
                interval=interval,
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
                volume=row['volume']
            )
            for _, row in df.iterrows()
        ]
        
        return bar_data_list
    
    async def get_latest_bar(
        self,
        session: Session,
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
        day_start = datetime.combine(today, time(0, 0), tzinfo=timezone.utc)

        mode = self.system_manager.mode.value

        # In live mode, fetch directly from the live data API (no DB).
        if mode == "live":
            if interval != "1m":
                raise NotImplementedError("Real-time latest_bar currently supports only 1m interval")

            from app.managers.data_manager.integrations.alpaca_data import fetch_1m_bars

            bars = fetch_1m_bars(symbol=symbol, start=day_start, end=now)
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

        # Backtest mode: read from Parquet up to current simulated time
        df = parquet_storage.read_bars(
            interval,
            symbol,
            start_date=day_start,
            end_date=now
        )

        if df.empty:
            return None

        # Get last row
        bar = df.iloc[-1]
        return BarData(
            symbol=bar['symbol'],
            timestamp=bar['timestamp'],
            interval=interval,
            open=bar['open'],
            high=bar['high'],
            low=bar['low'],
            close=bar['close'],
            volume=bar['volume'],
        )
    
    def start_bar_streams(
        self,
        session: Session,
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
        
        if not symbols:
            return 0
        
        session_data = get_session_data()
        symbols = [s.upper() for s in symbols]
        
        mode = self.system_manager.mode.value
        if mode != "backtest":
            logger.warning("start_bar_streams() only works in backtest mode")
            return 0
        
        coordinator = get_coordinator(self.system_manager, self)
        coordinator.start_worker()
        
        # VALIDATION: Only 1s or 1m bars can be streamed
        # Derived intervals (5m, 15m, etc.) are computed by the upkeep thread
        if interval not in ["1s", "1m"]:
            raise ValueError(
                f"Stream coordinator only supports 1s or 1m bars (requested: {interval}). "
                f"Derived intervals (5m, 15m, etc.) are automatically computed by the data upkeep thread. "
                f"Check your session configuration."
            )
        
        now = self.get_current_time()
        current_date = now.date()
        
        # Get trading session from TimeManager (proper way - use provided session)
        time_mgr = self.system_manager.get_time_manager()
        trading_session = time_mgr.get_trading_session(session, current_date)
        
        if not trading_session or trading_session.is_holiday:
            logger.warning(f"No trading session for {current_date}")
            return 0
        
        # Construct market open/close times in market timezone, then convert to UTC
        import pytz
        market_tz_str = time_mgr.get_market_timezone()
        market_tz = pytz.timezone(market_tz_str)
        
        start_time_naive = datetime.combine(current_date, trading_session.regular_open)
        end_time_naive = datetime.combine(current_date, trading_session.regular_close)
        
        start_time = market_tz.localize(start_time_naive).astimezone(timezone.utc)
        end_time = market_tz.localize(end_time_naive).astimezone(timezone.utc)
        
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
            session_data.register_symbol(symbol)
            session_data.mark_stream_active(symbol, "bars")
            
            # Register with coordinator
            success, input_queue = coordinator.register_stream(symbol, StreamType.BAR)
            if not success:
                logger.error(f"Failed to register bar stream for {symbol}")
                session_data.mark_stream_inactive(symbol, "bars")
                continue
            
            # BLOCK and fetch current day from Parquet
            logger.info(f"Fetching bars for {symbol} on {current_date}...")
            df = parquet_storage.read_bars(
                interval,
                symbol,
                start_date=start_time,
                end_date=end_time
            )
            
            if df.empty:
                logger.warning(f"No bars found for {symbol} on {current_date}")
                session_data.mark_stream_inactive(symbol, "bars")
                continue
            
            # Convert DataFrame to list of objects for iteration
            bars = df.to_dict('records')
            logger.info(f"Fetched {len(bars)} bars for {symbol} on {current_date}")
            
            # Feed to coordinator (bars will be added to session_data by coordinator as time advances)
            def bar_iterator():
                for bar in bars:
                    yield BarData(
                        symbol=bar['symbol'],
                        timestamp=bar['timestamp'],
                        interval=interval,
                        open=bar['open'],
                        high=bar['high'],
                        low=bar['low'],
                        close=bar['close'],
                        volume=bar['volume'],
                    )
            
            coordinator.feed_stream(symbol, StreamType.BAR, bar_iterator())
            logger.success(f"✓ Started bar stream for {symbol} ({len(bars)} bars)")
            streams_started += 1
        
        # Activate session immediately if we started streams successfully
        # (Upkeep thread will also activate, but this ensures immediate activation)
        if streams_started > 0:
            session_data.activate_session()
            logger.info(f"✓ Session activated ({streams_started} streams started)")
        
        return streams_started
    
    async def stream_bars(
        self,
        session: Session,
        symbols: List[str],
        interval: str = "1m",
        stream_id: Optional[str] = None,
    ) -> Iterator[BarData]:
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
            coordinator = get_coordinator(self.system_manager, self)
            
            # Start worker thread if not already running
            coordinator.start_worker()
            
            now = self.get_current_time()
            current_date = now.date()
            
            # Determine end time: CURRENT DAY ONLY at market close + 1 minute buffer
            # Get market hours from TimeManager
            from app.models.database import SessionLocal
            from datetime import timedelta
            with SessionLocal() as db_session:
                time_mgr = self.system_manager.get_time_manager()
                trading_session = time_mgr.get_trading_session(db_session, current_date)
                if trading_session:
                    start_time = trading_session.get_regular_open_datetime()
                    end_time = trading_session.get_regular_close_datetime()
                    # Add 1-minute buffer to capture close-of-day data (e.g., 16:00 bar)
                    end_time = end_time + timedelta(minutes=1)
                else:
                    logger.warning(f"No trading session for {current_date}, using defaults")
                    # Fallback if no session found
                    from zoneinfo import ZoneInfo
                    system_tz = ZoneInfo(self.system_manager.timezone)
                    start_time = datetime.combine(current_date, time(9, 30), tzinfo=system_tz)
                    end_time = datetime.combine(current_date, time(16, 1), tzinfo=system_tz)
            
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
                session_data.register_symbol(symbol)
                session_data.mark_stream_active(symbol, "bars")
                
                # 4. Register stream with coordinator
                success, input_queue = coordinator.register_stream(symbol, StreamType.BAR)
                if not success:
                    logger.error(f"Failed to register bar stream for {symbol}")
                    session_data.mark_stream_inactive(symbol, "bars")
                    continue
                
                # 5. BLOCK and fetch current day only from Parquet
                logger.info(f"Fetching bars for {symbol} on {current_date}...")
                df = parquet_storage.read_bars(
                    interval,
                    symbol,
                    start_date=start_time,
                    end_date=end_time
                )
                
                if df.empty:
                    logger.warning(f"No bars found for {symbol} on {current_date}")
                    session_data.mark_stream_inactive(symbol, "bars")
                    continue
                
                # Convert DataFrame to list of dicts for iteration
                bars = df.to_dict('records')
                logger.info(f"Fetched {len(bars)} bars for {symbol} on {current_date}")
                
                # Feed data to coordinator (bars will be added to session_data by coordinator as time advances)
                def bar_iterator():
                    for bar in bars:
                        if cancel_event.is_set():
                            break
                        yield BarData(
                            symbol=bar['symbol'],
                            timestamp=bar['timestamp'],
                            interval=interval,
                            open=bar['open'],
                            high=bar['high'],
                            low=bar['low'],
                            close=bar['close'],
                            volume=bar['volume'],
                        )
                
                coordinator.feed_stream(symbol, StreamType.BAR, bar_iterator())
                logger.success(f"✓ Started bar stream for {symbol} ({len(bars)} bars)")
            
            # All symbols started, now yield from merged stream if consumer wants to iterate
            # NOTE: For system startup, we don't consume - streams run in coordinator worker thread
            # The coordinator worker already adds bars to session_data, so we just yield them here
            for data in coordinator.get_merged_stream():
                if cancel_event.is_set():
                    break
                
                yield data
            
            # Cleanup when stream ends
            for symbol in symbols:
                session_data.mark_stream_inactive(symbol, "bars")
            self._bar_stream_cancel_tokens.pop(stream_id, None)
            return

        # Live mode: delegate to provider-specific streaming implementation.
        # To keep DataManager focused, we import the provider lazily.
        provider = self.data_api.lower()
        if provider == "alpaca":
            from app.managers.data_manager.integrations import alpaca_streams

            for bar in alpaca_streams.stream_bars(
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
        session: Session,
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
        # Tick data is stored as 1s bars in Parquet
        df = parquet_storage.read_bars(
            '1s',  # Ticks stored as 1s bars
            symbol,
            start_date=start,
            end_date=end
        )
        
        if df.empty:
            return []

        ticks: List[TickData] = [
            TickData(
                symbol=row['symbol'],
                timestamp=row['timestamp'],
                price=row['close'],
                size=row['volume'],
            )
            for _, row in df.iterrows()
        ]
        return ticks

    async def get_latest_tick(
        self,
        session: Session,
        symbol: str,
    ) -> Optional[TickData]:
        """Get the most recent tick for a symbol.

        Tick data is stored as 1s bars in Parquet.
        """
        now = self.get_current_time()
        today = now.date()
        day_start = datetime.combine(today, time(0, 0), tzinfo=timezone.utc)

        mode = self.system_manager.mode.value

        if mode == "live":
            from app.managers.data_manager.integrations.alpaca_data import fetch_ticks

            ticks = fetch_ticks(symbol=symbol, start=day_start, end=now)
            if not ticks:
                return None

            last = ticks[-1]
            return TickData(
                symbol=last["symbol"],
                timestamp=last["timestamp"],
                price=last["close"],
                size=last["volume"],
            )

        # Backtest mode: read from Parquet
        df = parquet_storage.read_bars(
            '1s',  # Ticks stored as 1s bars
            symbol,
            start_date=day_start,
            end_date=now
        )

        if df.empty:
            return None

        # Get last row
        b = df.iloc[-1]
        return TickData(
            symbol=b['symbol'],
            timestamp=b['timestamp'],
            price=b['close'],
            size=b['volume'],
        )

    # ==================== QUOTE DATA ====================

    async def get_quotes(
        self,
        session: Session,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> List[Any]:
        """Get historical bid/ask quotes for a symbol."""
        return QuoteRepository.get_quotes_by_symbol(
            session,
            symbol,
            start_date=start,
            end_date=end,
        )
    
    async def get_latest_quote(
        self,
        session: Session,
        symbol: str,
    ) -> Optional[Any]:
        """Get the most recent bid/ask quote for a symbol.

        Only considers quotes from the current DataManager date.
        """
        now = self.get_current_time()
        today = now.date()
        day_start = datetime.combine(today, time(0, 0), tzinfo=timezone.utc)

        mode = self.system_manager.mode.value

        if mode == "live":
            from app.managers.data_manager.integrations.alpaca_data import fetch_quotes

            quotes = fetch_quotes(symbol=symbol, start=day_start, end=now)
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
        quotes = QuoteRepository.get_quotes_by_symbol(
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
        session: Session,
        symbols: List[str],
        stream_id: Optional[str] = None,
    ) -> Iterator[Any]:
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
            # Both DataManager and coordinator use TimeManager for time synchronization
            coordinator = get_coordinator(self.system_manager, self)
            
            # Start worker thread if not already running
            coordinator.start_worker()
            
            # Get backtest window from time_manager
            time_mgr = self.system_manager.get_time_manager()
            now = time_mgr.get_current_time()
            
            # Determine end time (end of backtest window at market close + 1 minute buffer)
            if time_mgr.backtest_end_date is None:
                logger.warning("backtest_end_date not set, using current date")
                end_date = now
            else:
                # End at market close on backtest_end_date + 1 minute buffer
                from app.models.database import SessionLocal
                from datetime import timedelta
                with SessionLocal() as db_session:
                    trading_session = time_mgr.get_trading_session(db_session, time_mgr.backtest_end_date)
                    if trading_session:
                        end_date = trading_session.get_regular_close_datetime()
                        # Add 1-minute buffer to capture close-of-day data
                        end_date = end_date + timedelta(minutes=1)
                    else:
                        # Fallback
                        from zoneinfo import ZoneInfo
                        system_tz = ZoneInfo(self.system_manager.timezone)
                        end_date = datetime.combine(time_mgr.backtest_end_date, time(16, 1), tzinfo=system_tz)
            
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
                    quotes = QuoteRepository.get_quotes_by_symbol(
                        session,
                        sym,
                        start_date=now,
                        end_date=end_date,
                    )
                    
                    def quote_iterator():
                        for q in quotes:
                            if cancel_event.is_set():
                                break
                            yield q
                    
                    coordinator.feed_stream(sym, StreamType.QUOTE, quote_iterator())
                
                # Spawn background task
                asyncio.create_task(feed_quotes(symbol))
            
            # Yield from merged stream (quotes don't update session tracker volume/high/low)
            for data in coordinator.get_merged_stream():
                if cancel_event.is_set():
                    break
                yield data
            
            # Cleanup
            self._quote_stream_cancel_tokens.pop(stream_id, None)
            return

        provider = self.data_api.lower()
        if provider == "alpaca":
            from app.managers.data_manager.integrations import alpaca_streams

            for q in alpaca_streams.stream_quotes(
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
        session: Session,
        symbols: List[str],
        stream_id: Optional[str] = None,
    ) -> Iterator[TickData]:
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
            # Both DataManager and coordinator use TimeManager for time synchronization
            coordinator = get_coordinator(self.system_manager, self)
            
            # Start worker thread if not already running
            coordinator.start_worker()
            
            # Get backtest window from time_manager
            time_mgr = self.system_manager.get_time_manager()
            now = time_mgr.get_current_time()
            
            # Determine end time (end of backtest window at market close + 1 minute buffer)
            if time_mgr.backtest_end_date is None:
                logger.warning("backtest_end_date not set, using current date")
                end_date = now
            else:
                # End at market close on backtest_end_date + 1 minute buffer
                from app.models.database import SessionLocal
                from datetime import timedelta
                with SessionLocal() as db_session:
                    trading_session = time_mgr.get_trading_session(db_session, time_mgr.backtest_end_date)
                    if trading_session:
                        end_date = trading_session.get_regular_close_datetime()
                        # Add 1-minute buffer to capture close-of-day data
                        end_date = end_date + timedelta(minutes=1)
                    else:
                        # Fallback
                        from zoneinfo import ZoneInfo
                        system_tz = ZoneInfo(self.system_manager.timezone)
                        end_date = datetime.combine(time_mgr.backtest_end_date, time(16, 1), tzinfo=system_tz)
            
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
                    """Background task to feed ticks from Parquet to coordinator."""
                    df = parquet_storage.read_bars(
                        '1s',  # Ticks stored as 1s bars
                        sym,
                        start_date=now,
                        end_date=end_date
                    )
                    bars = df.to_dict('records') if not df.empty else []
                    
                    def tick_iterator():
                        for bar in bars:
                            if cancel_event.is_set():
                                break
                            yield TickData(
                                symbol=bar['symbol'],
                                timestamp=bar['timestamp'],
                                price=bar['close'],
                                size=bar['volume'],
                            )
                    
                    coordinator.feed_stream(sym, StreamType.TICK, tick_iterator())
                
                # Spawn background task
                asyncio.create_task(feed_ticks(symbol))
            
            # Yield from merged stream (ticks stored as bars, can update session tracker)
            from app.managers.data_manager.session_tracker import get_session_tracker
            tracker = get_session_tracker()
            
            for data in coordinator.get_merged_stream():
                if cancel_event.is_set():
                    break
                
                # Update session tracker with tick/bar data
                if hasattr(data, 'high') and hasattr(data, 'low') and hasattr(data, 'volume'):
                    session_date = data.timestamp.date()
                    tracker.update_session(
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

            for tick in alpaca_streams.stream_ticks(
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
        session: Session,
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
        
        result = CSVImportService.import_csv_to_database(
            session=session,
            file_path=file_path,
            symbol=symbol,
            **options
        )
        
        logger.info(f"CSV import complete: {result.get('imported', 0)} bars")
        return result
    
    async def import_from_api(
        self,
        session: Session,
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

            ticks = fetch_ticks(symbol=symbol, start=start_date, end=end_date)

            if not ticks:
                logger.warning(f"No ticks returned from {provider.title()} for {symbol.upper()}")
                return {
                    "success": False,
                    "message": f"No ticks returned from {provider.title()}",
                    "total_rows": 0,
                    "imported": 0,
                    "symbol": symbol.upper(),
                }

            # Convert ticks to 1s bars and store in Parquet
            from app.managers.data_manager.parquet_storage import parquet_storage
            
            try:
                # Aggregate ticks to 1s bars
                bars_1s = parquet_storage.aggregate_ticks_to_1s(ticks)
                
                # Write to Parquet
                logger.info(f"[Parquet] Writing {len(bars_1s)} 1s bars (from {len(ticks)} ticks) for {symbol.upper()}...")
                imported, files = parquet_storage.write_bars(bars_1s, '1s', symbol.upper(), append=True)
                logger.info(f"[Parquet] ✓ Successfully wrote {imported} 1s bars to {len(files)} file(s)")
                
            except Exception as exc:  # noqa: BLE001
                logger.error("Error writing ticks to Parquet: %s", exc)
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

            quotes = fetch_quotes(symbol=symbol, start=start_date, end=end_date)

            if not quotes:
                logger.warning(f"No quotes returned from {provider.title()} for {symbol.upper()}")
                return {
                    "success": False,
                    "message": f"No quotes returned from {provider.title()}",
                    "total_rows": 0,
                    "imported": 0,
                    "symbol": symbol.upper(),
                }

            # Aggregate quotes to 1 per second and store in Parquet
            from app.managers.data_manager.parquet_storage import parquet_storage
            
            try:
                # Aggregate to 1 quote per second (tightest spread)
                quotes_aggregated = parquet_storage.aggregate_quotes_by_second(quotes)
                
                # Write to Parquet
                logger.info(f"[Parquet] Writing {len(quotes_aggregated)} aggregated quotes (from {len(quotes)} quotes) for {symbol.upper()}...")
                imported, files = parquet_storage.write_quotes(quotes_aggregated, symbol.upper(), append=True)
                logger.info(f"[Parquet] ✓ Successfully wrote {imported} quotes to {len(files)} file(s)")
                
            except Exception as exc:  # noqa: BLE001
                logger.error("Error writing quotes to Parquet: %s", exc)
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

            bars = fetch_1m_bars(symbol=symbol, start=start_date, end=end_date)

            if not bars:
                logger.warning(f"No bars returned from {provider.title()} for {symbol.upper()}")
                return {
                    "success": False,
                    "message": f"No bars returned from {provider.title()}",
                    "total_rows": 0,
                    "imported": 0,
                    "symbol": symbol.upper(),
                }

            # Keep ALL data including pre-market and after-hours
            # No filtering - full trading day data stored
            logger.info(f"Storing all {len(bars)} bars (including pre/post-market)")

            # Write to Parquet
            from app.managers.data_manager.parquet_storage import parquet_storage
            
            imported = 0
            try:
                logger.info(f"[Parquet] Writing {len(bars)} 1m bars for {symbol.upper()}...")
                imported, files = parquet_storage.write_bars(bars, '1m', symbol.upper(), append=True)
                logger.info(f"[Parquet] ✓ Successfully wrote {imported} 1m bars to {len(files)} file(s)")
            except Exception as exc:  # noqa: BLE001
                logger.error("Error writing 1m bars to Parquet: %s", exc)
                raise

            # Quality metrics (Parquet-based - count and date range)
            timestamps = [b["timestamp"] for b in bars]
            timestamps.sort()
            date_range = {
                "start": timestamps[0].isoformat(),
                "end": timestamps[-1].isoformat(),
            }
            
            result: Dict[str, Any] = {
                "success": True,
                "message": f"Successfully imported {imported} bars for {symbol.upper()} from {provider.title()} to Parquet",
                "total_rows": len(bars),
                "imported": imported,
                "symbol": symbol.upper(),
                "date_range": date_range,
                "storage": "parquet",
            }

            logger.success(
                "%s import complete for %s: %s bars written to Parquet",
                provider.title(),
                symbol.upper(),
                imported,
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

            bars = fetch_1d_bars(symbol=symbol, start=start_date, end=end_date)

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

            # Write to Parquet
            from app.managers.data_manager.parquet_storage import parquet_storage
            
            imported = 0
            try:
                logger.info(f"[Parquet] Writing {len(bars)} daily bars for {symbol.upper()}...")
                imported, files = parquet_storage.write_bars(bars, '1d', symbol.upper(), append=True)
                logger.info(f"[Parquet] ✓ Successfully wrote {imported} daily bars to {len(files)} file(s)")
            except Exception as exc:  # noqa: BLE001
                logger.error("Error writing daily bars to Parquet: %s", exc)
                raise

            # Quality metrics (Parquet-based)
            timestamps = [b["timestamp"] for b in bars]
            timestamps.sort()
            date_range = {
                "start": timestamps[0].isoformat(),
                "end": timestamps[-1].isoformat(),
            }

            result: Dict[str, Any] = {
                "success": True,
                "message": f"Successfully imported {imported} daily bars for {symbol.upper()} from {provider.title()} to Parquet",
                "total_rows": len(bars),
                "imported": imported,
                "symbol": symbol.upper(),
                "date_range": date_range,
                "storage": "parquet",
            }

            logger.success(
                "%s import complete for %s: %s daily bars written to Parquet",
                provider.title(),
                symbol.upper(),
                imported,
            )

            return result

        logger.warning("%s import_from_api does not support data_type=%s", provider.title(), data_type)
        raise NotImplementedError(
            f"{provider.title()} import_from_api currently supports 1-minute bars, daily bars, ticks, or quotes (got {data_type})"
        )
    
    # ==================== DATA QUALITY ====================
    
    def check_data_quality(
        self,
        session: Session,
        symbol: str,
        interval: str = "1m"
    ) -> Dict[str, Any]:
        """
        Check data quality for a symbol from Parquet.
        
        Args:
            session: Database session (unused, kept for compatibility)
            symbol: Stock symbol
            interval: Time interval ('1m', '1d', '1s', 'tick')
            
        Returns:
            Quality metrics dictionary
        """
        # Map 'tick' to '1s' (ticks stored as 1s bars in Parquet)
        parquet_interval = '1s' if interval == 'tick' else interval
        
        try:
            df = parquet_storage.read_bars(parquet_interval, symbol.upper())
            
            if df.empty:
                return {
                    'total_bars': 0,
                    'expected_bars': 0,
                    'missing_bars': 0,
                    'duplicate_timestamps': 0,
                    'quality_score': 0.0,
                    'date_range': None
                }
            
            total_bars = len(df)
            start_date = df['timestamp'].min()
            end_date = df['timestamp'].max()
            
            # Check for duplicates
            duplicate_timestamps = df['timestamp'].duplicated().sum()
            
            # Simple quality calculation (100% if no duplicates)
            quality_score = 1.0 if duplicate_timestamps == 0 else 0.95
            
            return {
                'total_bars': total_bars,
                'expected_bars': total_bars,  # Simplified - actual calculation would check market hours
                'missing_bars': 0,  # Parquet doesn't track missing bars
                'duplicate_timestamps': int(duplicate_timestamps),
                'quality_score': quality_score,
                'date_range': {
                    'start': start_date.strftime('%Y-%m-%d %H:%M:%S'),
                    'end': end_date.strftime('%Y-%m-%d %H:%M:%S')
                }
            }
        except FileNotFoundError:
            return {
                'total_bars': 0,
                'expected_bars': 0,
                'missing_bars': 0,
                'duplicate_timestamps': 0,
                'quality_score': 0.0,
                'date_range': None
            }
    
    def get_symbols(
        self,
        session: Session,
        interval: str = "1m"
    ) -> List[str]:
        """
        Get list of all available symbols from Parquet storage.
        
        Args:
            session: Database session (unused, kept for compatibility)
            interval: Time interval filter ('1m', '1d', '1s', 'tick')
            
        Returns:
            List of symbol strings
        """
        # Map 'tick' to '1s' (ticks stored as 1s bars in Parquet)
        parquet_interval = '1s' if interval == 'tick' else interval
        return parquet_storage.get_available_symbols(parquet_interval)

    def get_bar_count(
        self,
        session: Session,
        symbol: Optional[str] = None,
        interval: str = "1m",
    ) -> int:
        """Return the number of records for a symbol/interval from Parquet.

        Used by CLI commands to summarize both bar and tick data.
        
        Args:
            session: Database session (unused, kept for compatibility)
            symbol: Stock symbol (required)
            interval: Time interval ('1m', '1d', '1s', 'tick')
            
        Returns:
            Number of bars/ticks
        """
        if not symbol:
            return 0
        
        # Map 'tick' to '1s' (ticks stored as 1s bars in Parquet)
        parquet_interval = '1s' if interval == 'tick' else interval
        
        try:
            df = parquet_storage.read_bars(parquet_interval, symbol.upper())
            return len(df)
        except FileNotFoundError:
            return 0
    
    def get_date_range(
        self,
        session: Session,
        symbol: str,
        interval: str = "1m"
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        """
        Get date range for a symbol's data from Parquet.
        
        Args:
            session: Database session (unused, kept for compatibility)
            symbol: Stock symbol
            interval: Time interval ('1m', '1d', '1s', 'tick')
            
        Returns:
            Tuple of (start_date, end_date)
        """
        # Map 'tick' to '1s' (ticks stored as 1s bars in Parquet)
        parquet_interval = '1s' if interval == 'tick' else interval
        
        try:
            return parquet_storage.get_date_range(parquet_interval, symbol.upper())
        except FileNotFoundError:
            return (None, None)
    
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
            return fetch_snapshot(symbol)
        
        logger.warning(f"Snapshot not implemented for provider: {provider}")
        return None
    
    # ==================== VOLUME & PRICE ANALYTICS ====================
    
    async def get_average_volume(
        self,
        session: Session,
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
        avg_volume = MarketDataRepository.calculate_average_volume(
            session, symbol, days, end_date, interval
        )
        
        # Cache the result
        tracker.cache_avg_volume(symbol, days, avg_volume)
        
        return avg_volume
    
    async def get_time_specific_average_volume(
        self,
        session: Session,
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
        avg_volume = MarketDataRepository.calculate_time_specific_average_volume(
            session, symbol, target_time, days, end_date, interval
        )
        
        # Cache the result
        tracker.cache_time_specific_volume(symbol, target_time, days, avg_volume)
        
        return avg_volume
    
    async def get_current_session_volume(
        self,
        session: Session,
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
        metrics = tracker.get_session_metrics(symbol, session_date)
        
        # If tracker has recent data, use it
        if metrics.last_update and metrics.session_volume > 0:
            return metrics.session_volume
        
        # In live mode, try to fetch from Alpaca API
        mode = self.system_manager.mode.value
        if mode == "live" and use_api and self.data_api.lower() == "alpaca":
            from app.managers.data_manager.integrations.alpaca_data import fetch_session_data
            
            session_data = fetch_session_data(symbol, session_date)
            if session_data:
                # Update tracker with API data
                tracker.update_session(
                    symbol=symbol,
                    session_date=session_date,
                    bar_high=session_data["high"],
                    bar_low=session_data["low"],
                    bar_volume=session_data["volume"],
                    timestamp=current_time
                )
                return session_data["volume"]
        
        # Fallback to database query
        volume = MarketDataRepository.get_session_volume(
            session, symbol, session_date, interval
        )
        
        return volume
    
    async def get_historical_high_low(
        self,
        session: Session,
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
        high, low = MarketDataRepository.get_historical_high_low(
            session, symbol, days, end_date, interval
        )
        
        # Cache if we have valid data
        if high is not None and low is not None:
            tracker.cache_historical_hl(symbol, days, high, low)
        
        return (high, low)
    
    async def get_current_session_high_low(
        self,
        session: Session,
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
        metrics = tracker.get_session_metrics(symbol, session_date)
        
        # If tracker has recent data, use it
        if metrics.last_update and metrics.session_high is not None:
            return (metrics.session_high, metrics.session_low)
        
        # In live mode, try to fetch from Alpaca API
        mode = self.system_manager.mode.value
        if mode == "live" and use_api and self.data_api.lower() == "alpaca":
            from app.managers.data_manager.integrations.alpaca_data import fetch_session_data
            
            session_data = fetch_session_data(symbol, session_date)
            if session_data:
                # Update tracker with API data
                tracker.update_session(
                    symbol=symbol,
                    session_date=session_date,
                    bar_high=session_data["high"],
                    bar_low=session_data["low"],
                    bar_volume=session_data["volume"],
                    timestamp=current_time
                )
                return (session_data["high"], session_data["low"])
        
        # Fallback to database query
        high, low = MarketDataRepository.get_session_high_low(
            session, symbol, session_date, interval
        )
        
        return (high, low)
    
    # ==================== DATA DELETION ====================
    
    async def delete_symbol_data(
        self,
        session: Session,
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
        return MarketDataRepository.delete_bars_by_symbol(
            session,
            symbol,
            interval
        )

    async def delete_all_data(
        self,
        session: Session,
    ) -> int:
        """Delete ALL market data from the database.

        Args:
            session: Database session

        Returns:
            Total number of bars deleted
        """
        logger.warning("Deleting ALL market data from database")
        return MarketDataRepository.delete_all_bars(session)
