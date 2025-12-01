# TimeManager - Complete Documentation

**Single source of truth for ALL time and calendar operations**

---

## Overview

TimeManager handles all time and calendar operations:
- ✅ Current time (live/backtest modes)
- ✅ Trading sessions (hours, holidays, early closes)
- ✅ Market hours (database-driven, per exchange/asset class)
- ✅ Calendar navigation
- ✅ Holiday management
- ✅ Timezone handling
- ✅ Backtest time control

---

## Architecture

### System Flow
```
SystemManager → TimeManager → MarketHours DB → Application
```

### Core Principles

**1. Always Query, Never Store**
```python
# ❌ Wrong
self.current_time = datetime.now()
self.market_open = time(9, 30)

# ✅ Correct
current_time = time_mgr.get_current_time()
session = time_mgr.get_trading_session(db, date)
```

**2. System Defaults Everywhere**
```python
time_mgr.default_timezone        # → system_manager.timezone
time_mgr.default_exchange_group  # → system_manager.exchange_group
time_mgr.default_asset_class     # → system_manager.asset_class
```

**3. Database-Driven Configuration**
- Market hours loaded from `MarketHours` table
- No hardcoded times
- Timezone metadata preserved

---

## Quick Start

```python
from app.managers.system_manager import get_system_manager
from app.models.database import SessionLocal

# Initialize
system_mgr = get_system_manager()
system_mgr.start("session_configs/example_session.json")
time_mgr = system_mgr.get_time_manager()

# Get current time
current_time = time_mgr.get_current_time()  # Uses system timezone

# Get trading session
with SessionLocal() as db:
    session = time_mgr.get_trading_session(db, date(2025, 7, 2))
    print(f"{session.regular_open} - {session.regular_close}")
```

---

## API Reference

### Time Operations

**`get_current_time(timezone: Optional[str] = None) -> datetime`**
- Live mode: Returns real datetime.now()
- Backtest mode: Returns simulated time
- Default timezone: system_manager.timezone

```python
# System timezone (ET)
time = time_mgr.get_current_time()

# Explicit timezone
utc_time = time_mgr.get_current_time("UTC")
```

### Trading Sessions

**`get_trading_session(session, date, exchange=None, asset_class=None) -> TradingSession`**

Returns `TradingSession` with:
- `regular_open`, `regular_close`
- `pre_market_open`, `post_market_close`
- `is_trading_day`, `is_holiday`
- `timezone`, `exchange`, `asset_class`

**`is_market_open(session, timestamp=None, exchange=None, asset_class=None) -> bool`**

**`get_market_session(session, timestamp=None, exchange=None, asset_class=None) -> str`**
- Returns: `"pre_market"`, `"regular"`, `"post_market"`, or `"closed"`

### Calendar Navigation

**`get_next_trading_date(session, from_date, exchange=None) -> date`**

**`get_previous_trading_date(session, from_date, exchange=None) -> date`**

**`count_trading_days(session, start_date, end_date, exchange=None) -> int`**

**`is_trading_day(session, date, exchange=None) -> bool`**

### Holiday Management

**CRITICAL**: Holidays are stored at **exchange group level**, not per exchange.

**Why Exchange Groups for Holidays?**
- NYSE, NASDAQ, AMEX share identical holiday schedules
- Storing per exchange = unnecessary duplication
- Single source of truth per market group
- Matches `MarketHours` architecture

**Database Schema:**
```sql
trading_holidays (
    date,
    exchange_group,  -- US_EQUITY, LSE, TSE (NOT NYSE, NASDAQ)
    holiday_name,
    is_closed,
    early_close_time
    UNIQUE(date, exchange_group)
)
```

**Auto-Mapping:**
All holiday APIs automatically map individual exchanges to groups:
```python
# User provides NYSE → Auto-maps to US_EQUITY
time_mgr.is_holiday(db, date, exchange="NYSE")     # → US_EQUITY
time_mgr.is_holiday(db, date, exchange="NASDAQ")   # → US_EQUITY
time_mgr.is_holiday(db, date, exchange="US_EQUITY") # → US_EQUITY

# Default uses system configuration
time_mgr.is_holiday(db, date)  # → system_manager.exchange_group
```

**API Methods:**

**`is_holiday(session, date, exchange=None) -> Tuple[bool, Optional[str]]`**
- Returns: `(is_holiday, holiday_name)`
- Full closures only (early closes return False)
- Auto-maps exchanges to groups

**`is_early_close(session, date, exchange=None) -> Tuple[bool, Optional[time]]`**
- Returns: `(is_early_close, close_time)`
- Auto-maps exchanges to groups

