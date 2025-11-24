"""Quote Data Repository
Database operations for bid/ask quote ticks
"""
from typing import List, Optional, Tuple
from datetime import datetime

from sqlalchemy import select, and_, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import QuoteData
from app.logger import logger


class QuoteRepository:
    """Repository for quote (bid/ask) data operations."""

    @staticmethod
    async def bulk_create_quotes(
        session: AsyncSession,
        quotes: List[dict],
    ) -> Tuple[int, int]:
        """Bulk upsert quotes.

        Uses SQLite INSERT OR REPLACE semantics on (symbol, timestamp).
        Returns (inserted_count, updated_count) for API compatibility.
        """
        from sqlalchemy.dialects.sqlite import insert

        inserted = 0

        for quote_data in quotes:
            try:
                stmt = insert(QuoteData).values(**quote_data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol", "timestamp"],
                    set_={
                        "bid_price": stmt.excluded.bid_price,
                        "bid_size": stmt.excluded.bid_size,
                        "ask_price": stmt.excluded.ask_price,
                        "ask_size": stmt.excluded.ask_size,
                        "exchange": stmt.excluded.exchange,
                    },
                )
                await session.execute(stmt)
                inserted += 1
            except Exception as e:
                logger.error(f"Error upserting quote: {e}")
                raise

        try:
            await session.commit()
            logger.info(f"Bulk upserted {inserted} quotes")
            return inserted, 0
        except Exception as e:
            await session.rollback()
            logger.error(f"Bulk quote upsert failed: {e}")
            raise

    @staticmethod
    async def get_quotes_by_symbol(
        session: AsyncSession,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[QuoteData]:
        query = select(QuoteData).where(QuoteData.symbol == symbol.upper())

        if start_date:
            query = query.where(QuoteData.timestamp >= start_date)
        if end_date:
            query = query.where(QuoteData.timestamp <= end_date)

        query = query.order_by(QuoteData.timestamp.asc())

        if limit:
            query = query.limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_quote_count(
        session: AsyncSession,
        symbol: Optional[str] = None,
    ) -> int:
        query = select(func.count()).select_from(QuoteData)
        if symbol:
            query = query.where(QuoteData.symbol == symbol.upper())
        result = await session.execute(query)
        return result.scalar()

    @staticmethod
    async def get_symbols(
        session: AsyncSession,
    ) -> List[str]:
        query = select(QuoteData.symbol).distinct()
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_date_range(
        session: AsyncSession,
        symbol: str,
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        query = select(
            func.min(QuoteData.timestamp),
            func.max(QuoteData.timestamp),
        ).where(QuoteData.symbol == symbol.upper())

        result = await session.execute(query)
        row = result.first()
        if row:
            return row[0], row[1]
        return None, None

    @staticmethod
    async def delete_quotes_by_symbol(
        session: AsyncSession,
        symbol: str,
    ) -> int:
        query = delete(QuoteData).where(QuoteData.symbol == symbol.upper())
        result = await session.execute(query)
        await session.commit()
        deleted = result.rowcount
        logger.info(f"Deleted {deleted} quotes for {symbol}")
        return deleted

    @staticmethod
    async def delete_all_quotes(session: AsyncSession) -> int:
        query = delete(QuoteData)
        result = await session.execute(query)
        await session.commit()
        deleted = result.rowcount
        logger.warning(f"Deleted ALL quotes: {deleted}")
        return deleted
