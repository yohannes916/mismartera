"""
Market Data Repository
Database operations for OHLCV market data
"""
from typing import List, Optional, Dict
from datetime import datetime, date, time, timedelta
from sqlalchemy import select, and_, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import MarketData
from app.logger import logger


class MarketDataRepository:
    """Repository for market data operations"""
    
    @staticmethod
    async def create_bar(
        session: AsyncSession,
        symbol: str,
        timestamp: datetime,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        interval: str = "1m"
    ) -> MarketData:
        """
        Create a single market data bar
        
        Args:
            session: Database session
            symbol: Stock symbol
            timestamp: Bar timestamp
            open_price: Opening price
            high: High price
            low: Low price
            close: Close price
            volume: Trading volume
            interval: Time interval (default: 1m)
            
        Returns:
            Created MarketData instance
        """
        bar = MarketData(
            symbol=symbol.upper(),
            timestamp=timestamp,
            interval=interval,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume
        )
        
        session.add(bar)
        await session.commit()
        await session.refresh(bar)
        
        return bar
    
    @staticmethod
    async def bulk_create_bars(
        session: AsyncSession,
        bars: List[dict]
    ) -> tuple[int, int]:
        """
        Bulk upsert market data bars (insert or update on conflict)
        
        Args:
            session: Database session
            bars: List of bar dictionaries
            
        Returns:
            Tuple of (inserted_count, updated_count)
        """
        from sqlalchemy.dialects.sqlite import insert
        
        inserted = 0
        updated = 0
        
        for bar_data in bars:
            try:
                # Use SQLite INSERT OR REPLACE (upsert)
                stmt = insert(MarketData).values(**bar_data)
                
                # On conflict (duplicate symbol+timestamp+interval), update all columns
                stmt = stmt.on_conflict_do_update(
                    index_elements=['symbol', 'timestamp', 'interval'],
                    set_={
                        'open': stmt.excluded.open,
                        'high': stmt.excluded.high,
                        'low': stmt.excluded.low,
                        'close': stmt.excluded.close,
                        'volume': stmt.excluded.volume,
                    }
                )
                
                result = await session.execute(stmt)
                
                # SQLite doesn't tell us if it was insert or update easily,
                # so we'll count all as "processed"
                inserted += 1
                
            except Exception as e:
                logger.error(f"Error upserting bar: {e}")
                raise
        
        try:
            await session.commit()
            logger.info(f"Bulk upserted {inserted} market data bars")
            return inserted, 0  # Return as tuple for compatibility
        except Exception as e:
            await session.rollback()
            logger.error(f"Bulk upsert failed: {e}")
            raise
    
    @staticmethod
    async def get_bars_by_symbol(
        session: AsyncSession,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1m",
        limit: Optional[int] = None
    ) -> List[MarketData]:
        """
        Get market data bars for a symbol
        
        Args:
            session: Database session
            symbol: Stock symbol
            start_date: Start date filter (optional)
            end_date: End date filter (optional)
            interval: Time interval
            limit: Maximum number of bars to return
            
        Returns:
            List of MarketData bars ordered by timestamp
        """
        query = select(MarketData).where(
            and_(
                MarketData.symbol == symbol.upper(),
                MarketData.interval == interval
            )
        )
        
        if start_date:
            query = query.where(MarketData.timestamp >= start_date)
        
        if end_date:
            query = query.where(MarketData.timestamp <= end_date)
        
        query = query.order_by(MarketData.timestamp.asc())
        
        if limit:
            query = query.limit(limit)
        
        result = await session.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def get_bar_count(
        session: AsyncSession,
        symbol: Optional[str] = None,
        interval: str = "1m"
    ) -> int:
        """
        Count market data bars
        
        Args:
            session: Database session
            symbol: Optional symbol filter
            interval: Time interval
            
        Returns:
            Number of bars
        """
        query = select(func.count()).select_from(MarketData).where(
            MarketData.interval == interval
        )
        
        if symbol:
            query = query.where(MarketData.symbol == symbol.upper())
        
        result = await session.execute(query)
        return result.scalar()
    
    @staticmethod
    async def get_symbols(
        session: AsyncSession,
        interval: str = "1m"
    ) -> List[str]:
        """
        Get list of all symbols in database
        
        Args:
            session: Database session
            interval: Time interval filter
            
        Returns:
            List of unique symbols
        """
        query = select(MarketData.symbol).where(
            MarketData.interval == interval
        ).distinct()
        
        result = await session.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def get_date_range(
        session: AsyncSession,
        symbol: str,
        interval: str = "1m"
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        """
        Get date range for a symbol
        
        Args:
            session: Database session
            symbol: Stock symbol
            interval: Time interval
            
        Returns:
            Tuple of (min_date, max_date)
        """
        query = select(
            func.min(MarketData.timestamp),
            func.max(MarketData.timestamp)
        ).where(
            and_(
                MarketData.symbol == symbol.upper(),
                MarketData.interval == interval
            )
        )
        
        result = await session.execute(query)
        row = result.first()
        
        if row:
            return row[0], row[1]
        
        return None, None
    
    @staticmethod
    async def delete_bars_by_symbol(
        session: AsyncSession,
        symbol: str,
        interval: str = "1m"
    ) -> int:
        """
        Delete all bars for a symbol
        
        Args:
            session: Database session
            symbol: Stock symbol
            interval: Time interval
            
        Returns:
            Number of bars deleted
        """
        query = delete(MarketData).where(
            and_(
                MarketData.symbol == symbol.upper(),
                MarketData.interval == interval
            )
        )
        
        result = await session.execute(query)
        await session.commit()
        
        deleted = result.rowcount
        logger.info(f"Deleted {deleted} bars for {symbol}")
        
        return deleted
    
    @staticmethod
    async def delete_all_bars(
        session: AsyncSession
    ) -> int:
        """
        Delete ALL market data from database (use with caution!)
        
        Args:
            session: Database session
            
        Returns:
            Number of bars deleted
        """
        query = delete(MarketData)
        
        result = await session.execute(query)
        await session.commit()
        
        deleted = result.rowcount
        logger.warning(f"Deleted ALL market data: {deleted} bars")
        
        return deleted
    
    @staticmethod
    async def check_data_quality(
        session: AsyncSession,
        symbol: str,
        interval: str = "1m",
        use_cache: bool = True
    ) -> Dict:
        """Check data quality for a symbol using centralized quality checker.
        
        This method now delegates to the unified quality_checker module which:
        - Uses trading calendar to accurately count expected trading minutes
        - Accounts for holidays and early closes
        - Caches expected minute counts for performance
        - Assumes off-hours data is already filtered during import
        
        Args:
            session: Database session
            symbol: Stock symbol
            interval: Time interval (only "1m" is validated)
            use_cache: Whether to use cached expected minute counts
            
        Returns:
            Dictionary with quality metrics
        """
        # Only 1m bars are validated with calendar-aware logic
        if interval != "1m":
            raise ValueError(f"Quality checking only supports '1m' interval, got: {interval}")
        
        # Fetch all bars for the symbol
        bars = await MarketDataRepository.get_bars_by_symbol(
            session, symbol, interval=interval
        )
        
        # Use centralized quality checker
        from app.managers.data_manager.quality_checker import check_bar_quality
        
        metrics = await check_bar_quality(
            session,
            symbol,
            bars,
            use_cache=use_cache
        )
        
        # Convert to dictionary format for backward compatibility
        return {
            "total_bars": metrics.total_bars,
            "expected_bars": metrics.expected_minutes,
            "missing_bars": metrics.missing_minutes,
            "duplicate_timestamps": metrics.duplicate_count,
            "quality_score": metrics.quality_score,
            "completeness_pct": metrics.completeness_pct,
            "date_range": {
                "start": metrics.date_range_start.isoformat() if metrics.total_bars > 0 else None,
                "end": metrics.date_range_end.isoformat() if metrics.total_bars > 0 else None
            }
        }