**`get_holidays_in_range(session, start_date, end_date, exchange=None) -> List[Dict]`**
- Returns all holidays in range
- Auto-maps exchanges to groups

**`bulk_import_holidays(session, holidays, exchange_group=None) -> int`**
- Bulk insert holidays for a group
- Uses system default if not specified
- Returns: Number imported

**Examples:**
```python
with SessionLocal() as db:
    # Uses system default (US_EQUITY)
    is_holiday, name = time_mgr.is_holiday(db, date(2025, 7, 4))
    
    # Explicit group
    is_holiday, name = time_mgr.is_holiday(db, date, "US_EQUITY")
    
    # Individual exchange (auto-mapped to US_EQUITY)
    is_holiday, name = time_mgr.is_holiday(db, date, "NYSE")
    
    # Different market
    is_holiday, name = time_mgr.is_holiday(db, date, "LSE")
```

### Backtest Operations

**`set_backtest_time(timestamp: datetime) -> None`**
```python
time_mgr.set_backtest_time(datetime(2025, 7, 2, 9, 30))
```

**`init_backtest(session) -> None`**
- Computes window from `backtest_days` config
- Sets clock to first trading day at market open

**`advance_to_market_open(session, exchange=None, asset_class=None, include_extended=False) -> datetime`**
```python
# Advance to next regular open
new_time = time_mgr.advance_to_market_open(db)

# Advance to pre-market open
new_time = time_mgr.advance_to_market_open(db, include_extended=True)
```

**`set_backtest_window(session, start_date, end_date=None, exchange="NYSE") -> None`**

---

## Exchange Groups

### Concept
Exchange group = single exchange OR group of exchanges sharing hours/timezone/calendar

**Examples:**
- `US_EQUITY`: NYSE + NASDAQ + AMEX + ARCA
- `LSE`: London Stock Exchange
- `TSE`: Tokyo Stock Exchange

### Configuration

**Database (MarketHours table):**
```sql
INSERT INTO market_hours (
    exchange_group, asset_class, exchanges, timezone,
    regular_open, regular_close
) VALUES (
    'US_EQUITY', 'EQUITY', 'NYSE,NASDAQ,AMEX,ARCA', 'America/New_York',
    '09:30:00', '16:00:00'
);
```

**Session Config:**
```json
{
  "exchange_group": "US_EQUITY",
  "asset_class": "EQUITY"
}
```

---

## Timezone Handling

### Flow
```
Input: Dates in system timezone
  ↓
Internal: UTC storage
  ↓
Output: Timestamps in system timezone
```

### UTC Day Boundaries
**Problem:** ET extended hours cross UTC midnight
```
ET: July 2, 4 AM - 8 PM
UTC: July 2, 8 AM - July 3, 12 AM (spans 2 UTC days!)
```

**Solution:** TimeManager handles automatically when reading data.

### Examples
```python
# All return different timezones for same moment
et_time = time_mgr.get_current_time()           # ET
utc_time = time_mgr.get_current_time("UTC")     # UTC
london = time_mgr.get_current_time("Europe/London")  # London
```

---

## Integration

### With DataManager
```python
class DataManager:
    def get_current_time(self) -> datetime:
        """Helper delegating to TimeManager"""
        return self.system_manager.get_time_manager().get_current_time()
```

### With Background Threads
```python
# Store reference in __init__
self._time_manager = system_manager.get_time_manager()

# Use throughout thread
current_time = self._time_manager.get_current_time()
```

---

## CLI Commands

```bash
# Current time
time now
time now --timezone UTC

# Trading session
time session 2025-07-02
time session 2025-07-02 --exchange LSE

# Market status
time is-trading-day 2025-07-02
time is-holiday 2025-07-04

# Backtest
time advance         # Advance to next market open
time reset           # Reset to start of window
time set 2025-07-02 09:30  # Set to specific time

# Holidays (Exchange Group Level)
time holidays                              # List current year (system default)
time holidays 2025                         # List specific year
time holidays 2025 --exchange US_EQUITY    # Specific group
time holidays 2025 --exchange NYSE         # Auto-maps NYSE → US_EQUITY

time holidays import data/holidays/us_equity_2024-2026.json
time holidays import data/holidays/2025_Holiday_Schedule.csv
time holidays delete 2025                  # Delete by year (system default)
time holidays delete 2025 --exchange LSE   # Different group

# Configuration
time config          # Show current config
time exchange        # Show exchange group info
```

---

## Examples

