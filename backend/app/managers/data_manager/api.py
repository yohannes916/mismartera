"""
DataManager Public API

Single source of truth for all datasets.
All CLI and API routes must use this interface.
"""
from datetime import datetime, date
from typing import List, Optional, AsyncIterator, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import BarData, TickData
from app.models.trading_calendar import TradingHoliday, TradingHours
from app.managers.data_manager.time_provider import TimeProvider
from app.managers.data_manager.repositories.market_data_repo import MarketDataRepository
from app.managers.data_manager.repositories.holiday_repo import HolidayRepository
from app.managers.data_manager.config import DataManagerConfig
from app.managers.data_manager.integrations.holiday_import_service import (
    holiday_import_service,
)
from app.integrations import alpaca_client
from app.logger import logger


class DataManager:
    """
    📊 DataManager - Single source of truth for all data
    
    Provides:
    - Current time (real or backtest)
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
    ):
        """Initialize DataManager.

        Args:
            mode: Optional override for operating mode ("real" or "backtest").
            config: Optional DataManagerConfig. If not provided, defaults are
                loaded from global settings.
        """
        self.config = config or DataManagerConfig()

        # Determine operating mode (CLI override wins over config default)
        effective_mode = mode or self.config.operating_mode
        self.mode = effective_mode

        # Selected data API provider name (e.g., "alpaca", "schwab")
        self.data_api: str = self.config.data_api

        # Connection status flag for the active data provider
        self._data_provider_connected: bool = False

        self.time_provider = TimeProvider(mode=effective_mode)
        logger.info(
            f"DataManager initialized in {effective_mode} mode "
            f"using data_api={self.data_api}"
        )

    # ==================== CONFIGURATION & PROVIDERS ====================

    async def set_operating_mode(self, mode: str) -> None:
        """Set operating mode to "realtime" or "backtest".

        This updates the internal time provider accordingly.
        """
        normalized = mode.lower()
        if normalized not in {"real", "realtime", "backtest"}:
            raise ValueError(f"Invalid operating mode: {mode}")

        # Normalize to existing TimeProvider modes
        effective_mode = "real" if normalized in {"real", "realtime"} else "backtest"

        if self.mode == effective_mode:
            logger.info(f"DataManager operating mode already {effective_mode}")
            return

        logger.info(f"Changing DataManager operating mode to {effective_mode}")
        self.mode = effective_mode
        self.time_provider = TimeProvider(mode=effective_mode)

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

        # For now, only Alpaca is supported as a real provider.
        if provider == "alpaca":
            logger.info("Selecting Alpaca as data provider and validating connection")
            ok = await alpaca_client.validate_connection()
            self._data_provider_connected = ok
            return ok

        logger.warning(f"Data provider '{provider}' is not yet implemented")
        return False
    
    # ==================== TIME & STATUS ====================
    
    def get_current_time(self) -> datetime:
        """
        Get current date/time.
        In backtest mode, returns simulated time.
        In real mode, returns actual current time.
        
        Returns:
            Current datetime
        """
        return self.time_provider.get_current_time()
    
    async def is_market_open(
        self,
        session: AsyncSession,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """
        Check if market is currently open.
        
        Args:
            session: Database session
            timestamp: Optional specific time to check (defaults to current time)
            
        Returns:
            True if market is open, False otherwise
        """
        check_time = timestamp or self.get_current_time()
        
        # Check if it's a holiday
        is_holiday = await HolidayRepository.is_holiday(
            session,
            check_time.date()
        )
        if is_holiday:
            return False
        
        # Check if it's within trading hours
        is_open = await HolidayRepository.is_market_open_at(
            session,
            check_time
        )
        return is_open
    
    async def get_trading_hours(
        self,
        session: AsyncSession,
        date: date
    ) -> Optional[TradingHours]:
        """
        Get trading hours for a specific date.
        
        Args:
            session: Database session
            date: Date to query
            
        Returns:
            TradingHours object or None if market closed
        """
        return await HolidayRepository.get_trading_hours(session, date)
    
    async def get_holidays(
        self,
        session: AsyncSession,
        start_date: date,
        end_date: date
    ) -> List[TradingHoliday]:
        """
        Get holidays in a date range.
        
        Args:
            session: Database session
            start_date: Start date
            end_date: End date
            
        Returns:
            List of TradingHoliday objects
        """
        return await HolidayRepository.get_holidays(session, start_date, end_date)
    
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
        bars = await MarketDataRepository.get_bars_by_symbol(
            session,
            symbol=symbol,
            interval=interval,
            limit=1
        )
        
        if not bars:
            return None
        
        bar = bars[0]
        return BarData(
            symbol=bar.symbol,
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume
        )
    
    async def stream_bars(
        self,
        session: AsyncSession,
        symbols: List[str]
    ) -> AsyncIterator[BarData]:
        """
        Stream real-time bar data.
        In backtest mode, yields bars from database in chronological order.
        In real mode, would connect to live data feed.
        
        Args:
            session: Database session
            symbols: List of symbols to stream
            
        Yields:
            BarData objects
        """
        # TODO: Implement streaming logic
        # For now, this is a placeholder
        raise NotImplementedError("Bar streaming not yet implemented")
    
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
        # TODO: Implement tick data retrieval
        # For now, return empty list
        logger.warning(f"Tick data not yet implemented for {symbol}")
        return []
    
    async def stream_ticks(
        self,
        session: AsyncSession,
        symbols: List[str]
    ) -> AsyncIterator[TickData]:
        """
        Stream real-time tick data.
        
        Args:
            session: Database session
            symbols: List of symbols to stream
            
        Yields:
            TickData objects
        """
        # TODO: Implement tick streaming
        raise NotImplementedError("Tick streaming not yet implemented")
    
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

        Currently supports Alpaca 1-minute bars only.

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

        if provider != "alpaca":
            logger.warning(
                "API import not implemented for provider=%s, data_type=%s",
                provider,
                data_type,
            )
            raise NotImplementedError(
                f"API import from {provider} not yet implemented for data_type={data_type}"
            )

        # Only 1-minute bars for now
        if normalized_type not in {"1m", "1min", "1-min", "1-min"}:
            logger.warning("Alpaca import supports only 1-minute bars for now (got %s)", data_type)
            raise NotImplementedError(
                f"Alpaca import_from_api currently supports only 1-minute bars (got {data_type})"
            )

        from app.managers.data_manager.integrations.alpaca_data import fetch_1m_bars

        logger.info(
            "Importing 1m bars from Alpaca: symbol=%s start=%s end=%s",
            symbol.upper(),
            start_date,
            end_date,
        )

        bars = await fetch_1m_bars(symbol=symbol, start=start_date, end=end_date)

        if not bars:
            logger.warning("No bars returned from Alpaca for %s", symbol.upper())
            return {
                "success": False,
                "message": "No bars returned from Alpaca",
                "total_rows": 0,
                "imported": 0,
                "symbol": symbol.upper(),
            }

        # Persist via repository
        imported = 0
        try:
            imported, _ = await MarketDataRepository.bulk_create_bars(session, bars)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error importing Alpaca bars into database: %s", exc)
            raise

        # Get quality metrics after import
        quality = await MarketDataRepository.check_data_quality(session, symbol.upper())

        result: Dict[str, Any] = {
            "success": True,
            "message": f"Successfully imported {imported} bars for {symbol.upper()} from Alpaca",
            "total_rows": len(bars),
            "imported": imported,
            "symbol": symbol.upper(),
            "date_range": quality.get("date_range"),
            "quality_score": quality.get("quality_score"),
            "missing_bars": quality.get("missing_bars", 0),
        }

        logger.success(
            "Alpaca import complete for %s: %s/%s bars upserted (quality: %.1f%%)",
            symbol.upper(),
            imported,
            len(bars),
            (quality.get("quality_score", 0) or 0) * 100.0,
        )

        return result
    
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
            use_trading_calendar=True
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
