"""Parquet Storage Manager for Market Data

Handles storage and retrieval of market data in Parquet format.

Unified Structure (multi-exchange support + ANY interval):
  data/parquet/<exchange_group>/
    ├── bars/<interval>/<SYMBOL>/<YEAR>/<MONTH>/<DAY>.parquet  (daily files for 1s, 1m)
    ├── bars/<interval>/<SYMBOL>/<YEAR>.parquet                (yearly files for 1d, 1w)
    └── quotes/<SYMBOL>/<YEAR>/<MONTH>/<DAY>.parquet           (daily files)

Storage Strategy (automatic):
  - Sub-daily intervals (1s, 1m, Ns, Nm) → Daily files (session-aligned)
  - Daily+ intervals (1d, 1w, Nd, Nw) → Yearly files

Examples:
  - 1s   → bars/1s/AAPL/2025/07/15.parquet (daily - 1 file per trading day)
  - 1m   → bars/1m/AAPL/2025/07/15.parquet (daily - 1 file per trading day)
  - 60m  → bars/60m/AAPL/2025/12/31.parquet (daily - use minutes NOT hours)
  - 1d   → bars/1d/AAPL/2025.parquet (yearly - 1 file per year)
  - 1w   → bars/1w/AAPL/2025.parquet (yearly - 1 file per year)

Rationale for daily files (seconds/minutes):
  - Perfect alignment with session-based processing
  - Faster single-day access (~500KB vs ~15MB)
  - Cleaner incremental updates (append new day)
  - Better gap management (missing file = missing day)
  - Memory efficient for high-frequency data

Note: Hourly intervals (1h, 2h) are NOT supported. Use minute intervals (60m, 120m).

TIMEZONE ARCHITECTURE:
- Storage: Timestamps are timezone-aware in EXCHANGE TIMEZONE
- Exchange group implies timezone (US_EQUITY = America/New_York)
- Files grouped by exchange timezone day (not UTC)
- NO conversion on read/write - data stored and returned as-is
- Rest of system works exclusively in exchange timezone
"""
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime, date, timezone, time as time_type, timedelta
from collections import defaultdict
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from app.config import settings
from app.logger import logger
from app.managers.data_manager.symbol_exchange_mapping import (
    get_symbol_exchange,
    register_symbol
)
from app.managers.data_manager.interval_storage import IntervalStorageStrategy