### Complete Session Check
```python
with SessionLocal() as db:
    session = time_mgr.get_trading_session(db, date(2025, 7, 2))
    
    if session.is_holiday:
        print(f"Holiday: {session.holiday_name}")
    elif session.early_close:
        print(f"Early close at {session.early_close_time}")
    else:
        print(f"Regular hours: {session.regular_open} - {session.regular_close}")
        print(f"Pre-market: {session.pre_market_open}")
        print(f"Post-market: {session.post_market_close}")
```

### Backtest Time Control
```python
# Initialize backtest
with SessionLocal() as db:
    time_mgr.init_backtest(db)
    
    # Process each trading day
    while time_mgr.get_current_time().date() <= time_mgr.backtest_end_date:
        current = time_mgr.get_current_time()
        print(f"Processing: {current}")
        
        # ... process data ...
        
        # Advance to next day
        time_mgr.advance_to_market_open(db)
```

### Multi-Exchange Support
```python
with SessionLocal() as db:
    # US market
    us_session = time_mgr.get_trading_session(db, date, "US_EQUITY")
    
    # London market
    lse_session = time_mgr.get_trading_session(db, date, "LSE")
    
    # Tokyo market
    tse_session = time_mgr.get_trading_session(db, date, "TSE")
```

---

## Testing

```python
# Mock for testing
class MockTimeManager:
    def __init__(self):
        self._time = datetime(2025, 7, 2, 10, 30)
    
    def get_current_time(self, timezone=None):
        return self._time
    
    def set_backtest_time(self, time):
        self._time = time
```

---

## Best Practices

### ✅ DO
- Always use TimeManager for time operations
- Use system defaults (no explicit timezone in 95% of code)
- Query trading sessions from database
- Handle timezone conversions via TimeManager
- Use backtest mode for historical testing

### ❌ DON'T
- Use `datetime.now()` or `date.today()` directly
- Hardcode market hours (9:30, 16:00)
- Implement manual holiday checks
- Store current_time as attribute
- Mix timezone assumptions

---

## Related Documentation

- `TIMEZONE_REFACTOR_FINAL.md` - Complete timezone refactor details
- `MARKET_HOURS_DATABASE_DESIGN.md` - Database schema
- `EXCHANGE_GROUP_CONCEPT.md` - Exchange group architecture
- `TIMEZONE_PRINCIPLES.md` - Core timezone principles

---

## Holiday Data Import Workflow

### Initial Setup

**1. Delete Old Data (if reimporting)**
```bash
./start_cli.sh
system@mismartera: time holidays delete 2025
```

**2. Import Fresh Data**
```bash
# From CSV (simpler, year-by-year)
system@mismartera: time holidays import data/holidays/2025_Holiday_Schedule.csv

# From JSON (multi-year, more structured)
system@mismartera: time holidays import data/holidays/us_equity/us_equity_2024-2026.json
```

**3. Verify Import**
```bash
system@mismartera: time holidays 2025
```

Expected output:
```
Holidays 2025 (US_EQUITY)
┌────────────┬───────────┬─────────────────────────────┬────────────────────────┐
│ Date       │ Day       │ Holiday Name                │ Status                 │
├────────────┼───────────┼─────────────────────────────┼────────────────────────┤
│ 2025-07-03 │ Thursday  │ Day before Independence Day │ Early Close (13:00:00) │
│ 2025-07-04 │ Friday    │ Independence Day            │ Closed                 │
└────────────┴───────────┴─────────────────────────────┴────────────────────────┘
```

### Important Notes

**Data Source Files**:
- CSV files: `data/holidays/YYYY_Holiday_Schedule.csv` (NYSE published)
- JSON files: `data/holidays/us_equity/us_equity_YYYY-YYYY.json` (consolidated)

**Both formats supported** - choose based on preference:
- CSV: Official NYSE format, year-by-year
- JSON: More structured, can span multiple years

**Exchange Group Mapping**:
The import service automatically:
1. Reads exchange from file or uses `--exchange` parameter
2. Maps to exchange group (NYSE → US_EQUITY)
3. Stores once per group (no duplicates)
4. Creates unique constraint on (date, exchange_group)

**Upsert Behavior**:
- If holiday already exists: Updates with new data
- If holiday doesn't exist: Inserts new record
- Safe to re-import without deleting first

**System Integration**:
- TimeManager queries holidays on-demand
- Display shows correct hours: `(09:30-13:00) ⚡Short Day`
- Stream coordinator filters bars after early close
- All components use TimeManager as single source

---

**Version:** 2.1  
**Last Updated:** 2025-11-30  
**Status:** Production Ready
