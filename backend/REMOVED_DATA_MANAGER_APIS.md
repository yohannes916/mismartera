# Removed APIs from Data Manager

These APIs have been **removed** from `data_manager` and **migrated** to `time_manager`.

---

## ❌ Removed Methods

### 1. `check_market_open(timestamp)` 
**Replacement**: `time_mgr.is_market_open(session, timestamp)`

### 2. `get_current_time()`
**Replacement**: `time_mgr.get_current_time()`

### 3. `async init_backtest_window(session)`
**Replacement**: `time_mgr.init_backtest_window(session)`

### 4. `async init_backtest(session)`
**Replacement**: `time_mgr.init_backtest(session)`

### 5. `async reset_backtest_clock()`
**Replacement**: `time_mgr.reset_backtest_clock(session)`

### 6. `async get_trading_hours(session, day)`
**Replacement**: `time_mgr.get_trading_session(session, day)` (returns full TradingSession)

### 7. `async is_holiday(session, day)`
**Replacement**: `time_mgr.is_holiday(session, day)` (returns tuple)

### 8. `async get_current_day_market_info(session)`
**Replacement**: `time_mgr.get_trading_session(session, date.today())`

### 9. `async import_holidays_from_file(session, file_path, exchange)`
**Replacement**: CLI command `time import-holidays <file> [--exchange <group>]`

### 10. `clear_holiday_cache()`
**Replacement**: Not needed (time_manager handles caching internally)

---

## ❌ Removed Attributes

- `self.backtest_days`
- `self.backtest_start_date`
- `self.backtest_end_date`
- `self.time_provider`
- `self._holiday_cache`
- `self.opening_time`
- `self.closing_time`

---

##  Migration Examples

### Example 1: Get Current Time

**Before**:
```python
dm = system_mgr.get_data_manager()
current = dm.get_current_time()
```

**After**:
```python
time_mgr = system_mgr.get_time_manager()
current = time_mgr.get_current_time()
```

### Example 2: Check Market Open

**Before**:
```python
dm = system_mgr.get_data_manager()
is_open = dm.check_market_open(datetime.now())
```

**After**:
```python
time_mgr = system_mgr.get_time_manager()
async with AsyncSessionLocal() as session:
    is_open = time_mgr.is_market_open(session, datetime.now())
```

### Example 3: Get Trading Hours

**Before**:
```python
async with session:
    hours = dm.get_trading_hours(session, date.today())
    print(hours.open_time, hours.close_time)
```

**After**:
```python
async with session:
    trading_session = time_mgr.get_trading_session(session, date.today())
    print(trading_session.regular_open, trading_session.regular_close)
```

### Example 4: Initialize Backtest

**Before**:
```python
async with session:
    dm.init_backtest(session)
```

**After**:
```python
async with session:
    time_mgr.init_backtest(session)
```

### Example 5: Import Holidays

**Before**:
```python
async with session:
    dm.import_holidays_from_file(session, 'holidays.csv', exchange='NYSE')
```

**After**:
```bash
# Use CLI command (now supports JSON format with exchange groups)
time import-holidays data/holidays/us_equity_2024.json
```

Or programmatically:
```python
from app.managers.time_manager.holiday_import_service import HolidayImportService

async with session:
    result = HolidayImportService.import_from_file(
        session,
        'holidays.json',
        exchange_override='US_EQUITY'
    )
```

---

## ✅ What Remains in Data Manager

Data Manager now focuses on its core responsibility: **data streaming and storage**

**Still Available**:
- `async start_bars_stream(symbol, interval)`
- `async stop_bars_stream(symbol, interval)`
- `async start_ticks_stream(symbol)`
- `async stop_ticks_stream(symbol)`
- `async get_historical_bars(symbol, start, end, interval)`
- `async import_bars_from_parquet(file_path)`
- Stream coordinator management
- Session data management
- Prefetch management
- Data upkeep thread

---

## Files Deleted

- ❌ `app/managers/data_manager/time_provider.py`
- ❌ `app/managers/data_manager/trading_calendar.py`
- ❌ `app/managers/data_manager/integrations/holiday_import_service.py`

---

## Single Source of Truth

**Before**: Multiple sources
- TimeProvider → Current time
- DataManager → Trading hours, holidays
- TradingCalendar → Holiday calculations

**After**: One source
- **TimeManager** → Everything time/calendar related

This eliminates confusion and ensures consistency across all components!
