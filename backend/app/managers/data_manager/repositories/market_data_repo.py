"""
Market Data Repository
Database operations for OHLCV market data
"""
from typing import List, Optional, Dict
from datetime import datetime
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
        use_trading_calendar: bool = True
    ) -> Dict:
        """
        Check data quality for a symbol
        
        Args:
            session: Database session
            symbol: Stock symbol
            interval: Time interval
            use_trading_calendar: Use trading calendar for accurate calculation
            
        Returns:
            Dictionary with quality metrics
        """
        bars = await MarketDataRepository.get_bars_by_symbol(
            session, symbol, interval=interval
        )
        
        if not bars:
            return {
                "total_bars": 0,
                "expected_bars": 0,
                "missing_bars": 0,
                "duplicate_timestamps": 0,
                "quality_score": 0.0
            }
        
        total_bars = len(bars)
        
        # Check for duplicates (shouldn't exist with unique constraint)
        timestamps = [b.timestamp for b in bars]
        duplicate_timestamps = len(timestamps) - len(set(timestamps))
        
        # Calculate expected bars
        if len(bars) > 1 and use_trading_calendar:
            from app.repositories.trading_calendar_repository import TradingCalendarRepository
            from app.models.trading_calendar import TradingHours
            
            start_date = bars[0].timestamp.date()
            end_date = bars[-1].timestamp.date()
            
            # Count trading days
            trading_days = await TradingCalendarRepository.count_trading_days(
                session, start_date, end_date
            )
            
            # Expected bars = trading days × bars per day (390 for 1-minute)
            if interval == "1m":
                expected_bars = trading_days * TradingHours.MINUTES_PER_DAY
            else:
                # For other intervals, fall back to simple calculation
                time_diff = (bars[-1].timestamp - bars[0].timestamp).total_seconds() / 60
                expected_bars = int(time_diff) + 1
        elif len(bars) > 1:
            # Simple calculation without trading calendar (less accurate)
            time_diff = (bars[-1].timestamp - bars[0].timestamp).total_seconds() / 60
            expected_bars = int(time_diff) + 1
        else:
            expected_bars = 1
        
        missing_bars = max(0, expected_bars - total_bars)
        
        # Quality score (0-1)
        if expected_bars > 0:
            completeness = total_bars / expected_bars
        else:
            completeness = 1.0
        
        quality_score = min(1.0, completeness) * (1.0 if duplicate_timestamps == 0 else 0.9)
        
        return {
            "total_bars": total_bars,
            "expected_bars": expected_bars,
            "missing_bars": missing_bars,
            "duplicate_timestamps": duplicate_timestamps,
            "quality_score": round(quality_score, 3),
            "date_range": {
                "start": bars[0].timestamp.isoformat(),
                "end": bars[-1].timestamp.isoformat()
            }
        }