class ParquetStorage:
    """Manager for Parquet-based market data storage."""
    
    def __init__(self, base_path: Optional[str] = None, exchange_group: str = "US_EQUITY"):
        """Initialize Parquet storage manager.
        
        Args:
            base_path: Base directory for Parquet files. Defaults to data/parquet/
            exchange_group: Exchange group for data storage (e.g., 'US_EQUITY')
        """
        self.base_path = Path(base_path or "data/parquet")
        self.exchange_group = exchange_group
        
        # Initialize unified storage strategy
        self.storage_strategy = IntervalStorageStrategy(self.base_path, exchange_group)
        
        logger.info(f"Parquet storage initialized: base={self.base_path}, group={exchange_group}")
    
    def _get_system_timezone(self) -> str:
        """Get system timezone from SystemManager"""
        from app.managers.system_manager import get_system_manager
        
        sys_mgr = get_system_manager()
        if sys_mgr.timezone is None:
            logger.warning("SystemManager timezone not initialized, using default: America/New_York")
            return "America/New_York"
        return sys_mgr.timezone
    
    # OLD UTC CONVERSION METHODS REMOVED
    # Storage now uses exchange timezone, no UTC conversion needed
    # See EXCHANGE_TIMEZONE_STORAGE.md for details
    
    def _ensure_symbol_directory(self, data_type: str, symbol: str, year: int, month: Optional[int] = None) -> Path:
        """Create and return directory path for a symbol's data.
        
        Uses unified storage strategy for bar intervals.
        
        Args:
            data_type: Interval string (e.g., '1s', '1m', '1h', '1d', '1w') or 'quotes'
            symbol: Stock symbol
            year: Year
            month: Month (only for quotes daily files)
            
        Returns:
            Directory path
        """
        symbol = symbol.upper()
        
        if data_type == 'quotes':
            # quotes/<SYMBOL>/<YEAR>/<MONTH>/
            if month is None:
                raise ValueError("Month required for quotes directory")
            dir_path = self.base_path / self.exchange_group / "quotes" / symbol / str(year) / f"{month:02d}"
            dir_path.mkdir(parents=True, exist_ok=True)
            return dir_path
        else:
            # Bar intervals: use unified storage strategy
            return self.storage_strategy.get_directory_path(data_type, symbol, year, month)
    
    def get_file_path(
        self,
        data_type: str,
        symbol: str,
        year: int,
        month: Optional[int] = None,
        day: Optional[int] = None,
    ) -> Path:
        """Get file path for a given data type and time period.
        
        Uses unified storage strategy for ANY bar interval.
        
        Structure:
          - bars: <exchange_group>/bars/<interval>/<SYMBOL>/<YEAR>/[<MONTH>.parquet or <YEAR>.parquet]
          - quotes: <exchange_group>/quotes/<SYMBOL>/<YEAR>/<MONTH>/<DAY>.parquet
        
        Args:
            data_type: Interval string (e.g., '1s', '1m', '1h', '1d', '1w') or 'quotes'
            symbol: Stock symbol (e.g., 'AAPL')
            year: Year
            month: Month (1-12). Required for sub-daily intervals and quotes
            day: Day (1-31). Required for quotes (daily files)
            
        Returns:
            Path to Parquet file
        """
        symbol = symbol.upper()
        
        if data_type == 'quotes':
            # quotes/<SYMBOL>/<YEAR>/<MONTH>/<DAY>.parquet (daily files)
            if month is None or day is None:
                raise ValueError("Month and day required for quotes (daily files)")
            dir_path = self._ensure_symbol_directory(data_type, symbol, year, month)
            filename = f"{day:02d}.parquet"
            return dir_path / filename
        else:
            # Bar intervals: use unified storage strategy
            return self.storage_strategy.get_file_path(data_type, symbol, year, month, day)
    
    def aggregate_ticks_to_1s(self, ticks: List[Dict]) -> List[Dict]:
        """Aggregate trade ticks to 1-second bars.
        
        Uses unified bar aggregation framework.
        
        Args:
            ticks: List of tick dicts with timestamp, symbol, close, volume
            
        Returns:
            List of 1s bar dicts
        """
        if not ticks:
            return []
        
        logger.info(f"Aggregating {len(ticks)} ticks to 1s bars...")
        
        # Use unified framework
        from app.managers.data_manager.bar_aggregation import (
            BarAggregator,
            AggregationMode
        )
        
        aggregator = BarAggregator(
            source_interval="tick",
            target_interval="1s",
            time_manager=None,  # Not needed for TIME_WINDOW mode
            mode=AggregationMode.TIME_WINDOW
        )
        
        bars = aggregator.aggregate(
            ticks,
            require_complete=False,  # Allow any number of ticks
            check_continuity=False   # Ticks can be sparse
        )
        
        # Convert BarData objects back to dicts
        bars_1s = [bar.dict() for bar in bars]
        
        logger.info(f"Created {len(bars_1s)} 1s bars from {len(ticks)} ticks")
        return bars_1s
    
    def aggregate_quotes_by_second(self, quotes: List[Dict]) -> List[Dict]:
        """Aggregate quotes to 1 per second (tightest spread).
        
        Args:
            quotes: List of quote dicts with timestamp, bid_price, ask_price, etc.
            
        Returns:
            List of aggregated quote dicts (1 per second)
        """
        if not quotes:
            return []
        
        logger.info(f"Aggregating {len(quotes)} quotes to 1 per second (tightest spread)...")
        
        # Group by second
        by_second = defaultdict(list)
        
        for quote in quotes:
            ts = quote['timestamp']
            # Round down to second
            second_key = ts.replace(microsecond=0)
            
            # Calculate spread if not present
            if 'spread' not in quote:
                if quote.get('ask_price') and quote.get('bid_price'):
                    quote['spread'] = quote['ask_price'] - quote['bid_price']
                else:
                    quote['spread'] = float('inf')  # Invalid quote
            
            by_second[second_key].append(quote)
        
        # Keep quote with tightest spread per second
        aggregated = []
        for second, quotes_in_second in sorted(by_second.items()):
            # Pick quote with smallest spread
            best_quote = min(quotes_in_second, key=lambda q: q.get('spread', float('inf')))
            
            # Update timestamp to rounded second
            best_quote['timestamp'] = second
            aggregated.append(best_quote)
        
        logger.info(f"Aggregated to {len(aggregated)} quotes (from {len(quotes)})")
        return aggregated
    
    def write_bars(
        self,
        bars: List[Dict],
        data_type: str,
        symbol: str,
        compression: str = 'zstd',
        append: bool = False,
    ) -> Tuple[int, Path]:
        """Write bars to Parquet file(s).
        
        Automatically splits by granularity:
        - Sub-daily intervals (1s, 1m): One file per day
        - Daily+ intervals (1d, 1w): One file per year
        
        Args:
            bars: List of bar dicts
            data_type: Interval string (e.g., '1s', '1m', '60m', '1d', '1w')
            symbol: Stock symbol
            compression: Compression codec (zstd, snappy, gzip, none)
            append: If True, append to existing file (reads, merges, writes)
            
        Returns:
            (total_written, file_paths): Count and list of files written
        """
        if not bars:
            logger.warning("No bars to write")
            return 0, []
        
        symbol = symbol.upper()
        
        # Convert to DataFrame
        df = pd.DataFrame(bars)
        
        # Ensure timestamp is datetime and in exchange timezone
        # Exchange group implies timezone (US_EQUITY = America/New_York)
        # Data is stored timezone-aware but in exchange timezone (NO conversion)
        exchange_tz = self._get_system_timezone()
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is not None:
            # Has timezone info, ensure it's in exchange timezone
            df['timestamp'] = df['timestamp'].dt.tz_convert(exchange_tz)
        else:
            # Naive timestamp, assume it's already in exchange timezone
            df['timestamp'] = df['timestamp'].dt.tz_localize(exchange_tz)
        
        # Sort by timestamp
        df = df.sort_values('timestamp')
        
        # Determine granularity using storage strategy
        from app.managers.data_manager.interval_storage import FileGranularity
        
        granularity = self.storage_strategy.get_file_granularity(data_type)
        
        # Extract date components directly (already in exchange timezone)
        # No conversion needed - timestamps are stored in exchange timezone
        # July 15 ET trading day → bars/1s/AAPL/2025/07/15.parquet
        df['year'] = df['timestamp'].dt.year
        df['month'] = df['timestamp'].dt.month
        df['day'] = df['timestamp'].dt.day
        
        # Group based on granularity
        if granularity == FileGranularity.DAILY:
            # Sub-daily intervals: one file per day
            grouped = df.groupby(['year', 'month', 'day'])
        else:
            # Daily+ intervals: one file per year
            grouped = df.groupby(['year'])
        
        total_written = 0
        files_written = []
        
        for group_key, group_df in grouped:
            if granularity == FileGranularity.YEARLY:
                # group_key is a tuple when grouping by single column: (2024,)
                year = group_key[0] if isinstance(group_key, tuple) else group_key
                month = None
                day = None
            else:
                # DAILY granularity
                year, month, day = group_key
            
            file_path = self.get_file_path(data_type, symbol, year, month, day)
            
            # Drop helper columns
            group_df = group_df.drop(columns=['year', 'month', 'day'])
            
            # Handle append mode
            if append and file_path.exists():
                logger.info(f"Appending to existing file: {file_path}")
                existing_df = pd.read_parquet(file_path)
                group_df = pd.concat([existing_df, group_df])
                
                # Remove duplicates (keep last)
                group_df = group_df.drop_duplicates(subset=['symbol', 'timestamp'], keep='last')
                group_df = group_df.sort_values('timestamp')
            
            # Write to Parquet
            group_df.to_parquet(
                file_path,
                compression=compression,
                index=False,
                engine='pyarrow',
            )
            
            rows_written = len(group_df)
            total_written += rows_written
            files_written.append(file_path)
            
            logger.info(
                f"Wrote {rows_written} {data_type} bars to {file_path.name} "
                f"(size: {file_path.stat().st_size / 1024:.1f} KB)"
            )
        
        return total_written, files_written
    
    def write_quotes(
        self,
        quotes: List[Dict],
        symbol: str,
        compression: str = 'zstd',
        append: bool = False,
    ) -> Tuple[int, List[Path]]:
        """Write quotes to Parquet file(s).
        
        Automatically splits by day (one file per day).
        
        Args:
            quotes: List of quote dicts
            symbol: Stock symbol
            compression: Compression codec
            append: If True, append to existing file
            
        Returns:
            (total_written, file_paths): Count and list of files written
        """
        if not quotes:
            logger.warning("No quotes to write")
            return 0, []
        
        symbol = symbol.upper()
        
        # Convert to DataFrame
        df = pd.DataFrame(quotes)
        
        # Ensure timestamp is datetime and in exchange timezone
        # Exchange group implies timezone (US_EQUITY = America/New_York)
        # Data is stored timezone-aware but in exchange timezone (NO conversion)
        exchange_tz = self._get_system_timezone()
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is not None:
            # Has timezone info, ensure it's in exchange timezone
            df['timestamp'] = df['timestamp'].dt.tz_convert(exchange_tz)
        else:
            # Naive timestamp, assume it's already in exchange timezone
            df['timestamp'] = df['timestamp'].dt.tz_localize(exchange_tz)
        
        # Sort by timestamp
        df = df.sort_values('timestamp')
        
        # Extract date components directly (already in exchange timezone)
        # No conversion needed - timestamps are stored in exchange timezone
        df['year'] = df['timestamp'].dt.year
        df['month'] = df['timestamp'].dt.month
        df['day'] = df['timestamp'].dt.day
        grouped = df.groupby(['year', 'month', 'day'])
        
        total_written = 0
        files_written = []
        
        for (year, month, day), group_df in grouped:
            file_path = self.get_file_path('quotes', symbol, year, month, day)
            
            # Drop helper columns
            group_df = group_df.drop(columns=['year', 'month', 'day'])
            
            # Handle append mode
            if append and file_path.exists():
                logger.info(f"Appending to existing file: {file_path}")
                existing_df = pd.read_parquet(file_path)
                group_df = pd.concat([existing_df, group_df])
                
                # Remove duplicates
                group_df = group_df.drop_duplicates(subset=['symbol', 'timestamp'], keep='last')
                group_df = group_df.sort_values('timestamp')
            
            # Write to Parquet
            group_df.to_parquet(
                file_path,
                compression=compression,
                index=False,
                engine='pyarrow',
            )
            
            rows_written = len(group_df)
            total_written += rows_written
            files_written.append(file_path)
            
            logger.info(
                f"Wrote {rows_written} quotes to {file_path.name} "
                f"(size: {file_path.stat().st_size / 1024:.1f} KB)"
            )
        
        return total_written, files_written
    
    def read_bars(
        self,
        data_type: str,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        request_timezone: Optional[str] = None,
        regular_hours_only: bool = False
    ) -> pd.DataFrame:
        """Read bars from Parquet file(s).
        
        TIMEZONE BEHAVIOR:
        - Storage: Timestamps are timezone-aware in exchange timezone
        - Exchange group implies timezone (US_EQUITY = America/New_York)
        - Returns: Data returned as-is (no conversion) in exchange timezone
        - Input dates: Assumed to be in exchange timezone
        
        Args:
            data_type: Interval string (e.g., '1s', '1m', '60m', '1d', '1w')
            symbol: Stock symbol
            start_date: Optional start date in exchange timezone
            end_date: Optional end date in exchange timezone
            request_timezone: DEPRECATED - data always returned in exchange timezone
            regular_hours_only: If True, filter to regular trading hours only
                               (09:30-16:00 ET). Default False keeps all hours.
        
        Returns:
            DataFrame with bars in exchange timezone (timezone-aware)
        
        Examples:
            # Standard usage
            df = storage.read_bars("1m", "AAPL", date(2025, 7, 2), date(2025, 7, 2))
            # df['timestamp'] is timezone-aware in ET (America/New_York)
        """
        symbol = symbol.upper()
        
        # Default to system timezone
        if request_timezone is None:
            request_timezone = self._get_system_timezone()
        
        # Determine which files to read
        if start_date is None and end_date is None:
            # Read all available files for this symbol
            symbol_dir = self.base_path / self.exchange_group / "bars" / data_type / symbol
            if not symbol_dir.exists():
                logger.warning(f"No data directory found for {symbol} {data_type}")
                return pd.DataFrame()
            
            files = sorted(symbol_dir.rglob("*.parquet"))
            
            # Read and concatenate all files
            dfs = []
            for file_path in files:
                try:
                    df = pd.read_parquet(file_path)
                    dfs.append(df)
                except Exception as e:
                    logger.error(f"Error reading {file_path}: {e}")
            
            if not dfs:
                logger.warning(f"No Parquet files found for {symbol} {data_type}")
                return pd.DataFrame()
            
            result = pd.concat(dfs, ignore_index=True)
            result = result.sort_values('timestamp').reset_index(drop=True)
            
        else:
            # Read specific date range
            # Files are organized by exchange timezone day, so this is straightforward
            start_dt = datetime.combine(start_date, datetime.min.time())
            end_dt = datetime.combine(end_date, datetime.max.time())
            
            logger.info(f"[read_bars] Querying {data_type} for {symbol}: {start_dt} to {end_dt}")
            
            files = self._get_files_for_date_range(
                data_type, symbol,
                start_dt,
                end_dt
            )
            
            logger.info(f"[read_bars] Found {len(files)} files for {symbol} {data_type}: {files}")
            
            if not files:
                logger.warning(f"No files found for {symbol} {data_type} in date range {start_date} to {end_date}")
                return pd.DataFrame()
            
            # Read and concatenate files
            dfs = []
            for file_path in files:
                try:
                    df = pd.read_parquet(file_path)
                    dfs.append(df)
                except Exception as e:
                    logger.error(f"Error reading {file_path}: {e}")
            
            if not dfs:
                return pd.DataFrame()
            
            result = pd.concat(dfs, ignore_index=True)
            result = result.sort_values('timestamp').reset_index(drop=True)
        
        if result.empty:
            logger.warning(f"No bars found for {symbol} {data_type}")
            return result
        
        # Data is already in exchange timezone - no conversion needed
        # Timestamps are timezone-aware as stored in parquet
        
        # Filter to regular trading hours if requested
        if regular_hours_only and not result.empty and start_date is not None:
            from app.managers.system_manager import get_system_manager
            from app.models.database import SessionLocal
            
            sys_mgr = get_system_manager()
            time_mgr = sys_mgr.get_time_manager()
            
            # CRITICAL: Ensure we have a date object for trading session query
            # start_date might be a datetime (from session_coordinator passing datetime objects)
            query_date = start_date.date() if isinstance(start_date, datetime) else start_date
            
            # Get regular trading hours for the start date
            try:
                logger.info(f"[FILTER] Querying trading session for date: {query_date} (original: {start_date}, type: {type(start_date)})")
                
                with SessionLocal() as session:
                    trading_session = time_mgr.get_trading_session(session, query_date)
                    
                    if trading_session:
                        logger.info(
                            f"[FILTER] {start_date}: Trading session: "
                            f"is_early_close={trading_session.is_early_close}, "
                            f"regular_close={trading_session.regular_close}"
                        )
                    
                    if trading_session and not trading_session.is_holiday:
                        # Create timezone-aware market open/close times using the date object
                        from zoneinfo import ZoneInfo
                        tz = ZoneInfo(request_timezone)
                        market_open = datetime.combine(query_date, trading_session.regular_open).replace(tzinfo=tz)
                        market_close = datetime.combine(query_date, trading_session.regular_close).replace(tzinfo=tz)
                        
                        # Log early close detection
                        if trading_session.is_early_close:
                            logger.info(
                                f"[FILTER] Early close day {start_date}: market closes at {trading_session.regular_close} "
                                f"(holiday: {trading_session.holiday_name})"
                            )
                        
                        # Filter bars
                        bars_before = len(result)
                        logger.info(f"[FILTER] {start_date}: Before filtering: {bars_before} bars (range: {market_open.time()}-{market_close.time()})")
                        
                        # Apply filter (make a copy to avoid view issues)
                        result = result[(result['timestamp'] >= market_open) & (result['timestamp'] <= market_close)].copy()
                        bars_filtered = bars_before - len(result)
                        
                        logger.info(
                            f"[FILTER] {start_date}: Filtered {bars_filtered}/{bars_before} extended hours bars for {symbol} "
                            f"(kept {len(result)} regular hours: {market_open.time()}-{market_close.time()})"
                        )
                        
                        # Debug: Show first and last bar after filtering
                        if len(result) > 0:
                            first_bar_time = result.iloc[0]['timestamp'].time()
                            last_bar_time = result.iloc[-1]['timestamp'].time()
                            logger.info(
                                f"[FILTER] {start_date}: After filtering: First bar={first_bar_time}, Last bar={last_bar_time}"
                            )
            except Exception as e:
                logger.warning(f"Could not filter to regular hours: {e}, returning all bars")
        
        logger.info(
            f"Loaded {len(result)} {data_type} bars for {symbol} "
            f"(timezone: {request_timezone})"
        )
        return result
    
    def read_quotes(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        request_timezone: Optional[str] = None
    ) -> pd.DataFrame:
        """Read quotes from Parquet file(s).
        
        TIMEZONE BEHAVIOR:
        - Input dates assumed to be in system timezone
        - Output timestamps returned in system timezone by default
        - Internal storage is UTC
        
        Args:
            symbol: Stock symbol
            start_date: Optional start date in system timezone
            end_date: Optional end date in system timezone
            request_timezone: Optional override for output timezone
            
        Returns:
            DataFrame with quotes in request_timezone
        """
        symbol = symbol.upper()
        
        # Default to system timezone
        if request_timezone is None:
            request_timezone = self._get_system_timezone()
        
        # Determine which files to read
        if start_date is None and end_date is None:
            # Read all available quotes
            symbol_dir = self.base_path / self.exchange_group / "quotes" / symbol
            if not symbol_dir.exists():
                logger.warning(f"No quotes directory found for {symbol}")
                return pd.DataFrame()
            
            files = sorted(symbol_dir.rglob("*.parquet"))
            
            dfs = []
            for file_path in files:
                try:
                    df = pd.read_parquet(file_path)
                    dfs.append(df)
                except Exception as e:
                    logger.error(f"Error reading {file_path}: {e}")
            
            if not dfs:
                return pd.DataFrame()
            
            result = pd.concat(dfs, ignore_index=True)
            result = result.sort_values('timestamp').reset_index(drop=True)
        else:
            # Read specific date range
            # Quotes organized by exchange timezone day
            files = self._get_files_for_date_range(
                'quotes', symbol,
                datetime.combine(start_date, datetime.min.time()),
                datetime.combine(end_date, datetime.max.time())
            )
            
            if not files:
                logger.warning(f"No quote files found for {symbol} in date range")
                return pd.DataFrame()
            
            dfs = []
            for file_path in files:
                try:
                    df = pd.read_parquet(file_path)
                    dfs.append(df)
                except Exception as e:
                    logger.error(f"Error reading {file_path}: {e}")
            
            if not dfs:
                return pd.DataFrame()
            
            result = pd.concat(dfs, ignore_index=True)
            result = result.sort_values('timestamp').reset_index(drop=True)
        
        if result.empty:
            return result
        
        # Data already in exchange timezone - no conversion needed
        # Timestamps are timezone-aware as stored in parquet
        
        logger.info(f"Loaded {len(result)} quotes for {symbol}")
        return result
    
    def _get_files_for_date_range(
        self,
        data_type: str,
        symbol: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> List[Path]:
        """Get list of files covering a date range.
        
        For quotes: iterates through each day (daily files).
        For bars: uses storage strategy to determine granularity:
          - Sub-daily (1s, 1m): iterates through each day
          - Daily+ (1d, 1w): iterates through each year
        """
        if start_date is None or end_date is None:
            # Fallback to all files (handled by caller)
            return []
        
        files = []
        
        if data_type == 'quotes':
            # Quotes are stored daily - iterate through each day
            from datetime import timedelta
            current = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
            
            while current <= end:
                year = current.year
                month = current.month
                day = current.day
                
                file_path = self.get_file_path(data_type, symbol, year, month, day)
                if file_path.exists():
                    files.append(file_path)
                
                current += timedelta(days=1)
        else:
            # Bars: use storage strategy to determine granularity
            from app.managers.data_manager.interval_storage import FileGranularity
            from datetime import timedelta
            
            granularity = self.storage_strategy.get_file_granularity(data_type)
            
            if granularity == FileGranularity.DAILY:
                # Daily files: iterate through each day
                current = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
                end = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
                
                while current <= end:
                    year = current.year
                    month = current.month
                    day = current.day
                    
                    file_path = self.get_file_path(data_type, symbol, year, month, day)
                    if file_path.exists():
                        files.append(file_path)
                    
                    current += timedelta(days=1)
            else:
                # Yearly files: iterate through years
                current = start_date.replace(month=1, day=1)
                end = end_date.replace(month=1, day=1)
                
                logger.info(f"[_get_files] YEARLY granularity for {data_type}, iterating {current.year} to {end.year}")
                
                while current <= end:
                    year = current.year
                    
                    file_path = self.get_file_path(data_type, symbol, year, None, None)
                    logger.info(f"[_get_files] Checking {file_path}, exists={file_path.exists()}")
                    
                    if file_path.exists():
                        files.append(file_path)
                    
                    current = current.replace(year=current.year + 1)
        
        logger.info(f"[_get_files] Returning {len(files)} files for {symbol} {data_type}")
        return files
    
    def get_available_symbols(self, data_type: str = '1m') -> List[str]:
        """Get list of symbols with available data.
        
        Args:
            data_type: Data type to check
            
        Returns:
            List of symbols
        """
        # New structure: <exchange_group>/bars/<interval>/<SYMBOL>/ or <exchange_group>/quotes/<SYMBOL>/
        if data_type == 'quotes':
            file_dir = self.base_path / self.exchange_group / "quotes"
        else:
            file_dir = self.base_path / self.exchange_group / "bars" / data_type
        
        if not file_dir.exists():
            return []
        
        # Extract symbols from directory names (each symbol has its own folder)
        symbols = set()
        for symbol_dir in file_dir.glob("*"):
            if symbol_dir.is_dir():
                symbols.add(symbol_dir.name)
        
        return sorted(symbols)
    
    def get_available_intervals(self, symbol: str) -> List[str]:
        """Get list of available bar intervals for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            List of interval strings (e.g., ['1s', '1m', '1d'])
        """
        # Scan bars directory for intervals
        bars_dir = self.base_path / self.exchange_group / "bars"
        
        if not bars_dir.exists():
            return []
        
        intervals = set()
        
        # Check each interval directory
        for interval_dir in bars_dir.glob("*"):
            if interval_dir.is_dir():
                # Check if this interval has data for the symbol
                symbol_dir = interval_dir / symbol.upper()
                if symbol_dir.exists() and symbol_dir.is_dir():
                    # Check if there are any parquet files
                    has_data = any(symbol_dir.rglob("*.parquet"))
                    if has_data:
                        intervals.add(interval_dir.name)
        
        # Also check for quotes
        quotes_dir = self.base_path / self.exchange_group / "quotes" / symbol.upper()
        if quotes_dir.exists() and quotes_dir.is_dir():
            has_quotes = any(quotes_dir.rglob("*.parquet"))
            if has_quotes:
                intervals.add("quotes")
        
        return sorted(intervals)
    
    def get_date_range(self, data_type: str, symbol: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Get earliest and latest dates available for a symbol.
        
        Args:
            data_type: Data type to check
            symbol: Stock symbol
            
        Returns:
            (min_date, max_date) or (None, None) if no data
        """
        try:
            df = self.read_bars(data_type, symbol) if data_type != 'quotes' else self.read_quotes(symbol)
            if df.empty:
                return None, None
            return df['timestamp'].min(), df['timestamp'].max()
        except Exception as e:
            logger.error(f"Error getting date range: {e}")
            return None, None


# Global instance
parquet_storage = ParquetStorage()
