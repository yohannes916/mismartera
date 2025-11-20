"""
Trading Calendar Repository
Database operations for market holidays and calendar
"""
from typing import List, Optional
from datetime import datetime, date, time
from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading_calendar import TradingHoliday, TradingHours
from app.logger import logger


class TradingCalendarRepository:
    """Repository for trading calendar operations"""
    
    @staticmethod
    async def create_holiday(
        session: AsyncSession,
        date: date,
        holiday_name: str,
        notes: Optional[str] = None,
        early_close_time: Optional[time] = None
    ) -> TradingHoliday:
        """
        Add a holiday or early close day
        
        Args:
            session: Database session
            date: Holiday date
            holiday_name: Name of the holiday
            notes: Optional notes
            early_close_time: If set, market closes early (not full closure)
        """
        is_closed = early_close_time is None
        
        holiday = TradingHoliday(
            date=date,
            holiday_name=holiday_name,
            notes=notes,
            is_closed=is_closed,
            early_close_time=early_close_time
        )
        
        session.add(holiday)
        await session.commit()
        await session.refresh(holiday)
        
        logger.info(f"Added holiday: {holiday_name} on {date}")
        return holiday
    
    @staticmethod
    async def bulk_create_holidays(
        session: AsyncSession,
        holidays: List[dict]
    ) -> int:
        """
        Bulk insert holidays (upsert - replace if exists)
        
        Args:
            session: Database session
            holidays: List of holiday dictionaries
            
        Returns:
            Number of holidays inserted
        """
        from sqlalchemy.dialects.sqlite import insert
        
        inserted = 0
        for holiday_data in holidays:
            try:
                stmt = insert(TradingHoliday).values(**holiday_data)
                
                # On conflict (duplicate date), update all fields
                stmt = stmt.on_conflict_do_update(
                    index_elements=['date'],
                    set_={
                        'holiday_name': stmt.excluded.holiday_name,
                        'notes': stmt.excluded.notes,
                        'is_closed': stmt.excluded.is_closed,
                        'early_close_time': stmt.excluded.early_close_time,
                    }
                )
                
                await session.execute(stmt)
                inserted += 1
                
            except Exception as e:
                logger.error(f"Error inserting holiday: {e}")
                raise
        
        await session.commit()
        logger.info(f"Bulk upserted {inserted} holidays")
        return inserted
    
    @staticmethod
    async def get_holiday(
        session: AsyncSession,
        date: date
    ) -> Optional[TradingHoliday]:
        """Get holiday for a specific date"""
        query = select(TradingHoliday).where(TradingHoliday.date == date)
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_holidays_in_range(
        session: AsyncSession,
        start_date: date,
        end_date: date
    ) -> List[TradingHoliday]:
        """Get all holidays in a date range"""
        query = select(TradingHoliday).where(
            and_(
                TradingHoliday.date >= start_date,
                TradingHoliday.date <= end_date
            )
        ).order_by(TradingHoliday.date)
        
        result = await session.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def is_trading_day(
        session: AsyncSession,
        date: datetime
    ) -> bool:
        """
        Check if a date is a trading day
        
        Args:
            session: Database session
            date: Date to check
            
        Returns:
            True if trading day, False if weekend/holiday
        """
        # Check if weekend
        if TradingHours.is_weekend(date):
            return False
        
        # Check if holiday (full closure)
        holiday = await TradingCalendarRepository.get_holiday(session, date.date())
        if holiday and holiday.is_closed:
            return False
        
        return True
    
    @staticmethod
    async def get_market_close_time(
        session: AsyncSession,
        date: datetime
    ) -> time:
        """
        Get market close time for a date (handles early closes)
        
        Args:
            session: Database session
            date: Date to check
            
        Returns:
            Market close time (standard 16:00 or early close)
        """
        holiday = await TradingCalendarRepository.get_holiday(session, date.date())
        
        if holiday and holiday.early_close_time:
            return holiday.early_close_time
        
        # Default close time
        return time.fromisoformat(TradingHours.MARKET_CLOSE)
    
    @staticmethod
    async def count_trading_days(
        session: AsyncSession,
        start_date: date,
        end_date: date
    ) -> int:
        """
        Count trading days in a date range (excluding weekends and holidays)
        
        Args:
            session: Database session
            start_date: Start date
            end_date: End date
            
        Returns:
            Number of trading days
        """
        from datetime import timedelta
        
        count = 0
        current = start_date
        
        while current <= end_date:
            current_dt = datetime.combine(current, time())
            if await TradingCalendarRepository.is_trading_day(session, current_dt):
                count += 1
            current += timedelta(days=1)
        
        return count
    
    @staticmethod
    async def delete_all_holidays(
        session: AsyncSession
    ) -> int:
        """Delete all holidays (use with caution)"""
        query = delete(TradingHoliday)
        result = await session.execute(query)
        await session.commit()
        
        deleted = result.rowcount
        logger.warning(f"Deleted all holidays: {deleted} entries")
        return deleted
