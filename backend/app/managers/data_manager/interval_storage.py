"""Interval Storage Strategy

Generic storage path determination for ANY interval type.
No hardcoding - uses parse_interval() to determine storage strategy.
"""
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Tuple
from enum import Enum

from app.threads.quality.requirement_analyzer import parse_interval, IntervalType
from app.logger import logger


class FileGranularity(Enum):
    """File storage granularity based on interval type."""
    DAILY = "daily"      # Sub-daily intervals (1s, 1m, Ns, Nm) - one file per day
    YEARLY = "yearly"    # Daily+ intervals (1d, 1w, Nd, Nw) - one file per year


class IntervalStorageStrategy:
    """Unified storage strategy for ANY interval type.
    
    Determines storage path structure based on interval characteristics:
    - Sub-daily intervals (seconds, minutes) → Daily files (session-aligned)
    - Daily+ intervals (days, weeks) → Yearly files
    
    Example paths:
        1s  → bars/1s/AAPL/2025/07/01.parquet (daily)
        1m  → bars/1m/AAPL/2025/07/15.parquet (daily)
        5m  → bars/5m/AAPL/2025/12/31.parquet (daily)
        1d  → bars/1d/AAPL/2025.parquet (yearly)
        1w  → bars/1w/AAPL/2025.parquet (yearly)
    
    Rationale for daily files:
    - Perfect alignment with session-based processing
    - Faster single-day access (load ~500KB not ~15MB)
    - Cleaner incremental updates (append new day, don't touch existing)
    - Better gap management (missing file = missing day)
    - Memory efficient for high-frequency data
    
    Note: Hourly intervals are NOT supported per system design.
    """
    
    def __init__(self, base_path: Path, exchange_group: str):
        """Initialize storage strategy.
        
        Args:
            base_path: Base directory for all data
            exchange_group: Exchange group identifier
        """
        self.base_path = base_path
        self.exchange_group = exchange_group
    
    def get_file_granularity(self, interval: str) -> FileGranularity:
        """Determine file granularity for an interval.
        
        Args:
            interval: Interval string (e.g., "1s", "1m", "1d", "1w")
        
        Returns:
            FileGranularity enum
            
        Raises:
            ValueError: If hourly intervals are provided (not supported)
        """
        try:
            interval_info = parse_interval(interval)
        except ValueError as e:
            # Re-raise with more context
            raise ValueError(f"Failed to parse interval '{interval}': {e}") from e
        
        # Note: Hourly intervals are not supported per system design
        # They would be rejected by parse_interval() with a helpful error message
        
        # Sub-daily intervals (seconds, minutes) use daily files
        # Rationale: Session-aligned, faster access, cleaner updates
        if interval_info.type in [IntervalType.SECOND, IntervalType.MINUTE]:
            return FileGranularity.DAILY
        
        # Daily+ intervals (days, weeks) use yearly files
        else:
            return FileGranularity.YEARLY
    
    def get_directory_path(
        self,
        interval: str,
        symbol: str,
        year: int,
        month: Optional[int] = None
    ) -> Path:
        """Get directory path for an interval.
        
        Args:
            interval: Interval string
            symbol: Stock symbol
            year: Year
            month: Month (required for daily files, used as subdirectory)
        
        Returns:
            Directory path
        """
        symbol = symbol.upper()
        granularity = self.get_file_granularity(interval)
        
        # Base structure: <exchange_group>/bars/<interval>/<SYMBOL>/<YEAR>/
        dir_path = self.base_path / self.exchange_group / "bars" / interval / symbol / str(year)
        
        # For daily granularity, add month subdirectory (cleaner organization)
        # Path: bars/1s/AAPL/2025/07/
        if granularity == FileGranularity.DAILY:
            if month is None:
                raise ValueError(f"Month required for daily files ({interval})")
            dir_path = dir_path / f"{month:02d}"
        
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path
    
    def get_file_path(
        self,
        interval: str,
        symbol: str,
        year: int,
        month: Optional[int] = None,
        day: Optional[int] = None
    ) -> Path:
        """Get complete file path for an interval.
        
        Args:
            interval: Interval string (e.g., "1s", "1m", "1d", "1w")
            symbol: Stock symbol
            year: Year
            month: Month (required for daily granularity)
            day: Day (required for daily granularity)
        
        Returns:
            Complete file path
            
        Examples:
            Daily:  bars/1s/AAPL/2025/07/15.parquet
            Yearly: bars/1d/AAPL/2025.parquet
        """
        symbol = symbol.upper()
        granularity = self.get_file_granularity(interval)
        
        # Get directory
        dir_path = self.get_directory_path(interval, symbol, year, month)
        
        # Determine filename based on granularity
        if granularity == FileGranularity.DAILY:
            if month is None or day is None:
                raise ValueError(
                    f"Month and day required for {interval} (sub-daily interval). "
                    f"Got month={month}, day={day}"
                )
            filename = f"{day:02d}.parquet"
        else:
            # Yearly files
            filename = f"{year}.parquet"
        
        return dir_path / filename
    
    def get_date_components(
        self,
        interval: str,
        timestamp: datetime
    ) -> Tuple[int, Optional[int], Optional[int]]:
        """Extract date components based on interval granularity.
        
        Args:
            interval: Interval string
            timestamp: Timestamp to extract components from
        
        Returns:
            Tuple of (year, month, day) where:
            - Daily files: (year, month, day)
            - Yearly files: (year, None, None)
        """
        granularity = self.get_file_granularity(interval)
        
        if granularity == FileGranularity.DAILY:
            return timestamp.year, timestamp.month, timestamp.day
        else:
            return timestamp.year, None, None
    
    def validate_interval(self, interval: str) -> bool:
        """Validate that an interval is supported.
        
        Args:
            interval: Interval string
        
        Returns:
            True if interval is valid and supported
        """
        try:
            parse_interval(interval)
            return True
        except ValueError as e:
            logger.warning(f"Invalid interval {interval}: {e}")
            return False
