# Data Manager Timezone Refactor Plan

**Objective:** Remove all timezone conversions and hardcoded timezones from data_manager code

---

## Files Needing Refactor

### 1. data_upkeep_thread.py

**Issues:**
- References to "UTC" in log messages
- Uses `get_regular_open_utc()` and `get_regular_close_utc()` (should use datetime methods)
- Log messages mention "UTC" explicitly

**Changes:**
```python
# OLD
logger.info(f"EOD: Market close reached at {current_time} UTC")
open_time = trading_session.get_regular_open_utc()

# NEW  
logger.info(f"EOD: Market close reached at {current_time}")
open_time = trading_session.get_regular_open_datetime()
```

---

### 2. prefetch_worker.py

**Issues:**
- Uses `tzinfo=timezone.utc` when combining date and time
- Hardcodes UTC assumption

**Changes:**
```python
# OLD
day_open = datetime.combine(target_date, trading_session.regular_open, tzinfo=timezone.utc)

# NEW
day_open = trading_session.get_regular_open_datetime()
```

---

### 3. integrations/alpaca_data.py

**Issues:**
- Converts to UTC explicitly: `.astimezone(timezone.utc)`
- Assumes input is UTC if naive

**Changes:**
```python
# OLD
def _to_alpaca_ts(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()

# NEW
def _to_alpaca_ts(dt: datetime) -> str:
    # Alpaca expects ISO format - just ensure timezone-aware
    if dt.tzinfo is None:
        # Should not happen - all datetimes should be timezone-aware
        raise ValueError("Datetime must be timezone-aware")
    return dt.isoformat()
```

---

### 4. integrations/schwab_data.py

**Issues:**
- Hardcoded `"America/New_York"` fallback
- Explicit UTC conversion

**Changes:**
```python
# OLD
def _to_schwab_ts(dt: datetime) -> int:
    if dt.tzinfo is None:
        from zoneinfo import ZoneInfo
        dt = dt.replace(tzinfo=ZoneInfo("America/New_York"))
    return int(dt.astimezone(timezone.utc).timestamp())

# NEW
def _to_schwab_ts(dt: datetime) -> int:
    # Schwab expects Unix timestamp
    if dt.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware")
    return int(dt.timestamp())  # timestamp() handles timezone conversion automatically
```

Also:
- Replace `datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)` 
- With `datetime.fromtimestamp(ts_ms / 1000, tz=system_tz)`

---

### 5. quality_checker.py

**Issues:**
- Uses `TradingHours.MARKET_OPEN` and `TradingHours.MARKET_CLOSE` (hardcoded constants)
- Uses `TradingHours.is_weekend()` (hardcoded logic)

**Changes:**
```python
# OLD
market_open = time.fromisoformat(TradingHours.MARKET_OPEN)
if TradingHours.is_weekend(date):
    return False

# NEW
# Get market hours from TimeManager/database for each date
with SessionLocal() as db:
    trading_session = time_mgr.get_trading_session(db, date)
    if not trading_session or trading_session.is_holiday:
        return False
    market_open = trading_session.regular_open
```

---

### 6. api.py

**Issues:**
- Hardcoded `TradingHours.MARKET_OPEN` and `TradingHours.MARKET_CLOSE`
- Explicit `tzinfo=timezone.utc` usage

**Changes:**
```python
# OLD (lines 579-580)
open_et = time.fromisoformat(TradingHours.MARKET_OPEN)
close_et = time.fromisoformat(TradingHours.MARKET_CLOSE)
start_time = datetime.combine(current_date, open_et, tzinfo=timezone.utc)

# NEW
with SessionLocal() as db:
    trading_session = time_mgr.get_trading_session(db, current_date)
    start_time = trading_session.get_regular_open_datetime()
    end_time = trading_session.get_regular_close_datetime()
```

---

## Implementation Strategy

### Phase 1: Remove hardcoded constants
1. Replace all `TradingHours.MARKET_OPEN/CLOSE` with TimeManager queries
2. Replace all `TradingHours.is_weekend()` with TimeManager queries

### Phase 2: Remove explicit timezone conversions
1. Remove `.astimezone(timezone.utc)` calls
2. Remove `tzinfo=timezone.utc` parameters
3. Change logging from "UTC" to generic time references

### Phase 3: Remove hardcoded timezone strings
1. Replace `"America/New_York"` with system_manager.timezone
2. Get timezone from TimeManager, not hardcoded

### Phase 4: Simplify datetime handling
1. Use TradingSession helper methods (get_regular_open_datetime())
2. Trust that all datetimes are in system timezone
3. Only convert when interfacing with external APIs

---

## Key Principles

1. **All dates/times in system timezone** - No conversions within application
2. **Get timezone from TimeManager** - No hardcoded timezone strings
3. **Get market hours from database** - No hardcoded time constants
4. **External APIs handle their own timezone** - We pass timezone-aware datetimes, they convert as needed
5. **Log messages don't mention timezone** - Just log the time, timezone is implicit

---

## Testing Strategy

1. Compile all modified files
2. Start system and check for errors
3. Run a backtest to verify data flow
4. Check logs to ensure no timezone mismatch warnings

---

## Status

- [ ] Phase 1: Remove hardcoded constants
- [ ] Phase 2: Remove explicit timezone conversions  
- [ ] Phase 3: Remove hardcoded timezone strings
- [ ] Phase 4: Simplify datetime handling
- [ ] Testing

**Next:** Execute refactor systematically
