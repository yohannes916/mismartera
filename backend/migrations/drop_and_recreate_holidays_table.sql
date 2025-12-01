-- Drop old trading_holidays table and recreate with exchange_group
-- This is a CLEAN BREAK - old data will be lost (reimport from CSV)

DROP TABLE IF EXISTS trading_holidays;

CREATE TABLE trading_holidays (id INTEGER PRIMARY KEY AUTOINCREMENT, date DATE NOT NULL, exchange_group VARCHAR(50) NOT NULL DEFAULT 'US_EQUITY', holiday_name VARCHAR(200) NOT NULL, notes VARCHAR(500), is_closed BOOLEAN DEFAULT 1, early_close_time TIME, created_at DATE DEFAULT CURRENT_DATE, UNIQUE(date, exchange_group));

CREATE INDEX ix_trading_holidays_date ON trading_holidays (date);

CREATE INDEX ix_trading_holidays_exchange_group ON trading_holidays (exchange_group);
