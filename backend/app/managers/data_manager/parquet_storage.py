"""Parquet Storage Manager for Market Data

Handles storage and retrieval of market data in Parquet format.

New Structure (multi-exchange support):
  data/parquet/<exchange_group>/
    ├── bars/1s/<SYMBOL>/<YEAR>/<MONTH>.parquet
    ├── bars/1m/<SYMBOL>/<YEAR>/<MONTH>.parquet
    ├── bars/1d/<SYMBOL>/<YEAR>.parquet
    └── quotes/<SYMBOL>/<YEAR>/<MONTH>/<DAY>.parquet

TIMEZONE BEHAVIOR:
- Internal storage: All timestamps in UTC
- Input: Dates assumed to be in system timezone (system_manager.timezone)
- Output: Timestamps returned in system timezone by default
- UTC day boundaries: Handled transparently for ET extended hours
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
        logger.info(f"Parquet storage initialized: base={self.base_path}, group={exchange_group}")
    
    def _get_system_timezone(self) -> str:
        """Get system timezone from SystemManager"""
        from app.managers.system_manager import get_system_manager
        
        sys_mgr = get_system_manager()
        return sys_mgr.timezone
    
    def _convert_dates_to_utc(
        self,
        start_date: date,
        end_date: date,
        source_timezone: Optional[str] = None
    ) -> Tuple[datetime, datetime]:
        """
        Convert dates from source timezone to UTC datetime range.
        
        For trading days, includes pre-market to post-market hours to ensure
        complete data retrieval (handles UTC day boundaries).
        
        Args:
            start_date: Start date in source timezone
            end_date: End date in source timezone
            source_timezone: Timezone of dates (uses system default if None)
        
        Returns:
            (utc_start, utc_end) - UTC datetime range
        """
        if source_timezone is None:
            source_timezone = self._get_system_timezone()
        
        from app.managers.system_manager import get_system_manager
        from app.models.database import SessionLocal
        
        sys_mgr = get_system_manager()
        time_mgr = sys_mgr.get_time_manager()
        
        try:
            with SessionLocal() as session:
                # Get trading session to determine hours
                trading_session = time_mgr.get_trading_session(session, start_date)
                
                if trading_session and not trading_session.is_holiday and trading_session.is_trading_day:
                    # Use pre-market to post-market for complete coverage
                    start_time = trading_session.pre_market_open or trading_session.regular_open
                    end_time = trading_session.post_market_close or trading_session.regular_close
                    
                    logger.info(
                        f"[TIMEZONE] Using trading session hours for {start_date}: "
                        f"{start_time} - {end_time} (includes pre/post market)"
                    )
                    
                    # Ensure we have valid time objects
                    if start_time is None or end_time is None:
                        start_time = time_type(0, 0)
                        end_time = time_type(23, 59, 59)
                        logger.warning(f"[TIMEZONE] Trading session had null times, using full day")
                else:
                    # Fallback: full day for non-trading days
                    start_time = time_type(0, 0)
                    end_time = time_type(23, 59, 59)
        except Exception as e:
            logger.warning(f"Could not get trading session, using full day: {e}")
            start_time = time_type(0, 0)
            end_time = time_type(23, 59, 59)
        
        # CRITICAL: Ensure we have date objects, not datetime
        # session_coordinator might pass datetime objects instead of dates
        if isinstance(start_date, datetime):
            logger.warning(f"start_date is datetime, extracting date part: {start_date}")
            start_date = start_date.date()
        if isinstance(end_date, datetime):
            logger.warning(f"end_date is datetime, extracting date part: {end_date}")
            end_date = end_date.date()
        
        # Combine dates with times in source timezone
        source_tz = ZoneInfo(source_timezone)
        start_dt = datetime.combine(start_date, start_time)
        end_dt = datetime.combine(end_date, end_time)
        
        start_aware = start_dt.replace(tzinfo=source_tz)
        end_aware = end_dt.replace(tzinfo=source_tz)
        
        # Convert to UTC
        utc_start = start_aware.astimezone(ZoneInfo("UTC"))
        utc_end = end_aware.astimezone(ZoneInfo("UTC"))
        
        # Log the conversion
        logger.info(
            f"[TIMEZONE] Query range: {start_date} {start_time} - {end_date} {end_time} ({source_timezone})"
        )
        logger.info(
            f"[TIMEZONE] UTC range: {utc_start} - {utc_end}"
        )
        
        logger.debug(
            f"Date conversion: {start_date} - {end_date} ({source_timezone}) → "
            f"{utc_start} - {utc_end} (UTC)"
        )
        
        return utc_start, utc_end
    
    def _read_utc_partitions(
        self,
        data_type: str,
        symbol: str,
        utc_start: datetime,
        utc_end: datetime
    ) -> pd.DataFrame:
        """
        Read bars spanning multiple UTC day partitions.
        
        Handles the case where an ET trading day spans two UTC days
        (e.g., extended hours: 4 AM ET July 2 = 8 AM UTC July 2,
                             8 PM ET July 2 = 12 AM UTC July 3).
        
        Args:
            data_type: '1s', '1m', or '1d'
            symbol: Stock symbol
            utc_start: Start datetime in UTC
            utc_end: End datetime in UTC
        
        Returns:
            DataFrame with bars in UTC timezone
        """
        symbol = symbol.upper()
        frames = []
        
        # Determine all UTC days that need to be read
        current_date = utc_start.date()
        end_date = utc_end.date()
        
        # CRITICAL: Track files already read to avoid reading same monthly file multiple times
        # when UTC range spans multiple days in same month
        files_read = set()
        
        while current_date <= end_date:
            # Get partition file for this UTC day
            file_path = self.get_file_path(
                data_type,
                symbol,
                current_date.year,
                current_date.month if data_type in ['1s', '1m'] else None
            )
            
            # Skip if we already read this file (monthly files contain multiple days)
            if file_path and file_path in files_read:
                logger.debug(f"Skipping already-read file: {file_path.name}")
                current_date += timedelta(days=1)
                continue
            
            if file_path and file_path.exists():
                files_read.add(file_path)
                try:
                    df_partition = pd.read_parquet(file_path)
                    
                    if not df_partition.empty:
                        # CRITICAL: Make timestamps timezone-aware for comparison
                        # Parquet stores as naive UTC, must convert for proper filtering
                        if df_partition['timestamp'].dt.tz is None:
                            df_partition['timestamp'] = pd.to_datetime(df_partition['timestamp'], utc=True)
                        
                        bars_before_filter = len(df_partition)
                        
                        # Filter to requested UTC time range
                        df_partition = df_partition[
                            (df_partition['timestamp'] >= utc_start) &
                            (df_partition['timestamp'] <= utc_end)
                        ]
                        
                        bars_after_filter = len(df_partition)
                        
                        if bars_before_filter != bars_after_filter:
                            logger.info(
                                f"[UTC_FILTER] {file_path.name}: {bars_before_filter} → {bars_after_filter} bars "
                                f"(filtered {bars_before_filter - bars_after_filter} outside UTC range)"
                            )
                        
                        if not df_partition.empty:
                            frames.append(df_partition)
                            logger.debug(f"Read {len(df_partition)} bars from {file_path.name}")
                except Exception as e:
                    logger.error(f"Error reading partition {file_path}: {e}")
            
            current_date += timedelta(days=1)
        
        if not frames:
            return pd.DataFrame()
        
        # Combine all partitions and sort
        df = pd.concat(frames, ignore_index=True)
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Check for duplicate timestamps (should not happen with file deduplication, but verify)
        duplicates = df[df.duplicated(subset=['timestamp'], keep=False)]
        if len(duplicates) > 0:
            logger.error(
                f"[UTC_COMBINE] UNEXPECTED: Found {len(duplicates)} bars with duplicate timestamps "
                f"(unique timestamps: {df['timestamp'].nunique()}, total bars: {len(df)}) - this should not happen!"
            )
            
            # Drop duplicates as safety measure
            bars_before_dedup = len(df)
            df = df.drop_duplicates(subset=['timestamp'], keep='first').reset_index(drop=True)
            bars_dropped = bars_before_dedup - len(df)
            
            logger.warning(
                f"[UTC_COMBINE] Dropped {bars_dropped} duplicate bars as safety measure "
                f"(kept {len(df)} unique bars)"
            )
        
        logger.info(f"[UTC_COMBINE] Combined {len(frames)} partitions into {len(df)} bars (UTC range: {utc_start.date()} to {utc_end.date()})")
        return df
    
    def _ensure_symbol_directory(self, data_type: str, symbol: str, year: int, month: Optional[int] = None) -> Path:
        """Create and return directory path for a symbol's data
        
        Args:
            data_type: One of '1s', '1m', '1d', 'quotes'
            symbol: Stock symbol
            year: Year
            month: Month (only for quotes daily files)
            
        Returns:
            Directory path
        """
        symbol = symbol.upper()
        
        if data_type in ['1s', '1m']:
            # bars/<interval>/<SYMBOL>/<YEAR>/
            dir_path = self.base_path / self.exchange_group / "bars" / data_type / symbol / str(year)
        elif data_type == '1d':
            # bars/1d/<SYMBOL>/
            dir_path = self.base_path / self.exchange_group / "bars" / "1d" / symbol
        elif data_type == 'quotes':
            # quotes/<SYMBOL>/<YEAR>/<MONTH>/
            if month is None:
                raise ValueError("Month required for quotes directory")
            dir_path = self.base_path / self.exchange_group / "quotes" / symbol / str(year) / f"{month:02d}"
        else:
            raise ValueError(f"Invalid data_type: {data_type}")
        
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path
    
    def get_file_path(
        self,
        data_type: str,
        symbol: str,
        year: int,
        month: Optional[int] = None,
        day: Optional[int] = None,
    ) -> Path:
        """Get file path for a given data type and time period.
        
        New structure:
          - bars: <exchange_group>/bars/<interval>/<SYMBOL>/<YEAR>/<MONTH>.parquet
          - quotes: <exchange_group>/quotes/<SYMBOL>/<YEAR>/<MONTH>/<DAY>.parquet
        
        Args:
            data_type: One of '1s', '1m', '1d', 'quotes'
            symbol: Stock symbol (e.g., 'AAPL')
            year: Year
            month: Month (1-12). Required for 1s/1m bars and quotes
            day: Day (1-31). Required for quotes (daily files)
            
        Returns:
            Path to Parquet file
        """
        symbol = symbol.upper()
        
        if data_type in ['1s', '1m']:
            # bars/<interval>/<SYMBOL>/<YEAR>/<MONTH>.parquet
            if month is None:
                raise ValueError(f"Month required for {data_type} bars")
            dir_path = self._ensure_symbol_directory(data_type, symbol, year)
            filename = f"{month:02d}.parquet"
            return dir_path / filename
        
        elif data_type == '1d':
            # bars/1d/<SYMBOL>/<YEAR>.parquet
            dir_path = self._ensure_symbol_directory(data_type, symbol, year)
            filename = f"{year}.parquet"
            return dir_path / filename
        
        elif data_type == 'quotes':
            # quotes/<SYMBOL>/<YEAR>/<MONTH>/<DAY>.parquet (daily files)
            if month is None or day is None:
                raise ValueError("Month and day required for quotes (daily files)")
            dir_path = self._ensure_symbol_directory(data_type, symbol, year, month)
            filename = f"{day:02d}.parquet"
            return dir_path / filename
        
        else:
            raise ValueError(f"Invalid data_type: {data_type}. Must be 1s, 1m, 1d, or quotes")
    
    def aggregate_ticks_to_1s(self, ticks: List[Dict]) -> List[Dict]:
        """Aggregate trade ticks to 1-second bars.
        
        Args:
            ticks: List of tick dicts with timestamp, price, size
            
        Returns:
            List of 1s bar dicts
        """
        if not ticks:
            return []
        
        logger.info(f"Aggregating {len(ticks)} ticks to 1s bars...")
        
        # Group by second
        by_second = defaultdict(list)
        
        for tick in ticks:
            ts = tick['timestamp']
            # Round down to second (remove microseconds)
            second_key = ts.replace(microsecond=0)
            by_second[second_key].append(tick)
        
        # Build 1s bars
        bars_1s = []
        for second, ticks_in_second in sorted(by_second.items()):
            prices = [t['close'] for t in ticks_in_second]  # ticks have 'close' as price
            volumes = [t['volume'] for t in ticks_in_second]
            
            bar = {
                'symbol': ticks_in_second[0]['symbol'],
                'timestamp': second,
                'open': ticks_in_second[0]['close'],  # First tick price
                'high': max(prices),
                'low': min(prices),
                'close': ticks_in_second[-1]['close'],  # Last tick price
                'volume': sum(volumes),
                'trade_count': len(ticks_in_second),
            }
            bars_1s.append(bar)
        
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
        
        Automatically splits by month.
        
        Args:
            bars: List of bar dicts
            data_type: '1s', '1m', or '1d'
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
        
        # Ensure timestamp is datetime
        # If timezone-aware, convert to UTC; if naive, assume already UTC
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is not None:
            # Has timezone info, convert to UTC
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
        else:
            # Naive timestamp, assume it's already UTC and mark it
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        
        # Sort by timestamp
        df = df.sort_values('timestamp')
        
        # Group by year-month (extract directly to avoid timezone warning)
        df['year'] = df['timestamp'].dt.year
        df['month'] = df['timestamp'].dt.month
        grouped = df.groupby(['year', 'month']) if data_type != '1d' else df.groupby(['year'])
        
        total_written = 0
        files_written = []
        
        for group_key, group_df in grouped:
            if data_type == '1d':
                year = group_key
                month = None
            else:
                year, month = group_key
            
            file_path = self.get_file_path(data_type, symbol, year, month)
            
            # Drop helper columns
            group_df = group_df.drop(columns=['year', 'month'])
            
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
        
        # Ensure timestamp is datetime with UTC timezone
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        
        # Sort by timestamp
        df = df.sort_values('timestamp')
        
        # Group by year-month-day (daily files)
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
        - Input dates assumed to be in system timezone (system_manager.timezone)
        - Output timestamps returned in system timezone by default
        - Internal storage is UTC (transparent to caller)
        - Handles UTC day boundaries for ET extended hours automatically
        
        Args:
            data_type: '1s', '1m', or '1d'
            symbol: Stock symbol
            start_date: Optional start date in system timezone
            end_date: Optional end date in system timezone
            request_timezone: Optional override for output timezone
                            If None, uses system_manager.timezone
            regular_hours_only: If True, filter to regular trading hours only
                               (09:30-16:00 ET). Default False keeps all hours.
        
        Returns:
            DataFrame with bars in request_timezone (or system timezone)
        
        Examples:
            # Standard usage (system timezone)
            df = storage.read_bars("1m", "AAPL", date(2025, 7, 2), date(2025, 7, 2))
            # df['timestamp'] is in ET (system timezone)
            
            # Advanced: Get ET data in UTC
            df = storage.read_bars("1m", "AAPL", date(2025, 7, 2), date(2025, 7, 2),
                                  request_timezone="UTC")
            # df['timestamp'] is in UTC
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
            # Read specific date range with UTC day boundary handling
            # Convert input dates (system timezone) to UTC range
            utc_start, utc_end = self._convert_dates_to_utc(
                start_date, end_date, request_timezone
            )
            
            # Read from UTC partitions (may span multiple days!)
            result = self._read_utc_partitions(data_type, symbol, utc_start, utc_end)
        
        if result.empty:
            logger.warning(f"No bars found for {symbol} {data_type}")
            return result
        
        # Convert output to request timezone
        if 'timestamp' in result.columns:
            # Ensure timestamps are timezone-aware UTC
            if result['timestamp'].dt.tz is None:
                result['timestamp'] = pd.to_datetime(result['timestamp'], utc=True)
            
            # Convert to request timezone
            result['timestamp'] = result['timestamp'].dt.tz_convert(request_timezone)
        
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
            # Read specific date range with UTC day boundary handling
            utc_start, utc_end = self._convert_dates_to_utc(
                start_date, end_date, request_timezone
            )
            result = self._read_utc_partitions('quotes', symbol, utc_start, utc_end)
        
        if result.empty:
            return result
        
        # Convert output to request timezone
        if 'timestamp' in result.columns:
            if result['timestamp'].dt.tz is None:
                result['timestamp'] = pd.to_datetime(result['timestamp'], utc=True)
            result['timestamp'] = result['timestamp'].dt.tz_convert(request_timezone)
        
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
        
        For quotes (daily files), iterates through each day.
        For bars, iterates through each month (1s, 1m) or year (1d).
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
            # Bars: iterate by month (1s, 1m) or year (1d)
            current = start_date.replace(day=1)
            end = end_date.replace(day=1)
            
            while current <= end:
                year = current.year
                month = current.month if data_type != '1d' else None
                
                file_path = self.get_file_path(data_type, symbol, year, month)
                if file_path.exists():
                    files.append(file_path)
                
                # Move to next month (or year for daily)
                if data_type == '1d':
                    current = current.replace(year=current.year + 1)
                else:
                    if current.month == 12:
                        current = current.replace(year=current.year + 1, month=1)
                    else:
                        current = current.replace(month=current.month + 1)
        
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
