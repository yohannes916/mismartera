"""
Trading Calendar Repository
Database operations for trading holidays and market hours configuration
"""
from typing import List, Optional
from datetime import date, time
from sqlalchemy import select, delete, and_
from sqlalchemy.orm import Session

from app.models.trading_calendar import TradingHoliday
from app.logger import logger


class TradingCalendarRepository:
    """Repository for trading calendar operations with multi-exchange support
    
    Supports per-exchange holiday calendars. All queries are exchange-aware.
    """
    
    @staticmethod
    def create_holiday(
        session: Session,
        date: date,
        holiday_name: str,
        exchange: str = "NYSE",
        country: Optional[str] = None,
        notes: Optional[str] = None,
        early_close_time: Optional[time] = None
    ) -> TradingHoliday:
        """Add a holiday or early close day
        
        Args:
            session: Database session
            date: Holiday date
            holiday_name: Name of the holiday
            exchange: Exchange identifier
            country: Country code (optional, for metadata)
            notes: Optional notes
            early_close_time: If set, market closes early (not full closure)
        """
        is_closed = early_close_time is None
        
        holiday = TradingHoliday(
            date=date,
            exchange=exchange,
            holiday_name=holiday_name,
            notes=notes,
            is_closed=is_closed,
            early_close_time=early_close_time
        )
        
        session.add(holiday)
        session.commit()
        session.refresh(holiday)
        
        logger.info(f"Added holiday: {holiday_name} on {date} (exchange={exchange})")
        return holiday
    
    @staticmethod
    def bulk_create_holidays(
        session: Session,
        holidays: List[dict],
        exchange: str = "NYSE"
    ) -> int:
        """Bulk insert holidays (upsert - replace if exists)
        
        Args:
            session: Database session
            holidays: List of holiday dictionaries
            exchange: Exchange identifier
            
        Returns:
            Number of holidays inserted
        """
        from sqlalchemy.dialects.sqlite import insert
        
        inserted = 0
        for holiday_data in holidays:
            try:
                # Ensure exchange is set
                if 'exchange' not in holiday_data:
                    holiday_data['exchange'] = exchange
                
                # Keep only valid columns
                clean_data = {
                    k: v for k, v in holiday_data.items()
                    if k in ['date', 'exchange', 'holiday_name', 'notes', 'is_closed', 'early_close_time']
                }
                
                stmt = insert(TradingHoliday).values(**clean_data)
                
                # On conflict (duplicate date+exchange), update all fields
                stmt = stmt.on_conflict_do_update(
                    index_elements=['date', 'exchange'],
                    set_={
                        'holiday_name': stmt.excluded.holiday_name,
                        'notes': stmt.excluded.notes,
                        'is_closed': stmt.excluded.is_closed,
                        'early_close_time': stmt.excluded.early_close_time,
                    }
                )
                
                session.execute(stmt)
                inserted += 1
                
            except Exception as e:
                logger.error(f"Error inserting holiday: {e}")
                raise
        
        session.commit()
        logger.info(f"Bulk upserted {inserted} holidays (exchange={exchange})")
        return inserted
    
    @staticmethod
    def get_holiday(
        session: Session,
        date: date,
        exchange: str = "NYSE"
    ) -> Optional[TradingHoliday]:
        """Get holiday for a specific date and exchange
        
        Args:
            session: Database session
            date: Date to query
            exchange: Exchange identifier
        """
        query = select(TradingHoliday).where(
            and_(
                TradingHoliday.date == date,
                TradingHoliday.exchange == exchange
            )
        )
        result = session.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    def get_holidays_in_range(
        session: Session,
        start_date: date,
        end_date: date,
        exchange: str = "NYSE"
    ) -> List[TradingHoliday]:
        """Get all holidays in a date range for a specific exchange
        
        Args:
            session: Database session
            start_date: Start date
            end_date: End date
            exchange: Exchange identifier
        """
        query = select(TradingHoliday).where(
            and_(
                TradingHoliday.date >= start_date,
                TradingHoliday.date <= end_date,
                TradingHoliday.exchange == exchange
            )
        ).order_by(TradingHoliday.date)
        
        result = session.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    def delete_all_holidays(
        session: Session,
        exchange: str = "NYSE"
    ) -> int:
        """Delete all holidays for a specific exchange (use with caution)
        
        Args:
            session: Database session
            exchange: Exchange identifier
        """
        query = delete(TradingHoliday).where(TradingHoliday.exchange == exchange)
        result = session.execute(query)
        session.commit()
        
        deleted = result.rowcount
        logger.warning(f"Deleted all holidays for {exchange}: {deleted} entries")
        return deleted

    @staticmethod
    def delete_holidays_for_year(
        session: Session,
        year: int,
        exchange: str = "NYSE"
    ) -> int:
        """Delete all holidays for a specific year and exchange
        
        Args:
            session: Database session
            year: Year to delete
            exchange: Exchange identifier
        """
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        query = delete(TradingHoliday).where(
            and_(
                TradingHoliday.date >= start_date,
                TradingHoliday.date <= end_date,
                TradingHoliday.exchange == exchange
            )
        )
        result = session.execute(query)
        session.commit()
        deleted = result.rowcount
        logger.warning(f"Deleted {deleted} holidays for {exchange} year {year}")
        return deleted
