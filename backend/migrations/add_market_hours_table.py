#!/usr/bin/env python3
"""
Migration: Add market_hours table

Creates the market_hours table to store exchange group trading hours
and seeds it with default data for US_EQUITY, LSE, and TSE.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.database import SessionLocal, engine, Base
from app.models.trading_calendar import MarketHours
from sqlalchemy import text
from datetime import time
from app.logger import logger


def upgrade():
    """Create market_hours table and seed with default data"""
    
    logger.info("Starting migration: add_market_hours_table")
    
    # Create table
    logger.info("Creating market_hours table...")
    MarketHours.__table__.create(engine, checkfirst=True)
    logger.info("✓ Table created")
    
    # Seed default data
    logger.info("Seeding default market hours...")
    
    with SessionLocal() as session:
        # Check if data already exists
        existing = session.query(MarketHours).first()
        if existing:
            logger.info("Market hours data already exists, skipping seed")
            return
        
        market_hours_data = [
            # US Equity Exchanges (grouped - all share same hours)
            MarketHours(
                exchange_group="US_EQUITY",
                asset_class="EQUITY",
                exchanges="NYSE,NASDAQ,AMEX,ARCA",
                timezone="America/New_York",
                country="USA",
                exchange_name="US Equity Markets",
                regular_open=time(9, 30),
                regular_close=time(16, 0),
                pre_market_open=time(4, 0),
                pre_market_close=time(9, 30),
                post_market_open=time(16, 0),
                post_market_close=time(20, 0),
                trading_days="0,1,2,3,4",
                is_active=True,
            ),
            # UK Exchange (single exchange, not grouped)
            MarketHours(
                exchange_group="LSE",
                asset_class="EQUITY",
                exchanges="LSE",
                timezone="Europe/London",
                country="UK",
                exchange_name="London Stock Exchange",
                regular_open=time(8, 0),
                regular_close=time(16, 30),
                pre_market_open=None,
                pre_market_close=None,
                post_market_open=None,
                post_market_close=None,
                trading_days="0,1,2,3,4",
                is_active=True,
            ),
            # Japan Exchange (single exchange, not grouped)
            MarketHours(
                exchange_group="TSE",
                asset_class="EQUITY",
                exchanges="TSE",
                timezone="Asia/Tokyo",
                country="Japan",
                exchange_name="Tokyo Stock Exchange",
                regular_open=time(9, 0),
                regular_close=time(15, 0),
                pre_market_open=None,
                pre_market_close=None,
                post_market_open=None,
                post_market_close=None,
                trading_days="0,1,2,3,4",
                is_active=True,
            ),
        ]
        
        for mh in market_hours_data:
            session.add(mh)
        
        session.commit()
        logger.info(f"✓ Seeded {len(market_hours_data)} market hours configurations")
    
    logger.info("Migration completed successfully")


def downgrade():
    """Drop market_hours table"""
    logger.info("Rolling back migration: add_market_hours_table")
    
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS market_hours"))
    
    logger.info("✓ Table dropped")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Market Hours Table Migration")
    parser.add_argument(
        "action",
        choices=["upgrade", "downgrade"],
        help="Migration action to perform"
    )
    
    args = parser.parse_args()
    
    if args.action == "upgrade":
        upgrade()
    else:
        downgrade()
