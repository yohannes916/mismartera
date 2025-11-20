"""
Base interface for data source integrations.
All data source integrations must implement this interface.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.models.trading import BarData, TickData


class DataSourceInterface(ABC):
    """
    Abstract base class for data source integrations.
    Ensures all data sources provide a consistent interface.
    """
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Name of the data source (e.g., 'csv', 'polygon', 'alphavantage')"""
        pass
    
    @abstractmethod
    async def fetch_bars(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = "1m"
    ) -> List[BarData]:
        """
        Fetch historical bar data.
        
        Args:
            symbol: Stock symbol
            start_date: Start datetime
            end_date: End datetime
            interval: Time interval (1m, 5m, 1h, 1d, etc.)
            
        Returns:
            List of BarData objects
        """
        pass
    
    @abstractmethod
    async def fetch_ticks(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[TickData]:
        """
        Fetch tick-level data.
        
        Args:
            symbol: Stock symbol
            start_date: Start datetime
            end_date: End datetime
            
        Returns:
            List of TickData objects
        """
        pass
    
    @abstractmethod
    async def validate_connection(self) -> bool:
        """
        Validate that the data source is accessible.
        
        Returns:
            True if connection is valid, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_available_symbols(self) -> List[str]:
        """
        Get list of available symbols from this source.
        
        Returns:
            List of symbol strings
        """
        pass
